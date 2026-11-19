# Etapa 2: verificación de la compilación en el servidor (Vivado real)

Los tests automáticos usan un «vivado» falso. Esta lista es la que confirma que `VivadoCompiler`
funciona con Vivado 2022.2 de verdad. Se hace en el servidor, en una rama `hw/compilador` creada
desde `etapa-2`, con commits pequeños (ver [trabajar-con-claude-code.md](trabajar-con-claude-code.md)).
Config: `config/lab.toml` con la Nexys 4 (`model = "nexys4"`) y, opcionalmente,
`work_dir = "work"` y `compile_timeout_s = 900`.

| # | Comando | Resultado esperado |
|---|---|---|
| a | `drl doctor` | Vivado `[OK]`. |
| b | `drl compile examples/contador.vhd --clock 1hz -o build/contador.bit` | «Compilado en N s». Confirma que `bin/vivado` funciona **sin** `source settings64.sh` (entorno reducido). Si falla por eso, el arreglo es pasar a `VivadoCompiler` las variables que haga falta, no relajar el entorno entero. |
| c | `drl info build/contador.bit` | Bitstream válido para la placa (`7a100t...`). |
| d | `drl compile examples/contador.vhd --clock 1hz --program --snapshot foto.jpg` | Carga el diseño. Con SW0 arriba, LED0..LED3 cuentan a 1 Hz; SW0 abajo los congela. |
| e | Repite (d) con `--clock 10hz`, `--clock 1khz` y `--clock manual` | 10 Hz se ve como cuenta rápida; 1 kHz como luz casi fija; manual solo avanza al pulsar BTNC (botón físico). |
| f | Mira `work/<id>/vivado.log`, `timing.rpt` y `clocks.rpt` | Anota los avisos de reloj: el reloj lento sale de un registro y de momento no tiene `create_generated_clock`. Si Vivado se queja de temporización sin restringir o de cruces de dominio, propón la restricción **verificada** (nombre real de la celda en la netlist) en un commit aparte. |
| g | `drl compile` de un VHDL con un puerto no permitido (cambia `LED3` por `LEDX`) | Rechazo inmediato con mensaje en español; no se crea carpeta en `work/` y Vivado no se ejecuta. |
| h | Un VHDL con un bucle combinacional (p. ej. `LED0 <= not LED0_i; LED0_i <= LED0;` mediante una señal) | Fallo de Vivado con líneas `ERROR:` legibles en la salida de `drl`, sin traza de Python. |
| i | Con `compile_timeout_s = 5` | «La compilación superó el tiempo máximo» y no quedan procesos `vivado` ni `java` huérfanos (`pgrep -a vivado`). |
| j | Dos compilaciones seguidas | Cada una en su carpeta; el `HOME` de Vivado es `work/<id>/home` (no se toca `~/.Xilinx`). |

## Web (`drl serve`)

Instala con `pip install -e ".[web,camera,dev]"`. Arranca `drl serve` en el servidor y entra por un
túnel SSH (`ssh -L 8000:127.0.0.1:8000 servidor`), o desde X2Go en `http://127.0.0.1:8000`.

| # | Prueba | Resultado esperado |
|---|---|---|
| k | Abre la página | Se ve el vídeo de la cámara real, fluido y sin retraso de varios segundos. Si hay mucho retraso, anota fps y latencia: `OpenCVCamera(keep_open=True)` pide un búfer de 1 fotograma, pero no todas las cámaras lo respetan. |
| l | Sube `examples/contador.vhd` con reloj `1hz` desde el navegador | Estados «Compilando», «Cargando» y «Listo»; los LED cuentan a 1 Hz y se ven en el vídeo. |
| m | Sube un `.bit` de la Zybo | Rechazo inmediato con mensaje de FPGA incorrecta; la placa no se toca. |
| n | Sube un VHDL con un puerto no permitido | Lista de problemas en español, sin cola ni Vivado. |
| o | Sube dos diseños seguidos (el segundo mientras compila el primero) | El segundo queda «En cola, posición 1» y se carga al terminar el primero. |
| p | Mientras carga `openFPGALoader`, el vídeo sigue | La cámara no se corta al programar (son dispositivos distintos). |
| q | Cierra la pestaña de vídeo y mira `top` | El servidor no consume CPU de más sin espectadores (el hilo de la cámara sí sigue leyendo; si pesa, hay que pararlo sin espectadores). |

## Pendiente de resolver aquí

- **Memoria y usuario sin privilegios.** `VivadoCompiler` limita tiempo, entorno y tamaño de
  fichero, pero no la memoria: Vivado reserva mucho espacio virtual y `RLIMIT_AS` lo rompe. Hay que
  decidir con informática (o con `systemd-run --scope -p MemoryMax=...` y un usuario dedicado)
  cómo se aplica al desplegar. No cambies permisos del sistema sin pedir confirmación.
- **`read_vhdl` en VHDL-93.** El ejemplo usa `ieee.std_logic_unsigned`, como Digital. Si Vivado lo
  rechaza o avisa, anótalo antes de pasar a `-vhdl2008`.
- **Limpieza** de `work/` (política de retención): decidir cuándo se borran las carpetas viejas.
