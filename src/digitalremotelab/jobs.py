"""Cola de trabajos del laboratorio: compilar y/o cargar un diseño, de uno en uno.

Con una sola placa (etapa 2) hay un único hilo trabajador: los envíos se encolan y se atienden por
orden. La validación (VHDL o cabecera del .bit) se hace al enviar, para que el alumno vea el
error al momento y no ocupe un sitio de la cola con un diseño inválido. Los turnos por usuario y el
reparto entre varias placas llegan en las etapas 3 y 4.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from digitalremotelab.compiler import new_job_id
from digitalremotelab.errors import DRLError
from digitalremotelab.lab import Lab
from digitalremotelab.portcheck import check_vhdl
from digitalremotelab.wrapper import DEFAULT_CLOCK_MODE, generate_wrapper

log = logging.getLogger(__name__)

MAX_QUEUE = 5
MAX_HISTORY = 50


class JobQueueFull(DRLError):
    """Hay demasiados trabajos en cola."""


class JobNotFound(DRLError):
    """No existe ese trabajo."""


class JobState(str, Enum):
    QUEUED = "queued"
    COMPILING = "compiling"
    PROGRAMMING = "programming"
    DONE = "done"
    ERROR = "error"


@dataclass
class Job:
    id: str
    kind: str  # "vhdl" | "bit"
    board_id: str
    clock_mode: str | None
    state: JobState = JobState.QUEUED
    errors: list[str] = field(default_factory=list)
    design_name: str | None = None
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    compile_s: float | None = None
    program_s: float | None = None

    def to_dict(self, queue_position: int | None = None) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "board": self.board_id,
            "clock": self.clock_mode,
            "state": self.state.value,
            "queue_position": queue_position,
            "errors": list(self.errors),
            "design": self.design_name,
            "compile_s": self.compile_s,
            "program_s": self.program_s,
        }

    @property
    def finished_ok(self) -> bool:
        return self.state is JobState.DONE


class JobManager:
    def __init__(
        self,
        lab: Lab,
        max_queue: int = MAX_QUEUE,
        max_history: int = MAX_HISTORY,
        on_programmed: Callable[[Job], None] | None = None,
    ) -> None:
        self._lab = lab
        self._max_queue = max_queue
        self._max_history = max_history
        self._on_programmed = on_programmed
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._pending: list[str] = []
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="drl-job")

    # --- envío ---------------------------------------------------------------------------------

    def submit_vhdl(
        self, vhdl: str, board_id: str | None = None, clock_mode: str = DEFAULT_CLOCK_MODE
    ) -> Job:
        board = self._lab.config.board(board_id)
        # Mismas comprobaciones que hará el compilador: errores inmediatos y en español.
        generate_wrapper(check_vhdl(vhdl), board.model, clock_mode)
        job = Job(new_job_id(), "vhdl", board.id, clock_mode)
        return self._enqueue(job, lambda: self._run_vhdl(job, vhdl))

    def submit_bitstream(self, data: bytes, board_id: str | None = None) -> Job:
        board = self._lab.config.board(board_id)
        job = Job(new_job_id(), "bit", board.id, None)
        folder = Path(self._lab.config.work_dir) / job.id
        # Se valida antes de encolar: un .bit de otra FPGA no llega nunca a la placa.
        folder.mkdir(parents=True, exist_ok=False)
        path = folder / "upload.bit"
        path.write_bytes(data)
        try:
            info = self._lab.validate(path, board.id)
        except DRLError:
            path.unlink(missing_ok=True)
            folder.rmdir()
            raise
        job.design_name = info.design_name
        return self._enqueue(job, lambda: self._run_bitstream(job, path))

    def _enqueue(self, job: Job, work: Callable[[], None]) -> Job:
        with self._lock:
            if len(self._pending) >= self._max_queue:
                raise JobQueueFull(f"Hay {len(self._pending)} trabajos en cola. Inténtalo luego.")
            self._jobs[job.id] = job
            self._pending.append(job.id)
            while len(self._jobs) > self._max_history:
                oldest = next(iter(self._jobs))
                if oldest in self._pending:
                    break
                del self._jobs[oldest]
        self._executor.submit(self._guard, job, work)
        return job

    # --- consulta ------------------------------------------------------------------------------

    def get(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(f"No existe el trabajo '{job_id}'.")
            position = self._pending.index(job_id) if job_id in self._pending else None
            return job.to_dict(position)

    def queue_length(self) -> int:
        with self._lock:
            return len(self._pending)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # --- trabajo -------------------------------------------------------------------------------

    def _set(self, job: Job, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)

    def _guard(self, job: Job, work: Callable[[], None]) -> None:
        with self._lock:
            if job.id in self._pending:
                self._pending.remove(job.id)
        self._set(job, started=time.time())
        try:
            work()
        except DRLError as exc:
            self._set(job, state=JobState.ERROR, errors=[str(exc)])
        except Exception:  # un fallo nuestro: se registra y no se enseña la traza al alumno
            log.exception("Error interno en el trabajo %s", job.id)
            self._set(job, state=JobState.ERROR, errors=["Error interno del laboratorio."])
        finally:
            self._set(job, finished=time.time())

    def _run_vhdl(self, job: Job, vhdl: str) -> None:
        self._set(job, state=JobState.COMPILING)
        result = self._lab.compile(
            vhdl, job.board_id, job.clock_mode or DEFAULT_CLOCK_MODE, job_id=job.id
        )
        self._set(job, compile_s=result.duration_s)
        if not result.ok or result.bitstream is None:
            self._set(job, state=JobState.ERROR, errors=list(result.errors))
            return
        self._program(job, result.bitstream)

    def _run_bitstream(self, job: Job, path: Path) -> None:
        self._program(job, path)

    def _program(self, job: Job, bitstream: Path) -> None:
        self._set(job, state=JobState.PROGRAMMING)
        info, result = self._lab.program(bitstream, job.board_id)
        self._set(job, design_name=info.design_name, program_s=result.duration_s)
        if not result.ok:
            self._set(job, state=JobState.ERROR, errors=[result.error or "Fallo al programar."])
            return
        self._set(job, state=JobState.DONE)
        if self._on_programmed:
            self._on_programmed(job)
