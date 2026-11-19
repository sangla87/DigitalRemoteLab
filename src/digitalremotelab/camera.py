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

    def __init__(
        self, config: CameraConfig, cv2_module: Any = None, keep_open: bool = False
    ) -> None:
        self._config = config
        self._cv2 = cv2_module
        self._keep_open = keep_open  # True para el vídeo en continuo (hilo único)
        self._cap: Any = None

    def _open(self, cv2: Any) -> Any:
        device = self._config.device
        if isinstance(device, str) and device.isdigit():
            device = int(device)
        cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            raise CameraError(
                f"No se puede abrir la cámara {device!r}. Comprueba la ruta y los permisos "
                "(el usuario debe pertenecer al grupo 'video')."
            )
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # poca latencia en el vídeo en directo
        return cap

    def _warm_up(self, cap: Any) -> None:
        for _ in range(self._config.warmup_frames):
            cap.read()

    def capture_jpeg(self) -> bytes:
        cv2 = self._cv2 or _import_cv2()
        if self._keep_open:
            if self._cap is None:
                self._cap = self._open(cv2)
                self._warm_up(self._cap)
            cap = self._cap
        else:
            cap = self._open(cv2)
            self._warm_up(cap)
        try:
            ok, frame = cap.read()
            if not ok:
                self.close()
                raise CameraError("La cámara no entregó ningún fotograma.")
            ok, buffer = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._config.jpeg_quality]
            )
            if not ok:
                raise CameraError("No se pudo codificar el fotograma como JPEG.")
            return buffer.tobytes()
        finally:
            if not self._keep_open:
                cap.release()

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class FakeCamera:
    def __init__(self, data: bytes = _FAKE_JPEG) -> None:
        self._data = data
        self.captures = 0

    def capture_jpeg(self) -> bytes:
        self.captures += 1
        return self._data
