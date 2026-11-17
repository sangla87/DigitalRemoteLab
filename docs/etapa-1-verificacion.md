# Etapa 1: verificación con hardware real (Nexys 4)

Esta lista se ejecuta **en el servidor del laboratorio** (Ubuntu 22.04) con la placa y la cámara
conectadas. Los tests automáticos usan hardware simulado, así que esta es la prueba que confirma
que la carga por JTAG y la cámara funcionan de verdad. Puedes hacerla a mano o pedirle a Claude
Code que la ejecute (ver [trabajar-con-claude-code.md](trabajar-con-claude-code.md)).

Placas soportadas: `nexys4`, `nexys4ddr` (Nexys 4 DDR / Nexys A7-100T) y `zybo_z7_10`. La
Nexys 4 y la Nexys 4 DDR llevan la misma FPGA pero **tienen pines distintos**: comprueba cuál
tienes (el modelo viene serigrafiado en la placa; la DDR lleva memoria DDR2 en lugar de
CellularRAM).

## 0. Preparar la placa

- Conecta el micro-USB de programación de la placa al servidor (da alimentación, JTAG y UART).
- Enciende la placa con su interruptor de alimentación.
- Pon el jumper de modo de configuración en **JTAG**, para que ningún arranque desde flash, USB o
  microSD sustituya al diseño cargado (confirma el jumper exacto en el manual de referencia de
  Digilent de tu modelo).
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

Comprueba que tu placa está en su lista de placas soportadas:

```bash
openFPGALoader --list-boards | grep -i nexys
```

Deberían aparecer `nexys_a7_50` y `nexys_a7_100` (no hay entradas `nexys4` ni `nexys4ddr`). Tanto
la Nexys 4 DDR como la Nexys 4 usan `nexys_a7_100`: llevan la misma FPGA (XC7A100T) y el mismo
JTAG, y solo se carga en SRAM. Si no aparece ni siquiera `nexys_a7_100`, la versión de
`openFPGALoader` es demasiado antigua: anota la salida de `openFPGALoader -V` y vuelve a
compilarla desde el repositorio (no la instales con `apt`).

## 2. Instalar el proyecto y los permisos

```bash
git clone https://github.com/sangla87/DigitalRemoteLab.git
cd DigitalRemoteLab && git checkout etapa-1
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[camera,dev]"
cp config/lab.example.toml config/lab.toml
```

Permisos para usar el JTAG y la cámara sin `sudo` (desde la carpeta del proyecto):

```bash
sudo cp udev/99-zybo-jtag.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG plugdev,video "$USER"   # cierra sesión y vuelve a entrar
```

(La regla se llama `zybo` por historia, pero vale para cualquier placa Digilent con el FTDI
`0403:6010`, que es el caso de la Zybo y de la Nexys.)

## 3. Identificar la placa y la cámara

```bash
drl devices
```

Muestra los dispositivos FTDI conectados con su **número de serie** y las rutas estables de las
cámaras. Edita `config/lab.toml`:

- `model` en `[lab]`: `nexys4` o `nexys4ddr` (el de arriba es `nexys4ddr`).
- `ftdi_serial` de la placa (con una sola placa conectada puede omitirse).
- `device` de la cámara: la ruta `/dev/v4l/by-id/...-video-index0`.

Comprueba la configuración con `drl boards`.

## 4. Generar un .bit de prueba para la placa

El `.bit` de la Zybo **no sirve** en la Nexys: la FPGA es otra y `drl` lo rechazará. En el
repositorio hay un diseño de prueba (`hdl/test_board`) que se compila con Vivado en modo batch:

```bash
source /tools/Xilinx/Vivado/2022.2/settings64.sh
vivado -mode batch -nojournal -nolog -source scripts/build_test_bitstream.tcl \
    -tclargs nexys4ddr            # o: nexys4
```

Genera `build/nexys4ddr/test_board.bit`. El diseño muestra en `LED[7:0]` un contador de 8 bits que
avanza unas 3 veces por segundo, y en `LED[15:8]` el valor de los interruptores `SW[7:0]`.

## 5. Comprobaciones

| # | Comando | Resultado esperado |
|---|---|---|
| a | `drl doctor` | `[OK]` en openFPGALoader, placa USB, vídeo y OpenCV. Vivado debe aparecer `[OK]`. |
| b | `drl boards` | La placa configurada, con su modelo, `-b` de openFPGALoader y número de serie. |
| c | `drl info build/nexys4ddr/test_board.bit` | Diseño `test_board`, parte `7a100t...` y "Bitstream válido". |
| d | `openFPGALoader -b nexys_a7_100 --detect` | Detecta una FPGA `xc7a100t`. |
| e | `drl detect` | Lo mismo, a través del proyecto. |
| f | `drl program build/nexys4ddr/test_board.bit --snapshot foto.jpg` | "Diseño 'test_board' cargado en N s"; los LEDs inferiores cuentan en binario y `foto.jpg` los muestra. |
| g | Mueve los interruptores SW0..SW7 y repite `drl snapshot -o sw.jpg` | Los LED[15:8] de la foto reflejan los interruptores. |
| h | Con un `ftdi_serial` falso en `lab.toml`, repite (f) | Debe **fallar** (no encuentra el dispositivo) en lugar de programar otra placa. |
| i | `drl info` con el `.bit` de una Zybo (`Contadores_Bitstream.bit`) | Debe **rechazarlo**: es para `7z010`, la placa usa `7a100t`. |

Si no tienes a mano el `.bit` de una Zybo para (i), sirve cualquier `.bit` generado para la
parte `xc7z010clg400-1` (por ejemplo, el diseño de prueba sintetizado para esa parte en un
directorio de `build/`): solo se usa con `drl info` y nunca se carga en la placa.

La comprobación (h) valida que `--ftdi-serial` se combina bien con `-b <placa>`, que es lo que
usaremos para distinguir varias placas en la etapa 4. Si `openFPGALoader` necesitara otro
argumento para tu cable, se añade en `extra_args` de la placa sin tocar código.

## 6. Qué enviar si algo falla

- La salida completa de `drl doctor`, `drl devices` y `openFPGALoader -b <placa> --detect`.
- La salida de `drl program ...` (incluye la orden exacta que se ejecutó).
- La foto obtenida con `drl snapshot`.
- La versión de `openFPGALoader` que compilaste: `git -C openFPGALoader log -1 --oneline`.

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| `LIBUSB_ERROR_ACCESS` o "Permission denied" | Falta la regla udev, o el usuario no está en `plugdev` (reinicia la sesión). |
| No detecta ninguna FPGA | Placa apagada o cable solo de carga; prueba otro cable y el interruptor de la placa. |
| `drl snapshot` falla al abrir la cámara | Ruta incorrecta o usuario fuera del grupo `video`. Usa `drl devices` o `v4l2-ctl --list-devices`. |
| Avisos `Corrupt JPEG data: N extraneous bytes...` al hacer una foto | Los emite libjpeg con algunas webcams (vistos con una Logitech `046d:0825`); son inofensivos si la foto sale bien. |
| Imagen oscura o borrosa | Sube `warmup_frames` en `[boards.camera]` o revisa la iluminación. |
| El diseño carga pero no se mueve nada | Pines de otra placa: usa `nexys4.xdc` en la Nexys 4 y `nexys4ddr.xdc` en la 4 DDR. |
| Vivado falla al generar el `.bit` | Guarda la salida de la ventana (informe de timing, DRC) y envíala. |
