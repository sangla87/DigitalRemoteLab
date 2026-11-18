# DigitalRemoteLab

Laboratorio remoto para la asignatura de electrónica digital: permite usar FPGAs Digilent reales
como entorno de desarrollo de circuitos digitales sencillos. Mediante una webcam y un entorno web
se gestionarán los turnos y se visualizarán los cambios en las salidas en tiempo real.

Los alumnos diseñan sus circuitos con el simulador
[Digital](https://github.com/hneemann/Digital), que exporta VHDL, y los prueban en una placa real
sin instalar nada.

## Placas soportadas

La placa es configurable por modelo (`config/lab.toml`). Cada modelo define cómo se llama para
`openFPGALoader` y qué FPGA lleva, para rechazar bitstreams generados para otro dispositivo.

| Modelo (`model`) | Placa | FPGA | Estado |
|---|---|---|---|
| `nexys4ddr` | Digilent Nexys 4 DDR / Nexys A7-100T | Artix-7 XC7A100T | Pendiente de verificar con hardware (mismo FPGA y JTAG que la Nexys 4) |
| `nexys4` | Digilent Nexys 4 | Artix-7 XC7A100T | Verificada con hardware real (etapa 1) |
| `zybo_z7_10` | Digilent Zybo Z7-10 | Zynq-7010 | Probado solo con un `.bit` real y hardware simulado |

La Nexys 4 y la Nexys 4 DDR llevan la misma FPGA pero **tienen pines distintos**: sus `.xdc` no son
intercambiables. Una placa que no esté en el catálogo puede definirse en `lab.toml` con
`ofl_board` y `part_prefix`. La Basys 2 (Spartan-3E) no es viable: no la soporta Vivado, solo ISE.

## Estado del proyecto

| Etapa | Contenido | Estado |
|---|---|---|
| 0 | Decisiones de diseño | Hecha (ver más abajo) |
| 1 | Validación de `.bit`, carga con `openFPGALoader`, captura de cámara, CLI `drl`, placa configurable, diseño de prueba para la Nexys | Hecha. Verificada el 17/11/2026 con una Nexys 4 y una webcam reales: todas las [comprobaciones](docs/etapa-1-verificacion.md) correctas |
| 2 | Compilación en el servidor (Vivado en modo batch desde el VHDL de Digital) y backend web con vídeo en vivo | En diseño: ver [docs/etapa-2-diseno.md](docs/etapa-2-diseno.md) |
| 3 | Interruptores y pulsadores virtuales (por UART del FT2232, a confirmar), reloj del alumno en ejecución | Pendiente |
| 4 | Turnos, sesiones, tiempo máximo, reinicio de la placa al terminar y varias placas | Pendiente |
| 5 | Despliegue estable (servicio, HTTPS) y acceso restringido a alumnos (VPN o aula virtual) | Pendiente |

### Lo que hay hecho (etapa 1)

- `bitstream.py`: lee la cabecera de un `.bit` de Vivado y rechaza ficheros que no sean `.bit`,
  truncados, demasiado grandes o de otra FPGA distinta de la de la placa. Probado con un `.bit`
  real generado con Vivado 2020.2.
- `boards.py` y `config.py`: catálogo de modelos de placa y configuración TOML con varias placas,
  cada una con su modelo, su número de serie FTDI y su cámara.
- `programmer.py`: carga el `.bit` en la SRAM de la FPGA ejecutando `openFPGALoader` (sin shell),
  con tiempo máximo, captura de la salida y selección de placa por número de serie.
- `camera.py`: captura un JPEG de la webcam con OpenCV (V4L2), descartando los primeros
  fotogramas para que la cámara ajuste la exposición.
- `usb.py`: lista las placas USB con su número de serie y las cámaras, sin privilegios.
- `lab.py`: fachada que valida, programa y fotografía una placa. La reutilizará el backend web.
- `cli.py`: comando `drl` (`info`, `detect`, `program`, `snapshot`, `boards`, `devices`, `doctor`).
- `hdl/test_board/` y `scripts/build_test_bitstream.tcl`: diseño de prueba (contador en los LEDs
  e interruptores reflejados) con banco de pruebas, y script para compilarlo con Vivado en modo
  batch para la Nexys 4 o la Nexys 4 DDR. Los pines proceden de los XDC oficiales de Digilent.
- 76 tests con placa y cámara simuladas, más la simulación del banco de pruebas en GHDL si está
  instalado (uno solo se ejecuta si se aporta un `.bit` real). Los tests no leen el `lab.toml`
  del servidor.
- Verificación con hardware real (Nexys 4, openFPGALoader v1.2.0, Vivado 2022.2): carga en SRAM
  en unos 5 s, el contador y los interruptores se ven en la foto, un número de serie FTDI falso
  hace fallar la carga sin tocar otras placas y se rechaza un `.bit` de la Zybo.

### Lo que hay hecho (etapa 2, sin web todavía)

- `portcheck.py`: valida el VHDL de Digital (entidad `main`, puertos y librerías permitidos).
- `hdl/wrapper/clock_gen.vhd` y `wrapper.py`: envoltorio `drl_top` con reloj de 1 kHz, 1 Hz, 10 Hz o
  manual, entradas sincronizadas, y segmentos y ánodos con polaridad corregida.
- `pins.py`: pines de la Nexys 4 y la Nexys 4 DDR verificados contra los XDC maestros de Digilent.
- `compiler.py` y `drl compile`: VHDL de Digital a `.bit` con Vivado en modo batch (probado solo
  con un Vivado simulado; falta la verificación con el real, ver
  [docs/etapa-2-verificacion.md](docs/etapa-2-verificacion.md)).

### Pendiente

- Verificar también la Nexys 4 DDR con hardware real cuando esté disponible (la etapa 1 se ha
  verificado solo con la Nexys 4).
- Etapa 2 ([diseño](docs/etapa-2-diseno.md)): verificar `drl compile` con Vivado real, y escribir el
  backend (FastAPI) con vídeo MJPEG y la página de subida.
- Acceso de los alumnos sin VPN ni acceso directo al servidor (proxy inverso o máquina
  intermedia, y LTI 1.3 desde el aula virtual): a consultar con informática.
- Etapas 3 a 5 (ver tabla) y las decisiones abiertas (ver "Decisiones de diseño").
- Estudiar, como etapa opcional y aparte, un flujo abierto (Yosys + nextpnr-xilinx, vía openXC7)
  para Artix-7 que evite depender de Vivado.

## Cómo funcionará

```
Alumno (navegador)
   │   VHDL de Digital  (o un .bit ya generado)
   ▼
Servidor web ── turnos ── compilación Vivado ──► .bit
   │                                              │
   │  controles virtuales (WebSocket)             ▼
   ▼                                      openFPGALoader (JTAG)
UART (FT2232, canal B) ──► receptor en la placa ◄── Placa FPGA
                                                  ▲
Vídeo en vivo (MJPEG) ◄───────── webcam ──────────┘
```

## Requisitos

- Servidor con Ubuntu 22.04 y Python 3.10 o superior.
- [openFPGALoader](https://github.com/trabucayre/openFPGALoader) (se compila desde su repositorio).
- Vivado 2022.2 en `/tools/Xilinx/Vivado/2022.2` (para generar `.bit`; la etapa 1 solo carga).
- Una placa de la tabla de arriba y una webcam USB compatible con V4L2 (UVC).
- Opcional: GHDL, para ejecutar la simulación del diseño de prueba en los tests.

## Instalación

La guía completa, con la preparación de la placa, los permisos USB y la compilación de
`openFPGALoader`, está en [docs/etapa-1-verificacion.md](docs/etapa-1-verificacion.md). Resumen:

```bash
git clone https://github.com/sangla87/DigitalRemoteLab.git
cd DigitalRemoteLab
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[camera]"          # sin la cámara: pip install -e .
cp config/lab.example.toml config/lab.toml
```

## Configuración

Copia `config/lab.example.toml` a `config/lab.toml` (no se sube a git). La ruta también puede
indicarse con `drl -c RUTA` o con la variable `DRL_CONFIG`. Lo más importante:

- `model` en `[lab]` (y opcionalmente por placa): `nexys4ddr`, `nexys4` o `zybo_z7_10`.
- `ftdi_serial` de cada placa: necesario cuando hay varias conectadas. `drl devices` lo muestra.
- `device` de la cámara: mejor una ruta estable de `/dev/v4l/by-id/` que un índice.
- `vivado_dir`: ruta de Vivado (por defecto `/tools/Xilinx/Vivado/2022.2`).

## Uso

```bash
drl doctor                                   # comprueba el servidor
drl devices                                  # placas USB (con su nº de serie) y cámaras
drl boards                                   # placas configuradas y modelos soportados
drl info test_board.bit                      # valida un .bit contra la placa y muestra su cabecera
drl detect                                   # detecta la FPGA conectada
drl program test_board.bit                   # carga el .bit en la placa
drl program test_board.bit --snapshot f.jpg  # lo carga y guarda una foto
drl snapshot -o foto.jpg                     # solo la foto
drl program test_board.bit -b nexys2         # elige la placa configurada con id nexys2
```

Para generar un `.bit` de prueba para la Nexys (necesita Vivado):

```bash
source /tools/Xilinx/Vivado/2022.2/settings64.sh
vivado -mode batch -nojournal -nolog -source scripts/build_test_bitstream.tcl -tclargs nexys4ddr
drl program build/nexys4ddr/test_board.bit --snapshot foto.jpg
```

Con `--fake` (por ejemplo `drl --fake program x.bit`) se usan una placa y una cámara simuladas,
útil para desarrollar sin hardware. `drl` devuelve 0 si todo va bien y 1 si hay un error, con un
mensaje claro en español.

## Desarrollo

```bash
pip install -e ".[dev,camera]"
pytest                    # tests con hardware simulado
ruff check . && ruff format .
DRL_SAMPLE_BIT=ruta/al/Contadores.bit pytest   # incluye la prueba con un .bit real
```

Cada etapa se desarrolla en una rama `etapa-N` y se integra en `main` mediante un pull request.
El hardware real siempre va detrás de interfaces (`Programmer`, `Camera`) con versiones
simuladas, de modo que la lógica de turnos, la API y la web se puedan probar sin placa. El trabajo
con la placa real desde el servidor, con Claude Code, está explicado en
[docs/trabajar-con-claude-code.md](docs/trabajar-con-claude-code.md) y sus reglas en
[CLAUDE.md](CLAUDE.md).

```
src/digitalremotelab/   código del paquete
tests/                  tests automáticos
config/                 plantilla de configuración
hdl/test_board/         diseño de prueba, banco de pruebas y restricciones por placa
scripts/                scripts de Vivado
udev/                   regla udev para el JTAG de las placas Digilent (FTDI)
docs/                   documentación y listas de verificación
```

## Decisiones de diseño

- **Quién compila.** Los alumnos exportan VHDL desde Digital y el servidor genera el `.bit` con
  Vivado (más rápido que MyApps y sin instalar nada). La subida directa de un `.bit` se mantiene
  como vía alternativa.
- **Placa.** Configurable por modelo. Se prevé usar la Nexys 4 (Artix-7 100T), que además trae
  display de 7 segmentos de 8 dígitos, 16 LEDs y 16 interruptores. Se descarta la Basys 2
  (Spartan-3E: sin soporte de Vivado ni de herramientas abiertas).
- **Cargador.** `openFPGALoader` en lugar de Vivado Lab: ligero y sin licencia. La etapa 1 sirve
  para confirmar que funciona bien con la placa elegida.
- **Cámara.** Webcam USB (UVC) vía OpenCV; vídeo MJPEG en la web por su sencillez.
- **Acceso.** Inicialmente solo desde la red de la universidad. Más adelante, VPN o aula
  virtual, para lo que se necesitará la colaboración del servicio de informática.
- **Herramientas abiertas.** Yosys + nextpnr-xilinx (openXC7) cubren Artix-7, pero son
  experimentales: se valorarán como etapa aparte, tras tener funcionando el flujo con Vivado.

### Decisiones abiertas

- **Convención de nombres de puertos.** Digital exporta una entidad `main` con los puertos que
  tenga el circuito (en el ejemplo: `SW0`, `SW1`, `SW2`, `CLK`, `LED0`..`LED3`). Un `.xdc`
  plantilla asignará pines por nombre (`SW0..15`, `BTN0..4`, `LED0..15`, `CLK`...). Hay que fijar la
  lista y documentarla para los alumnos.
- **Reloj (decidido).** El oscilador va a 100 MHz: un contador conectado directamente a `CLK`
  parecería congelado en la cámara. Un envoltorio (`drl_top`) entrega al diseño del alumno un reloj
  sin *glitches* de 1 kHz (para multiplexar displays), 1 Hz, 10 Hz o pulsos manuales desde un botón virtual; el alumno no genera
  relojes. Detalle en [docs/etapa-2-diseno.md](docs/etapa-2-diseno.md).
- **Controles virtuales.** Los pulsadores e interruptores físicos de la placa van cableados a la
  FPGA, por lo que los virtuales actuarán a través de la UART de la placa (el servidor no tiene GPIO): un
  receptor en el envoltorio actualiza interruptores y botones virtuales. Pendiente de confirmar.
- **Seguridad de la compilación.** Vivado se ejecutará sobre código de los alumnos: usuario sin
  privilegios, directorio de trabajo aislado y límites de tiempo y memoria.

## Licencia

GNU GPL v3. Consulta el fichero [LICENSE](LICENSE).
