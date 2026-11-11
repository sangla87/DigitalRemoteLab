import pytest

from digitalremotelab.config import ConfigError, LabConfig, load_config, parse_config


def test_defaults_when_no_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DRL_CONFIG", raising=False)
    config = load_config()
    assert config == LabConfig()
    assert config.board().id == "zybo1"
    assert config.vivado_dir == "/tools/Xilinx/Vivado/2022.2"


def test_load_full_file(tmp_path):
    path = tmp_path / "lab.toml"
    path.write_text(
        """
[lab]
program_timeout_s = 30
jtag_freq_hz = 6000000

[[boards]]
id = "zybo1"
ftdi_serial = "AAA"
extra_args = ["--cable", "digilent_hs2"]

[boards.camera]
device = "/dev/video2"
width = 640

[[boards]]
id = "zybo2"
ftdi_serial = "BBB"
"""
    )
    config = load_config(path)
    assert config.program_timeout_s == 30.0
    assert config.jtag_freq_hz == 6_000_000
    assert [b.id for b in config.boards] == ["zybo1", "zybo2"]
    assert config.board("zybo1").camera.device == "/dev/video2"
    assert config.board("zybo1").camera.width == 640
    assert config.board("zybo1").extra_args == ("--cable", "digilent_hs2")
    assert config.board("zybo2").ftdi_serial == "BBB"


def test_env_var_selects_file(tmp_path, monkeypatch):
    path = tmp_path / "otro.toml"
    path.write_text('[[boards]]\nid = "desdeenv"\n')
    monkeypatch.setenv("DRL_CONFIG", str(path))
    assert load_config().board().id == "desdeenv"


def test_example_file_in_repo_is_valid():
    config = load_config("config/lab.example.toml")
    assert config.board().id == "zybo1"


def test_unknown_key_is_rejected():
    with pytest.raises(ConfigError, match="desconocidas"):
        parse_config({"lab": {"openfpgaloder": "x"}})


def test_duplicate_board_ids_are_rejected():
    with pytest.raises(ConfigError, match="repetidos"):
        parse_config({"boards": [{"id": "a"}, {"id": "a"}]})


@pytest.mark.parametrize("bad_id", ["", "con espacio", "../x", "a" * 40])
def test_invalid_board_id_is_rejected(bad_id):
    with pytest.raises(ConfigError):
        parse_config({"boards": [{"id": bad_id}]})


def test_wrong_types_are_rejected():
    with pytest.raises(ConfigError):
        parse_config({"lab": {"program_timeout_s": "rápido"}})
    with pytest.raises(ConfigError):
        parse_config({"boards": [{"id": "a", "extra_args": "--cable x"}]})
    with pytest.raises(ConfigError):
        parse_config({"lab": {"jtag_freq_hz": True}})


def test_unknown_board_lookup_lists_known_ones():
    with pytest.raises(ConfigError, match="zybo1"):
        LabConfig().board("nope")


def test_missing_and_malformed_files(tmp_path):
    with pytest.raises(ConfigError, match="No existe"):
        load_config(tmp_path / "nada.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("[lab\n")
    with pytest.raises(ConfigError, match="sintaxis"):
        load_config(bad)
