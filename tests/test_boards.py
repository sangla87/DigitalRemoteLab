import pytest
from conftest import build_bit

from digitalremotelab.bitstream import BitstreamError, parse_bitstream
from digitalremotelab.boards import MODELS
from digitalremotelab.camera import FakeCamera
from digitalremotelab.config import BoardConfig, ConfigError, LabConfig, parse_config
from digitalremotelab.lab import Lab
from digitalremotelab.programmer import FakeProgrammer, OpenFPGALoaderProgrammer


def test_catalog_has_expected_models():
    assert MODELS["zybo_z7_10"].part_prefix == "7z010"
    assert MODELS["nexys4"].part_prefix == "7a100t"
    assert MODELS["nexys4ddr"].part_prefix == "7a100t"
    assert MODELS["nexys4"].ofl_board != MODELS["nexys4ddr"].ofl_board


def test_board_resolves_openfpgaloader_name_and_part_from_model():
    board = BoardConfig(id="a", model="nexys4ddr")
    assert board.ofl_board == "nexys4ddr"
    assert board.part_prefix == "7a100t"
    assert "Nexys 4 DDR" in board.model_name


def test_unknown_model_without_overrides_is_rejected():
    with pytest.raises(ConfigError, match="Modelos conocidos"):
        BoardConfig(id="a", model="basys2")


def test_unlisted_board_can_be_defined_by_hand():
    board = BoardConfig(id="a", model="otra", ofl_board="mi_placa", part_prefix="7a35t")
    assert board.ofl_board == "mi_placa"
    assert board.model_name == "otra"


def test_lab_model_is_the_default_for_every_board():
    config = parse_config(
        {
            "lab": {"model": "nexys4ddr"},
            "boards": [{"id": "a"}, {"id": "b", "model": "zybo_z7_10"}],
        }
    )
    assert config.board("a").model == "nexys4ddr"
    assert config.board("b").model == "zybo_z7_10"
    assert config.board("b").part_prefix == "7z010"


def test_lab_model_without_boards_creates_one_default_board():
    config = parse_config({"lab": {"model": "nexys4"}})
    assert [b.model for b in config.boards] == ["nexys4"]


def test_config_rejects_unknown_model():
    with pytest.raises(ConfigError, match="desconocido"):
        parse_config({"boards": [{"id": "a", "model": "nope"}]})


def test_openfpgaloader_command_uses_the_board_model(tmp_path):
    calls = []

    def runner(cmd, **kwargs):
        from types import SimpleNamespace

        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    prog = OpenFPGALoaderProgrammer(LabConfig(), runner=runner)
    prog.program(BoardConfig(id="a", model="nexys4ddr", ftdi_serial="S1"), tmp_path / "x.bit")
    assert calls[0][:5] == ["openFPGALoader", "-b", "nexys4ddr", "--ftdi-serial", "S1"]


def make_lab(boards):
    config = LabConfig(boards=tuple(boards))
    return Lab(config, FakeProgrammer(), lambda board: FakeCamera())


def test_artix_bitstream_is_accepted_by_a_nexys_and_rejected_by_a_zybo(make_bit):
    artix = make_bit(part="7a100tcsg324")
    lab = make_lab([BoardConfig(id="nexys", model="nexys4ddr"), BoardConfig(id="zybo")])
    assert lab.validate(artix, "nexys").part == "7a100tcsg324"
    with pytest.raises(BitstreamError, match="Zybo Z7-10"):
        lab.validate(artix, "zybo")


def test_zynq_bitstream_is_rejected_by_a_nexys(make_bit):
    lab = make_lab([BoardConfig(id="nexys", model="nexys4")])
    with pytest.raises(BitstreamError, match="Nexys 4"):
        lab.validate(make_bit(part="7z010clg400"), "nexys")


def test_vivado_part_names_with_xc_prefix_are_accepted():
    from digitalremotelab.bitstream import validate_for_part

    info = parse_bitstream(build_bit(part="xc7a100tcsg324-1"))
    validate_for_part(info, "7a100t")
