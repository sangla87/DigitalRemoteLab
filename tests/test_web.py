import asyncio
import time

import pytest
from test_wrapper import STUDENT

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient  # noqa: E402

from digitalremotelab.camera import FakeCamera  # noqa: E402
from digitalremotelab.compiler import FakeCompiler  # noqa: E402
from digitalremotelab.config import BoardConfig, LabConfig  # noqa: E402
from digitalremotelab.lab import Lab  # noqa: E402
from digitalremotelab.programmer import FakeProgrammer  # noqa: E402
from digitalremotelab.stream import CameraStream  # noqa: E402
from digitalremotelab.web.app import BOUNDARY, create_app, mjpeg_parts  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0FAKE\xff\xd9"


@pytest.fixture
def client(tmp_path):
    config = LabConfig(boards=(BoardConfig(id="n1", model="nexys4"),), work_dir=str(tmp_path / "w"))
    programmer = FakeProgrammer()
    lab = Lab(config, programmer, lambda b: FakeCamera(JPEG), FakeCompiler(config.work_dir))
    app = create_app(lab, CameraStream(FakeCamera(JPEG), fps=50))
    with TestClient(app) as c:
        c.programmer = programmer
        yield c


def wait_job(client, job_id, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "error"):
            return job
        time.sleep(0.02)
    raise AssertionError("trabajo sin terminar")


def upload(client, name, data, **form):
    return client.post("/api/jobs", files={"file": (name, data)}, data=form)


def test_index_and_config(client):
    page = client.get("/")
    assert page.status_code == 200 and "Laboratorio remoto" in page.text
    cfg = client.get("/api/config").json()
    assert cfg["boards"] == [{"id": "n1", "name": "Digilent Nexys 4"}]
    assert set(cfg["clocks"]) == {"1khz", "1hz", "10hz", "manual"}


def test_upload_vhdl_runs_the_whole_flow(client):
    res = upload(client, "contador.vhd", STUDENT, clock="1khz")
    assert res.status_code == 202
    job = wait_job(client, res.json()["id"])
    assert job["state"] == "done" and job["clock"] == "1khz"
    assert len(client.programmer.programmed) == 1


def test_invalid_vhdl_gets_all_the_problems(client):
    bad = STUDENT.replace("LED1", "LEDX").replace("SEG_A", "SEGX")
    res = upload(client, "x.vhdl", bad)
    assert res.status_code == 422
    text = " ".join(res.json()["errors"])
    assert "LEDX" in text and "SEGX" in text


def test_upload_bitstream(client, make_bit):
    data = make_bit(part="7a100tcsg324").read_bytes()
    res = upload(client, "d.bit", data)
    assert res.status_code == 202
    assert wait_job(client, res.json()["id"])["state"] == "done"
    wrong = make_bit(part="7z010clg400", name="z.bit").read_bytes()
    res = upload(client, "z.bit", wrong)
    assert res.status_code == 422 and "7z010" in " ".join(res.json()["errors"])


def test_rejects_other_extensions_non_utf8_and_oversize(client):
    assert upload(client, "virus.exe", b"x").status_code == 415
    assert upload(client, "a.vhd", b"\xff\xfe\xfa").status_code == 422
    assert upload(client, "a.vhd", b"x" * (5 * 1024 * 1024)).status_code == 413


def test_unknown_clock_and_unknown_job(client):
    res = upload(client, "a.vhd", STUDENT, clock="2hz")
    assert res.status_code == 422 and "reloj" in " ".join(res.json()["errors"])
    assert client.get("/api/jobs/nada").status_code == 404


def test_snapshot_returns_the_latest_frame(client):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        res = client.get("/api/snapshot")
        if res.status_code == 200:
            break
        time.sleep(0.02)
    assert res.status_code == 200 and res.content == JPEG
    assert res.headers["content-type"] == "image/jpeg"


def test_mjpeg_parts_have_boundary_and_length():
    stream = CameraStream(FakeCamera(JPEG), fps=100)
    stream.start()

    async def collect():
        return [part async for part in mjpeg_parts(stream, fps=100, max_frames=2)]

    try:
        parts = asyncio.run(asyncio.wait_for(collect(), 5))
    finally:
        stream.stop()
    assert len(parts) == 2
    for part in parts:
        assert part.startswith(f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n".encode())
        assert f"Content-Length: {len(JPEG)}".encode() in part and JPEG in part


def test_stream_survives_camera_errors_and_recovers():
    from digitalremotelab.camera import CameraError

    class Flaky:
        def __init__(self):
            self.calls = 0

        def capture_jpeg(self):
            self.calls += 1
            if self.calls < 3:
                raise CameraError("sin cámara")
            return JPEG

    stream = CameraStream(Flaky(), fps=100, retry_s=0.01)
    stream.start()
    try:
        end = time.monotonic() + 5
        while stream.latest()[1] is None and time.monotonic() < end:
            time.sleep(0.01)
        assert stream.latest()[1] == JPEG and stream.error is None
    finally:
        stream.stop()
