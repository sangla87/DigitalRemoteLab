"""Fotogramas de la cámara en continuo para el vídeo de la web.

Un único hilo lee la cámara y guarda el último fotograma JPEG; todos los espectadores leen ese
fotograma, así que la cámara no se abre una vez por espectador. Si la cámara falla, el hilo lo
anota y reintenta cada pocos segundos.
"""

from __future__ import annotations

import logging
import threading
import time

from digitalremotelab.camera import Camera
from digitalremotelab.errors import DRLError

log = logging.getLogger(__name__)


class CameraStream:
    def __init__(self, camera: Camera, fps: float = 5.0, retry_s: float = 3.0) -> None:
        self._camera = camera
        self._period = 1.0 / fps
        self._retry_s = retry_s
        self._lock = threading.Lock()
        self._frame: bytes | None = None
        self._seq = 0
        self._error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="drl-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def latest(self) -> tuple[int, bytes | None]:
        """Número de secuencia y último fotograma (None si aún no hay ninguno)."""
        with self._lock:
            return self._seq, self._frame

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                frame = self._camera.capture_jpeg()
            except DRLError as exc:
                with self._lock:
                    self._error = str(exc)
                log.warning("Cámara: %s", exc)
                self._stop.wait(self._retry_s)
                continue
            with self._lock:
                self._frame = frame
                self._seq += 1
                self._error = None
            self._stop.wait(max(self._period - (time.monotonic() - started), 0.0))
