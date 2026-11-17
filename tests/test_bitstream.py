import os
from pathlib import Path

import pytest
from conftest import build_bit

from digitalremotelab.bitstream import (
    BitstreamError,
    load_bitstream,
    parse_bitstream,
    validate_for_part,
)


def test_parse_valid_header():
    data = build_bit(design="Contadores", part="7z010clg400", version="2020.2", payload_size=2048)
    info = parse_bitstream(data)
    assert info.design_name == "Contadores"
    assert info.part == "7z010clg400"
    assert info.tool_version == "2020.2"
    assert info.date == "2024/10/27"
    assert info.time == "22:15:09"
    assert info.payload_length == 2048
    assert info.total_length == len(data)


def test_reject_raw_bin_without_header():
    raw_bin = b"\xff" * 32 + bytes.fromhex("AA995566") + b"\x00" * 100
    with pytest.raises(BitstreamError, match="no un .bin|\\.bit"):
        parse_bitstream(raw_bin)


def test_reject_empty_and_tiny_files():
    with pytest.raises(BitstreamError):
        parse_bitstream(b"")
    with pytest.raises(BitstreamError):
        parse_bitstream(b"\x00\x09\x0f")


def test_reject_truncated_payload():
    data = build_bit(payload_size=2048)
    with pytest.raises(BitstreamError, match="truncado o modificado"):
        parse_bitstream(data[:-10])


def test_reject_declared_size_larger_than_actual():
    with pytest.raises(BitstreamError, match="truncado o modificado"):
        parse_bitstream(build_bit(declared_extra=5))


def test_reject_missing_sync_word():
    with pytest.raises(BitstreamError, match="sincronización"):
        parse_bitstream(build_bit(with_sync=False))


def test_validate_part_accepts_zynq_7010():
    validate_for_part(parse_bitstream(build_bit(part="7z010clg400")), "7z010")
    validate_for_part(parse_bitstream(build_bit(part="xc7z010clg400")), "7z010")


def test_validate_part_rejects_other_devices():
    info = parse_bitstream(build_bit(part="7z020clg400"))
    with pytest.raises(BitstreamError, match="7z020clg400"):
        validate_for_part(info, "7z010")


def test_load_rejects_wrong_extension(tmp_path):
    path = tmp_path / "design.bin"
    path.write_bytes(build_bit())
    with pytest.raises(BitstreamError, match="extensión"):
        load_bitstream(path, 1_000_000)


def test_load_rejects_missing_file(tmp_path):
    with pytest.raises(BitstreamError, match="No existe"):
        load_bitstream(tmp_path / "nada.bit", 1_000_000)


def test_load_rejects_too_large(make_bit):
    path = make_bit(payload_size=5000)
    with pytest.raises(BitstreamError, match="máximo"):
        load_bitstream(path, 1000)


def test_load_ok(make_bit):
    info = load_bitstream(make_bit(), 1_000_000)
    assert info.design_name == "Contadores"


@pytest.mark.skipif(
    "DRL_SAMPLE_BIT" not in os.environ,
    reason="Define DRL_SAMPLE_BIT con la ruta de un .bit real de Vivado.",
)
def test_real_bitstream_from_vivado():
    info = load_bitstream(Path(os.environ["DRL_SAMPLE_BIT"]), 4 * 1024 * 1024)
    validate_for_part(info, "7z010")
