"""Compilación del VHDL de un alumno hasta un `.bit`, con Vivado en modo batch.

Cada compilación vive en su propia carpeta `work/<id>/` con estos ficheros, todos con nombre fijo:

    student.vhd      el VHDL del alumno, ya validado con `portcheck`
    clock_gen.vhd    generador del reloj lento (de hdl/wrapper)
    drl_top.vhd      envoltorio generado por `wrapper.py`
    constraints.xdc  pines de la placa
    build.tcl        script de Vivado (no contiene texto del alumno)
    vivado.log       salida de Vivado
    drl.bit          resultado

El texto del alumno solo llega a Vivado como contenido de `student.vhd`: nunca se interpola en el
Tcl ni en la línea de órdenes.
"""

from __future__ import annotations

import os
import re
import resource
import secrets
import shutil
import signal
import struct
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from digitalremotelab.bitstream import MAGIC, SYNC_WORD
from digitalremotelab.config import BoardConfig, LabConfig
from digitalremotelab.errors import DRLError
from digitalremotelab.portcheck import check_vhdl
from digitalremotelab.wrapper import DEFAULT_CLOCK_MODE, generate_wrapper

BITSTREAM_NAME = "drl.bit"
LOG_NAME = "vivado.log"
CLOCK_GEN_VHDL = Path(__file__).resolve().parents[2] / "hdl" / "wrapper" / "clock_gen.vhd"
MAX_REPORTED_LINES = 20
MAX_LINE_CHARS = 300

_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ERROR_LINE_RE = re.compile(r"^(ERROR|CRITICAL WARNING):")

BUILD_TCL = """\
# Generado por DigitalRemoteLab. No contiene texto del alumno.
set part {part}

read_vhdl student.vhd
read_vhdl clock_gen.vhd
read_vhdl drl_top.vhd
read_xdc  constraints.xdc

synth_design -top drl_top -part $part
opt_design
place_design
route_design

report_utilization -file utilization.rpt
report_timing_summary -file timing.rpt
report_clock_networks -file clocks.rpt

write_bitstream -force {bitstream}
puts "OK: bitstream generado"
"""


class CompileError(DRLError):
    """No se pudo preparar o lanzar la compilación (no es un fallo del diseño del alumno)."""


@dataclass(frozen=True)
class CompileJob:
    job_id: str
    vhdl: str
    board: BoardConfig
    clock_mode: str = DEFAULT_CLOCK_MODE


@dataclass(frozen=True)
class CompileResult:
    ok: bool
    job_dir: Path
    bitstream: Path | None = None
    errors: tuple[str, ...] = ()  # mensajes para el alumno
    duration_s: float = 0.0
    timed_out: bool = False

    @property
    def log_path(self) -> Path:
        return self.job_dir / LOG_NAME

    @property
    def error(self) -> str:
        return "\n".join(self.errors)


class Compiler(Protocol):
    def compile(self, job: CompileJob) -> CompileResult: ...


def new_job_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"


def extract_errors(log: str) -> tuple[str, ...]:
    """Líneas `ERROR:` y `CRITICAL WARNING:` de la salida de Vivado, recortadas y sin repetir."""
    found: list[str] = []
    for line in log.splitlines():
        if _ERROR_LINE_RE.match(line) and line not in found:
            found.append(line[:MAX_LINE_CHARS])
        if len(found) >= MAX_REPORTED_LINES:
            break
    return tuple(found)


def prepare_job(job: CompileJob, work_dir: str | Path) -> Path:
    """Valida el VHDL, genera el envoltorio y escribe los ficheros de la compilación.

    Lanza `VhdlError` o `WrapperError` si el diseño no cumple el contrato, antes de tocar Vivado.
    """
    if not _JOB_ID_RE.match(job.job_id):
        raise CompileError(f"Identificador de compilación inválido: {job.job_id!r}.")
    part = job.board.vivado_part
    if not part:
        raise CompileError(
            f"La placa '{job.board.id}' ({job.board.model_name}) no tiene parte de Vivado: "
            "no se puede compilar para ella."
        )
    info = check_vhdl(job.vhdl)
    wrapper = generate_wrapper(info, job.board.model, job.clock_mode)

    job_dir = Path(work_dir) / job.job_id
    try:
        job_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise CompileError(f"Ya existe la compilación '{job.job_id}'.") from None
    (job_dir / "student.vhd").write_text(job.vhdl, encoding="utf-8")
    shutil.copyfile(CLOCK_GEN_VHDL, job_dir / "clock_gen.vhd")
    (job_dir / "drl_top.vhd").write_text(wrapper.vhdl, encoding="utf-8")
    (job_dir / "constraints.xdc").write_text(wrapper.xdc, encoding="utf-8")
    (job_dir / "build.tcl").write_text(
        BUILD_TCL.format(part=part, bitstream=BITSTREAM_NAME), encoding="utf-8"
    )
    return job_dir


