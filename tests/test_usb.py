from digitalremotelab.usb import list_cameras, list_ftdi_devices


def make_usb(root, name, vid, pid, product="", serial=""):
    d = root / name
    d.mkdir()
    (d / "idVendor").write_text(vid + "\n")
    (d / "idProduct").write_text(pid + "\n")
    if product:
        (d / "product").write_text(product + "\n")
    if serial:
        (d / "serial").write_text(serial + "\n")


def test_lists_only_ftdi_devices_with_serials(tmp_path):
    make_usb(tmp_path, "1-1", "0403", "6010", "Digilent USB Device", "210292AAAAAA")
    make_usb(tmp_path, "1-2", "046d", "085c", "C922 Pro Stream Webcam", "XYZ")
    make_usb(tmp_path, "1-3", "0403", "6010", "Digilent USB Device", "210292BBBBBB")
    (tmp_path / "usb1").mkdir()  # entrada sin idVendor: se ignora

    devices = list_ftdi_devices(tmp_path)

    assert [d.serial for d in devices] == ["210292AAAAAA", "210292BBBBBB"]
    assert devices[0].vid_pid == "0403:6010"
    assert devices[0].bus_path == "1-1"


def test_missing_sysfs_returns_empty(tmp_path):
    assert list_ftdi_devices(tmp_path / "nada") == []


def test_device_without_serial_is_listed_with_empty_serial(tmp_path):
    make_usb(tmp_path, "1-1", "0403", "6010")
    assert list_ftdi_devices(tmp_path)[0].serial == ""


def test_cameras_list_only_capture_nodes(tmp_path):
    for name in ("usb-Logi_C922-video-index0", "usb-Logi_C922-video-index1"):
        (tmp_path / name).touch()
    assert list_cameras(tmp_path) == [str(tmp_path / "usb-Logi_C922-video-index0")]
    assert list_cameras(tmp_path / "nada") == []
