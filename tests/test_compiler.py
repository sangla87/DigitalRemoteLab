import stat
import time

import pytest
from test_wrapper import STUDENT

from digitalremotelab.cli import main
from digitalremotelab.compiler import (
    CompileError,
    CompileJob,
    FakeCompiler,
    VivadoCompiler,
    build_fake_bitstream,
    extract_errors,
    prepare_job,
)
from digitalremotelab.config import BoardConfig, LabConfig, parse_config
from digitalremotelab.lab import Lab
from digitalremotelab.portcheck import VhdlError
from digitalremotelab.programmer import FakeProgrammer
from digitalremotelab.wrapper import WrapperError

NEXYS = BoardConfig(id="n1", model="nexys4")


def job(job_id="j1", vhdl=STUDENT, board=NEXYS, clock="1khz"):
    return CompileJob(job_id, vhdl, board, clock)


# --- prepare_job -----------------------------------------------------------------------------


def test_prepare_job_writes_fixed_file_names(tmp_path):
    job_dir = prepare_job(job(), tmp_path)
    names = {p.name for p in job_dir.iterdir()}
    assert names == {"student.vhd", "clock_gen.vhd", "drl_top.vhd", "constraints.xdc", "build.tcl"}
    tcl = (job_dir / "build.tcl").read_text()
    assert "set part xc7a100tcsg324-1" in tcl and "write_bitstream -force drl.bit" in tcl


def test_student_text_never_reaches_tcl_xdc_or_wrapper(tmp_path):
    hostile = STUDENT + "\n-- ; exec rm -rf / ; [exec touch /tmp/pwned] $env(HOME)\n"
    job_dir = prepare_job(job(vhdl=hostile), tmp_path)
    for name in ("build.tcl", "constraints.xdc", "drl_top.vhd"):
        text = (job_dir / name).read_text()
        assert "rm -rf" not in text and "pwned" not in text and "$env" not in text
    assert "rm -rf" in (job_dir / "student.vhd").read_text()


@pytest.mark.parametrize("bad", ["", "../x", "a b", "x" * 65, "a/b"])
def test_invalid_job_ids(tmp_path, bad):
    with pytest.raises(CompileError, match="inválido"):
        prepare_job(job(job_id=bad), tmp_path)


def test_duplicate_job_id(tmp_path):
    prepare_job(job(), tmp_path)
    with pytest.raises(CompileError, match="Ya existe"):
        prepare_job(job(), tmp_path)


