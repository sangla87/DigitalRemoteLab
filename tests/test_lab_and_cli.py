from digitalremotelab.camera import FakeCamera
from digitalremotelab.cli import main
from digitalremotelab.config import LabConfig
from digitalremotelab.lab import Lab
from digitalremotelab.programmer import FakeProgrammer


def make_lab(programmer=None):
    programmer = programmer or FakeProgrammer()
    return Lab(LabConfig(), programmer, lambda board: FakeCamera()), programmer


def test_lab_programs_valid_bitstream(make_bit):
    lab, programmer = make_lab()
    info, result = lab.program(make_bit())
    assert result.ok
    assert info.design_name == "Contadores"
    assert len(programmer.programmed) == 1


def test_lab_does_not_touch_the_board_with_an_invalid_bitstream(make_bit):
    from digitalremotelab.bitstream import BitstreamError

    lab, programmer = make_lab()
    wrong_part = make_bit(part="7z020clg400")
    try:
        lab.program(wrong_part)
    except BitstreamError:
        pass
    else:
        raise AssertionError("debía rechazar el bitstream")
    assert programmer.programmed == []


def test_lab_snapshot_returns_jpeg():
    lab, _ = make_lab()
    assert lab.snapshot().startswith(b"\xff\xd8")


def test_cli_info(make_bit, capsys):
    assert main(["--fake", "info", str(make_bit())]) == 0
    out = capsys.readouterr().out
    assert "Contadores" in out and "7z010clg400" in out and "2020.2" in out


def test_cli_info_rejects_wrong_part(make_bit, capsys):
    assert main(["--fake", "info", str(make_bit(part="7z020clg400"))]) == 1
    assert "7z020clg400" in capsys.readouterr().err


def test_cli_program_with_snapshot(make_bit, tmp_path, capsys):
    out_jpg = tmp_path / "foto.jpg"
    code = main(["--fake", "program", str(make_bit()), "--snapshot", str(out_jpg), "--settle", "0"])
    assert code == 0
    assert out_jpg.read_bytes().startswith(b"\xff\xd8")
    assert "cargado" in capsys.readouterr().out


def test_cli_snapshot_and_detect(tmp_path, capsys):
    out_jpg = tmp_path / "s.jpg"
    assert main(["--fake", "snapshot", "-o", str(out_jpg)]) == 0
    assert out_jpg.exists()
    assert main(["--fake", "detect"]) == 0
    assert "xc7z010" in capsys.readouterr().out


def test_cli_reports_missing_file_without_traceback(tmp_path, capsys):
    assert main(["--fake", "program", str(tmp_path / "no.bit")]) == 1
    assert "No existe" in capsys.readouterr().err


def test_cli_unknown_board(make_bit, capsys):
    assert main(["--fake", "program", str(make_bit()), "-b", "zybo9"]) == 1
    assert "zybo9" in capsys.readouterr().err


def test_cli_boards_lists_configured_board_and_models(capsys):
    assert main(["--fake", "boards"]) == 0
    out = capsys.readouterr().out
    assert "board1" in out and "Zybo Z7-10" in out
    assert "nexys4ddr" in out and "nexys4" in out


def test_cli_devices_runs_without_hardware(capsys):
    assert main(["--fake", "devices"]) == 0
    out = capsys.readouterr().out
    assert "FTDI" in out and "Cámaras" in out


def test_cli_info_with_board_option(make_bit, tmp_path, capsys):
    cfg = tmp_path / "lab.toml"
    cfg.write_text(
        '[[boards]]\nid = "n1"\nmodel = "nexys4ddr"\n[[boards]]\nid = "z1"\nmodel = "zybo_z7_10"\n'
    )
    bit = str(make_bit(part="7a100tcsg324"))
    assert main(["-c", str(cfg), "--fake", "info", bit, "-b", "n1"]) == 0
    assert "Nexys 4 DDR" in capsys.readouterr().out
    assert main(["-c", str(cfg), "--fake", "info", bit, "-b", "z1"]) == 1
    assert "7z010" in capsys.readouterr().err


def test_cli_doctor_runs_and_reports(capsys):
    code = main(["--fake", "doctor"])
    out = capsys.readouterr().out
    assert "openFPGALoader" in out
    assert code in (0, 1)


def test_cli_ignores_server_lab_toml_outside_the_test(make_bit, capsys):
    """Regresión: con un config/lab.toml de Nexys 4 en el directorio del proyecto, los tests de la
    CLI usaban esa placa y rechazaban el .bit de la Zybo. Los tests deben usar su propia config."""
    from digitalremotelab.config import load_config

    assert [b.model for b in load_config().boards] == [LabConfig().boards[0].model]
    assert main(["--fake", "info", str(make_bit())]) == 0
