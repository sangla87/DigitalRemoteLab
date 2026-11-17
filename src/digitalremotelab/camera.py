"""Captura de imágenes de la placa con una webcam USB (V4L2)."""

from __future__ import annotations

from typing import Any, Protocol

from digitalremotelab.config import CameraConfig
from digitalremotelab.errors import DRLError

_FAKE_JPEG = b"\xff\xd8\xff\xd9"  # solo marcadores SOI/EOI: basta para los tests


class CameraError(DRLError):
    """No se pudo abrir la cámara o leer un fotograma."""


class Camera(Protocol):
    def capture_jpeg(self) -> bytes: ...


def _import_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise CameraError(
            "Falta OpenCV. Instálalo con: pip install 'digitalremotelab[camera]'"
        ) from exc
    return cv2


class OpenCVCamera:
    """Abre la cámara solo durante la captura (suficiente para la etapa 1).

    Se descartan unos fotogramas iniciales para que la cámara ajuste exposición
    y balance de blancos antes de guardar la imagen.
    """

    def __init__(self, config: CameraConfig, cv2_module: Any = None) -> None:
        self._config = config
        self._cv2 = cv2_module

    def capture_jpeg(self) -> bytes:
        cv2 = self._cv2 or _import_cv2()
        device = self._config.device
        if isinstance(device, str) and device.isdigit():
            device = int(device)

        cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        try:
            if not cap.isOpened():
                raise CameraError(
                    f"No se puede abrir la cámara {device!r}. Comprueba la ruta y los permisos "
                    "(el usuario debe pertenecer al grupo 'video')."
                )
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.height)
            frame = None
            for _ in range(self._config.warmup_frames + 1):
                ok, frame = cap.read()
                if not ok:
                    raise CameraError("La cámara no entregó ningún fotograma.")
            ok, buffer = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._config.jpeg_quality]
            )
            if not ok:
                raise CameraError("No se pudo codificar el fotograma como JPEG.")
            return buffer.tobytes()
        finally:
            cap.release()


class FakeCamera:
    def __init__(self, data: bytes = _FAKE_JPEG) -> None:
        self._data = data
        self.captures = 0

    def capture_jpeg(self) -> bytes:
        self.captures += 1
        return self._data
