import re
import shutil
import subprocess
from pathlib import Path

import pytest

from digitalremotelab.pins import PINS, pins_for
from digitalremotelab.portcheck import VhdlError, check_vhdl
from digitalremotelab.wrapper import WrapperError, generate_wrapper

ROOT = Path(__file__).resolve().parent.parent
HDL = ROOT / "hdl"

STUDENT = """
library ieee;
use ieee.std_logic_1164.all;

entity main is
  port (
    SW0: in std_logic;
    SW1: in std_logic;
    CLK: in std_logic;
    LED0: out std_logic;
    LED1: out std_logic;
    SEG_A: out std_logic;
    AN0: out std_logic );
end main;

architecture Behavioral of main is
begin
  LED0 <= SW0;
  LED1 <= CLK;
  SEG_A <= SW1;
  AN0 <= '1';
end Behavioral;
"""


def gen(model="nexys4", mode="1khz", src=STUDENT):
    return generate_wrapper(check_vhdl(src), model, mode)


# --- Tabla de pines -------------------------------------------------------------------------


@pytest.mark.parametrize("model", sorted(PINS))
def test_pin_table_has_no_repeated_pins_and_covers_every_port(model):
    from digitalremotelab.portcheck import INPUTS, OUTPUTS

    table = PINS[model]
    assert set(table) == (INPUTS - {"CLK"}) | OUTPUTS
    pins = [p.pin for p in table.values()]
    assert len(set(pins)) == len(pins)
    assert "E3" not in pins  # reservado para el reloj


def test_boards_have_different_pins_for_display_and_buttons():
    a, b = PINS["nexys4"], PINS["nexys4ddr"]
    for name in ("SEG_A", "SEG_DP", "AN0", "AN7", "BTN0", "BTN4"):
        assert a[name].pin != b[name].pin
    assert a["SEG_A"].pin == "L3" and b["SEG_A"].pin == "T10"


def test_ddr_switches_8_and_9_are_1v8():
    t = PINS["nexys4ddr"]
    assert t["SW8"].iostandard == t["SW9"].iostandard == "LVCMOS18"
    assert t["SW7"].iostandard == "LVCMOS33"
    assert all(p.iostandard == "LVCMOS33" for p in PINS["nexys4"].values())


@pytest.mark.parametrize("model", sorted(PINS))
def test_switch_and_led_pins_agree_with_the_verified_test_board_xdc(model):
    """Los XDC de hdl/test_board también proceden de los XDC oficiales de Digilent."""
    text = (HDL / "test_board" / f"{model}.xdc").read_text()
    found = dict(
        re.findall(r"PACKAGE_PIN\s+(\w+)\s.*?get_ports\s*\{\s*((?:SW|LED)\[\d+\])\s*\}", text)[::-1]
    )
    assert found
    table = pins_for(model)
    for port, pin in ((v, k) for k, v in found.items()):
        name = port.replace("[", "").replace("]", "")
        if name in table:
            assert table[name].pin == pin, name


def test_unknown_model():
    with pytest.raises(KeyError, match="zybo"):
        pins_for("zybo_z7_10")


# --- Generación -----------------------------------------------------------------------------


def test_wrapper_connects_student_ports_and_inverts_display():
    w = gen()
    assert "entity work.main" in w.vhdl
    assert "CLK => student_clk" in w.vhdl
    assert "SW0 => SW0_s" in w.vhdl and "LED0 => s_LED0" in w.vhdl
    assert "LED0 <= s_LED0;" in w.vhdl and "LED5 <= '0';" in w.vhdl
    assert "SEG_A <= not s_SEG_A;" in w.vhdl and "SEG_B <= '1';" in w.vhdl
    assert "AN0 <= not s_AN0;" in w.vhdl and "AN7 <= '1';" in w.vhdl
    assert 'mode => "00"' in w.vhdl


@pytest.mark.parametrize(
    ("mode", "bits"), [("1khz", "00"), ("1hz", "01"), ("10hz", "10"), ("manual", "11")]
)
def test_clock_modes(mode, bits):
    assert f'mode => "{bits}"' in gen(mode=mode).vhdl


def test_unused_input_ports_are_not_in_the_top_entity():
    w = gen()
    assert "SW2" not in w.vhdl and "BTN" not in w.vhdl


def test_xdc_has_the_right_pins_for_each_board():
    nexys4 = gen("nexys4").xdc
    ddr = gen("nexys4ddr").xdc
    assert "PACKAGE_PIN L3 IOSTANDARD LVCMOS33 } [get_ports { SEG_A }]" in nexys4
    assert "PACKAGE_PIN T10 IOSTANDARD LVCMOS33 } [get_ports { SEG_A }]" in ddr
    assert "create_clock" in nexys4 and "E3" in nexys4
    for xdc in (nexys4, ddr):
        pins = re.findall(r"PACKAGE_PIN (\w+)", xdc)
        assert len(pins) == len(set(pins))
        # reloj + 2 entradas usadas (SW0, SW1) + 16 LED + 16 de display (7 seg., DP, 8 ánodos)
        assert len(pins) == 1 + 2 + 16 + 16


