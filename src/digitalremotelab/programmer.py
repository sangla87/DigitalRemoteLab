"""Carga de bitstreams en la FPGA mediante openFPGALoader (JTAG por USB)."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from digitalremotelab.config import BoardConfig, LabConfig


@dataclass(frozen=True)
class ProgramResult:
    ok: bool
    command: tuple[str, ...]
    returncode: int | None
    output: str
    duration_s: float
    error: str | None = None


class Programmer(Protocol):
    def program(self, board: BoardConfig, bitstream: Path) -> ProgramResult: ...

    def detect(self, board: BoardConfig) -> ProgramResult: ...


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class OpenFPGALoaderProgrammer:
    """Ejecuta openFPGALoader como proceso externo (sin shell)."""

    def __init__(
        self,
        config: LabConfig,
        runner: Callable[..., Any] = subprocess.run,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._runner = runner
        self._clock = clock

    def build_command(
        self, board: BoardConfig, bitstream: Path | None = None, detect: bool = False
    ) -> list[str]:
        cmd = [self._config.openfpgaloader, "-b", self._config.board_model]
        if board.ftdi_serial:
            cmd += ["--ftdi-serial", board.ftdi_serial]
        if self._config.jtag_freq_hz:
            cmd += ["--freq", str(self._config.jtag_freq_hz)]
        cmd += list(board.extra_args)
        if detect:
            cmd.append("--detect")
        else:
            if bitstream is None:
                raise ValueError("Falta el bitstream a cargar.")
            # -m: cargar en SRAM (volátil). La ruta es absoluta, así que nunca
            # puede interpretarse como una opción.
            cmd += ["-m", str(Path(bitstream).resolve())]
        return cmd

    def program(self, board: BoardConfig, bitstream: Path) -> ProgramResult:
        return self._run(self.build_command(board, bitstream=bitstream))

    def detect(self, board: BoardConfig) -> ProgramResult:
        return self._run(self.build_command(board, detect=True))

    def _run(self, cmd: list[str]) -> ProgramResult:
        timeout = self._config.program_timeout_s
        start = self._clock()
        try:
            proc = self._runner(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        except FileNotFoundError:
            return ProgramResult(
                ok=False,
                command=tuple(cmd),
                returncode=None,
                output="",
                duration_s=self._clock() - start,
                error=f"No se encuentra '{cmd[0]}'. ¿Está openFPGALoader instalado y en el PATH?",
            )
        except subprocess.TimeoutExpired as exc:
            return ProgramResult(
                ok=False,
                command=tuple(cmd),
                returncode=None,
                output=_to_text(exc.stdout) + _to_text(exc.stderr),
                duration_s=self._clock() - start,
                error=f"openFPGALoader no terminó en {timeout:g} s y se canceló.",
            )
        output = _to_text(proc.stdout) + _to_text(proc.stderr)
        ok = proc.returncode == 0
        return ProgramResult(
            ok=ok,
            command=tuple(cmd),
            returncode=proc.returncode,
            output=output,
            duration_s=self._clock() - start,
            error=None if ok else f"openFPGALoader terminó con código {proc.returncode}.",
        )


class FakeProgrammer:
    """Simula la placa: para tests y para desarrollar sin hardware."""

    def __init__(self, fail_with: str | None = None) -> None:
        self.fail_with = fail_with
        self.programmed: list[tuple[str, Path]] = []
        self.detected: list[str] = []

    def program(self, board: BoardConfig, bitstream: Path) -> ProgramResult:
        if self.fail_with:
            return ProgramResult(False, ("fake",), 1, "", 0.0, error=self.fail_with)
        self.programmed.append((board.id, Path(bitstream)))
        return ProgramResult(
            True, ("fake", board.id), 0, f"FAKE: cargado {Path(bitstream).name}", 0.0
        )

    def detect(self, board: BoardConfig) -> ProgramResult:
        if self.fail_with:
            return ProgramResult(False, ("fake",), 1, "", 0.0, error=self.fail_with)
        self.detected.append(board.id)
        return ProgramResult(True, ("fake", board.id), 0, "FAKE: xc7z010 detectada", 0.0)
