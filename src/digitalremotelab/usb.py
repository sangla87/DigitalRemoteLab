"""Descubrimiento de dispositivos USB (JTAG de las placas) y cámaras.

Lee /sys/bus/usb/devices, así que no necesita privilegios ni `lsusb -v`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

FTDI_VENDOR = "0403"
SYSFS_USB = Path("/sys/bus/usb/devices")
V4L_BY_ID = Path("/dev/v4l/by-id")


@dataclass(frozen=True)
class UsbDevice:
    bus_path: str  # p. ej. "1-4.2"
    vid_pid: str  # p. ej. "0403:6010"
    product: str
    serial: str


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def list_ftdi_devices(sysfs: Path = SYSFS_USB) -> list[UsbDevice]:
    """Dispositivos USB de FTDI (el JTAG de las placas Digilent), con su número de serie."""
    devices = []
    if not sysfs.is_dir():
        return devices
    for entry in sorted(sysfs.iterdir()):
        if _read(entry / "idVendor") != FTDI_VENDOR:
            continue
        devices.append(
            UsbDevice(
                bus_path=entry.name,
                vid_pid=f"{FTDI_VENDOR}:{_read(entry / 'idProduct')}",
                product=_read(entry / "product"),
                serial=_read(entry / "serial"),
            )
        )
    return devices


def list_cameras(by_id: Path = V4L_BY_ID) -> list[str]:
    """Rutas estables de cámara (solo el nodo de captura 'index0' de cada una)."""
    if not by_id.is_dir():
        return []
    return sorted(str(p) for p in by_id.iterdir() if p.name.endswith("-index0"))
