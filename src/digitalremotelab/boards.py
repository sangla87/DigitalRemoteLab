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
    notes: str = ""


MODELS: dict[str, BoardModel] = {
    m.key: m
    for m in (
        BoardModel(
            key="zybo_z7_10",
            name="Digilent Zybo Z7-10",
            ofl_board="zybo_z7_10",
            part_prefix="7z010",
        ),
        BoardModel(
            key="nexys4",
            name="Digilent Nexys 4",
            ofl_board="nexys4",
            part_prefix="7a100t",
            notes="No es intercambiable con la Nexys 4 DDR: los pines son distintos.",
        ),
        BoardModel(
            key="nexys4ddr",
            name="Digilent Nexys 4 DDR / Nexys A7-100T",
            ofl_board="nexys4ddr",
            part_prefix="7a100t",
            notes="Misma FPGA que la Nexys 4, pero con otros pines.",
        ),
    )
}


def known_models() -> str:
    return ", ".join(MODELS)
