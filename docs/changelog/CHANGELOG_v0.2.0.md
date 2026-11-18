# OGR Core v0.2.0

**Un solo núcleo otra vez.** La v0.1.0 salió de una rama de OGR Slip2D (`dev/extraer-ogr-core`,
commit `2d68c29`) que nunca entró en su `main`: Slip2D siguió 101 versiones con su propia copia del
núcleo, su paquete `ogr_fem2d` y su runner de tests, y OGR-Core se quedó donde estaba. Esta versión
vuelve a tomar el núcleo de Slip2D, ahora en su commit **`d48e2b3`** (`main`, v0.1.471), con la
malla y la filtración dentro de `ogr_core/fem/`, y trae su runner. A partir de aquí el núcleo se
cambia solo en este repositorio.

Donde las dos copias diferían manda la de Slip2D, que es la desarrollada y la probada. De la v0.1.0
se conserva lo único que era suyo: lo que añadió al runner.

## 0. Lo que se encontró

- **«OGR-Core no tiene código propio» era casi cierto.** `ogr_core/` de la v0.1.0 era byte a byte
  el de `2d68c29` salvo la versión, y los 34 tests movidos, también. Pero el runner sí era propio:
  452 líneas distintas del de Slip2D en la separación (paquetes propios y compartidos, versión
  fijada, ganchos, el commit de un worktree), y OGR FEM2D depende de ellas. Traer el runner de
  Slip2D ha sido una fusión a tres bandas, no una copia.
- **Rehacer F1 sobre el `main` de hoy sale limpio.** Fusionar `2d68c29` sobre `d48e2b3` da dos
  conflictos, los dos triviales (`AGENTS.md` y la línea de versión de `ogr_fem2d/__init__.py`), y
  `fem/seepage.py` queda como el de Slip2D con las mismas tres líneas que cambió F1. Lo que la
  fusión no ve son las importaciones escritas después: 43 sentencias en 7 tests.
- **El detector de fugas, dentro de un paquete `ogr_*`, se ve a sí mismo.** Mira cada atributo de
  cada módulo `ogr_*`; en Slip2D vivía en `tests/_leaks.py` y quedaba fuera. Aquí su propia tabla
  de valores de importación (`_DEFAULTS`) salió como fuga en la primera corrida de su test. Va a la
  lista blanca con su porqué.
- **En un trozo de `--jobs`, el primer uso de la carpeta temporal era una fuga del archivo al que
  le tocaba.** `tempfile` la calcula la primera vez y la guarda. El runner de Slip2D la fijaba sin
  querer, al nombrar sus archivos de máquina al importarse; este, que los nombra solo si el
  repositorio da una etiqueta, no. La primera suite del núcleo con `--jobs 4` nombró cuatro
  archivos. Ahora `main()` la fija antes del primer archivo, también en cada trozo, y un archivo
  que la mueve sigue saliendo.
- **La misma trampa, en mis propios tests:** las fugas inyectadas del test del detector cambiaban
  de carpeta con `tempfile.gettempdir()` y, dentro de un trozo, el archivo «que lo deja todo como
  estaba» salía nombrado. El detector tenía razón.
- **Casi todo el código nuevo del núcleo lo cubren tests que importan el programa.** De los 11
  módulos nuevos, ninguno tiene un test que use solo el núcleo; de los 55 archivos cambiados, diez.
  La suite de este repositorio no los protege: los protege la de Slip2D corrida contra este núcleo,
  y por eso esa corrida es parte de publicar una versión (regla 8).
- **`ogr_core/report` importa matplotlib** desde Slip2D v0.1.417 (D351), para registrar las fuentes
  DejaVu que matplotlib trae. El núcleo no lo declara («sin gráficas»), y sin él el informe cae a
  Helvetica sin decirlo: el PDF depende de qué más haya instalado. **Se deja como está en Slip2D**,
  como se decidió con el plan de esta versión; arreglarlo es un cambio aparte.
