import subprocess
from types import SimpleNamespace

from digitalremotelab.config import BoardConfig, LabConfig
from digitalremotelab.programmer import FakeProgrammer, OpenFPGALoaderProgrammer


def make_programmer(runner, **config_kwargs):
    return OpenFPGALoaderProgrammer(LabConfig(**config_kwargs), runner=runner)


def ok_runner(calls):
    def runner(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout="Done\n", stderr="")

    return runner


def test_command_for_program_uses_board_serial_and_absolute_path(tmp_path):
    bit = tmp_path / "x.bit"
    calls = []
    prog = make_programmer(ok_runner(calls))
    board = BoardConfig(id="zybo1", ftdi_serial="210279ABC")

    result = prog.program(board, bit)

    cmd, kwargs = calls[0]
    assert cmd == [
        "openFPGALoader",
        "-b",
        "zybo_z7_10",
        "--ftdi-serial",
        "210279ABC",
        "-m",
        str(bit.resolve()),
    ]
    assert kwargs["timeout"] == 60.0
    assert kwargs["check"] is False
    assert "shell" not in kwargs
    assert result.ok and result.returncode == 0 and "Done" in result.output


def test_relative_bitstream_path_is_made_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    make_programmer(ok_runner(calls)).program(BoardConfig(id="a"), "-evil.bit")
    assert calls[0][0][-1] == str((tmp_path / "-evil.bit").resolve())


def test_command_includes_frequency_and_extra_args(tmp_path):
    calls = []
    prog = make_programmer(ok_runner(calls), jtag_freq_hz=6_000_000)
    board = BoardConfig(id="a", extra_args=("--cable", "digilent_hs2"))
    prog.program(board, tmp_path / "x.bit")
    cmd = calls[0][0]
    assert cmd[3:7] == ["--freq", "6000000", "--cable", "digilent_hs2"]


def test_detect_command_has_no_bitstream():
    calls = []
    make_programmer(ok_runner(calls)).detect(BoardConfig(id="a"))
    assert calls[0][0] == ["openFPGALoader", "-b", "zybo_z7_10", "--detect"]


def test_nonzero_exit_is_a_failure_with_output(tmp_path):
    def runner(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="JTAG init failed")

    result = make_programmer(runner).program(BoardConfig(id="a"), tmp_path / "x.bit")
    assert not result.ok
    assert result.returncode == 1
    assert "JTAG init failed" in result.output
    assert "código 1" in result.error


def test_missing_executable_gives_clear_error(tmp_path):
    def runner(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    result = make_programmer(runner).program(BoardConfig(id="a"), tmp_path / "x.bit")
    assert not result.ok
    assert "PATH" in result.error


def test_timeout_is_reported(tmp_path):
    def runner(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 60, output=b"partial", stderr=None)

    result = make_programmer(runner).program(BoardConfig(id="a"), tmp_path / "x.bit")
    assert not result.ok
    assert "no terminó" in result.error
    assert result.output == "partial"


def test_fake_programmer_records_calls_and_can_fail(tmp_path):
    fake = FakeProgrammer()
    assert fake.program(BoardConfig(id="a"), tmp_path / "x.bit").ok
    assert fake.programmed == [("a", tmp_path / "x.bit")]
    failing = FakeProgrammer(fail_with="boom")
    assert failing.program(BoardConfig(id="a"), tmp_path / "x.bit").error == "boom"