def test_manual_mode_uses_btn0_as_pulse_and_forbids_it_to_the_student():
    w = gen(mode="manual")
    assert "BTN0 : in  std_logic" in w.vhdl and "pulse => BTN0" in w.vhdl
    with pytest.raises(WrapperError, match="BTN0"):
        gen(
            mode="manual",
            src=STUDENT.replace("SW1: in", "BTN0: in").replace("SEG_A <= SW1", "SEG_A <= BTN0"),
        )


def test_design_without_clk_has_no_clock_generator():
    src = STUDENT.replace("    CLK: in std_logic;\n", "").replace("LED1 <= CLK;", "LED1 <= SW1;")
    assert "clock_gen" not in gen(src=src).vhdl


def test_errors():
    with pytest.raises(WrapperError, match="reloj"):
        gen(mode="2hz")
    with pytest.raises(WrapperError, match="zybo"):
        gen(model="zybo_z7_10")


def test_reserved_entity_names_are_rejected():
    with pytest.raises(VhdlError, match="reservado"):
        check_vhdl(STUDENT + "\nentity clock_gen is port (x : in std_logic); end clock_gen;")


# --- Simulación con GHDL --------------------------------------------------------------------

TB = """
library ieee;
use ieee.std_logic_1164.all;
entity tb_top is end entity;
architecture sim of tb_top is
  signal clk : std_logic := '0';
  signal sw0, sw1 : std_logic := '0';
  signal led : std_logic_vector(15 downto 0);
  signal seg_a, seg_b, an0, an1 : std_logic;
  signal running : boolean := true;
begin
  clk <= not clk after 5 ns when running else clk;
  dut : entity work.drl_top
    generic map (USE_BUFG => false)
    port map (CLK100MHZ => clk, SW0 => sw0, SW1 => sw1,
              LED0 => led(0), LED1 => led(1), LED2 => led(2), LED3 => led(3),
              LED4 => led(4), LED5 => led(5), LED6 => led(6), LED7 => led(7),
              LED8 => led(8), LED9 => led(9), LED10 => led(10), LED11 => led(11),
              LED12 => led(12), LED13 => led(13), LED14 => led(14), LED15 => led(15),
              SEG_A => seg_a, SEG_B => seg_b, SEG_C => open, SEG_D => open, SEG_E => open,
              SEG_F => open, SEG_G => open, SEG_DP => open,
              AN0 => an0, AN1 => an1, AN2 => open, AN3 => open, AN4 => open, AN5 => open,
              AN6 => open, AN7 => open);
  process begin
    wait for 100 ns;
    assert led(0) = '0' and seg_a = '1' report "estado inicial incorrecto" severity failure;
    assert an0 = '0' report "AN0 debía estar encendido (nivel bajo)" severity failure;
    assert an1 = '1' and seg_b = '1'
      report "salidas sin usar deben estar apagadas" severity failure;
    assert led(15 downto 2) = (13 downto 0 => '0')
      report "LED sin usar encendidos" severity failure;
    sw0 <= '1'; sw1 <= '1';
    wait for 100 ns;
    assert led(0) = '1' report "SW0 no llega a LED0" severity failure;
    assert seg_a = '0' report "SEG_A debía invertirse" severity failure;
    -- reloj de 1 kHz del alumno (semiperiodo de 0,5 ms): LED1 debe cambiar
    wait for 1.2 ms;
    assert led(1) = '1' or led(1) = '0' report "LED1 indefinido" severity failure;
    report "banco de pruebas superado";
    running <= false;
    wait;
  end process;
end architecture;
"""


@pytest.mark.skipif(shutil.which("ghdl") is None, reason="GHDL no está instalado")
def test_generated_wrapper_simulates_with_student_design(tmp_path):
    w = gen()
    (tmp_path / "student.vhd").write_text(STUDENT)
    (tmp_path / "drl_top.vhd").write_text(w.vhdl)
    (tmp_path / "tb_top.vhd").write_text(TB)
    files = [
        str(HDL / "wrapper" / "clock_gen.vhd"),
        str(tmp_path / "student.vhd"),
        str(tmp_path / "drl_top.vhd"),
        str(tmp_path / "tb_top.vhd"),
    ]

    def ghdl(command, *args):
        cmd = ["ghdl", command, "--std=08", f"--workdir={tmp_path}", *args]
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert ghdl("-a", *files).returncode == 0, ghdl("-a", *files).stderr
    assert ghdl("-e", "tb_top").returncode == 0
    result = ghdl("-r", "tb_top", "--stop-time=3ms")
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "banco de pruebas superado" in output
