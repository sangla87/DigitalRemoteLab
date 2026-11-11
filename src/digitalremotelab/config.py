"""Configuración del laboratorio: placas, cámaras y rutas de herramientas."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from digitalremotelab.errors import DRLError

ENV_VAR = "DRL_CONFIG"
DEFAULT_LOCATIONS = (Path("lab.toml"), Path("config/lab.toml"))
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

_TOP_KEYS = {"lab", "boards"}
_LAB_KEYS = {
    "openfpgaloader",
    "board_model",
    "expected_part_prefix",
    "max_bitstream_bytes",
    "program_timeout_s",
    "jtag_freq_hz",
    "vivado_dir",
}
_BOARD_KEYS = {"id", "ftdi_serial", "extra_args", "camera"}
_CAMERA_KEYS = {"device", "width", "height", "warmup_frames", "jpeg_quality"}


class ConfigError(DRLError):
    """Configuración inválida."""


@dataclass(frozen=True)
class CameraConfig:
    # Índice (0, 1...) o ruta estable, p. ej. /dev/v4l/by-id/usb-...-video-index0
    device: int | str = 0
    width: int = 1280
    height: int = 720
    warmup_frames: int = 5
    jpeg_quality: int = 85


@dataclass(frozen=True)
class BoardConfig:
    id: str
    # Número de serie del chip FTDI de la placa; imprescindible con varias placas.
    ftdi_serial: str | None = None
    # Argumentos extra para openFPGALoader (p. ej. ("--cable", "digilent_hs2")).
    extra_args: tuple[str, ...] = ()
    camera: CameraConfig = field(default_factory=CameraConfig)


@dataclass(frozen=True)
class LabConfig:
    boards: tuple[BoardConfig, ...] = (BoardConfig(id="zybo1"),)
    openfpgaloader: str = "openFPGALoader"
    board_model: str = "zybo_z7_10"
    expected_part_prefix: str = "7z010"
    max_bitstream_bytes: int = 4 * 1024 * 1024
    program_timeout_s: float = 60.0
    jtag_freq_hz: int | None = None
    vivado_dir: str = "/tools/Xilinx/Vivado/2022.2"

    def board(self, board_id: str | None = None) -> BoardConfig:
        """Devuelve la placa pedida o la primera si no se indica ninguna."""
        if board_id is None:
            return self.boards[0]
        for board in self.boards:
            if board.id == board_id:
                return board
        known = ", ".join(b.id for b in self.boards)
        raise ConfigError(f"Placa desconocida '{board_id}'. Placas configuradas: {known}.")


def _only_known(table: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(table) - allowed
    if unknown:
        raise ConfigError(f"Claves desconocidas en [{where}]: {', '.join(sorted(unknown))}.")


def _expect(value: Any, types: type | tuple[type, ...], name: str) -> Any:
    # bool es subclase de int: no se acepta como número.
    if isinstance(value, bool) or not isinstance(value, types):
        raise ConfigError(f"'{name}' tiene un tipo inválido: {value!r}.")
    return value


def _parse_camera(table: dict[str, Any], where: str) -> CameraConfig:
    _only_known(table, _CAMERA_KEYS, where)
    values: dict[str, Any] = {}
    if "device" in table:
        values["device"] = _expect(table["device"], (int, str), f"{where}.device")
    for key in ("width", "height", "warmup_frames", "jpeg_quality"):
        if key in table:
            number = _expect(table[key], int, f"{where}.{key}")
            if number < 0:
                raise ConfigError(f"'{where}.{key}' no puede ser negativo.")
            values[key] = number
    return CameraConfig(**values)


def _parse_board(table: dict[str, Any], index: int) -> BoardConfig:
    where = f"boards[{index}]"
    _only_known(table, _BOARD_KEYS, where)
    board_id = _expect(table.get("id"), str, f"{where}.id")
    if not _ID_RE.match(board_id):
        raise ConfigError(
            f"Identificador de placa inválido: {board_id!r} (usa letras, números, - y _)."
        )
    serial = table.get("ftdi_serial")
    if serial is not None:
        _expect(serial, str, f"{where}.ftdi_serial")
    extra = table.get("extra_args", [])
    _expect(extra, list, f"{where}.extra_args")
    for arg in extra:
        _expect(arg, str, f"{where}.extra_args")
    camera = _parse_camera(table.get("camera", {}), f"{where}.camera")
    return BoardConfig(id=board_id, ftdi_serial=serial, extra_args=tuple(extra), camera=camera)


def parse_config(data: dict[str, Any]) -> LabConfig:
    _only_known(data, _TOP_KEYS, "raíz")
    lab = data.get("lab", {})
    _only_known(lab, _LAB_KEYS, "lab")

    values: dict[str, Any] = {}
    for key in ("openfpgaloader", "board_model", "expected_part_prefix", "vivado_dir"):
        if key in lab:
            values[key] = _expect(lab[key], str, f"lab.{key}")
    if "max_bitstream_bytes" in lab:
        values["max_bitstream_bytes"] = _expect(
            lab["max_bitstream_bytes"], int, "lab.max_bitstream_bytes"
        )
    if "program_timeout_s" in lab:
        values["program_timeout_s"] = float(
            _expect(lab["program_timeout_s"], (int, float), "lab.program_timeout_s")
        )
    if "jtag_freq_hz" in lab:
        values["jtag_freq_hz"] = _expect(lab["jtag_freq_hz"], int, "lab.jtag_freq_hz")

    boards_raw = data.get("boards") or [{"id": "zybo1"}]
    boards = tuple(_parse_board(b, i) for i, b in enumerate(boards_raw))
    ids = [b.id for b in boards]
    if len(set(ids)) != len(ids):
        raise ConfigError("Hay identificadores de placa repetidos.")
    return LabConfig(boards=boards, **values)


def find_config_file(explicit: str | Path | None = None) -> Path | None:
    """Orden de búsqueda: argumento, variable DRL_CONFIG, ./lab.toml, ./config/lab.toml."""
    if explicit:
        return Path(explicit)
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env)
    for candidate in DEFAULT_LOCATIONS:
        if candidate.is_file():
            return candidate
    return None


def load_config(explicit: str | Path | None = None) -> LabConfig:
    path = find_config_file(explicit)
    if path is None:
        return LabConfig()
    if not path.is_file():
        raise ConfigError(f"No existe el fichero de configuración '{path}'.")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Error de sintaxis en '{path}': {exc}") from exc
    return parse_config(data)
