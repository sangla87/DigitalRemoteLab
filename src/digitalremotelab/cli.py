"""Línea de comandos `drl`: pruebas del laboratorio sin necesidad de la web."""

from __future__ import annotations

import argparse
import glob
import importlib.util
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from digitalremotelab import __version__
from digitalremotelab.config import LabConfig, load_config
from digitalremotelab.errors import DRLError
from digitalremotelab.lab import Lab
from digitalremotelab.programmer import ProgramResult


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drl", description="Laboratorio remoto de FPGAs (Zybo Z7-10)."
    )
    parser.add_argument("--version", action="version", version=f"drl {__version__}")
    parser.add_argument("-c", "--config", help="Fichero de configuración TOML.")
    parser.add_argument(
        "--fake",
        action="store_true",
        help="Usa placa y cámara simuladas (para probar sin hardware).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("info", help="Valida un .bit y muestra su cabecera.")
    p.add_argument("bitstream")

    p = sub.add_parser("detect", help="Detecta la FPGA conectada (openFPGALoader --detect).")
    p.add_argument("-b", "--board", help="Identificador de la placa (por defecto, la primera).")

    p = sub.add_parser("program", help="Valida y carga un .bit en la placa.")
    p.add_argument("bitstream")
    p.add_argument("-b", "--board")
    p.add_argument("--snapshot", metavar="FICHERO", help="Guarda una foto tras cargar el .bit.")
    p.add_argument(
        "--settle",
        type=float,
        default=1.0,
        help="Segundos de espera antes de la foto (por defecto 1).",
    )

    p = sub.add_parser("snapshot", help="Guarda una foto de la placa.")
    p.add_argument("-b", "--board")
    p.add_argument("-o", "--output", help="Fichero de salida (por defecto, con fecha y hora).")

    sub.add_parser("doctor", help="Comprueba que el servidor tiene todo lo necesario.")
    return parser


def _print_failure(result: ProgramResult) -> None:
    print(f"Error: {result.error}", file=sys.stderr)
    if result.output.strip():
        print("--- salida de openFPGALoader ---", file=sys.stderr)
        print(result.output.rstrip(), file=sys.stderr)
    print("Orden ejecutada: " + " ".join(result.command), file=sys.stderr)


def _cmd_info(lab: Lab, args: argparse.Namespace) -> int:
    info = lab.validate(args.bitstream)
    print(f"Diseño:     {info.design_name}")
    print(f"Parte:      {info.part}")
    print(f"Generado:   {info.date} {info.time} con Vivado {info.tool_version or '?'}")
    print(f"Datos:      {info.payload_length} bytes")
    print("Bitstream válido para la Zybo Z7-10.")
    return 0


def _cmd_detect(lab: Lab, args: argparse.Namespace) -> int:
    result = lab.detect(args.board)
    if not result.ok:
        _print_failure(result)
        return 1
    print(result.output.rstrip())
    return 0


def _write_snapshot(lab: Lab, board: str | None, output: str | None) -> Path:
    jpeg = lab.snapshot(board)
    path = Path(output or f"snapshot-{datetime.now():%Y%m%d-%H%M%S}.jpg")
    path.write_bytes(jpeg)
    return path


def _cmd_program(lab: Lab, args: argparse.Namespace) -> int:
    info, result = lab.program(args.bitstream, args.board)
    if not result.ok:
        _print_failure(result)
        return 1
    print(f"Diseño '{info.design_name}' cargado en {result.duration_s:.1f} s.")
    if args.snapshot:
        time.sleep(max(args.settle, 0.0))
        path = _write_snapshot(lab, args.board, args.snapshot)
        print(f"Foto guardada en {path}")
    return 0


def _cmd_snapshot(lab: Lab, args: argparse.Namespace) -> int:
    path = _write_snapshot(lab, args.board, args.output)
    print(f"Foto guardada en {path}")
    return 0


def _doctor_lines(config: LabConfig) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []

    exe = shutil.which(config.openfpgaloader)
    lines.append(
        ("OK", f"openFPGALoader encontrado: {exe}")
        if exe
        else ("FALTA", f"openFPGALoader no está en el PATH ('{config.openfpgaloader}').")
    )

    lsusb = shutil.which("lsusb")
    if lsusb:
        out = subprocess.run([lsusb], capture_output=True, text=True, check=False).stdout
        count = sum(1 for line in out.splitlines() if "0403:6010" in line)
        lines.append(
            ("OK", f"Detectado(s) {count} dispositivo(s) FTDI 0403:6010 (JTAG de la Zybo).")
            if count
            else ("AVISO", "No se ve ningún FTDI 0403:6010: ¿placa conectada y encendida?")
        )

    videos = sorted(glob.glob("/dev/video*"))
    lines.append(
        ("OK", f"Dispositivos de vídeo: {', '.join(videos)}")
        if videos
        else ("AVISO", "No hay dispositivos /dev/video*: ¿cámara conectada?")
    )

    lines.append(
        ("OK", "OpenCV instalado.")
        if importlib.util.find_spec("cv2")
        else ("FALTA", "Falta OpenCV: pip install 'digitalremotelab[camera]'")
    )

    vivado = Path(config.vivado_dir) / "bin" / "vivado"
    lines.append(
        ("OK", f"Vivado encontrado: {vivado}")
        if vivado.is_file()
        else ("AVISO", f"No se encuentra {vivado} (solo hace falta desde la etapa 2).")
    )
    return lines


def _cmd_doctor(lab: Lab, args: argparse.Namespace) -> int:
    lines = _doctor_lines(lab.config)
    for status, text in lines:
        print(f"[{status}] {text}")
    return 1 if any(status == "FALTA" for status, _ in lines) else 0


_COMMANDS = {
    "info": _cmd_info,
    "detect": _cmd_detect,
    "program": _cmd_program,
    "snapshot": _cmd_snapshot,
    "doctor": _cmd_doctor,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        lab = Lab.from_config(load_config(args.config), fake=args.fake)
        return _COMMANDS[args.command](lab, args)
    except DRLError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
