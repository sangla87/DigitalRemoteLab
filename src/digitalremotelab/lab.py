"""Fachada del laboratorio: valida, programa y fotografía una placa.

La CLI de la etapa 1 y el backend web de la etapa 2 usan esta misma clase, así
que el comportamiento (validación incluida) es idéntico en ambos.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from digitalremotelab.bitstream import BitstreamInfo, load_bitstream, validate_for_part
from digitalremotelab.camera import Camera, FakeCamera, OpenCVCamera
from digitalremotelab.compiler import (
    CompileError,
    CompileJob,
    Compiler,
    CompileResult,
    FakeCompiler,
    VivadoCompiler,
    new_job_id,
)
from digitalremotelab.config import BoardConfig, LabConfig
from digitalremotelab.programmer import (
    FakeProgrammer,
    OpenFPGALoaderProgrammer,
    Programmer,
    ProgramResult,
)
from digitalremotelab.wrapper import DEFAULT_CLOCK_MODE


class Lab:
    def __init__(
        self,
        config: LabConfig,
        programmer: Programmer,
        camera_factory: Callable[[BoardConfig], Camera],
        compiler: Compiler | None = None,
    ) -> None:
        self.config = config
        self._compiler = compiler
        self._programmer = programmer
        self._camera_factory = camera_factory

    @classmethod
    def from_config(cls, config: LabConfig, fake: bool = False) -> Lab:
        if fake:
            return cls(
                config,
                FakeProgrammer(),
                lambda board: FakeCamera(),
                FakeCompiler(config.work_dir),
            )
        return cls(
            config,
            OpenFPGALoaderProgrammer(config),
            lambda board: OpenCVCamera(board.camera),
            VivadoCompiler(config),
        )

    def validate(self, bitstream: str | Path, board_id: str | None = None) -> BitstreamInfo:
        """Valida el .bit contra la FPGA de la placa indicada (o de la primera)."""
        board = self.config.board(board_id)
        info = load_bitstream(bitstream, self.config.max_bitstream_bytes)
        validate_for_part(info, board.part_prefix, board.model_name)
        return info

    def program(
        self, bitstream: str | Path, board_id: str | None = None
    ) -> tuple[BitstreamInfo, ProgramResult]:
        """Valida el .bit y, solo si es correcto, lo carga en la placa."""
        info = self.validate(bitstream, board_id)
        board = self.config.board(board_id)
        return info, self._programmer.program(board, Path(bitstream))

    def compile(
        self,
        vhdl: str,
        board_id: str | None = None,
        clock_mode: str = DEFAULT_CLOCK_MODE,
        job_id: str | None = None,
    ) -> CompileResult:
        """Valida el VHDL del alumno y lo compila para la placa indicada (no la programa)."""
        if self._compiler is None:
            raise CompileError("Este laboratorio no tiene compilador configurado.")
        board = self.config.board(board_id)
        return self._compiler.compile(CompileJob(job_id or new_job_id(), vhdl, board, clock_mode))

    def compile_and_program(
        self,
        vhdl: str,
        board_id: str | None = None,
        clock_mode: str = DEFAULT_CLOCK_MODE,
        job_id: str | None = None,
    ) -> tuple[CompileResult, BitstreamInfo | None, ProgramResult | None]:
        """Compila y, solo si sale bien y el .bit es válido para la placa, lo carga."""
        result = self.compile(vhdl, board_id, clock_mode, job_id)
        if not result.ok or result.bitstream is None:
            return result, None, None
        info, programmed = self.program(result.bitstream, board_id)
        return result, info, programmed

    def detect(self, board_id: str | None = None) -> ProgramResult:
        return self._programmer.detect(self.config.board(board_id))

    def snapshot(self, board_id: str | None = None) -> bytes:
        board = self.config.board(board_id)
        return self._camera_factory(board).capture_jpeg()
