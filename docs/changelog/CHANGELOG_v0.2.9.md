# OGR Core v0.2.9

> **En curso.** `main` dice `0.2.9.dev0` y esta versión no está etiquetada. Este archivo cuenta lo
> que ya ha entrado camino de ella.

**El armazón de la capa de operaciones, sin Qt y sin `mcp`: `ogr_core.api`.** El registro de
operaciones, los errores con código, la conversión de argumentos, los trabajos en un proceso hijo
que se cancelan de verdad, el puente con la ventana abierta y el espacio de trabajo con sus
cerrojos y su deshacer. Sale de `ogr_api` de OGR Slip2D (v0.1.486, `03b6c2d`), sin nada de
equilibrio límite. Lo pidió OGR FEM2D (decisión D1 (i) de su spec 006 y su ADR-0005, aprobados por
la propietaria el 2026-11-24): bloquea la parte B de esa spec. Es compatible, porque no cambia nada
de lo que el núcleo ya hacía: solo se añade un subpaquete.

## 0. Lo que se encontró

- **Los errores de `ogr_api` chocaban con la regla 2.** Eran frases inglesas montadas con
  f-strings y los valores dentro (`f"Job {id} is still running."`, `f"Model {id} is busy with …
  ({since:.0f} s)."`, `f"Unknown {kind} {word!r}."`). En Slip2D vivían en una capa superior. En el
  núcleo, la regla lo prohíbe. Decisión de la propietaria (2026-11-24): codificarlas. Cada frase es
  una entrada de `API_MESSAGES` (72 en total), y lo que se escribe es
  `ogr_core.messages.coded(...)`: un `Coded` que **es** la frase inglesa y además lleva su código y
  sus valores.
- **El inglés no se mueve.** Hay 30 casos de conversión y de errores (todos los rechazos de
  `coerce_value`, `coerce_enum`, `point`, `points`, `resolve_field`, `unknown` e
  `internal_error`) que se corrieron con el `ogr_api` de Slip2D en su `.venv` y con
  `ogr_core.api`, y salen iguales byte a byte salvo uno, a propósito: la lista cortada de campos
  de `resolve_field` nombraba `settings_get`, que es una operación de Slip2D. Ahora la nombra solo
  si se pasa `lister="settings_get"`. Lo mismo vale para lo que nombraba el programa: «OGR
  Slip2D», `~/.ogr-slip2d`, el protocolo `ogr-slip2d-bridge/1`, `job_get`, `job_cancel`,
  `project_new`, `project_open`, `project_summary`, `project_list` y el ejemplo
  `methods.num_slices`. Todo eso son ahora argumentos (`BridgeConfig`, `WorkspaceNames`,
  `JobManager`, `resolve_field`), y con los valores de Slip2D las frases son las de Slip2D.
- **FEM2D pedía algo que Slip2D no hace** (su D9). Los trabajos de Slip2D matan el árbol en cuanto
  se cancelan, y su progreso es `done/total`. FEM2D quiere poder parar entre fases y que el progreso
  lleve fase, escalón e iteración. Ahora `cancel` acepta un plazo: escribe un archivo `stop`, que
  lee `JobContext.should_stop()`, y solo mata el árbol si el hijo no ha terminado en ese plazo. Con
  0, que es el valor por defecto, se mata en el acto, como en Slip2D. `progress(done, total,
  **extra)` añade campos, y un cambio en ellos se escribe aunque caiga dentro del medio segundo de
  freno.
- **El test de capas no deja que el núcleo use `importlib`.** El primer diseño importaba en el hijo
  un `"módulo:función"` por su nombre, y `test_core_layering_v10` lo cazó: `importlib` está
  prohibido en el núcleo, con una sola excepción, el runner. No se amplió la lista. El `target` de
  un trabajo es ahora la propia función del programa, definida en lo alto de uno de sus módulos, y
  viaja al hijo como pickle lleva una función, por su módulo y su nombre. Así el núcleo no nombra
  nunca un programa: es el programa quien se la da. Lo que pickle no puede llevar por nombre (una
  `lambda`, una función anidada) se rechaza al llamar a `start`, antes de lanzar ningún proceso.
- **Un `JobCancelled` definido en `worker.py` no servía.** El hijo corre ese archivo como
  `__main__`, así que la clase que el destino lanzaba (`ogr_core.api.jobs.worker.JobCancelled`) no
  era la que el `except` esperaba, y un trabajo cancelado acababa en `failed`. Lo encontró
  `test_api_jobs_v029`. La clase vive ahora en `ogr_core.api.jobs`.
- **Corrijo algo que dije en el plan.** Dije que `live_bridges()` de Slip2D listaba los puentes de
  otro protocolo, y no es así: ya los filtraba. Lo que cambia es que el protocolo pasa a ser de cada
  programa, así que dos programas que compartan `OGR_BRIDGE_DIR` no se ven el uno al otro. Hay un
  test que lo comprueba.
