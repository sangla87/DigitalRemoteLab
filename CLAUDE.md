# DigitalRemoteLab: instrucciones para Claude Code

Laboratorio remoto de FPGAs Digilent (Nexys 4, Nexys 4 DDR, Zybo Z7-10) para una asignatura de
electrónica digital de la URJC. Los alumnos diseñan con [Digital](https://github.com/hneemann/Digital),
exportan VHDL y probarán sus circuitos en una placa real vista por cámara. Trabaja en español.

## Estado

Ver el README ("Estado del proyecto"). Etapa 1 (cargar un `.bit` y fotografiar la placa, sin web)
escrita y probada con hardware simulado; falta verificarla con hardware real.

## Comandos

```bash
pip install -e ".[dev,camera]"
pytest                       # tests con hardware simulado (deben pasar siempre)
ruff check . && ruff format .
drl doctor | drl devices | drl boards | drl info X.bit | drl program X.bit --snapshot f.jpg
```

## Mapa del código (`src/digitalremotelab/`)

- `boards.py`: catálogo de modelos de placa (nombre en openFPGALoader, FPGA esperada).
- `config.py`: `lab.toml`; cada placa tiene `model`, número de serie del FTDI y cámara.
- `bitstream.py`: valida la cabecera de un `.bit` y que la FPGA coincide con la de la placa.
- `programmer.py`: ejecuta `openFPGALoader` (`Programmer`); `FakeProgrammer` para tests.
- `camera.py`: captura JPEG con OpenCV (`Camera`); `FakeCamera` para tests.
- `usb.py`: lista placas FTDI (con su serie) y cámaras leyendo sysfs.
- `lab.py`: fachada que usarán la CLI y el futuro backend web.
- `hdl/test_board/`: diseño de prueba (VHDL, XDC por placa) y `scripts/build_test_bitstream.tcl`.

## Reglas

- **Hardware siempre detrás de interfaces** con versión simulada. Si un fallo aparece solo con
  hardware real, arréglalo y añade un test que lo reproduzca con los simulados.
- **Solo SRAM.** Carga con `openFPGALoader -m`. No escribas nunca en la flash de la placa (`-f`) ni
  la borres. Una placa de un alumno nunca debe quedar con un diseño persistente.
- **No toques el sistema más allá de lo que pide `docs/etapa-1-verificacion.md`** (paquetes, regla
  udev, grupos). Pide confirmación antes de cualquier otro `sudo`.
- **Vivado** está en `/tools/Xilinx/Vivado/2022.2` (`source .../settings64.sh`). Se ejecuta siempre
  en modo batch y con un directorio de trabajo propio (`build/`).
- **No subas a git** `lab.toml`, ficheros `.bit`, fotos ni nada de `build/` (ya están en
  `.gitignore`). Nunca pegues credenciales ni números de serie reales en commits o issues.
- La Nexys 4 y la Nexys 4 DDR tienen **pines distintos**: no mezcles sus `.xdc`. Los pines de
  `hdl/test_board/*.xdc` proceden de los XDC oficiales de Digilent; si añades otros, verifícalos
  contra el XDC maestro de Digilent y no los escribas de memoria.
- Documenta en el README lo que quede hecho y lo pendiente, en español.

## Flujo de ramas

- La etapa vigente vive en una rama `etapa-N` con su pull request.
- Los arreglos hechos desde el servidor con hardware real van en una rama `hw/<tema>` creada desde
  la etapa vigente, con commits pequeños, y se abre un pull request hacia `etapa-N`.
- No hagas push directo a `main` ni a `etapa-N` si no te lo piden: dos sesiones editando la misma
  rama a la vez generan conflictos.
