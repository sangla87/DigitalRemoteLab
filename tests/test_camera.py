from types import SimpleNamespace

import pytest

from digitalremotelab.camera import CameraError, FakeCamera, OpenCVCamera
from digitalremotelab.config import CameraConfig


class StubCapture:
    def __init__(self, opened=True, frames_ok=True):
        self.opened = opened
        self.frames_ok = frames_ok
        self.reads = 0
        self.released = False
        self.settings = {}

    def isOpened(self):
        return self.opened

    def set(self, prop, value):
        self.settings[prop] = value

    def read(self):
        self.reads += 1
        return self.frames_ok, "frame"

    def release(self):
        self.released = True


def make_cv2(capture, encode_ok=True):
    calls = {}

    def video_capture(device, api):
        calls["device"] = device
        calls["api"] = api
        return capture

    return SimpleNamespace(
        CAP_V4L2=200,
        CAP_PROP_FOURCC=6,
        CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4,
        CAP_PROP_BUFFERSIZE=38,
        IMWRITE_JPEG_QUALITY=1,
        VideoWriter_fourcc=lambda *chars: "".join(chars),
        VideoCapture=video_capture,
        imencode=lambda ext, frame, params: (
            encode_ok,
            SimpleNamespace(tobytes=lambda: b"\xff\xd8JPEG\xff\xd9"),
        ),
        calls=calls,
    )


def test_capture_discards_warmup_frames_and_releases():
    capture = StubCapture()
    cv2 = make_cv2(capture)
    cam = OpenCVCamera(CameraConfig(device="2", warmup_frames=3, width=640, height=480), cv2)

    data = cam.capture_jpeg()

    assert data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")
    assert capture.reads == 4  # 3 de calentamiento + 1 útil
    assert capture.released
    assert cv2.calls == {"device": 2, "api": 200}
    assert capture.settings[3] == 640 and capture.settings[4] == 480


def test_device_path_is_kept_as_string():
    cv2 = make_cv2(StubCapture())
    OpenCVCamera(CameraConfig(device="/dev/v4l/by-id/cam-video-index0"), cv2).capture_jpeg()
    assert cv2.calls["device"] == "/dev/v4l/by-id/cam-video-index0"


def test_camera_that_cannot_open_raises_and_releases():
    capture = StubCapture(opened=False)
    with pytest.raises(CameraError, match="No se puede abrir"):
        OpenCVCamera(CameraConfig(), make_cv2(capture)).capture_jpeg()
    assert capture.released


def test_camera_without_frames_raises():
    with pytest.raises(CameraError, match="fotograma"):
        OpenCVCamera(CameraConfig(), make_cv2(StubCapture(frames_ok=False))).capture_jpeg()


def test_encode_failure_raises():
    with pytest.raises(CameraError, match="JPEG"):
        OpenCVCamera(CameraConfig(), make_cv2(StubCapture(), encode_ok=False)).capture_jpeg()


def test_fake_camera_returns_jpeg_markers():
    cam = FakeCamera()
    data = cam.capture_jpeg()
    assert data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")
    assert cam.captures == 1


def test_keep_open_opens_once_warms_up_once_and_closes_on_request():
    capture = StubCapture()
    opened = []
    cv2 = make_cv2(capture)
    original = cv2.VideoCapture
    cv2.VideoCapture = lambda device, api: opened.append(device) or original(device, api)
    cam = OpenCVCamera(CameraConfig(device="0", warmup_frames=2), cv2, keep_open=True)

    cam.capture_jpeg()
    cam.capture_jpeg()
    cam.capture_jpeg()

    assert opened == [0]
    assert capture.reads == 2 + 3  # calentamiento una sola vez
    assert not capture.released
    assert capture.settings[38] == 1  # poca latencia
    cam.close()
    assert capture.released


def test_keep_open_reopens_after_a_read_failure():
    capture = StubCapture(frames_ok=False)
    cam = OpenCVCamera(CameraConfig(device="0", warmup_frames=0), make_cv2(capture), keep_open=True)
    with pytest.raises(CameraError, match="fotograma"):
        cam.capture_jpeg()
    assert capture.released and cam._cap is None
