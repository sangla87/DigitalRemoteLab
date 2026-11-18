"""Línea de comandos `drl`: pruebas del laboratorio sin necesidad de la web."""

from __future__ import annotations

import argparse
import glob
import importlib.util
import shutil
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from digitalremotelab import __version__
from digitalremotelab.boards import MODELS
from digitalremotelab.config import LabConfig, load_config
from digitalremotelab.errors import DRLError
from digitalremotelab.lab import Lab
from digitalremotelab.programmer import ProgramResult
from digitalremotelab.usb import list_cameras, list_ftdi_devices
from digitalremotelab.wrapper import CLOCK_MODES, DEFAULT_CLOCK_MODE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drl", description="Laboratorio remoto de FPGAs de Digilent."
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
    p.add_argument("-b", "--board", help="Placa contra la que se valida (por defecto, la primera).")

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

    p = sub.add_parser("compile", help="Compila un VHDL de Digital a .bit con Vivado.")
    p.add_argument("vhdl")
    p.add_argument("-b", "--board")
    p.add_argument(
        "--clock",
        default=DEFAULT_CLOCK_MODE,
        choices=sorted(CLOCK_MODES),
        help="Reloj que recibe el diseño (por defecto 1hz).",
    )
    p.add_argument("-o", "--output", metavar="FICHERO", help="Copia aquí el .bit resultante.")
    p.add_argument("--program", action="store_true", help="Carga el .bit en la placa si sale bien.")
    p.add_argument("--snapshot", metavar="FICHERO", help="Con --program: foto tras cargar.")
    p.add_argument("--settle", type=float, default=1.0)

    p = sub.add_parser("snapshot", help="Guarda una foto de la placa.")
    p.add_argument("-b", "--board")
    p.add_argument("-o", "--output", help="Fichero de salida (por defecto, con fecha y hora).")

    sub.add_parser("boards", help="Muestra las placas configuradas y los modelos soportados.")
    sub.add_parser(
        "devices", help="Lista las placas USB (con su nº de serie) y las cámaras detectadas."
    )
    sub.add_parser("doctor", help="Comprueba que el servidor tiene todo lo necesario.")
    return parser


def _print_failure(result: ProgramResult) -> None:
    print(f"Error: {result.error}", file=sys.stderr)
    if result.output.strip():
        print("--- salida de openFPGALoader ---", file=sys.stderr)
        print(result.output.rstrip(), file=sys.stderr)
    print("Orden ejecutada: " + " ".join(result.command), file=sys.stderr)


def _cmd_info(lab: Lab, args: argparse.Namespace) -> int:
    info = lab.validate(args.bitstream, args.board)
    board = lab.config.board(args.board)
    print(f"Diseño:     {info.design_name}")
    print(f"Parte:      {info.part}")
    print(f"Generado:   {info.date} {info.time} con Vivado {info.tool_version or '?'}")
    print(f"Datos:      {info.payload_length} bytes")
    print(f"Bitstream válido para la placa '{board.id}' ({board.model_name}).")
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


def _cmd_compile(lab: Lab, args: argparse.Namespace) -> int:
    path = Path(args.vhdl)
    if not path.is_file():
        print(f"Error: No existe el fichero '{path}'.", file=sys.stderr)
        return 1
    vhdl = path.read_text(encoding="utf-8", errors="replace")
    if args.program:
        result, info, programmed = lab.compile_and_program(vhdl, args.board, args.clock)
    else:
        result, info, programmed = lab.compile(vhdl, args.board, args.clock), None, None
    if not result.ok:
        print("Error: la compilación ha fallado.", file=sys.stderr)
        for line in result.errors:
            print(f"  {line}", file=sys.stderr)
        print(f"Registro completo: {result.log_path}", file=sys.stderr)
        return 1
    print(f"Compilado en {result.duration_s:.0f} s: {result.bitstream}")
    if args.output:
        shutil.copyfile(result.bitstream, args.output)
        print(f"Copiado a {args.output}")
    if programmed is not None:
        if not programmed.ok:
            _print_failure(programmed)
            return 1
        print(f"Diseño '{info.design_name}' cargado en {programmed.duration_s:.1f} s.")
        if args.snapshot:
            time.sleep(max(args.settle, 0.0))
            print(f"Foto guardada en {_write_snapshot(lab, args.board, args.snapshot)}")
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

    ftdi = list_ftdi_devices()
    configured = len(config.boards)
    if len(ftdi) >= configured:
        lines.append(
            ("OK", f"{len(ftdi)} placa(s) USB FTDI detectada(s); hay {configured} configurada(s).")
        )
    else:
        lines.append(
            (
                "AVISO",
                f"Se detectan {len(ftdi)} dispositivo(s) FTDI y hay {configured} placa(s) "
                "configurada(s): ¿placa apagada o cable desconectado?",
            )
        )
    for board in config.boards:
        if board.ftdi_serial and board.ftdi_serial not in {d.serial for d in ftdi}:
            lines.append(
                (
                    "AVISO",
                    f"La placa '{board.id}' espera el serie '{board.ftdi_serial}', "
                    "que no aparece entre los dispositivos conectados (mira `drl devices`).",
                )
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


def _cmd_boards(lab: Lab, args: argparse.Namespace) -> int:
    print("Placas configuradas:")
    for board in lab.config.boards:
        print(f"  {board.id}: {board.model_name}")
        print(f"      openFPGALoader -b {board.ofl_board}; FPGA {board.part_prefix}...")
        print(f"      FTDI serial: {board.ftdi_serial or '(sin indicar)'}")
        print(f"      cámara: {board.camera.device!r}")
    print("Modelos soportados:")
    for model in MODELS.values():
        extra = f" ({model.notes})" if model.notes else ""
        print(f"  {model.key}: {model.name}{extra}")
    return 0


def _cmd_devices(lab: Lab, args: argparse.Namespace) -> int:
    ftdi = list_ftdi_devices()
    print("Dispositivos USB de FTDI (JTAG de las placas):")
    if not ftdi:
        print("  ninguno detectado")
    for dev in ftdi:
        print(f"  {dev.vid_pid}  serie={dev.serial or '?'}  {dev.product}  (USB {dev.bus_path})")
    cameras = list_cameras()
    print("Cámaras (rutas estables):")
    if not cameras:
        print("  ninguna detectada en /dev/v4l/by-id")
    for path in cameras:
        print(f"  {path}")
    return 0


def _cmd_doctor(lab: Lab, args: argparse.Namespace) -> int:
    lines = _doctor_lines(lab.config)
    for status, text in lines:
        print(f"[{status}] {text}")
    return 1 if any(status == "FALTA" for status, _ in lines) else 0


_COMMANDS = {
    "info": _cmd_info,
    "detect": _cmd_detect,
    "program": _cmd_program,
    "compile": _cmd_compile,
    "snapshot": _cmd_snapshot,
    "boards": _cmd_boards,
    "devices": _cmd_devices,
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
