import os
import struct
from pathlib import Path

import pytest

from digitalremotelab.bitstream import MAGIC, SYNC_WORD
from digitalremotelab.config import ENV_VAR


@pytest.fixture(autouse=True)
def isolated_from_server_config(tmp_path_factory, monkeypatch):
    """Aísla los tests del lab.toml del servidor.

    `drl` busca la configuración en DRL_CONFIG, ./lab.toml y ./config/lab.toml. En el servidor
    del laboratorio existe un config/lab.toml real (p. ej. una Nexys 4) y, sin este aislamiento,
    los tests de la CLI lo usaban y rechazaban sus .bit sintéticos de la Zybo.
    """
    sample = os.environ.get("DRL_SAMPLE_BIT")
    if sample:
        monkeypatch.setenv("DRL_SAMPLE_BIT", str(Path(sample).resolve()))
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))


def build_bit(
    design: str = "Contadores",
    part: str = "7z010clg400",
    version: str = "2020.2",
    payload_size: int = 4096,
    with_sync: bool = True,
    declared_extra: int = 0,
) -> bytes:
    """Construye un .bit sintético con la misma estructura que el de Vivado."""

    def text_field(key: str, text: str) -> bytes:
        raw = text.encode() + b"\x00"
        return key.encode() + struct.pack(">H", len(raw)) + raw

    sync = SYNC_WORD if with_sync else b"\x00" * len(SYNC_WORD)
    payload = (b"\xff" * 32 + sync).ljust(payload_size, b"\x00")
    header = struct.pack(">H", len(MAGIC)) + MAGIC + struct.pack(">H", 1)
    header += text_field("a", f"{design};UserID=0XFFFFFFFF;Version={version}")
    header += text_field("b", part)
    header += text_field("c", "2024/10/27")
    header += text_field("d", "22:15:09")
    header += b"e" + struct.pack(">I", len(payload) + declared_extra)
    return header + payload


@pytest.fixture
def make_bit(tmp_path):
    def _make(name: str = "design.bit", **kwargs) -> Path:
        path = tmp_path / name
        path.write_bytes(build_bit(**kwargs))
        return path

    return _make