- **El banco de cómputo de Slip2D no se podía ejecutar.** Está fuera de git, y su `comun.py` y el
  `banco.py` de las herramientas llevan escritas las rutas de antes de la reorganización en
  `OGR_Suite` (`C:\Samuel\OpenGeoRock_Slip2d\…`), que ya no existen. Además su `casos.py` y dos
  scripts del propio banco importan `ogr_fem2d`. La huella de esta versión se ha sacado con una
  copia del arnés en una carpeta temporal (ver §4); **el banco no se ha tocado, y hay que ponerlo
  al día cuando Slip2D adopte esta versión.**
- **En Windows, dentro de un entorno virtual, los pools de procesos de Slip2D se rompen cuando no
  hay consola.** No es del núcleo, y condiciona el plan de darle a Slip2D su propio `.venv`. Sin
  consola, `ogr_slip2d.processes` manda los procesos de cálculo a `pythonw.exe`, que en un venv es
  un lanzador y no el intérprete; `multiprocessing` solo sabe tratar el lanzador que coincide con
  `sys.executable`, y el pool muere (`BrokenProcessPool`). Se reproduce con un guion de doce líneas
  sin código de OGR: con el `pythonw.exe` del venv falla; con el `python.exe` del venv y con el
  `pythonw.exe` del sistema, funciona. El programa cae a un solo proceso y lo dice («The result is
  the same; only the time is not»), así que los números no cambian: cambian el tiempo, once tests
  que comprueban que el pool corrió, y la huella del banco en los ocho casos que abren pool (una
  nota de más). **Hay que arreglarlo en Slip2D antes de pasarlo a un `.venv`** (§4).
- **Un test de Slip2D era intermitente**, y vino con los cinco: `test_child_model_v1388`,
  `test_the_same_sequence`. Compara dos secuencias de llamadas sustituyendo cada objeto devuelto
  por «el paso que lo devolvió primero», con `id()`; cuando un modelo se reconstruye, el anterior
  se libera y el nuevo puede ocupar su dirección, y entonces su `id` es el de un paso viejo. Falló
  en las dos corridas enteras de la suite de Slip2D contra este núcleo y no en la de `d48e2b3`; con
  ruido de memoria entre pasadas, en el Slip2D de verdad y sin tocar, **fallaba 59 veces de 3000**.
  No depende del núcleo. Se trajo como estaba, anotado, y **la primera CI de esta versión lo sacó
  en Python 3.12 (Linux) las dos veces**, con 676 de 677 y 3.11 y 3.13 en verde: cuatro modelos
  mostraban tres identidades. Arreglado aquí: los modelos devueltos se guardan mientras dura la
  secuencia, así que una identidad nombra un solo objeto. Ningún valor esperado cambia. Con el
  mismo ruido, 0 fallos de 3000, y tres implementaciones mal hechas a propósito (un acierto que
  reconstruye, una edición en su sitio que no se ve, otro texto en el error) siguen dando otra
  secuencia. **El de Slip2D sigue como estaba** y necesita el mismo arreglo cuando adopte esta
  versión.
- **Una de mis medidas no valía, y lo dijo su procedencia.** Para repetir la huella del banco con
  el mismo intérprete que la de antes puse los dos árboles en `PYTHONPATH`; el orquestador del
  banco reescribe esa variable para cada trabajo, y los 23 casos midieron otra vez el Slip2D de
  verdad: 20 «idénticos» que no probaban nada, y tres fallos que eran lo único cierto. La huella
  guarda de qué archivo sale cada paquete, y ahí estaba. Se repitió con los árboles pasados por el
  orquestador (§5).
- **El número 009 de las specs de Slip2D está ocupado** en su `main` por otra función
  (`009-sarma-dovelas-no-verticales`); la spec de la extracción solo existe en la rama.
