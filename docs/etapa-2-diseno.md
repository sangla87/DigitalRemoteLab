# Etapa 2: diseño (VHDL de Digital → Vivado → placa, con web)

Estado: **propuesta para revisión**. No hay código de la etapa 2 hasta que se apruebe.

## 1. Alcance

Un alumno sube el VHDL exportado desde Digital (o un `.bit`), el servidor lo compila con Vivado
2022.2, lo carga en la placa y la web muestra el vídeo en vivo. Sin turnos (etapa 3) y con una sola
placa. Incluye:

- Validación del VHDL subido (contrato de puertos).
- Envoltorio `drl_top` con generador de reloj lento.
- `VivadoCompiler` (con `FakeCompiler` para tests).
- Backend FastAPI, vídeo MJPEG y una página HTML estática.

Fuera de alcance: turnos, varias placas, controles virtuales en tiempo real (etapa 3), acceso
externo por VPN o aula virtual.

## 2. Flujo

```
VHDL (Digital) ─► validar ─► envolver en drl_top ─► Vivado (batch) ─► .bit ─► drl program ─► vídeo
      └── rechazo con mensaje claro si no cumple el contrato ──┘   └── informe y log al alumno
```

Cada compilación usa un directorio propio `work/<id>/`, con límites de tiempo y de memoria.

## 3. Contrato del VHDL del alumno

Digital exporta una entidad `main` con puertos `std_logic` de 1 bit nombrados con las etiquetas del
circuito, más entidades auxiliares en el mismo fichero (p. ej. `DIG_CounterPreset`).

- Debe existir la entidad `main`; los puertos son `std_logic` de 1 bit.
- Nombres de entrada permitidos: `CLK`, `SW0..SW15`, `BTN0..BTN4` (según la placa).
- Nombres de salida permitidos: `LED0..LED15` (y, más adelante, segmentos/ánodos del display).
- Cualquier otro nombre se rechaza con un mensaje que lista los válidos.
- Solo se admiten las librerías `ieee.std_logic_1164`, `ieee.numeric_std`,
  `ieee.std_logic_unsigned` y `ieee.std_logic_arith`. Se rechaza todo lo demás (p. ej. `std.textio`,
  atributos de Xilinx, `library unisim`), para que el código del alumno no instancie primitivas de
  reloj ni haga cosas raras con los pines.
- Tamaño máximo del fichero: configurable (por defecto 1 MB).

El análisis se hace con un validador sencillo en Python (`portcheck.py`); no pretende ser un
parser VHDL completo: ante la duda, se deja pasar y Vivado dará el error.

## 4. Envoltorio `drl_top`

Es la entidad superior real. Instancia `main` del alumno, conecta los pines de la placa y es la
única que ve el reloj de 100 MHz. Así el alumno no genera relojes propios.

### Reloj del alumno

Un contador a 100 MHz activa un registro *toggle* que alimenta un `BUFG`: el reloj del alumno
sale limpio, sin *glitches*, y Vivado lo trata como reloj generado
(`create_generated_clock` en el XDC).

| Modo | Reloj entregado a `CLK` | Implementación |
|---|---|---|
| `1hz` | 1 Hz | alterna cada 50 000 000 ciclos |
| `10hz` | 10 Hz | alterna cada 5 000 000 ciclos |
| `manual` | un flanco por pulso | pulso del botón virtual, sincronizado y con detección de flanco |

En la etapa 2 el modo se fija **en compilación** con un `generic` (el alumno lo elige al subir el
VHDL). En la etapa 3 pasará a ser en ejecución, a través de los controles virtuales.

### Entradas

Los interruptores y botones pasan por sincronizadores de 2 flip-flops antes de llegar a `main`.

### Verificación

- Testbench en GHDL del generador de reloj (periodos y ausencia de *glitches*).
- Revisión del informe de temporización y de CDC de Vivado en el servidor.

## 5. Compilación con Vivado