def _limit_child() -> None:  # pragma: no cover - se ejecuta en el proceso hijo
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    two_gib = 2 * 1024**3
    resource.setrlimit(resource.RLIMIT_FSIZE, (two_gib, two_gib))


class VivadoCompiler:
    """Ejecuta `vivado -mode batch` sobre la carpeta de la compilación.

    Límites: tiempo (`compile_timeout_s`, se mata todo el grupo de procesos), entorno reducido,
    `HOME` y `TMPDIR` dentro de la carpeta de la compilación, sin núcleos de volcado y con tamaño
    máximo de fichero. El límite de memoria y el usuario sin privilegios se aplican desde fuera
    (systemd/cgroups) al desplegar: ver docs/etapa-2-diseno.md.
    """

    def __init__(self, config: LabConfig) -> None:
        self._config = config

    @property
    def executable(self) -> Path:
        return Path(self._config.vivado_dir) / "bin" / "vivado"

    def compile(self, job: CompileJob) -> CompileResult:
        if not self.executable.is_file():
            raise CompileError(f"No se encuentra Vivado en {self.executable}.")
        job_dir = prepare_job(job, self._config.work_dir)
        home = job_dir / "home"
        home.mkdir()
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C",
            "HOME": str(home),
            "TMPDIR": str(home),
        }
        command = [str(self.executable), "-mode", "batch", "-nojournal", "-nolog"]
        command += ["-source", "build.tcl"]

        started = time.monotonic()
        timed_out = False
        with open(job_dir / LOG_NAME, "wb") as log:
            try:
                proc = subprocess.Popen(
                    command,
                    cwd=job_dir,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    preexec_fn=_limit_child,  # noqa: PLW1509
                )
            except OSError as exc:
                raise CompileError(f"No se pudo ejecutar Vivado: {exc}") from exc
            try:
                returncode = proc.wait(timeout=self._config.compile_timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                returncode = -signal.SIGKILL
        duration = time.monotonic() - started
        return self._result(job_dir, returncode, timed_out, duration)

    def _result(self, job_dir: Path, returncode: int, timed_out: bool, duration: float):
        bit = job_dir / BITSTREAM_NAME
        if timed_out:
            limit = self._config.compile_timeout_s
            msg = f"La compilación superó el tiempo máximo ({limit:.0f} s) y se canceló."
            return CompileResult(False, job_dir, None, (msg,), duration, timed_out=True)
        if returncode == 0 and bit.is_file():
            return CompileResult(True, job_dir, bit, (), duration)
        log = (job_dir / LOG_NAME).read_text(encoding="utf-8", errors="replace")
        errors = extract_errors(log) or (
            f"Vivado terminó con código {returncode} y no generó el bitstream.",
        )
        return CompileResult(False, job_dir, None, errors, duration)


def build_fake_bitstream(part: str, design: str = "drl_top") -> bytes:
    """Un .bit sintético con la cabecera de Vivado, para pruebas y `--fake`."""

    def field(key: str, text: str) -> bytes:
        raw = text.encode() + b"\x00"
        return key.encode() + struct.pack(">H", len(raw)) + raw

    header_part = part.removeprefix("xc").rsplit("-", 1)[0]
    payload = (b"\xff" * 32 + SYNC_WORD).ljust(4096, b"\x00")
    header = struct.pack(">H", len(MAGIC)) + MAGIC + struct.pack(">H", 1)
    header += field("a", f"{design};UserID=0XFFFFFFFF;Version=2022.2")
    header += field("b", header_part)
    header += field("c", "2026/11/18") + field("d", "12:00:00")
    header += b"e" + struct.pack(">I", len(payload))
    return header + payload


class FakeCompiler:
    """Compilador simulado: hace todo menos ejecutar Vivado (valida, genera, escribe ficheros)."""

    def __init__(self, work_dir: str | Path, error: str | None = None) -> None:
        self._work_dir = work_dir
        self._error = error
        self.jobs: list[CompileJob] = []

    def compile(self, job: CompileJob) -> CompileResult:
        job_dir = prepare_job(job, self._work_dir)
        self.jobs.append(job)
        if self._error:
            return CompileResult(False, job_dir, None, (self._error,), 0.0)
        bit = job_dir / BITSTREAM_NAME
        bit.write_bytes(build_fake_bitstream(job.board.vivado_part))
        return CompileResult(True, job_dir, bit, (), 0.0)
