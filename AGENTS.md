# OGR Core

Núcleo compartido de la suite: geometría, materiales, modelo de proyecto, cargas, soportes,
hidráulica, estadística, anotaciones, DXF, informes, y la malla y la filtración por elementos
finitos.

**Dos niveles de nombre**: *OpenGeoRock* (u *OGR Suite*) es el paraguas de los programas de la
suite; **OGR Core** es la biblioteca común. La distribución se llama `ogr-core` y el paquete de
importación, `ogr_core`. La usan **OGR Slip2D** (equilibrio límite), de cuyo núcleo sale, y
**OGR FEM2D** (elementos finitos): los dos fijan una versión etiquetada.

Autor y titular del copyright: Samuel Sáez López (UPCT). Licencia AGPL-3.0-or-later.

> Este archivo es el **contrato de trabajo** con cualquier agente de IA. Se consulta antes de cada
> acción. Deriva del `AGENTS.md` de OGR Slip2D, de donde sale el código.

> **Estado (2026-11-24, v0.2.8):** hay un solo núcleo. El código es el de OGR Slip2D en su commit
> `d48e2b3` (v0.1.471), con su malla y su filtración dentro de `ogr_core/fem/`, más el runner de la
> suite (`docs/changelog/CHANGELOG_v0.2.0.md` dice de dónde sale cada parte). OGR Slip2D lo adoptó
> en su v0.1.473 y OGR FEM2D en su v0.0.3; desde entonces **el código de `ogr_core` solo se cambia
> en este repositorio**. Qué versión fija cada programa y qué cambios están en curso:
> [`docs/consumidores.md`](docs/consumidores.md). Un Slip2D hasta la v0.1.471 lleva su propia copia
> y un paquete llamado `ogr_fem2d`, y no comparte entorno de Python con otro programa de la suite.

---

## Stack

- **Lenguaje**: Python 3.11+, con anotaciones de tipo donde aclaren.
- **Numérico**: NumPy, SciPy. **Geometría**: Shapely. **CAD**: ezdxf. **Informes**: reportlab.
  **Resultados**: h5py.
- **Sin Qt** y sin gráficas: el núcleo se importa desde un script, un cuaderno o un test sin
  arrastrar ninguna interfaz.
- **Tests**: el runner de la suite, que vive aquí (`ogr_core/testing/`: `runner.py` y la
  comprobación de fugas de estado, `leaks.py`) y que usan también los programas; aporta un `pytest`
  simulado. **No** hay pytest real instalado.

## Comandos

```bash
python tests/_runner.py          # toda la suite (lo que corre la CI)
python tests/_runner.py geometry # solo los archivos que contengan eso
python tests/_runner.py -k erfc  # solo los tests con ese nombre
python tests/_runner.py --jobs 4 # en cuatro procesos
pip install -e .                 # instalar en editable
```

Una ejecución filtrada lo dice antes y después de sus totales (`FILTERED RUN`) y no es evidencia
para publicar. Tampoco lo es la de un programa lanzada con `--dev-core`, que es como se prueba un
programa contra un núcleo que está cambiando (versión `X.Y.Z.devN` posterior a la que fija): sin
esa opción, el runner del programa se niega.

Para probar un programa contra este núcleo mientras se cambia **no se instala nada**: desde la
carpeta del programa y con su `.venv`,

```bash
PYTHONPATH=<este árbol, o el worktree del cambio> <la suite entera del programa> --dev-core
```

El runner del programa dice en su cabecera de qué árbol, de qué commit y de qué versión sale
`ogr_core`: compruébalo ahí. Mientras dura, la corrida deja `OGR_DEV_CORE=1` en su entorno; así lo
saben sus tests (`ogr_core.testing.runner.dev_core_run()`) y los runners que esos tests relancen,
que aceptan el mismo núcleo sin que nadie les pase la opción.

## Capas