- **Errores propios al hacer esto**, por si se repiten: (1) medí qué `ogr_core` resolvía cada
  Python desde la carpeta de este repositorio, donde gana la carpeta actual, y parecía que el
  Python del sistema usaba OGR-Core cuando usa la copia de Slip2D; (2) un `grep` recursivo sobre la
  carpeta de referencias corrió unos dos minutos a la vez que la suite de Slip2D de referencia (se
  paró; la suite salió con sus cifras de siempre); (3) el primer test de `--dev-core` en trozos
  falseaba el paquete compartido con un parche que los trozos, que son procesos, no ven: ahora usa
  un paquete sintético importable de verdad.

## 1. De dónde sale cada parte

| Parte | Sale de | Notas |
|---|---|---|
| `ogr_core/` salvo `fem/` y `testing/` | Slip2D `d48e2b3`, `ogr_core/` | Copia exacta. 44 archivos cambian respecto a la v0.1.0 y 11 son nuevos |
| `ogr_core/fem/mesh.py`, `seepage_data.py`, `__init__.py` | Slip2D `d48e2b3`, `ogr_core/fem/` | Con los cambios de docstring de F1 (`2d68c29`): ya no hay reexportación desde `ogr_fem2d` |
| `ogr_core/fem/generator.py` | Slip2D `d48e2b3`, `ogr_fem2d/mesh/generator.py` | Sin cambios (igual que en la v0.1.0) |
| `ogr_core/fem/seepage.py` | Slip2D `d48e2b3`, `ogr_fem2d/solvers/seepage.py` | Con las tres líneas de F1: `from . import messages`, la importación diferida del generador y un docstring |
| `ogr_core/fem/bc_targets.py`, `streamlines.py`, `messages.py` | Slip2D `d48e2b3`, `ogr_fem2d/solvers/` y `ogr_fem2d/messages.py` | Sin cambios |
| `ogr_core/project/project.py` | Slip2D `d48e2b3` | Con un comentario de F1 (`fem_mesh`) |
| `ogr_core/testing/runner.py` | Slip2D `d48e2b3`, `tests/_runner.py`, **fusionado** con el de OGR-Core v0.1.0 | Ver §3 |
| `ogr_core/testing/leaks.py` | Slip2D `d48e2b3`, `tests/_leaks.py` | Ver §3 |
| Los 34 tests movidos en la v0.1.0 | Slip2D `2d68c29` | En `d48e2b3` siguen byte a byte como estaban en la separación; no cambian |
| 5 tests nuevos del núcleo | Slip2D `d48e2b3`: `test_child_model_v1388`, `test_strength_reader_v1391`, `test_published_fluxes_v1392`, `test_seepage_element_cache_v1393`, `test_transient_system_reuse_v1394` | Solo cambian sus importaciones de `ogr_fem2d`, y en `test_child_model_v1388` el arreglo de su intermitencia (§0); ningún valor ni tolerancia. En Slip2D siguen hasta que adopte esta versión |
| Tests del runner y de las fugas (`*_v020.py`) | Slip2D `d48e2b3`: `test_leaks_v1374`, `test_runner_state_v1373`, `test_runner_jobs_v1375`, `test_runner_fast_v1376`, `test_runner_shutdown_v1377`, `test_test_imports_v1372` | Reescritos sobre el runner compartido; `test_runner_dev_core_v020` es nuevo |

Lo que `main` de Slip2D cambió en el núcleo entre la separación (`32cb051`, v0.1.370) y `d48e2b3`,
que es lo que esta versión trae respecto a la v0.1.0:

