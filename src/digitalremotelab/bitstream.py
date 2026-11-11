"""Lectura y validación de la cabecera de un fichero .bit de Xilinx (Vivado).

Formato (todos los enteros son big-endian):

    2 bytes  longitud de la marca (9)
    9 bytes  marca 0F F0 0F F0 0F F0 0F F0 00
    2 bytes  valor 1
    'a'  2 bytes de longitud + texto: "diseño;UserID=...;Version=..."
    'b'  2 bytes de longitud + texto: parte, p. ej. "7z010clg400"
    'c'  2 bytes de longitud + texto: fecha
    'd'  2 bytes de longitud + texto: hora
    'e'  4 bytes de longitud + datos del bitstream (empiezan por 0xFF... y la
         palabra de sincronización AA 99 55 66)

Un fichero .bin (sin cabecera) o uno truncado se rechazan antes de llegar a
la placa.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from digitalremotelab.errors import DRLError

MAGIC = bytes.fromhex("0FF00FF00FF00FF000")
SYNC_WORD = bytes.fromhex("AA995566")
SYNC_SEARCH_WINDOW = 512


class BitstreamError(DRLError):
    """El fichero no es un .bit válido o no es apto para esta placa."""


@dataclass(frozen=True)
class BitstreamInfo:
    design_name: str
    part: str
    date: str
    time: str
    tool_version: str | None
    header_length: int
    payload_length: int
    properties: dict[str, str] = field(default_factory=dict)

    @property
    def total_length(self) -> int:
        return self.header_length + self.payload_length


def _take(data: bytes, offset: int, count: int, what: str) -> tuple[bytes, int]:
    end = offset + count
    if end > len(data):
        raise BitstreamError(f"Fichero truncado: no se pudo leer {what}.")
    return data[offset:end], end


def parse_bitstream(data: bytes) -> BitstreamInfo:
    """Interpreta la cabecera y comprueba que el tamaño declarado es el real."""
    not_a_bit = BitstreamError(
        "No parece un fichero .bit de Xilinx (cabecera no reconocida). "
        "Sube el .bit generado por Vivado, no un .bin ni otro fichero."
    )
    raw, off = _take(data, 0, 2, "la cabecera")
    (magic_len,) = struct.unpack(">H", raw)
    if magic_len != len(MAGIC):
        raise not_a_bit
    magic, off = _take(data, off, magic_len, "la marca inicial")
    if magic != MAGIC:
        raise not_a_bit
    raw, off = _take(data, off, 2, "la cabecera")
    if struct.unpack(">H", raw)[0] != 1:
        raise BitstreamError("Cabecera .bit con formato inesperado.")

    fields: dict[str, str] = {}
    while True:
        key_raw, off = _take(data, off, 1, "un campo de la cabecera")
        key = key_raw.decode("latin-1")
        if key == "e":
            raw, off = _take(data, off, 4, "la longitud de los datos")
            (payload_length,) = struct.unpack(">I", raw)
            break
        if key not in ("a", "b", "c", "d"):
            raise BitstreamError(f"Campo de cabecera desconocido: {key!r}.")
        raw, off = _take(data, off, 2, f"la longitud del campo {key!r}")
        (length,) = struct.unpack(">H", raw)
        value, off = _take(data, off, length, f"el campo {key!r}")
        fields[key] = value.rstrip(b"\x00").decode("latin-1")

    for key, name in (("a", "nombre del diseño"), ("b", "parte")):
        if not fields.get(key):
            raise BitstreamError(f"La cabecera no contiene el {name}.")

    remaining = len(data) - off
    if remaining != payload_length:
        raise BitstreamError(
            f"El tamaño declarado ({payload_length} bytes) no coincide con el real "
            f"({remaining} bytes): el fichero está truncado o modificado."
        )
    if SYNC_WORD not in data[off : off + SYNC_SEARCH_WINDOW]:
        raise BitstreamError("No se encuentra la palabra de sincronización del bitstream.")

    design, *props_raw = fields["a"].split(";")
    properties: dict[str, str] = {}
    for item in props_raw:
        name, _, value = item.partition("=")
        if name:
            properties[name] = value

    return BitstreamInfo(
        design_name=design,
        part=fields["b"],
        date=fields.get("c", ""),
        time=fields.get("d", ""),
        tool_version=properties.get("Version"),
        header_length=off,
        payload_length=payload_length,
        properties=properties,
    )


def validate_for_part(info: BitstreamInfo, expected_prefix: str) -> None:
    """Comprueba que el bitstream es para la FPGA de la placa (p. ej. '7z010')."""
    part = info.part.lower().removeprefix("xc")
    if not part.startswith(expected_prefix.lower()):
        raise BitstreamError(
            f"El bitstream es para '{info.part}', pero la placa usa una '{expected_prefix}...'. "
            "Genera el bitstream para la Zybo Z7-10 (xc7z010clg400-1)."
        )


def load_bitstream(path: str | Path, max_bytes: int) -> BitstreamInfo:
    """Valida extensión, tamaño y cabecera de un .bit en disco."""
    path = Path(path)
    if path.suffix.lower() != ".bit":
        raise BitstreamError(f"'{path.name}' no tiene extensión .bit.")
    if not path.is_file():
        raise BitstreamError(f"No existe el fichero '{path}'.")
    size = path.stat().st_size
    if size > max_bytes:
        raise BitstreamError(f"El fichero ocupa {size} bytes; el máximo permitido es {max_bytes}.")
    return parse_bitstream(path.read_bytes())
