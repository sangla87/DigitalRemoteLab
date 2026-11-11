import struct
from pathlib import Path

import pytest

from digitalremotelab.bitstream import MAGIC, SYNC_WORD


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
