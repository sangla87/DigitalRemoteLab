# DigitalRemoteLab

Laboratorio remoto para la asignatura de electrónica digital: permite usar FPGAs Zybo Z7-10
reales como entorno de desarrollo de circuitos digitales sencillos. Mediante una webcam y un
entorno web se gestionarán los turnos y se visualizarán los cambios en las salidas en tiempo real.

Los alumnos diseñan sus circuitos con el simulador
[Digital](https://github.com/hneemann/Digital), que exporta VHDL, y los prueban en una placa real
sin instalar nada.

## Estado del proyecto

| Etapa | Contenido | Estado |
|---|---|---|
| 0 | Decisiones de diseño | Hecha (ver más abajo) |
| 1 | Validación de `.bit`, carga con `openFPGALoader`, captura de cámara y CLI `drl` | Código y tests listos (hardware simulado). **Pendiente de verificar con la Zybo y la cámara reales**: [lista de comprobaciones](docs/etapa-1-verificacion.md) |
| 2 | Compilación en el servidor (Vivado en modo batch desde el VHDL de Digital) y backend web con vídeo en vivo | Pendiente |
| 3 | Interruptores y pulsadores virtuales (GPIO a Pmod), `.xdc` plantilla, solución para el reloj | Pendiente |
| 4 | Turnos, sesiones, tiempo máximo, reinicio de la placa al terminar y las cuatro placas | Pendiente |
| 5 | Despliegue estable (servicio, HTTPS) y acceso restringido a alumnos (VPN o aula virtual) | Pendiente |

### Lo que hay hecho (etapa 1)

- `bitstream.py`: lee la cabecera de un `.bit` de Vivado y rechaza ficheros que no sean `.bit`,
  truncados, demasiado grandes o de otra FPGA (la parte debe ser `7z010`). Probado también con un
  `.bit` real generado con Vivado 2020.2.
- `programmer.py`: carga el `.bit` en la SRAM de la FPGA ejecutando `openFPGALoader` (sin shell),
  con tiempo máximo, captura de la salida y selección de placa por número de serie del FTDI.
- `camera.py`: captura un JPEG de la webcam con OpenCV (V4L2), descartando los primeros
  fotogramas para que la cámara ajuste la exposición.
- `lab.py`: fachada que valida, programa y fotografía una placa. La reutilizará el backend web.
- `cli.py`: comando `drl` (`info`, `detect`, `program`, `snapshot`, `doctor`).
- `config.py`: configuración TOML con varias placas, cada una con su cámara.
- 50 tests con placa y cámara simuladas (uno solo se ejecuta si se aporta un `.bit` real).

### Pendiente

- Verificar la etapa 1 con hardware real y ajustar lo que haga falta.
- Etapa 2: compilar el VHDL en el servidor con Vivado 2022.2
  (`/tools/Xilinx/Vivado/2022.2`), backend (FastAPI) y vídeo MJPEG.
- Etapas 3 a 5 (ver tabla).
- Decisiones abiertas (ver "Decisiones de diseño").

## Cómo funcionará

```
Alumno (navegador)
   │   VHDL de Digital  (o un .bit ya generado)
   ▼
Servidor web ── turnos ── compilación Vivado ──► .bit
   │                                              │
   │  controles virtuales (WebSocket)             ▼
   ▼                                      openFPGALoader (JTAG)
GPIO ──► pines Pmod de la Zybo ◄───────────── Zybo Z7-10 (×4)
                                                  ▲
Vídeo en vivo (MJPEG) ◄───────── webcam ──────────┘
```

## Requisitos

- Servidor con Ubuntu 22.04 y Python 3.10 o superior.
- [openFPGALoader](https://github.com/trabucayre/openFPGALoader) (se compila desde su repositorio).
- Vivado 2022.2 en `/tools/Xilinx/Vivado/2022.2` (solo desde la etapa 2).
- Placa Zybo Z7-10 y una webcam USB compatible con V4L2 (UVC).

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

- `ftdi_serial` de cada placa: necesario cuando hay varias conectadas.
- `device` de la cámara: mejor una ruta estable de `/dev/v4l/by-id/` que un índice.
- `vivado_dir`: ruta de Vivado (por defecto `/tools/Xilinx/Vivado/2022.2`).

## Uso

```bash
drl doctor                                   # comprueba el servidor
drl info Contadores.bit                      # valida un .bit y muestra su cabecera
drl detect                                   # detecta la FPGA conectada
drl program Contadores.bit                   # carga el .bit en la placa
drl program Contadores.bit --snapshot f.jpg  # lo carga y guarda una foto
drl snapshot -o foto.jpg                     # solo la foto
drl program Contadores.bit -b zybo2          # elige la placa configurada como zybo2
```

Con `--fake` (por ejemplo `drl --fake program Contadores.bit`) se usan una placa y una cámara
simuladas, útil para desarrollar sin hardware. `drl` devuelve 0 si todo va bien y 1 si hay un
error, con un mensaje claro en español.

## Desarrollo

```bash
pip install -e ".[dev,camera]"
pytest                    # tests con hardware simulado
ruff check . && ruff format .
DRL_SAMPLE_BIT=ruta/al/Contadores.bit pytest   # incluye la prueba con un .bit real
```

Cada etapa se desarrolla en una rama `etapa-N` y se integra en `main` mediante un pull request.
El hardware real siempre va detrás de interfaces (`Programmer`, `Camera`) con versiones
simuladas, de modo que la lógica de turnos, la API y la web se puedan probar sin placa.

```
src/digitalremotelab/   código del paquete
tests/                  tests automáticos
config/                 plantilla de configuración
udev/                   regla udev para el JTAG de la Zybo
docs/                   documentación y listas de verificación
```

## Decisiones de diseño

- **Quién compila.** Los alumnos exportan VHDL desde Digital y el servidor genera el `.bit` con
  Vivado (más rápido que MyApps y sin instalar nada). La subida directa de un `.bit` se mantiene
  como vía alternativa.
- **Cargador.** `openFPGALoader` en lugar de Vivado Lab: ligero y sin licencia. La etapa 1 sirve
  para confirmar que funciona bien con la Zybo Z7-10.
- **Cámara.** Webcam USB (UVC) vía OpenCV; vídeo MJPEG en la web por su sencillez.
- **Acceso.** Inicialmente solo desde la red de la universidad. Más adelante, VPN o aula
  virtual, para lo que se necesitará la colaboración del servicio de informática.

### Decisiones abiertas

- **Convención de nombres de puertos.** Digital exporta una entidad `main` con los puertos que
  tenga el circuito (en el ejemplo: `SW0`, `SW1`, `SW2`, `CLK`, `LED0`..`LED3`). Un `.xdc`
  plantilla asignará pines por nombre (`SW0..3`, `BTN0..3`, `LED0..3`, `CLK`...). Hay que fijar la
  lista y documentarla para los alumnos.
- **Reloj.** El oscilador de la Zybo va a 125 MHz: un contador conectado directamente a `CLK`
  parecería congelado en la cámara. Opciones: pulsos de reloj manuales desde un botón virtual,
  un reloj dividido (1 o 2 Hz) en un envoltorio, o un selector entre ambos.
- **Displays de 7 segmentos.** La Zybo Z7-10 no los incluye; harían falta Pmods.
- **Controles virtuales.** Los pulsadores físicos de la placa van cableados a la FPGA, por lo que
  los virtuales actuarán a través de GPIO del servidor conectados a pines Pmod.
- **Seguridad de la compilación.** Vivado se ejecutará sobre código de los alumnos: usuario sin
  privilegios, directorio de trabajo aislado y límites de tiempo y memoria.

## Licencia

GNU GPL v3. Consulta el fichero [LICENSE](LICENSE).