`ogr_core` **no importa ningún programa ni ninguna capa superior**: ni `ogr_slip2d`, ni `ogr_fem2d`
(el programa 03), ni `ogr_api`, `ogr_gui`, `ogr_cli`, `ogr_mcp`, `PySide6` o `mcp`. Lo comprueba un
test, que lee el código y también mira `sys.modules` en tiempo de ejecución.

El núcleo **contiene un solver**: el de filtración, en `ogr_core/fem/`, porque lo usan los dos
programas (decisión P1 de la especificación 009). Lo que solo usa un programa vive en ese programa.

Una regla que necesitan dos programas vive aquí, y los programas la preguntan; copiarla es cómo
acaban diciendo cosas distintas.

---

## Las siete reglas de la suite

Son las de OGR Slip2D. Cada una existe porque su ausencia causó un problema real.

1. **El trabajo numérico se valida contra algo EXTERNO**: un caso publicado, una solución cerrada o
   una identidad analítica. Nunca una captura de lo que el código imprime hoy.
2. **El núcleo no traduce.** Todo mensaje que vaya a ver el usuario sale como un código con su
   plantilla inglesa (`ogr_core.messages`), y la interfaz de cada programa lo traduce. Ningún texto
   del núcleo se compone a mano con los números dentro.
3. **Toda acción debe ser alcanzable desde un menú.** Aquí no hay menús: la cumple cada programa con
   lo que ofrece del núcleo.
4. **Cada archivo lleva su cabecera de licencia** (SPDX AGPL-3.0-or-later y copyright).
5. **Los tests no filtran estado**: lo global (unidades, cachés de módulo) se restaura. Lo comprueba
   el runner archivo a archivo: lo que un archivo deja cambiado sale como `✗ [LEAK]` y hace fallar
   la corrida. Se arregla en el test; a la lista blanca solo va lo que no es del test, con su porqué
   (la de la suite, en `ogr_core/testing/leaks.py`; la de cada programa, en su `tests/_runner.py`).
6. **Las anomalías se reportan ANTES de corregirlas**, con la evidencia.
7. **Ningún ajuste puede no hacer nada**: toda opción lleva el test que demuestra que mueve el
   número.

## Reglas propias del núcleo

8. **Un cambio aquí se prueba también en los programas.** Antes de etiquetar una versión: la suite
   entera de este repositorio y la de **cada** programa de `docs/consumidores.md`, contra el núcleo
   que se va a etiquetar y con `--dev-core`. *Entera* quiere decir **sin filtrar** (sin patrones,
   sin `-k`, sin `--fast`); no quiere decir «en serie» ni «sin argumentos». Cada programa se corre
   con el comando que su `AGENTS.md` da para publicar, que esa tabla repite: **léelo antes de
   lanzarla**. OGR Slip2D va con `--jobs 4` y siempre con `QT_QPA_PLATFORM=offscreen`; sin esa
   variable abre sus ventanas en la pantalla y la corrida no vale. En este PC (16 núcleos físicos,
   64 GB; decisión de la propietaria del 2026-11-22) **las suites de programas distintos pueden
   correr a la vez**. **Dos corridas del mismo programa a la vez, no**, tampoco desde dos
   worktrees: comparten los archivos que el runner guarda en la carpeta temporal
   (`<programa>-test-durations.json` y compañía), y la suite de este repositorio comprueba que
   nadie los toque mientras corre (`test_runner_jobs_v020.py`). Pasa cuando esta sesión corre la
   suite de un programa contra un núcleo sin etiquetar mientras la sesión de ese programa corre la
   suya: se avisa antes. **Una corrida que se cronometra va sola**: si comparte máquina, su reloj
   no se compara con nada.
