# Quién usa OGR Core

Qué programas de la suite usan este núcleo, qué versión fija cada uno, qué cambios del núcleo
están en curso y para quién, y cómo se pide y se adopta un cambio. Las reglas están en
[`AGENTS.md`](../AGENTS.md); esto es el estado.

## Programas

| Programa | Repositorio | Núcleo que fija | Desde | Suite entera |
|---|---|---|---|---|
| OGR Slip2D | `samuelsl27/OGR-Slip2D` | `v0.2.10` | su v0.1.489 (`f1ba594`) | `QT_QPA_PLATFORM=offscreen python tests/_runner.py --jobs 4` |
| OGR FEM2D | `samuelsl27/OGR-FEM2D` | `v0.2.9` | su `6b3604c` (su v0.0.13) | `python tests/_runner.py` |

- **La verdad es el `pyproject.toml` de cada programa** (`ogr-core @ git+…@vX.Y.Z`). Esta tabla la
  repite para que se vea de un vistazo quién se queda atrás, y se corrige aquí cuando un programa
  sube su fijación. Un test de este repositorio (`tests/test_consumers_v022.py`) comprueba su
  forma, que cada versión fijada existe y que ningún comando filtra. Que coincide con el programa
  lo comprueba la CI, que es quien puede leer otro repositorio: el trabajo `pins` compara cada
  fila con el `pyproject.toml` de la rama principal del programa, y **se pone en rojo cuando un
  programa sube su fijación y esta tabla no se ha corregido**. Ese rojo se arregla aquí, en la
  fila.
- **La CI de este repositorio lee esta tabla** (`.github/scripts/program_suite.py`): de aquí salen
  el repositorio, la fijación y el comando de cada programa. Corre la suite entera de cada uno
  contra el núcleo de cada commit, en Linux y con Python 3.11. `tests/test_ci_programs_v023.py`
  falla si un programa de la tabla no tiene su trabajo ni una razón escrita para no tenerlo.
- **«Suite entera»** es el comando que el `AGENTS.md` del programa da para publicar, con el Python
  de su `.venv` y desde su carpeta. Es el de la regla 8: entera quiere decir sin filtrar (sin
  patrones, sin `-k`, sin `--fast`); `--jobs` no filtra. Contra un núcleo que se está cambiando se
  le añade `--dev-core` (abajo).
- Los dos programas tienen que poder fijar versiones distintas: por eso el núcleo va **instalado
  desde la etiqueta** en el `.venv` de cada uno, y no en editable desde un árbol común.

## Cambios del núcleo en curso

| Cambio | Para quién | Estado |
|---|---|---|
| Una sola regla para «el núcleo no está copiado en el árbol del programa» | Los dos | Sin decidir. Hoy cada programa tiene la suya en un test, y no dicen lo mismo |
| Un solo test de las acciones de la CI (el suelo de cada acción) | Los dos | Sin decidir. Hoy está copiado en los tres repositorios, cada copia con su lista |
| El lector DXF cuenta `skipped` por capa (en `DxfLayer`, como `entity_counts`), y no solo en todo el dibujo | OGR FEM2D | Sin pedir: no bloquea nada. FEM2D lo usaría para decir de qué capa viene cada entidad que el lector deja fuera (su nota del 2026-11-24 sobre la v0.2.8) |
| Los tests que leen «todos los `.py`» no entran en las carpetas ocultas | Los dos | Arreglado aquí en la v0.2.3, en sus tests. OGR FEM2D lo arregló en su v0.0.5 (`a4965b7`). OGR Slip2D usa el mismo patrón y hoy no tiene ningún `.py` oculto: pendiente |

Una fila sale de aquí cuando el cambio está en una versión etiquetada: desde entonces lo cuenta
su changelog.

## Cómo pide un programa un cambio del núcleo

El código de `ogr_core` solo se cambia en este repositorio. La sesión de un programa que necesita
algo del núcleo **no lo edita ni lo copia**: lo pide.

1. La petición es un escrito con lo que se encontró, la evidencia (la salida del runner, el
   archivo, la corrida de CI) y lo que el programa necesita. Lo lleva la propietaria a la sesión
   de OGR-Core.
2. El cambio se hace aquí, en una rama corta con su PR. Mientras dura, el núcleo dice una versión
   de desarrollo (`X.Y.Z.dev0`).
3. Antes de etiquetar se corre la suite entera de **cada** programa de la tabla contra ese núcleo
   (regla 8), no solo la del que lo pidió:

   ```bash
   # desde la carpeta del programa, con su .venv; el núcleo en curso, por delante del instalado
   PYTHONPATH=<árbol o worktree de OGR-Core> <suite entera del programa> --dev-core
   ```

   La corrida dice `DEV CORE` antes y después de sus totales y no es evidencia para publicar el
   programa. Sus tests y los runners que relancen lo saben por `OGR_DEV_CORE=1`. La CI hace esa
   misma corrida en Linux, en cada commit, para cada programa de la tabla.
4. Se etiqueta la versión, con su changelog, que dice **qué tiene que cambiar cada programa**.

## Cómo sube un programa la versión que fija

En un commit suyo y a propósito; nunca fija una rama.

1. `pyproject.toml`: `ogr-core @ git+https://github.com/samuelsl27/OGR-Core@vX.Y.Z`.
2. Su entorno, que no se entera solo:

   ```bash
   .venv/Scripts/python -m pip install --no-deps --force-reinstall "ogr-core @ git+https://github.com/samuelsl27/OGR-Core@vX.Y.Z"
   ```

   Sin `--no-deps` en lo que venga después: reinstalar el programa con sus dependencias trae el
   núcleo otra vez desde GitHub.
3. Lo que el changelog de esa versión del núcleo le pida.
4. Su suite entera, que ahora mide el núcleo fijado: la cabecera del runner lo nombra
   (`shared: ogr_core X.Y.Z …`) y se niega si no es ese.
5. La fila de la tabla de arriba, que se corrige en este repositorio. Hasta entonces el trabajo
   `pins` de su CI está en rojo.

## Versiones del núcleo

- `X.Y.Z` es una versión publicada: tiene etiqueta `vX.Y.Z` y changelog.
- `X.Y.Z.devN` es el núcleo camino de `X.Y.Z`. Es lo que dice `main` entre dos etiquetas, y el
  runner de un programa se niega con él si no se le pide con `--dev-core`.
- Mientras la serie sea 0.x: un cambio **incompatible** (un programa tiene que cambiar código para
  seguir funcionando) sube el segundo número, y se avisa con al menos una versión de margen: la
  versión anterior ya dice qué va a cambiar y sigue aceptando lo de antes. Uno **compatible** sube
  el tercero.
