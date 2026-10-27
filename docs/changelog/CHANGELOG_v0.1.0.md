# OGR Core v0.1.0

**El núcleo de la suite sale de OGR Slip2D a su propio repositorio.** Es `ogr_core` tal como quedó
en el commit **`2d68c29`** de OGR Slip2D (rama `dev/extraer-ogr-core`, fase F1 de su spec 009),
copiado sin cambios salvo `ogr_core/__init__.py` (la versión). Primera versión de una serie propia:
dentro de Slip2D el paquete llevó la versión del programa, de 0.1.0 a 0.1.370 (decisión P2 de la
spec 009).

## 0. Lo que se encontró

- **El censo de tests de la spec 009 se quedaba corto.** Contaba 36 tests movibles mirando solo las
  sentencias `import`, y siete cargan otro test por ruta (`spec_from_file_location`). Dos no pueden
  venir: uno carga un test que usa el motor de equilibrio límite y la interfaz, y otro lee la fuente
  de la interfaz. Vienen 34.
- **Un test no puede preguntar al sistema de importación si un paquete existe.** En una máquina con
  otra copia instalada en editable, `find_spec` contesta con ESA copia: la trampa de Slip2D v0.1.84.
  Por eso el runner nombra el árbol, y por eso los tests miran carpetas.
- **En un worktree el runner no sabía el commit** (`@ ?`): allí `.git` es un archivo que apunta al
  repositorio, y la rama vive en el directorio común. Ahora lo sigue, y también las referencias
  empaquetadas.
- **El runner, dentro de la distribución del núcleo, no puede instalar el `pytest` simulado al
  importarse**: importar un módulo del núcleo no debe tocar `sys.modules`. Lo instala `main()`.

## 1. Qué contiene

- `ogr_core/` de Slip2D `2d68c29`: geometría, materiales, cargas, soportes, proyecto, hidráulica,
  estadística, anotaciones, DXF, informes, y `ogr_core/fem/` con la malla, el generador, los solvers
  de filtración, los destinos de contorno, las líneas de corriente y los códigos `seepage.*`.
- `ogr_core/testing/runner.py`: el runner de la suite (decisión P4), movido del `tests/_runner.py`
  de Slip2D, con paquetes propios y compartidos, versión fijada leída de `pyproject.toml` y ganchos
  para la interfaz de cada programa.
- 34 tests de Slip2D movidos **sin tocar ningún valor ni tolerancia** (conservan su nombre, con la
  versión de Slip2D en la que nacieron), y los propios del núcleo: runner (selección, salida,
  procedencia, compartidos), licencia, nombres de productos (también los dos de elementos finitos),
  suelo de Python, acciones de CI, capas (censo estático y en tiempo de ejecución, con un modelo
  construido solo con el núcleo).
- `pyproject.toml` con las dependencias que el núcleo importa: numpy, scipy, shapely, ezdxf,
  reportlab y h5py. Sin Qt ni gráficas.

## 2. Pruebas

- **Suite entera, sin argumentos: 499 de 499, en 45 archivos** (`tree: …\OGR-Core`). Incluye los
  34 movidos, que en Slip2D pasaban con el mismo código (en el worktree de F1, 807 de 807 en los 59
  archivos que toca F1).
- No probado aquí todavía: la instalación en un entorno virtual limpio (`pip install -e .` sin
  PySide6). La hará la CI en cuanto el repositorio tenga este commit en GitHub.
- Lo que esta versión no prueba: que Slip2D funcione con ella. Eso es la fase F3 de la spec 009, y
  su suite entera es la prueba.
