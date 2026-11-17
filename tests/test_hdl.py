"""Comprueba que el diseño de prueba y sus restricciones son coherentes."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

HDL = Path(__file__).resolve().parent.parent / "hdl" / "test_board"
XDC_FILES = sorted(HDL.glob("*.xdc"))


def test_there_is_one_xdc_per_supported_nexys():
    assert {f.stem for f in XDC_FILES} == {"nexys4", "nexys4ddr"}


@pytest.mark.parametrize("xdc", XDC_FILES, ids=lambda f: f.stem)
def test_xdc_covers_exactly_the_vhdl_ports(xdc):
    text = xdc.read_text()
    ports = set(re.findall(r"get_ports\s*\{\s*([^\s}]+)\s*\}", text))
    expected = {"CLK100MHZ"}
    expected |= {f"SW[{i}]" for i in range(8)}
    expected |= {f"LED[{i}]" for i in range(16)}
    assert ports == expected


@pytest.mark.parametrize("xdc", XDC_FILES, ids=lambda f: f.stem)
def test_xdc_has_no_repeated_pins(xdc):
    pins = re.findall(r"PACKAGE_PIN\s+(\S+)", xdc.read_text())
    assert len(pins) == 25
    assert len(set(pins)) == len(pins)


def test_nexys4_and_nexys4ddr_use_different_pins():
    pins = {f.stem: re.findall(r"PACKAGE_PIN\s+(\S+)", f.read_text()) for f in XDC_FILES}
    # Solo el reloj (E3) coincide: los demás pines son distintos entre placas.
    assert pins["nexys4"][0] == pins["nexys4ddr"][0] == "E3"
    assert pins["nexys4"][1:] != pins["nexys4ddr"][1:]


@pytest.mark.skipif(shutil.which("ghdl") is None, reason="GHDL no está instalado")
def test_vhdl_testbench_passes_in_ghdl(tmp_path):
    def ghdl(command, *args, sim_options=()):
        # Las opciones de GHDL van antes de la unidad; las de simulación, después.
        cmd = ["ghdl", command, "--std=08", f"--workdir={tmp_path}", *args, *sim_options]
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

    files = [str(HDL / "test_board.vhd"), str(HDL / "tb_test_board.vhd")]
    assert ghdl("-a", *files).returncode == 0
    assert ghdl("-e", "tb_test_board").returncode == 0
    result = ghdl("-r", "tb_test_board", sim_options=["--stop-time=2us"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "banco de pruebas superado" in result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("ghdl") is None, reason="GHDL no está instalado")
def test_clock_gen_testbench_passes_in_ghdl(tmp_path):
    wrapper = HDL.parent / "wrapper"
    base = ["ghdl", "--std=08", f"--workdir={tmp_path}"]

    def run(command, *args):
        cmd = [base[0], command, *base[1:], *args]
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

    files = [str(wrapper / "clock_gen.vhd"), str(wrapper / "tb_clock_gen.vhd")]
    assert run("-a", *files).returncode == 0
    assert run("-e", "tb_clock_gen").returncode == 0
    result = run("-r", "tb_clock_gen", "--stop-time=20us")
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "banco de pruebas superado" in output