- `VivadoCompiler` ejecuta `vivado -mode batch` con un script Tcl generado a partir de una plantilla
  y el XDC de la placa (`nexys4.xdc` o `nexys4ddr.xdc`); no se mezclan.
- `Compiler` es un `Protocol` con `FakeCompiler` para tests, igual que `Programmer` y `Camera`.
- Salida: `.bit` y log recortado (errores y avisos críticos) para mostrar al alumno.
- Seguridad: usuario sin privilegios, directorio aislado por compilación, `timeout` y límite de
  memoria, y sin red. El Tcl nunca incluye texto del alumno: solo se pasa el fichero VHDL como
  fuente.
- Cola de una compilación a la vez al principio.

## 6. Backend y web

FastAPI, sin base de datos en esta etapa.

| Endpoint | Función |
|---|---|
| `POST /api/jobs` | sube VHDL (con modo de reloj) o `.bit`; devuelve un `id` |
| `GET /api/jobs/{id}` | estado: validando, compilando, cargando, listo, error, con log |
| `GET /video` | flujo MJPEG |
| `GET /api/snapshot` | foto JPEG |
| `GET /` | página estática con subida, estado y vídeo |

El vídeo lo sirve un hilo `CameraStream` que lee la cámara de forma continua y reparte el último
fotograma, para que varios espectadores no abran la cámara varias veces.

## 7. Organización del código

```
src/digitalremotelab/
  portcheck.py     validación del VHDL
  wrapper.py       genera el proyecto con drl_top
  compiler.py      Compiler, FakeCompiler, VivadoCompiler
  web/             app FastAPI, CameraStream, estáticos
hdl/wrapper/
  drl_top.vhd, clock_gen.vhd, tb_clock_gen.vhd
```

Tests con hardware y Vivado simulados; los de GHDL se omiten si no está instalado.

## 6bis. Controles virtuales: UART en lugar de GPIO

El servidor **no tiene GPIO**, por lo que la idea inicial de conectar pines a un Pmod no sirve.
Propuesta para la etapa 3: usar la UART de la propia placa. El FT2232 de la Nexys expone un canal
JTAG (A) y un puerto serie (B), ambos por el mismo USB. `drl_top` incluiría un receptor UART que
actualiza registros de interruptores y botones virtuales (y el pulso manual).

Pendiente de confirmar antes de la etapa 3:

- Los nombres de pines UART según los XDC oficiales de Digilent (no se escribirán de memoria).
- Que el canal B se pueda abrir mientras `openFPGALoader` usa el canal A.
- Cómo se combinan los interruptores físicos con los virtuales (OR o solo virtuales).

## 8. Reparto del trabajo

- **Aquí (sin hardware):** `portcheck`, generador de `drl_top` y `clock_gen` con GHDL, backend y
  web con simulados, documentación.
- **En el servidor (Claude Code, ramas `hw/<tema>`):** `VivadoCompiler` real, informes de
  temporización/CDC, cámara en continuo, UART, prueba con la placa.

## 9. Decisiones tomadas

- Envoltorio con reloj lento para que el alumno no genere relojes: 1 Hz, 10 Hz y pulso manual.
- El modo de reloj en la etapa 2 se fija en compilación; en la 3, en ejecución.
- Vivado para la síntesis; `openFPGALoader` para cargar (solo SRAM).
- Controles virtuales por UART (a confirmar).

## 10. Preguntas abiertas

- ¿Se acepta que el alumno no pueda usar `CLK` de 100 MHz en ningún caso?
- ¿Límite razonable de tiempo de compilación (propuesta: 10 min) y de tamaño del VHDL?
- ¿Los displays de 7 segmentos entran en la etapa 2 o en la 3? Requieren multiplexación en el
  envoltorio si Digital exporta los segmentos como señales sueltas.
- Cámara: ¿configuración opcional en `lab.toml` (50 Hz, exposición, ganancia)?
