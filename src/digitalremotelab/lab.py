"""Fachada del laboratorio: valida, programa y fotografía una placa.

La CLI de la etapa 1 y el backend web de la etapa 2 usan esta misma clase, así
que el comportamiento (validación incluida) es idéntico en ambos.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from digitalremotelab.bitstream import BitstreamInfo, load_bitstream, validate_for_part
from digitalremotelab.camera import Camera, FakeCamera, OpenCVCamera
from digitalremotelab.config import BoardConfig, LabConfig
from digitalremotelab.programmer import (
    FakeProgrammer,
    OpenFPGALoaderProgrammer,
    Programmer,
    ProgramResult,
)


class Lab:
    def __init__(
        self,
        config: LabConfig,
        programmer: Programmer,
        camera_factory: Callable[[BoardConfig], Camera],
    ) -> None:
        self.config = config
        self._programmer = programmer
        self._camera_factory = camera_factory

    @classmethod
    def from_config(cls, config: LabConfig, fake: bool = False) -> Lab:
        if fake:
            return cls(config, FakeProgrammer(), lambda board: FakeCamera())
        return cls(
            config,
            OpenFPGALoaderProgrammer(config),
            lambda board: OpenCVCamera(board.camera),
        )

    def validate(self, bitstream: str | Path) -> BitstreamInfo:
        info = load_bitstream(bitstream, self.config.max_bitstream_bytes)
        validate_for_part(info, self.config.expected_part_prefix)
        return info

    def program(
        self, bitstream: str | Path, board_id: str | None = None
    ) -> tuple[BitstreamInfo, ProgramResult]:
        """Valida el .bit y, solo si es correcto, lo carga en la placa."""
        info = self.validate(bitstream)
        board = self.config.board(board_id)
        return info, self._programmer.program(board, Path(bitstream))

    def detect(self, board_id: str | None = None) -> ProgramResult:
        return self._programmer.detect(self.config.board(board_id))

    def snapshot(self, board_id: str | None = None) -> bytes:
        board = self.config.board(board_id)
        return self._camera_factory(board).capture_jpeg()
