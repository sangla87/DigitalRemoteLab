"""Genera `drl_top.vhd` y el XDC para un diseño de alumno ya validado con `portcheck`.

`drl_top` es la entidad superior real: recibe el reloj de 100 MHz de la placa, entrega al diseño del
alumno (`main`) uno de los relojes lentos de `clock_gen`, sincroniza sus entradas y conecta sus
salidas a los pines. Las salidas que el alumno no usa quedan apagadas y los segmentos y ánodos
(activos a nivel bajo en la placa) se invierten, de modo que en Digital `1` significa «encendido».
"""

from __future__ import annotations

from dataclasses import dataclass

from digitalremotelab.errors import DRLError
from digitalremotelab.pins import CLOCK_PIN, CLOCK_PORT, pins_for
from digitalremotelab.portcheck import VhdlInfo

CLOCK_MODES = {"1khz": "00", "1hz": "01", "10hz": "10", "manual": "11"}
DEFAULT_CLOCK_MODE = "1hz"
MANUAL_PULSE_PORT = "BTN0"  # botón físico central: el pulso virtual llegará en la etapa 3

LEDS = tuple(f"LED{i}" for i in range(16))
DISPLAY = (*(f"SEG_{c}" for c in "ABCDEFG"), "SEG_DP", *(f"AN{i}" for i in range(8)))


class WrapperError(DRLError):
    """No se puede generar el envoltorio para esa combinación de diseño, placa y reloj."""


@dataclass(frozen=True)
class Wrapper:
    vhdl: str
    xdc: str
    clock_mode: str


def generate_wrapper(info: VhdlInfo, model: str, clock_mode: str = DEFAULT_CLOCK_MODE) -> Wrapper:
    if clock_mode not in CLOCK_MODES:
        raise WrapperError(
            f"Modo de reloj desconocido: «{clock_mode}». Disponibles: {', '.join(CLOCK_MODES)}."
        )
    try:
        pins = pins_for(model)
    except KeyError as exc:
        raise WrapperError(str(exc.args[0])) from None

    manual = clock_mode == "manual"
    if manual and MANUAL_PULSE_PORT in info.inputs:
        raise WrapperError(
            f"En modo de reloj manual el botón {MANUAL_PULSE_PORT} genera el pulso: "
            "el diseño no puede usarlo como entrada."
        )

    uses_clk = "CLK" in info.inputs
    data_inputs = [n for n in info.inputs if n != "CLK"]
    top_inputs = list(data_inputs) + ([MANUAL_PULSE_PORT] if manual else [])
    used_outputs = set(info.outputs)

    lines: list[str] = []
    add = lines.append
    add("-- Generado por DigitalRemoteLab: no editar a mano.")
    add("library ieee;")
    add("use ieee.std_logic_1164.all;")
    add("")
    add("entity drl_top is")
    add("  generic (USE_BUFG : boolean := true);")
    add("  port (")
    ports = [f"    {CLOCK_PORT} : in  std_logic"]
    ports += [f"    {n} : in  std_logic" for n in top_inputs]
    ports += [f"    {n} : out std_logic" for n in (*LEDS, *DISPLAY)]
    add(";\n".join(ports))
    add("  );")
    add("end entity drl_top;")
    add("")
    add("architecture rtl of drl_top is")
    add("  signal student_clk : std_logic := '0';")
    for n in top_inputs:
        add(f"  signal {n}_m, {n}_s : std_logic := '0';")
    for n in info.outputs:
        add(f"  signal s_{n} : std_logic;")
    add("begin")
    add("")
    if top_inputs:
        add("  -- Sincronizadores de 2 flip-flops en el dominio de 100 MHz.")
        add(f"  process ({CLOCK_PORT})")
        add("  begin")
        add(f"    if rising_edge({CLOCK_PORT}) then")
        for n in top_inputs:
            add(f"      {n}_m <= {n}; {n}_s <= {n}_m;")
        add("    end if;")
        add("  end process;")
        add("")
    if uses_clk:
        add("  clock_i : entity work.clock_gen")
        add("    generic map (USE_BUFG => USE_BUFG)")
        pulse = f"{MANUAL_PULSE_PORT}" if manual else "'0'"
        add(
            f'    port map (clk => {CLOCK_PORT}, mode => "{CLOCK_MODES[clock_mode]}", '
            f"pulse => {pulse}, clk_out => student_clk);"
        )
        add("")
    add("  student : entity work.main")
    maps = []
    if uses_clk:
        maps.append("CLK => student_clk")
    maps += [f"{n} => {n}_s" for n in data_inputs]
    maps += [f"{n} => s_{n}" for n in info.outputs]
    add("    port map (" + ",\n              ".join(maps) + ");")
    add("")
    for n in LEDS:
        add(f"  {n} <= s_{n};" if n in used_outputs else f"  {n} <= '0';")
    add("  -- Segmentos y ánodos: activos a nivel bajo en la placa.")
    for n in DISPLAY:
        add(f"  {n} <= not s_{n};" if n in used_outputs else f"  {n} <= '1';")
    add("")
    add("end architecture rtl;")
    vhdl = "\n".join(lines) + "\n"

    xdc: list[str] = [
        f"# Generado por DigitalRemoteLab para {model}: no editar a mano.",
        f"set_property -dict {{ PACKAGE_PIN {CLOCK_PIN} IOSTANDARD LVCMOS33 }} "
        f"[get_ports {{ {CLOCK_PORT} }}]",
        f"create_clock -add -name sys_clk_pin -period 10.00 -waveform {{0 5}} "
        f"[get_ports {{ {CLOCK_PORT} }}]",
    ]
    for n in (*top_inputs, *LEDS, *DISPLAY):
        p = pins[n]
        xdc.append(
            f"set_property -dict {{ PACKAGE_PIN {p.pin} IOSTANDARD {p.iostandard} }} "
            f"[get_ports {{ {n} }}]"
        )
    return Wrapper(vhdl=vhdl, xdc="\n".join(xdc) + "\n", clock_mode=clock_mode)