def test_invalid_vhdl_is_rejected_before_creating_anything(tmp_path):
    with pytest.raises(VhdlError):
        prepare_job(job(vhdl="entity main is end;"), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_board_without_pin_table_or_vivado_part(tmp_path):
    with pytest.raises(WrapperError, match="zybo"):
        prepare_job(job(board=BoardConfig(id="z", model="zybo_z7_10")), tmp_path)
    custom = BoardConfig(id="c", model="otra", ofl_board="x", part_prefix="7a100t")
    with pytest.raises(CompileError, match="parte de Vivado"):
        prepare_job(job(board=custom), tmp_path)


def test_extract_errors_keeps_errors_and_critical_warnings_without_duplicates():
    log = "\n".join(
        [
            "INFO: [Synth 8-638] algo",
            "WARNING: [Synth 8-327] ignorado",
            "CRITICAL WARNING: [Place 30-574] mal",
            "ERROR: [DRC LUTLP-1] bucle combinacional",
            "ERROR: [DRC LUTLP-1] bucle combinacional",
            "ERROR: " + "x" * 1000,
        ]
    )
    errors = extract_errors(log)
    assert len(errors) == 3 and errors[0].startswith("CRITICAL WARNING")
    assert all(len(e) <= 300 for e in errors)


# --- VivadoCompiler con un «vivado» falso -------------------------------------------------------


def fake_vivado(tmp_path, body: str) -> LabConfig:
    bin_dir = tmp_path / "viv" / "bin"
    bin_dir.mkdir(parents=True)
    exe = bin_dir / "vivado"
    exe.write_text("#!/bin/bash\n" + body)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return LabConfig(
        boards=(NEXYS,),
        vivado_dir=str(tmp_path / "viv"),
        work_dir=str(tmp_path / "work"),
        compile_timeout_s=10,
    )


def test_vivado_success_runs_in_job_dir_with_clean_env(tmp_path):
    bit = tmp_path / "ok.bit"
    bit.write_bytes(build_fake_bitstream("xc7a100tcsg324-1"))
    config = fake_vivado(
        tmp_path,
        f'echo "$@" > args.txt; echo "$HOME" > home.txt; echo "${{SECRET:-none}}" > secret.txt\n'
        f"test -f build.tcl && cp {bit} drl.bit\n",
    )
    import os

    os.environ["SECRET"] = "no-debe-verse"
    try:
        result = VivadoCompiler(config).compile(job())
    finally:
        del os.environ["SECRET"]
    assert result.ok and result.bitstream.is_file()
    d = result.job_dir
    assert (d / "args.txt").read_text().strip() == "-mode batch -nojournal -nolog -source build.tcl"
    assert (d / "home.txt").read_text().strip() == str(d / "home")
    assert (d / "secret.txt").read_text().strip() == "none"


def test_vivado_failure_reports_errors_from_the_log(tmp_path):
    config = fake_vivado(tmp_path, 'echo "ERROR: [Synth 8-1] boom"; echo "INFO: x"; exit 1\n')
    result = VivadoCompiler(config).compile(job())
    assert not result.ok and result.bitstream is None
    assert result.errors == ("ERROR: [Synth 8-1] boom",)
    assert "boom" in result.log_path.read_text()


def test_vivado_exit_zero_without_bitstream_is_a_failure(tmp_path):
    config = fake_vivado(tmp_path, "exit 0\n")
    result = VivadoCompiler(config).compile(job())
    assert not result.ok and "no generó" in result.error


def test_vivado_timeout_kills_the_process_group(tmp_path):
    config = fake_vivado(tmp_path, "sleep 30 &\nsleep 30\n")
    config = LabConfig(**{**config.__dict__, "compile_timeout_s": 0.5})
    started = time.monotonic()
    result = VivadoCompiler(config).compile(job())
    assert time.monotonic() - started < 5
    assert result.timed_out and not result.ok and "tiempo máximo" in result.error


def test_missing_vivado(tmp_path):
    config = LabConfig(vivado_dir=str(tmp_path / "nada"), work_dir=str(tmp_path / "w"))
    with pytest.raises(CompileError, match="No se encuentra Vivado"):
        VivadoCompiler(config).compile(job())


# --- FakeCompiler, Lab y CLI ----------------------------------------------------------------


def make_lab(tmp_path, compiler=None):
    config = LabConfig(boards=(NEXYS,), work_dir=str(tmp_path / "work"))
    programmer = FakeProgrammer()
    compiler = compiler or FakeCompiler(config.work_dir)
    return Lab(config, programmer, lambda b: None, compiler), programmer


def test_lab_compiles_and_programs_with_a_valid_bitstream(tmp_path):
    lab, programmer = make_lab(tmp_path)
    result, info, programmed = lab.compile_and_program(STUDENT, clock_mode="10hz")
    assert result.ok and info.part.startswith("7a100t") and programmed.ok
    assert len(programmer.programmed) == 1


def test_lab_does_not_program_after_a_failed_compilation(tmp_path):
    lab, programmer = make_lab(tmp_path, FakeCompiler(tmp_path / "w", error="ERROR: mal"))
    result, info, programmed = lab.compile_and_program(STUDENT)
    assert not result.ok and info is None and programmed is None
    assert programmer.programmed == []


def test_lab_without_compiler(tmp_path):
    lab = Lab(LabConfig(boards=(NEXYS,)), FakeProgrammer(), lambda b: None)
    with pytest.raises(CompileError, match="compilador"):
        lab.compile(STUDENT)


def test_config_accepts_work_dir_and_timeout():
    config = parse_config({"lab": {"work_dir": "/var/lib/drl", "compile_timeout_s": 120}})
    assert config.work_dir == "/var/lib/drl" and config.compile_timeout_s == 120.0


def test_cli_compile_and_program(tmp_path, capsys):
    cfg = tmp_path / "lab.toml"
    cfg.write_text(
        f'[lab]\nwork_dir = "{tmp_path / "work"}"\n[[boards]]\nid = "n1"\nmodel = "nexys4"\n'
    )
    vhdl = tmp_path / "main.vhd"
    vhdl.write_text(STUDENT)
    out = tmp_path / "out.bit"
    args = ["-c", str(cfg), "--fake", "compile", str(vhdl), "--clock", "1khz", "-o", str(out)]
    assert main([*args, "--program"]) == 0
    text = capsys.readouterr().out
    assert "Compilado" in text and "cargado" in text and out.is_file()


def test_cli_compile_reports_invalid_vhdl_without_traceback(tmp_path, capsys):
    cfg = tmp_path / "lab.toml"
    cfg.write_text(
        f'[lab]\nwork_dir = "{tmp_path / "work"}"\n[[boards]]\nid = "n1"\nmodel = "nexys4"\n'
    )
    vhdl = tmp_path / "main.vhd"
    vhdl.write_text(STUDENT.replace("LED1", "LEDX"))
    assert main(["-c", str(cfg), "--fake", "compile", str(vhdl)]) == 1
    assert "LEDX" in capsys.readouterr().err