- **El `pytest` simulado del runner no tiene `raises(...) as exc`, ni `.value`, ni `mark`.** Los
  tests nuevos usan un pequeño `_refused(cls, fn)` y bucles. No se ha tocado el runner.

## 1. Qué hay

`ogr_core/api/`, que solo importa la biblioteca estándar y el núcleo:

| Módulo | Qué es | Qué cambia respecto a Slip2D |
|---|---|---|
| `registry.py` | `Registry` y `Operation`: `@r.operation(name, toolset=, mutates=)` y `r.call(ws, name, **kw)` | Un objeto por programa, vacío al nacer, en lugar del diccionario de módulo que importaba las operaciones de Slip2D |
| `errors.py` | `OgrApiError` y `NotFound`, `InvalidArgument`, `Conflict`, `NotConfigured`, `Busy` y `JobFailed`; `did_you_mean`, `unknown`, `internal_error`, `from_dict` | `to_dict` añade `message_code`/`message_args` y `hint_code`/`hint_args` cuando el texto está codificado, y `from_dict` los devuelve |
| `coerce.py` | `coerce_value`, `coerce_enum`, `resolve_field`, `describe_type`, `point`, `points` | Frases codificadas; `resolve_field(root_name=, noun=, example=, lister=)` |
| `jobs/` | `JobManager`, `Job`, `JobHooks`, `JobCancelled`, `kill_tree`; el hijo, `python -m ogr_core.api.jobs.worker` con su `JobContext` | `target` como función; ganchos `on_end(job)`, `loading()` y `provenance`; `cancel_grace_s` y `should_stop()`; progreso con campos extra; el `PYTHONPATH` del hijo lleva el árbol del programa (`pythonpath`) y el del `ogr_core` que importó el padre, salvo que sea un `site-packages` |
| `bridge.py` | El cable, el descubrimiento, `BridgeClient`, `WindowRouter` y, nuevo, la parte que contesta: `BridgeSession` (el saludo con su testigo y el despacho al registro) y `BridgeServer` (con hilos, para un proceso sin bucle de eventos, y para los tests) | Todo recibe un `BridgeConfig`; el enrutador recibe su `local_call`. La parte que contesta estaba en la ventana de Slip2D, con Qt |
| `workspace.py` | `Workspace`, `ProjectHandle`, `StoredResult`, `WorkspaceNames` | `undo_step(description, fn, attrs)` y `document_hash(model)` los da el programa. Por defecto son lo de Slip2D: el `SnapshotCommand` del núcleo sobre `LIGHT_ATTRS` y el SHA-256 de `to_dict()`. `jobs_options` para el gestor de trabajos. El modelo se lee por pato (`name`; `file_path` e `is_dirty` en el de una ventana) |
| `messages.py` | `API_MESSAGES`, `say`, `part` | Nuevo (regla 2) |

## 2. Lo que tiene que cambiar cada programa (regla 10)

- **OGR FEM2D**: nada obligatorio. Para su parte B, sube la fijación (su T10) y escribe sobre
  esto:
  - `OPERATIONS = Registry()` y `@OPERATIONS.operation(...)` en sus módulos de operaciones;
  - `Workspace(undo_step=…, document_hash=…, names=WorkspaceNames(…), jobs_options={"target":
    <su función>, "pythonpath": [<su árbol>], "hooks": JobHooks(provenance=<su función>),
    "cancel_grace_s": <su plazo>})`, porque su modelo no es el `Project`;
  - su destino recibe el `JobContext`: `ctx.data` (el modelo separado), `ctx.params`,
    `ctx.progress(done, total, phase=…, step=…, iteration=…)` y `ctx.should_stop()`. Al parar,
    lanza `JobCancelled`, y devuelve `(payload, summary)`;
  - para el puente, `BridgeConfig("ogr-fem2d-bridge/1", "OGR FEM2D", ".ogr-fem2d", …)`. La ventana
    (en `ogr-gui`) le pasa a un `BridgeSession` las líneas que lee su socket;
  - su interfaz traduce estos mensajes por su código, con `API_MESSAGES` y
    `ogr_core.messages.render`.
- **OGR Slip2D**: nada. No usa `ogr_core.api`, y su `ogr_api` sigue como está. Si su sesión decide
  adoptarlo, lo que su `ogr_api` tendría que poner es esto:
  - `BridgeConfig("ogr-slip2d-bridge/1", "OGR Slip2D", ".ogr-slip2d")`, para que una ventana
    anterior siga respondiendo;
  - `resolve_field(…, example="methods.num_slices", lister="settings_get")`;
  - `JobHooks(on_end=` que borre las carpetas de `slice_store` de `job.pids()`,
    `loading=slice_store.arriving, provenance=` su versión`)`, y sus seis análisis como destinos;
  - su `Registry` en lugar de `REGISTRY`.

  Con eso las frases inglesas son las de hoy, byte a byte (§0). Hay dos cosas que cambian aunque se
  pongan esos valores. Un error de trabajo que falla dice `error` como antes, pero
  `status.json` lleva además `error_code` y `error_args`. Y `to_dict()` de un error añade las
  claves `message_code`/`hint_code` y sus argumentos; las que había no cambian.

