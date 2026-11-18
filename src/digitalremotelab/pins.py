"""Pines de las placas para los puertos que puede usar el alumno.

Todos los pines proceden de los XDC maestros oficiales de Digilent (Nexys-4-Master.xdc, rev. B, y
Nexys-4-DDR-Master.xdc, rev. C). La Nexys 4 y la Nexys 4 DDR **no** comparten pines (salvo el
reloj): no mezcles las tablas. Si añades pines, verifícalos contra el XDC maestro; no los escribas
de memoria.

Nombres de los puertos del alumno (ver `portcheck.py`):
    SW0..15, BTN0..4 = BTNC, BTNU, BTNL, BTNR, BTND
    LED0..15, SEG_A..SEG_G (= CA..CG), SEG_DP, AN0..AN7
"""

from __future__ import annotations

from dataclasses import dataclass

CLOCK_PORT = "CLK100MHZ"
CLOCK_PIN = "E3"  # igual en las dos placas
BUTTON_NAMES = ("BTN0", "BTN1", "BTN2", "BTN3", "BTN4")  # C, U, L, R, D


@dataclass(frozen=True)
class Pin:
    pin: str
    iostandard: str = "LVCMOS33"


def _table(
    sw: str, led: str, seg: str, dp: str, an: str, btn: str, low_voltage_sw: tuple[int, ...] = ()
) -> dict[str, Pin]:
    table: dict[str, Pin] = {}
    for i, pin in enumerate(sw.split()):
        table[f"SW{i}"] = Pin(pin, "LVCMOS18" if i in low_voltage_sw else "LVCMOS33")
    for i, pin in enumerate(led.split()):
        table[f"LED{i}"] = Pin(pin)
    for letter, pin in zip("ABCDEFG", seg.split(), strict=True):
        table[f"SEG_{letter}"] = Pin(pin)
    table["SEG_DP"] = Pin(dp)
    for i, pin in enumerate(an.split()):
        table[f"AN{i}"] = Pin(pin)
    for name, pin in zip(BUTTON_NAMES, btn.split(), strict=True):
        table[name] = Pin(pin)
    return table


PINS: dict[str, dict[str, Pin]] = {
    "nexys4": _table(
        sw="U9 U8 R7 R6 R5 V7 V6 V5 U4 V2 U2 T3 T1 R3 P3 P4",
        led="T8 V9 R8 T6 T5 T4 U7 U6 V4 U3 V1 R1 P5 U1 R2 P2",
        seg="L3 N1 L5 L4 K3 M2 L6",
        dp="M4",
        an="N6 M6 M3 N5 N2 N4 L1 M1",
        btn="E16 F15 T16 R10 V10",
    ),
    "nexys4ddr": _table(
        sw="J15 L16 M13 R15 R17 T18 U18 R13 T8 U8 R16 T13 H6 U12 U11 V10",
        led="H17 K15 J13 N14 R18 V17 U17 U16 V16 T15 U14 T16 V15 V14 V12 V11",
        seg="T10 R10 K16 K13 P15 T11 L18",
        dp="H15",
        an="J17 J18 T9 J14 P14 T14 K2 U13",
        btn="N17 M18 P17 M17 P18",
        low_voltage_sw=(8, 9),  # SW8 y SW9 están en un banco a 1,8 V
    ),
}


def pins_for(model: str) -> dict[str, Pin]:
    try:
        return PINS[model]
    except KeyError:
        known = ", ".join(sorted(PINS))
        raise KeyError(f"No hay tabla de pines para «{model}». Disponibles: {known}") from None