| Área | Versiones de Slip2D | Qué |
|---|---|---|
| `fem/mesh.py` | 0.1.383, 0.1.393 | El índice de rejilla de `Mesh.locate` y su invalidación |
| `fem/seepage.py` | 0.1.392–0.1.394, 0.1.433 | Ensamblado, flujos y transitorio sin rehacer trabajo; ningún número cambia según sus changelogs |
| `geometry/` | 0.1.415, 0.1.427, 0.1.434–0.1.437, 0.1.445, 0.1.447, 0.1.455–0.1.456, 0.1.465, 0.1.469 | `user_polyline.py`, `surface_ends.py` y `messages.py` (nuevos); `expand_shrink`, `slip_circle`, `slope_angle`, `transforms`, `boundary` |
| `project/` | 0.1.385–0.1.471 | `reported.py`, `file_shape.py`, `step_names.py`, `user_surfaces.py` (nuevos); `commands`, `project`, `settings`, `rules`, `properties_import`, `results_io`, `design_factors` |
| `report/report_generator.py` | 0.1.417–0.1.471 | Fuentes incrustadas, tablas nuevas (once versiones) |
| `materials/` | 0.1.388, 0.1.391, 0.1.437 | La caché del modelo hijo y el lector de resistencia |
| `statistics/`, `hydraulic/`, `loads/` | 0.1.385, 0.1.393, 0.1.434–0.1.437, 0.1.453, 0.1.459 | Distribuciones, niveles de desembalse, sobrecarga, `loads/messages.py` (nuevo) |
| raíz del paquete | 0.1.434–0.1.439, 0.1.468 | `naming.py`, `file_messages.py`, `result_rows.py` (nuevos), `messages.py` |

El detalle de cada una está en `docs/changelog/` de OGR Slip2D, con ese número de versión.

## 2. Qué cambia para quien usa el núcleo

- **Ningún nombre público desaparece** respecto a la v0.1.0 (comparados los nombres de primer nivel
  y los miembros de clase de los 94 módulos comunes; solo uno privado, `_unique` de
  `project/properties_import.py`). El comportamiento sí cambia en lo que cambió Slip2D: son 101
  versiones.
- **El runner ahora hace fallar una corrida por lo que un archivo deja cambiado en el proceso**
  (`✗ [LEAK]`), y antes no lo miraba. Un programa que suba a esta versión puede ver fugas que ya
  tenía.
- **`runner.main` y `runner.cli` aceptan lo de antes** (`own`, `shared`, `pinned`, `hooks`, `prog`):
  el `tests/_runner.py` de OGR FEM2D no necesita cambiar más que la versión que fija.

Por eso sube el segundo número.

## 3. El runner compartido

`ogr_core/testing/runner.py` es el de Slip2D v0.1.471 sobre el esqueleto de la v0.1.0. Lo que en
Slip2D eran constantes de su único runner es aquí lo que cada repositorio dice de sí mismo en su
`tests/_runner.py`:

| En Slip2D | Aquí |
|---|---|
| `PACKAGES`, todos del repositorio | `own` y `shared`, con `pinned` (de la v0.1.0) |
| `from ogr_gui import gc_guard` y `_release_windows()` | `Hooks(before_run, before_file, after_run)`: el núcleo no importa Qt |
| `OGR_BRIDGE_DIR` y `OGR_SETTINGS_DIR` | `run_folders={variable: clave}`: una carpeta nueva por corrida, repuesta tras cada archivo y comparada por el detector bajo esa clave |
| `ALLOWED`, 24 entradas | 15 en `leaks.ALLOWED` (las 14 de la suite: cachés del núcleo y lo que hace una librería al importarse; más la del propio detector) y 10 que se quedan en Slip2D, que las pasa como `allowed` |
| `ogr-slip2d-test-durations.json` y sus dos compañeros en `%TEMP%` | `label="ogr-slip2d"` da esos mismos nombres; sin etiqueta no se guarda nada |
| `SERIAL_EVERY = 100` | `serial_every`: sin él no se registra ni se pide ninguna serie |
| `tests/_slow.txt` junto al runner | `tests/_slow.txt` del repositorio (o `slow_list`) |
| cada trozo arranca `tests/_runner.py --child` | arranca el `tests/_runner.py` **del repositorio**, para que el trozo tenga sus ganchos y su lista; una carpeta sin runner propio la corre el módulo mismo |

