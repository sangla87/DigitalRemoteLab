"""Catálogo de modelos de placa soportados.

Cada modelo indica cómo se llama la placa para openFPGALoader (`-b`) y qué FPGA
lleva, para rechazar bitstreams generados para otro dispositivo. Para una placa
que no esté aquí, `lab.toml` permite indicar `ofl_board` y `part_prefix` a mano.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MODEL = "zybo_z7_10"


@dataclass(frozen=True)
class BoardModel:
    key: str  # identificador usado en lab.toml
    name: str  # nombre legible
    ofl_board: str  # valor de `-b` de openFPGALoader
    part_prefix: str  # prefijo de la parte en la cabecera del .bit (sin "xc")
    vivado_part: str = ""  # parte completa para Vivado, p. ej. xc7a100tcsg324-1
    notes: str = ""


MODELS: dict[str, BoardModel] = {
    m.key: m
    for m in (
        BoardModel(
            key="zybo_z7_10",
            name="Digilent Zybo Z7-10",
            ofl_board="zybo_z7_10",
            part_prefix="7z010",
            vivado_part="xc7z010clg400-1",
        ),
        BoardModel(
            key="nexys4",
            name="Digilent Nexys 4",
            ofl_board="nexys_a7_100",
            part_prefix="7a100t",
            vivado_part="xc7a100tcsg324-1",
            notes=(
                "Sin entrada propia en openFPGALoader: se usa la de la Nexys A7-100T, que lleva "
                "la misma FPGA y el mismo JTAG (solo se carga en SRAM). Sus pines NO son los "
                "de la Nexys 4 DDR."
            ),
        ),
        BoardModel(
            key="nexys4ddr",
            name="Digilent Nexys 4 DDR / Nexys A7-100T",
            ofl_board="nexys_a7_100",
            part_prefix="7a100t",
            vivado_part="xc7a100tcsg324-1",
            notes="Misma FPGA que la Nexys 4, pero con otros pines.",
        ),
    )
}


def known_models() -> str:
    return ", ".join(MODELS)
