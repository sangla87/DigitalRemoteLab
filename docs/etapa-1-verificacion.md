# Etapa 1: verificación con hardware real

Esta lista se ejecuta **en el servidor del laboratorio** (Ubuntu 22.04) con la Zybo Z7-10 y la
cámara conectadas. Los tests automáticos usan hardware simulado, así que esta es la prueba que
confirma que la carga por JTAG y la cámara funcionan de verdad.

## 0. Preparar la placa

- Conecta la Zybo por el micro-USB de programación (alimentación, JTAG y UART en un solo cable).
- Pon el jumper de modo de arranque en **JTAG** (evita que un arranque desde SD o QSPI
  reconfigure la FPGA) y el de alimentación en **USB**. En la Zybo Z7 son JP5 y JP6; confírmalo
  en el manual de referencia de Digilent.
- Coloca la cámara apuntando a los LEDs, con luz estable y sin reflejos.

## 1. Instalar dependencias del sistema

```bash
sudo apt update
sudo apt install -y git cmake g++ pkg-config usbutils v4l-utils \
    libftdi1-dev libhidapi-dev libudev-dev zlib1g-dev python3-venv python3-pip
```

`openFPGALoader` no viene empaquetado para Ubuntu 22.04: se compila desde su repositorio
(<https://github.com/trabucayre/openFPGALoader>).

```bash
git clone https://github.com/trabucayre/openFPGALoader.git
cd openFPGALoader && mkdir build && cd build
cmake .. && cmake --build . -j"$(nproc)"
sudo make install
```

## 2. Instalar el proyecto y los permisos

```bash
git clone https://github.com/sangla87/DigitalRemoteLab.git
cd DigitalRemoteLab && git checkout etapa-1
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[camera]"
cp config/lab.example.toml config/lab.toml
```

Permisos para usar el JTAG y la cámara sin `sudo` (desde la carpeta del proyecto):

```bash
sudo cp udev/99-zybo-jtag.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG plugdev,video "$USER"   # cierra sesión y vuelve a entrar
```

## 3. Identificar la placa y la cámara

```bash
lsusb | grep 0403:6010                          # la Zybo (FTDI FT2232H)
lsusb -v -d 0403:6010 2>/dev/null | grep iSerial   # número de serie de cada placa
ls -l /dev/v4l/by-id/                           # ruta estable de la cámara
```

Anota el número de serie y la ruta de la cámara en `config/lab.toml` (`ftdi_serial` y
`device`). Con una sola placa conectada, `ftdi_serial` puede omitirse.

## 4. Comprobaciones

| # | Comando | Resultado esperado |
|---|---|---|
| a | `drl doctor` | `[OK]` en openFPGALoader, FTDI, vídeo y OpenCV. Vivado puede salir como `[AVISO]` (solo hace falta en la etapa 2). |
| b | `drl info Contadores_Bitstream.bit` | Muestra el diseño, la parte `7z010clg400` y "Bitstream válido". |
| c | `openFPGALoader -b zybo_z7_10 --detect` | Detecta una FPGA Zynq 7010. |
| d | `drl detect` | Lo mismo, a través del proyecto. |
| e | `drl program Contadores_Bitstream.bit --snapshot foto.jpg` | "Diseño ... cargado en N s", la placa reacciona y `foto.jpg` muestra la placa. |
| f | `drl snapshot -o prueba.jpg` | Una imagen nítida y bien expuesta. |
| g | Con `ftdi_serial` falso en `lab.toml`, repite (e) | Debe **fallar** (no encuentra el dispositivo) en lugar de programar otra placa. |

Sobre (e): el `.bit` de ejemplo se llama `Contadores`, así que comprueba que los LEDs responden
como espera ese diseño.

La comprobación (g) valida que `--ftdi-serial` se combina bien con `-b zybo_z7_10`, que es lo que
usaremos para distinguir las cuatro placas en la etapa 4. Si `openFPGALoader` necesitara otro
argumento para tu cable, se añade en `extra_args` de la placa sin tocar código.

## 5. Qué enviar si algo falla

- La salida completa de `drl doctor` y de `openFPGALoader -b zybo_z7_10 --detect`.
- La salida de `drl program ...` (incluye la orden exacta que se ejecutó).
- La foto obtenida con `drl snapshot`.
- La versión de `openFPGALoader` que compilaste: `git -C openFPGALoader log -1 --oneline`.

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| `LIBUSB_ERROR_ACCESS` o "Permission denied" | Falta la regla udev, o el usuario no está en `plugdev` (reinicia la sesión). |
| No detecta ninguna FPGA | Placa sin alimentación o cable solo de carga; prueba otro cable. |
| `drl snapshot` falla al abrir la cámara | Ruta incorrecta o usuario fuera del grupo `video`. Usa `v4l2-ctl --list-devices`. |
| Imagen oscura o borrosa | Sube `warmup_frames` en `[boards.camera]` o revisa la iluminación. |
