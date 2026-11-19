"""Aplicación web (FastAPI) del laboratorio.

Endpoints:
    GET  /                 página con la subida, el estado y el vídeo
    GET  /api/config       placas, relojes disponibles y límites
    POST /api/jobs         sube un VHDL de Digital (.vhd/.vhdl) o un .bit; devuelve el trabajo
    GET  /api/jobs/{id}    estado del trabajo
    GET  /api/snapshot     foto JPEG de la placa
    GET  /video            vídeo MJPEG en directo

Sin autenticación todavía (etapa 5): escucha por defecto solo en 127.0.0.1 y debe ir detrás de un
proxy que limite el acceso.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from digitalremotelab.errors import DRLError
from digitalremotelab.jobs import JobManager, JobNotFound, JobQueueFull
from digitalremotelab.lab import Lab
from digitalremotelab.portcheck import MAX_VHDL_BYTES, VhdlError
from digitalremotelab.stream import CameraStream
from digitalremotelab.wrapper import CLOCK_MODES, DEFAULT_CLOCK_MODE

STATIC = Path(__file__).parent / "static"
BOUNDARY = "drlframe"
VHDL_SUFFIXES = (".vhd", ".vhdl")


async def mjpeg_parts(
    stream: CameraStream, fps: float = 5.0, max_frames: int | None = None
) -> AsyncIterator[bytes]:
    """Genera las partes de un `multipart/x-mixed-replace` con cada fotograma nuevo."""
    last = -1
    sent = 0
    while max_frames is None or sent < max_frames:
        seq, frame = stream.latest()
        if frame is not None and seq != last:
            last = seq
            sent += 1
            head = (
                f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(frame)}\r\n\r\n"
            )
            yield head.encode() + frame + b"\r\n"
        else:
            await asyncio.sleep(1.0 / (2 * fps))


def create_app(lab: Lab, stream: CameraStream, manager: JobManager | None = None) -> FastAPI:
    manager = manager or JobManager(lab)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stream.start()
        try:
            yield
        finally:
            stream.stop()
            manager.shutdown()

    app = FastAPI(title="DigitalRemoteLab", lifespan=lifespan)
    max_upload = max(lab.config.max_bitstream_bytes, MAX_VHDL_BYTES)

    @app.exception_handler(DRLError)
    async def drl_error(_, exc: DRLError) -> JSONResponse:
        status = (
            404 if isinstance(exc, JobNotFound) else 503 if isinstance(exc, JobQueueFull) else 422
        )
        errors = exc.problems if isinstance(exc, VhdlError) else [str(exc)]
        return JSONResponse({"errors": errors}, status_code=status)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/config")
    def config() -> dict:
        return {
            "boards": [{"id": b.id, "name": b.model_name} for b in lab.config.boards],
            "clocks": list(CLOCK_MODES),
            "default_clock": DEFAULT_CLOCK_MODE,
            "max_upload_bytes": max_upload,
        }

    @app.post("/api/jobs", status_code=202)
    async def submit(
        file: UploadFile, clock: str = Form(DEFAULT_CLOCK_MODE), board: str | None = Form(None)
    ) -> dict:
        name = (file.filename or "").lower()
        is_vhdl = name.endswith(VHDL_SUFFIXES)
        if not is_vhdl and not name.endswith(".bit"):
            raise HTTPException(415, "Sube un fichero .vhd/.vhdl (de Digital) o un .bit.")
        data = await file.read(max_upload + 1)
        if len(data) > max_upload:
            raise HTTPException(413, f"El fichero supera el máximo de {max_upload} bytes.")
        if is_vhdl:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(422, "El VHDL debe ser texto UTF-8.") from None
            job = await asyncio.to_thread(manager.submit_vhdl, text, board, clock)
        else:
            job = await asyncio.to_thread(manager.submit_bitstream, data, board)
        return manager.get(job.id)

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        return manager.get(job_id)

    @app.get("/api/snapshot")
    def snapshot() -> Response:
        _, frame = stream.latest()
        if frame is None:
            raise HTTPException(503, stream.error or "La cámara aún no ha entregado imagen.")
        return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/video")
    def video() -> StreamingResponse:
        return StreamingResponse(
            mjpeg_parts(stream),
            media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
            headers={"Cache-Control": "no-store"},
        )

    return app