Nuevo aquí: **`--dev-core`**. Entre dos etiquetas el `main` del núcleo dirá una versión de
desarrollo (`0.3.0.dev0`), y un programa que fija `0.2.0` se niega, como debe. Con `--dev-core` el
runner del programa acepta **solo** una `.devN` de una versión posterior a la fijada, lo dice antes
y después de los totales (`DEV CORE — … NOT evidence for a release`), no cuenta como la serie que
pide una versión, y con nada que aceptar sale con 2. Es como se prueba un cambio del núcleo contra
cada programa antes de fusionarlo.

## 4. Lo que tiene que cambiar cada programa (regla 10)

**OGR FEM2D** (hoy fija `v0.1.0`):

- `pyproject.toml`: `ogr-core @ git+https://github.com/samuelsl27/OGR-Core@v0.2.0`.
- Nada más es obligatorio. Su suite pasa ahora por el detector de fugas: ver §5.

**OGR Slip2D** (hoy lleva su copia):

- Fuera `ogr_core/` y `ogr_fem2d/`; dependencia `ogr-core @ git+…@v0.2.0`.
- Importaciones (229 sentencias en 59 archivos en `d48e2b3`):

  | Antes | Ahora |
  |---|---|
  | `ogr_fem2d.mesh` (`generate_mesh`, `generate_mesh_for_project`, `discretize_edges`), `ogr_fem2d.mesh.generator` | `ogr_core.fem.generator` |
  | `ogr_fem2d.mesh` (`Mesh`, `Node`, `Element`), `ogr_fem2d.mesh.mesh` | `ogr_core.fem.mesh` (o `ogr_core.fem`) |
  | `ogr_fem2d.solvers.seepage`, y los solvers y datos de `ogr_fem2d.solvers` | `ogr_core.fem.seepage` |
  | `SIDE_LEFT`, `SIDE_RIGHT`, `apply_reservoir`, `boundary_cycle`, `wetted_nodes` de `ogr_fem2d.solvers`; `ogr_fem2d.solvers.bc_targets` | `ogr_core.fem.bc_targets` |
  | `ogr_fem2d.solvers.streamlines` | `ogr_core.fem.streamlines` |
  | `ogr_fem2d.messages` | `ogr_core.fem.messages` |

- `tests/_runner.py` pasa a ser un envoltorio: `own` (sus cinco paquetes), `shared=("ogr_core",)`
  con la versión fijada, `Hooks` con `gc_guard` y el borrado de ventanas, `run_folders` con sus dos
  carpetas, `allowed` con sus diez entradas (las de `ogr_gui` y `ogr_api`, `mod:*.icon`,
  `mpl.rcParams` y `mp.executable`, con la regla `to_windowless`, que se va con ellas),
  `label="ogr-slip2d"`, `serial_every=100`. `tests/_leaks.py` desaparece o reexporta
  `ogr_core.testing.leaks`. Sus tests del runner cargan hoy `tests/_runner.py` por ruta y parchean
  sus constantes (`DURATIONS`, `SLOW_LIST`, `SERIAL_RECORD`): pasan a usar los parámetros
  (`records`, `slow_list`, `serial_every`), como los de aquí.
- **30 tests de 22 archivos leen fuentes del núcleo por ruta dentro del repositorio** y dejan de
  encontrarlas (son los que fallan en la corrida de §5; ninguno más): los censos de mensajes y de
  capas (`test_core_layering_v1340`, `test_api_layering_pyexec_v1194`, `test_dxf_drawings_v1341`,
  `test_dxf_export_census_v1354`, `test_dxf_messages_v1334`, `test_edit_messages_v1434`,
  `test_fem_data_in_core_v1342`, `test_focus_circle_in_core_v1343`, `test_import_messages_v1437`,
  `test_local_c_phi_in_core_v1345`, `test_model_notes_v1347`, `test_ogr_open_refusals_v1438`,
  `test_overburden_in_core_v1344`, `test_png_annotations_v1338`, `test_seepage_run_notes_v1352`,
  `test_setting_refusals_v1350`, `test_stat_notes_v1353`, `test_strength_refusals_v1351`,
  `test_window_undo_v1301`), el censo de ajustes (`test_settings_coverage_v1103`, que deja de ver
  quién lee `optimize_enabled`), `test_version_consistency_v176` (nueve sitios, uno en el núcleo)
  y `test_test_imports_v1372` (`ogr_core` pasa a ser un requisito declarado). Cada invariante
  queda en uno de los dos repositorios: o el test lee el árbol del núcleo instalado, o se muda
  aquí. Ninguno puede quedarse buscando en una carpeta que no existe.