9. **Versiones**: serie propia desde 0.1.0. El número va en dos sitios, `pyproject.toml` y
   `ogr_core/__init__.py`, y un test falla si discrepan. Es `X.Y.Z` en el commit que se etiqueta y
   `X.Y.Z.dev0` entre dos etiquetas: después de etiquetar, `main` pasa a la versión de desarrollo
   de la siguiente, para que un núcleo cambiado y sin etiquetar no responda por el etiquetado (el
   runner de un programa compara números). Cada versión publicada lleva su etiqueta `vX.Y.Z` y su
   changelog; los programas fijan la etiqueta, nunca una rama. Mientras la serie sea 0.x, un
   cambio incompatible sube el segundo número y se avisa con al menos una versión de margen; uno
   compatible, el tercero.
10. **Un cambio que obliga a cambiar un programa** se anota en el changelog con lo que ese programa
    tiene que cambiar.

## Un núcleo y varios programas

Los programas se desarrollan a la vez. Para que el núcleo no vuelva a separarse:

- **Un solo `main`**, siempre publicable, con etiquetas de versión. **Sin ramas largas por
  programa**: dos ramas largas son dos copias otra vez.
- **Cada cambio, en una rama corta con su PR.** La CI corre la suite de este repositorio y, contra
  el núcleo de la PR, la de cada programa de `docs/consumidores.md` (en Linux). La regla 8 antes
  de etiquetar, a mano.
- **Una rama se borra cuando su PR se fusiona**, en GitHub y en local: sus commits quedan en
  `main` por el commit de fusión y la PR conserva su historia. La única rama que vive es `main`, y
  las versiones son etiquetas, no ramas. **Una rama sin fusionar no se borra sin el OK del
  propietario**; si lleva algo que `main` no tiene y hay que conservarlo, antes se archiva con una
  etiqueta `archivo/<nombre>`.
- **El código de `ogr_core` solo se cambia aquí.** La sesión de un programa que necesita algo del
  núcleo lo pide; no lo edita ni lo copia. Y desde aquí no se edita un programa: lo que un programa
  tiene que cambiar se le da escrito a su sesión (regla 10).
- **Cada programa fija una etiqueta y la sube a propósito**, en un commit suyo. Su `.venv` tiene
  el núcleo instalado desde esa etiqueta, como su CI, y no este árbol en editable: así dos
  programas pueden fijar versiones distintas y este árbol puede seguir a `main`.
- **Dos cambios del núcleo a la vez**, cada uno en su `git worktree`. El `PYTHONPATH` de la
  corrida dice cuál se mide, y la cabecera del runner lo nombra. Sus suites, por turnos (regla 8).
- **`docs/consumidores.md` al día**: qué fija cada programa, qué cambios están en curso y para
  quién, y los pasos para pedir un cambio y para subir una fijación.

---

## Flujo de trabajo

- **Antes de una tarea no trivial, propón un plan y espera el OK del propietario.**
- **Una tarea a la vez.** Al terminar, di qué cambiaste y qué probaste.
- **Si no estás seguro al 80 %, pregunta. No inventes**, sobre todo en fórmulas.
- Cada versión con su changelog en `docs/changelog/`, registrando **qué se encontró**, no solo qué
  se escribió.

## No hagas

- **No instales dependencias sin preguntar**, y comprueba su licencia (compatible con AGPL-3.0).
- **No uses `pytest` directamente**: el runner aporta uno simulado.
- **No cambies `LICENSE`, `CLA.md` ni las cabeceras SPDX** sin pedirlo.
- **No añadas telemetría ni llamadas de red** que no se hayan pedido.
- **No toques un test de validación** para hacer pasar un cambio: si falla, el fallo está en el
  código o en el valor de referencia, y averiguar cuál es el trabajo.

## Documentación de referencia

La documentación de programas comerciales sirve para entender **qué** hace una función y **cómo**
se comporta. **El código no puede contener ninguna referencia a esos productos ni a sus marcas**, ni
copiar su texto. Las fórmulas se citan por su **fuente científica original** (autor y año).

---

© 2026 Samuel Sáez López — UPCT — AGPL-3.0-or-later