## 3. Pruebas

| Qué | Resultado |
|---|---|
| `tests/test_api_errors_registry_v029.py`: el registro, `did_you_mean`, el inglés de Slip2D copiado de su código, el código que cruza el cable, y la regla 2 en el paquete (ningún error se lanza con un literal o un f-string; todo código usado existe y toda entrada se usa) | 13 de 13 |
| `tests/test_api_coerce_v029.py`: la conversión que se niega a adivinar, la ruta con puntos y lo que mueve cada opción de `resolve_field` | 14 de 14 |
| `tests/test_api_jobs_v029.py`: un trabajo que termina, que falla, que se cae y que se mata desde fuera; cancelar matando también al nieto; el plazo con un destino que coopera y otro que no; sin plazo; `Busy`; los ganchos; `pythonpath`; nada de un programa en el hijo; el destino que pickle no puede llevar | 19 de 19 |
| `tests/test_api_job_progress_v029.py` (`SERIAL_LANE`): las carreras de Windows de Slip2D (v0.1.198 y v0.1.482) y los campos extra con el freno | 10 de 10 |
| `tests/test_api_bridge_v029.py`: de ida y vuelta por un `BridgeServer`, el testigo y el protocolo, el descubrimiento con dos programas en la misma carpeta, y el enrutador | 14 de 14 |
| `tests/test_api_workspace_v029.py`: con lo de Slip2D por defecto, sobre el `Project`, y con los ganchos, sobre un modelo que no lo es | 15 de 15 |
| `test_core_layering_v10` y `test_core_layering_runtime_v10`, sin tocar: el segundo importa también todo `ogr_core.api` en un intérprete nuevo | pasan |
| Suite del núcleo entera, `--jobs 4` (Windows, Python 3.14.10) | 959 de 959, sin fugas |

Doce mutantes de `ogr_core/api`, uno a uno, con los tests `test_api_*` y el archivo restaurado byte
a byte después (SHA-256 igual): **mueren los doce**.

| Mutante | Fallan |
|---|---|
| El plazo de `cancel` ignorado | 2 |
| Un cambio de fase sin saltarse el freno | 1 |
| Los campos extra pisan la cuenta | 1 |
| Sin `on_end` | 2 |
| Sin `loading` | 1 |
| El hijo sin el árbol del núcleo en su `PYTHONPATH` | 16 |
| El descubrimiento sin filtrar por protocolo | 2 |
| El saludo sin mirar el protocolo | 1 |
| El código del mensaje no cruza el cable | 3 |
| `lister` ignorado | 1 |
| `undo_step` ignorado | 2 |
| `WorkspaceNames` ignorado | 1 |

**La regla 8**, el 2026-11-24 en Windows, contra la rama `armazon-operaciones` en `0.2.9.dev0`:
`eeee542` y `96ee4ee` tienen el mismo `ogr_core` (entre los dos solo cambia este changelog).

| Qué | Resultado |
|---|---|
| OGR FEM2D `1a3d97f` (su v0.0.12, fija `v0.2.8`) **entera**, con `--dev-core` | 660 de 660, ninguna fuga, código 0. `shared: ogr_core 0.2.9.dev0 … @ eeee542`, `DEV CORE` antes y después. Su árbol, limpio antes y sin un archivo cambiado durante la corrida (17:41–17:48) |
| OGR Slip2D `ffd1dfc` (su v0.1.488, fija `v0.2.7`) **entera**, con `--jobs 4`, `--dev-core` y fuera de pantalla | 7584 casos: 7582 pasan, 0 fallos, 2 saltados (los de la plataforma, como en la 0.2.8), ninguna fuga, código 0. `shared: ogr_core 0.2.9.dev0 … @ 96ee4ee`, `DEV CORE` antes y después. Su árbol, limpio antes y sin un archivo cambiado durante la corrida (18:01–18:08) |
| CI de la PR 35 | todos los trabajos en verde, también los dos programas contra el núcleo de la PR (Linux) |

**Una primera corrida de OGR FEM2D no cuenta.** Contra su `fc3972e` dio 657 de 657, pero su
sesión cambió cinco archivos mientras corría (a las 17:09:34; subía su fijación a `v0.2.8`), uno de
ellos un test. Se repitió cuando cerró ese trabajo en `1a3d97f`.

Antes de escribir la §2 se comprobó en el código de los dos programas que ninguno importa
`ogr_core.api` (la lección de la nota de FEM2D sobre la 0.2.8: un aviso a un programa se contrasta
con su código).