- **Los pools de procesos en un entorno virtual** (§0): `ogr_slip2d.processes.child_executable`
  no puede dar el `pythonw.exe` de un venv. Va con su test, y antes de mover Slip2D a un `.venv`.
- Fuera de git: el banco de cómputo y dos scripts del banco de verificación importan `ogr_fem2d` y
  llevan rutas antiguas.

## 5. Pruebas

Todo en la máquina de desarrollo (Windows, Python 3.14.7), de una en una. La CI de este repositorio
cubre 3.11 a 3.13 en Linux.

### Antes de tocar nada (2026-11-18)

| Qué | Resultado |
|---|---|
| OGR-Core `5364a5c` (v0.1.0 más documentación), suite entera | 499 de 499, código 0 |
| OGR FEM2D `e3d34ba`, suite entera con su `.venv` (núcleo v0.1.0 instalado) | 185 de 185, código 0 |
| OGR Slip2D `d48e2b3`, suite entera con `--jobs 4`, Python del sistema | 8046 casos: 8044 pasan, 0 fallan, 2 saltados; código 0; 26,7 min |
| Huella del banco de cómputo de Slip2D sobre `d48e2b3` (lote `version`, 23 casos) | 23 con código 0, ninguno contaminado |

### La suite de este repositorio

57 archivos y 677 casos: los 499 de la v0.1.0, 52 de los cinco tests traídos de Slip2D y 126 del
runner, las fugas y las importaciones de los tests (siete archivos `*_v020.py`).

| Corrida | Resultado |
|---|---|
| En serie, sin argumentos (lo que corre la CI), Python del sistema | 677 de 677, código 0, ninguna fuga |
| `--jobs 4` | 677 de 677, código 0, ninguna fuga |
| En serie, con el Python del `.venv` de OGR FEM2D: numpy 2.5.5, scipy 1.18.1, shapely 2.2.0, ezdxf, h5py y reportlab, **sin PySide6 ni matplotlib** | 677 de 677, código 0 |

**Dientes.** 33 errores metidos a propósito, uno a uno, en `runner.py`, en `leaks.py` y en
`pyproject.toml` (sobre una copia del árbol), cada uno con los tests que deben cazarlo: mueren los
33. Dos sobrevivieron a la primera pasada y se arreglaron en los tests, no en la lista:

- «una corrida sin registros nombra archivos lentos», en el final de una corrida **en trozos**:
  solo se miraba el de la corrida en serie. Ahora se miran los dos.
- «`--fast` sin lista corre toda la selección» no se quedó vivo, sino colgado: con ese error, el
  test que comprueba la negativa lanzaba la suite entera dentro de sí mismo, él incluido, hasta su
  tiempo límite de 15 minutos. Ahora selecciona un solo test barato y falla en un segundo.

### OGR FEM2D contra esta versión

Una copia de `e3d34ba` con dos cambios (la etiqueta de `pyproject.toml` y las dos cadenas de
`tests/test_project_setup_v001.py` que dicen `0.1.0`), con su `.venv` y este árbol por delante:

- `shared: ogr_core 0.2.0 …\OGR-Core\ogr_core`, y **185 de 185 tests pasan**.
- **La corrida sale en rojo por una fuga que ya estaba**: `tests/test_benchmark_v001.py` deja
  `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` y `MKL_NUM_THREADS` en el entorno. Los pone
  `poc/benchmark.py` al importarse (`os.environ.setdefault`), para medir con un solo hilo. Con la
  v0.1.0 nadie lo miraba. **Es lo que OGR FEM2D tiene que resolver al subir a esta versión**: o el
  test los quita al terminar, o su `tests/_runner.py` los declara en `allowed` con su porqué.

