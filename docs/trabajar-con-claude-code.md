# Trabajar con Claude Code en el servidor

Claude Code se ejecuta en el propio servidor del laboratorio, así que puede hacer lo que una
conversación en la web no puede: ejecutar `drl` y `openFPGALoader` contra la placa real, lanzar
Vivado, mirar la foto de la cámara y depurar con la salida real. Las instrucciones permanentes
para él están en [`CLAUDE.md`](../CLAUDE.md), que lee solo al arrancar dentro del repositorio.

## Reparto de trabajo

| Dónde | Para qué |
|---|---|
| Conversación en claude.ai | Diseño, código nuevo y tests con hardware simulado, documentación, revisión de ramas |
| Claude Code en el servidor | Verificación con hardware real, depuración de JTAG y cámara, generar bitstreams con Vivado |

Se sincronizan a través de GitHub: cada uno trabaja en su rama y se revisa mediante pull request.
**No edites la misma rama desde los dos sitios a la vez.**

## 1. Preparar el servidor (una sola vez)

1. Instala las dependencias y los permisos de [etapa-1-verificacion.md](etapa-1-verificacion.md),
   secciones 1 y 2 (incluye `openFPGALoader`, la regla udev y los grupos `plugdev` y `video`).
2. Dale acceso a GitHub con permiso de escritura sobre el repositorio, de una de estas formas:
   - `gh auth login` (recomendado), o
   - una clave SSH de despliegue con escritura, o un token con acceso solo a este repositorio.
3. Clona y entra en el repositorio:

   ```bash
   git clone https://github.com/sangla87/DigitalRemoteLab.git
   cd DigitalRemoteLab
   git checkout etapa-1
   git checkout -b hw/verificacion-nexys4
   python3 -m venv .venv && . .venv/bin/activate
   pip install -e ".[camera,dev]"
   cp config/lab.example.toml config/lab.toml     # edítalo con `drl devices`
   ```

## 2. Primera sesión: verificar la etapa 1

Con la placa encendida, el jumper en JTAG y la cámara apuntándola, arranca Claude Code dentro de
la carpeta del repositorio y con el entorno virtual activado:

```bash
cd DigitalRemoteLab && . .venv/bin/activate && claude
```

Pega este mensaje (cambia `nexys4ddr` por `nexys4` si tu placa es la original):

> Verifica la etapa 1 con la placa real. Sigue `docs/etapa-1-verificacion.md` desde la sección 3:
> usa `drl devices` para rellenar `config/lab.toml` (modelo `nexys4ddr`, número de serie y cámara),
> genera el `.bit` de prueba con Vivado, y ejecuta las comprobaciones de la tabla de la sección 5
> en orden. Abre las fotos que hagas y dime qué LEDs ves encendidos. Cuando algo falle, diagnostica
> con la salida real y arréglalo en el código, añadiendo un test con los simuladores. Al terminar,
> dame una tabla con cada comprobación (correcta o fallida), y deja los cambios en commits sobre
> esta rama sin hacer push.

Qué esperar:

- Te pedirá permiso para ejecutar comandos. Puedes aprobar de forma permanente `drl`, `pytest` y
  `openFPGALoader -b ... --detect`. Revisa con más atención cualquier `sudo` o comando que escriba
  fuera de la carpeta del proyecto.
- Puede abrir las fotos (`foto.jpg`) y describir qué ve, así que sirve para la comprobación (f).
- Los pasos que requieren manos (mover los interruptores de la comprobación g, cambiar el cable)
  te los pedirá y esperará tu respuesta.

## 3. Devolver el resultado

Revisa los cambios (`git log`, `git diff etapa-1`) y súbelos:

```bash
git push -u origin hw/verificacion-nexys4
gh pr create --base etapa-1 --title "Verificación de la etapa 1 en la Nexys 4"
```

Después, en la conversación de claude.ai, di por ejemplo *«revisa la rama
`hw/verificacion-nexys4`»* y la leo, integro lo que haga falta y sigo con la etapa 2.

Si no quieres usar GitHub para esto, pega aquí la tabla de resultados y la salida de lo que haya
fallado.

## Consejos

- Una sesión de Claude Code por tarea: para empezar otra, sal con `/exit` o abre una nueva.
- Si el servidor se queda sin sesión gráfica, todo lo anterior funciona igual por SSH.
- Mientras `drl program` esté cargando, no ejecutes otra orden contra la misma placa.
- No dejes la clave o el token de GitHub en el repositorio: `lab.toml`, `.bit` y las fotos están en
  `.gitignore`, pero revisa `git status` antes de cada commit.
