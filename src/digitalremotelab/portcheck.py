"""Validación del VHDL que exporta Digital, antes de compilarlo con Vivado.

Contrato (ver docs/etapa-2-diseno.md):

- Existe la entidad `main` y todos sus puertos son `std_logic` de 1 bit.
- Los nombres de los puertos son los de la placa: entradas `CLK`, `SW0..15`, `BTN0..4`; salidas
  `LED0..15`, `SEG_A..SEG_G`, `SEG_DP` y `AN0..7`.
- Solo se usan las librerías `ieee` estándar (y `work` / `std.standard`).
- No se instancian primitivas de Xilinx (relojes, buffers, JTAG, memorias...).

No es un parser VHDL completo: se apoya en expresiones regulares sobre el texto sin comentarios.
Lo que no detecta aquí lo rechazará Vivado, y el servidor compila siempre con un Tcl propio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from digitalremotelab.errors import DRLError

MAX_VHDL_BYTES = 1_000_000

INPUTS = frozenset({"CLK", *(f"SW{i}" for i in range(16)), *(f"BTN{i}" for i in range(5))})
OUTPUTS = frozenset(
    {
        *(f"LED{i}" for i in range(16)),
        *(f"SEG_{c}" for c in "ABCDEFG"),
        "SEG_DP",
        *(f"AN{i}" for i in range(8)),
    }
)

ALLOWED_LIBRARIES = frozenset({"ieee", "work", "std"})
ALLOWED_IEEE_PACKAGES = frozenset(
    {"std_logic_1164", "numeric_std", "std_logic_unsigned", "std_logic_arith", "numeric_bit"}
)
ALLOWED_STD_PACKAGES = frozenset({"standard"})

FORBIDDEN_PRIMITIVES = re.compile(
    r"\b(unisim|unimacro|xpm|vcomponents|textio|"
    r"bufg\w*|bufh\w*|bufio\w*|bufr|ibuf\w*|obuf\w*|iobuf\w*|idelay\w*|odelay\w*|"
    r"iserdes\w*|oserdes\w*|mmcm\w*|plle2\w*|bscane2|startupe2|icape2|dna_port|xadc|"
    r"fd[rcps]e|lut\d|carry4|ramb\w+|dsp48\w*|srl\w*|ibufds\w*|obufds\w*)\b"
)
FORBIDDEN_ATTRIBUTES = re.compile(
    r"\battribute\s+(loc|iostandard|package_pin|clock_buffer_type|dont_touch|mark_debug|"
    r"keep_hierarchy|ram_style|async_reg|iob)\b"
)


class VhdlError(DRLError):
    """El VHDL no cumple el contrato. `problems` lista todos los motivos."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("VHDL no válido:\n- " + "\n- ".join(problems))


@dataclass(frozen=True)
class Port:
    name: str  # en mayúsculas
    direction: str  # "in" | "out"


@dataclass(frozen=True)
class VhdlInfo:
    ports: tuple[Port, ...]

    @property
    def inputs(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.ports if p.direction == "in")

    @property
    def outputs(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.ports if p.direction == "out")


def strip_comments(text: str) -> str:
    return re.sub(r"--[^\n]*", "", text)


def _split_ports(body: str) -> list[tuple[list[str], str, str]]:
    """Divide la lista de puertos en (nombres, dirección, tipo)."""
    result = []
    for decl in (d.strip() for d in body.split(";")):
        if not decl:
            continue
        m = re.fullmatch(
            r"([\w\s,]+?)\s*:\s*(in|out|inout|buffer|linkage)\s+(.+)", decl, re.I | re.S
        )
        if not m:
            raise VhdlError(
                [f"No se entiende la declaración de puerto: «{' '.join(decl.split())}»"]
            )
        names = [n.strip() for n in m.group(1).split(",")]
        result.append((names, m.group(2).lower(), " ".join(m.group(3).split()).lower()))
    return result


def check_vhdl(source: str | bytes) -> VhdlInfo:
    """Valida el VHDL y devuelve sus puertos; lanza `VhdlError` con todos los problemas."""
    if isinstance(source, bytes):
        if len(source) > MAX_VHDL_BYTES:
            raise VhdlError([f"El fichero es demasiado grande (máximo {MAX_VHDL_BYTES} bytes)."])
        try:
            source = source.decode("utf-8")
        except UnicodeDecodeError:
            raise VhdlError(["El fichero no es texto UTF-8."]) from None
    elif len(source.encode()) > MAX_VHDL_BYTES:
        raise VhdlError([f"El fichero es demasiado grande (máximo {MAX_VHDL_BYTES} bytes)."])

    text = strip_comments(source).lower()
    problems: list[str] = []

    for lib in re.findall(r"\blibrary\s+([\w,\s]+?);", text):
        for name in (n.strip() for n in lib.split(",")):
            if name not in ALLOWED_LIBRARIES:
                problems.append(f"Librería no permitida: «{name}».")
    for lib, pkg in re.findall(r"\buse\s+(\w+)\.(\w+)", text):
        if lib == "ieee" and pkg not in ALLOWED_IEEE_PACKAGES:
            problems.append(f"Paquete no permitido: «ieee.{pkg}».")
        elif lib == "std" and pkg not in ALLOWED_STD_PACKAGES:
            problems.append(f"Paquete no permitido: «std.{pkg}».")
        elif lib not in ALLOWED_LIBRARIES:
            problems.append(f"Librería no permitida: «{lib}.{pkg}».")
    for m in sorted(set(FORBIDDEN_PRIMITIVES.findall(text))):
        problems.append(f"Uso de una primitiva o librería de Xilinx no permitida: «{m}».")
    if FORBIDDEN_ATTRIBUTES.search(text):
        problems.append("No se permiten atributos de Vivado (pines, buffers, jerarquía...).")

    m = re.search(r"\bentity\s+main\s+is\b(.*?)\bend\b", text, re.S)
    ports: list[Port] = []
    if not m:
        problems.append("No se encuentra la entidad «main» (la que exporta Digital).")
    else:
        pm = re.search(r"\bport\s*\((.*)\)\s*;?\s*$", m.group(1).strip(), re.S)
        if not pm:
            problems.append("La entidad «main» no tiene lista de puertos.")
        else:
            try:
                declarations = _split_ports(pm.group(1))
            except VhdlError as exc:
                problems.extend(exc.problems)
                declarations = []
            seen: set[str] = set()
            for names, direction, typ in declarations:
                for name in (n.upper() for n in names):
                    if name in seen:
                        problems.append(f"Puerto repetido: «{name}».")
                    seen.add(name)
                    if typ != "std_logic":
                        problems.append(
                            f"El puerto «{name}» debe ser std_logic de 1 bit, no «{typ}»."
                        )
                    if direction not in ("in", "out"):
                        problems.append(
                            f"El puerto «{name}» debe ser `in` u `out`, no `{direction}`."
                        )
                        continue
                    valid = INPUTS if direction == "in" else OUTPUTS
                    if name not in valid:
                        kind = "entrada" if direction == "in" else "salida"
                        allowed = ", ".join(sorted(valid))
                        problems.append(f"«{name}» no es una {kind} válida. Permitidas: {allowed}.")
                    ports.append(Port(name, direction))
            if not any(p.direction == "out" for p in ports) and not problems:
                problems.append("El diseño no tiene ninguna salida.")

    if problems:
        raise VhdlError(sorted(set(problems), key=problems.index))
    return VhdlInfo(tuple(ports))