### OGR Slip2D contra esta versión

Sobre una copia desechable de `d48e2b3`, nunca sobre el repositorio: F1 (`2d68c29`) fusionada, las
43 importaciones que quedaban reescritas, `ogr_core/` y `ogr_fem2d/` fuera del árbol y `ogr_core`
fuera de los paquetes propios de su runner. Cambian 72 archivos fuera de esos dos paquetes: ocho
del programa (solo importaciones) y el resto tests y documentación. Es el ensayo de lo que Slip2D
tiene que hacer para adoptar esta versión.

**La suite entera, `--jobs 4`**, en un entorno virtual con los mismos 95 paquetes y versiones que
el Python del sistema, la copia y este árbol instalados en editable (`ogr_fem2d` no resuelve a
nada): 8047 casos, **8002 pasan, 43 fallan, 2 saltados, ninguna fuga**. Comparada test a test con
la de antes: 8001 con el mismo resultado, 43 que cambian, y tres tests de F1 en el sitio de dos
(`test_fem_data_in_core_v1342`: «una clase en las dos rutas» pasa a «en una»). Los 43:

| Cuántos | Qué son | Cómo se sabe |
|---|---|---|
| 30, en 22 archivos | Leen fuentes del núcleo por ruta dentro del repositorio (§4) | `FileNotFoundError`, o un censo que ya no encuentra nada que contar |
| 11, en 7 archivos | Comprueban que un pool de procesos corrió: el `pythonw.exe` del venv (§0) | Control 1 y control 2 |
| 1 | `test_report_pdf_v1417`: busca la ruta del proyecto de una pieza en el texto del PDF, y la carpeta temporal de la corrida era tan larga que la celda la parte | Control 1 y control 2 |
| 1 | `test_child_model_v1388`, intermitente (§0) | 59 fallos de 3000 pasadas en el Slip2D de verdad |

- **Control 1**: el Slip2D de verdad, `d48e2b3` sin tocar, con el intérprete de ese entorno virtual
  y la misma carpeta temporal, en los nueve archivos de las tres últimas filas: **fallan los mismos
  12** (el intermitente pasó).
- **Control 2**: la copia contra este núcleo, con el intérprete del sistema (sin entorno virtual) y
  una carpeta temporal corta, en los mismos nueve archivos: **114 de 114**.

Es decir: contra este núcleo, todo test de Slip2D da lo que daba, salvo los 30 que buscan el núcleo
dentro del repositorio.

### La huella del banco de cómputo de Slip2D

Lote `version`, los 23 casos, con el `comparar.py` del propio banco: idéntico solo si cada parte lo
es bit a bit y no queda ninguna clave sin pareja.

| Huella | Intérprete | Frente a la de `d48e2b3` |
|---|---|---|
| Copia de Slip2D contra este núcleo | El del sistema, el mismo de la de antes (Python 3.14.7, numpy 2.5.1, scipy 1.18.0, shapely 2.1.2) | **23 de 23 idénticos bit a bit** |
| La misma, en el entorno virtual | Mismas versiones; los pools caen a un proceso (§0) | 15 de 23 idénticos, entre ellos los de elementos finitos (K15 a K18). Los ocho que abren pool difieren solo en la nota del pool fallido y en sus avisos: ningún número |

La procedencia de cada huella dice qué midió: en la primera, `ogr_slip2d` de la copia y `ogr_core`
0.2.0 de este árbol en los 23 casos.

El banco no se ha tocado. Se usó una copia de su arnés en una carpeta temporal, con estos cambios,
y la misma copia para la huella de antes salvo los tres últimos:

- las dos rutas de `comun.py` llegan por el entorno (las escritas ya no existen);
- un manifiesto de entradas nuevo, con las rutas de hoy: los mismos hashes que el de la referencia
  0.1.377 (`inputs vs the 0.1.377 reference: identical` en las tres corridas);
- solo para «después»: las nueve sentencias `import` de `casos.py` y la de la procedencia, a
  `ogr_core.fem`; los dos scripts del banco que cargan K15 y K16, ejecutados con sus `import`
  reescritos en memoria, sin tocar el archivo; y los árboles medidos, añadidos al `PYTHONPATH` que
  el orquestador da a cada trabajo.

### La suite de Slip2D a través del runner compartido

Para saber si el diseño de §3 le sirve a quien más lo usa, antes de etiquetar: en la misma copia,
`tests/_runner.py` sustituido por un envoltorio de `ogr_core.testing.runner` (sus cinco paquetes,
`ogr_core` compartido y fijado en 0.2.0, los tres ganchos de Qt, sus dos carpetas, sus diez
entradas de la lista blanca, `label="ogr-slip2d"`, `serial_every=100`) y `tests/_leaks.py` por un
puente al módulo compartido. Con el intérprete del sistema, `--fast --jobs 4`:

- `shared: ogr_core 0.2.0 …\OGR-Core\ogr_core`; 502 de 539 archivos, 7383 casos, 15 minutos;
  **ningún trozo muerto**, y los pools de procesos funcionan.
- **7240 tests dan lo mismo que antes.** El detector, con las dos listas juntas, no nombra ninguna
  fuga que no lo sea en 502 archivos.
- Cambian 140: los 29 de rutas del núcleo que entran en `--fast` (el de las importaciones de los
  tests pasa, ahora que `ogr-core` es un requisito declarado), el intermitente otra vez, y **110
  que son tests del propio runner de Slip2D**: cargan `tests/_runner.py` por ruta y usan lo que
  tenía dentro (`DURATIONS`, `partition`, `run_test`, `_load_module`…). Son siete archivos del
  runner y de las fugas, y tres que toman prestada una pieza suya (`test_project_settings_wiring_v174`,
  `test_gc_guard_v1302`, `test_rules_moved_v1194`). La única fuga de la corrida es de uno de ellos,
  que se rompe antes de reponer su variable.

Los 110 son trabajo de la adopción (§4), no un defecto del runner: sus invariantes están aquí, en
los tests `*_v020.py`.

### Lo que no se ha probado

- **La CI de este repositorio** (Linux, Python 3.11 a 3.13) corrió por primera vez con la PR: 3.11
  y 3.13 en verde, y 3.12 con un solo fallo, el del test intermitente (§0). Todo lo demás de arriba
  es Windows y Python 3.14.7.
- **Instalar desde la etiqueta** (`pip install "ogr-core @ git+…@v0.2.0"`): la etiqueta no existe
  hasta que se apruebe; aquí el núcleo se ha usado desde su árbol.
- **La suite entera de Slip2D con el runner compartido**: solo `--fast`. Los 37 archivos lentos y
  la corrida en serie quedan para la adopción.
- **La corrida en serie de Slip2D contra este núcleo**: las de arriba son con `--jobs 4`.
- **Por qué el contexto saca el intermitente**: falló en las corridas enteras de la copia y en
  Python 3.12 de Linux, y no en la de `d48e2b3` ni solo. El mecanismo está medido (§0) y el
  arreglo no depende de saberlo, pero no se ha averiguado qué del contexto decide la dirección.

## 6. Queda abierto

- `ogr_core/report` y matplotlib (§0): el núcleo usa una librería que no declara.
- El arreglo del test intermitente en Slip2D (aquí está hecho).
- La versión de desarrollo en `main` (`0.3.0.dev0`) tras etiquetar, que es lo que da sentido a
  `--dev-core`: es parte de la forma de trabajar, que se escribe después. Con ella hay que decidir
  qué changelog pide `test_version_consistency_v10` a una `.devN` (hoy pide uno con el nombre
  exacto de la versión).
