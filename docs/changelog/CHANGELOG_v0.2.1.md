# OGR Core v0.2.1

**Dos arreglos del runner compartido**, los dos pedidos por lo que encontró la adopción del núcleo
en los programas. El resto del núcleo no cambia: `git diff v0.2.0 -- ogr_core` solo toca
`ogr_core/testing/` y el número de versión.

Es la primera versión que se hace con el núcleo ya compartido: OGR Slip2D lo fija desde su
v0.1.473 y OGR FEM2D desde su v0.0.3.

## 0. Lo que se encontró

- **En Linux, la primera `QApplication` cambia el locale del proceso, y el detector lo contaba
  como fuga del archivo que la crea.** La CI de OGR Slip2D lo nombra en todas sus corridas de Linux
  desde su v0.1.377, y también con este núcleo instalado desde la etiqueta (run 44391776432, commit
  `dbc316c`, Python 3.11, 3.12 y 3.13):

  ```
  === test_action_inventory_v1195.py ===  (2/495)
    ✗ [LEAK] locale: LC_CTYPE=C.UTF-8;LC_NUMERIC=C;LC_TIME=C;LC_COLLATE=C;LC_MONETARY=C;… → C.UTF-8
  ```

  Ese archivo es el primero de la suite que construye una `QApplication`; el anterior no la
  construye y no se nombra. En Windows no sale. La causa es de Qt y está en su documentación
  («Locale Settings», en `QCoreApplication`): en Unix, al construirse llama a
  `setlocale(LC_ALL, "")`. Python arranca con solo `LC_CTYPE` tomado del entorno y el resto en `C`;
  después de esa llamada todas las categorías son las del entorno. No lo hace el test ni el
  programa, y pasa una sola vez por proceso: va a la lista de la suite. Pedido por OGR Slip2D.
- **OGR FEM2D no la ve porque no usa Qt**: ni sus tests ni su paquete importan PySide6. No había
  nada que explicar en su CI.
- **Lo que no se ha confirmado: Qt, en Linux, desde aquí.** Esta máquina es Windows y el núcleo no
  instala Qt. La regla es la hipótesis puesta en código: solo deja pasar el paso exacto de «como
  arranca el intérprete» a «el locale del entorno», en el archivo que crea la aplicación. Si en
  ese archivo otra cosa moviera el locale, los valores no coincidirían y la fuga seguiría
  saliendo. **La confirmación es la CI de Slip2D cuando fije esta versión.**
- **Analizar la cadena del locale habría sido un error.** La primera idea era leer
  `LC_CTYPE=…;LC_NUMERIC=…` y comprobar categoría a categoría. Cada plataforma lo escribe a su
  manera (glibc, macOS y Windows no coinciden), y la regla habría valido para las máquinas en las
  que se escribió. Se mide: un intérprete nuevo, con el entorno de este proceso, dice cómo arranca
  y qué queda al adoptar el locale del entorno.
- **Las reglas de la lista solo sabían qué módulos se importaron por primera vez.** Importar Qt y
  crear la aplicación son dos momentos, y en un trozo de `--jobs` pueden caer en dos archivos
  (ya lo decía la entrada de `builtins.qApp`). Ahora una regla sabe también si la aplicación se
  creó en este archivo (`FIRST_APPLICATION`).
- **El runner no contaba los tests `async def` entre los declarados.** Salió al escribir el test
  del caso `async` (PR 2): el bucle los ejecuta, para hacerlos fallar, pero el recuento previo
  miraba solo los `def`. Un test `async` no aparecía en `--list`, el progreso de su corrida pasaba
  del 100 % y una corrida con `--jobs` decía que los trozos habían corrido un test que la fuente no
  declaraba, en vez de decir que el test fallaba.
- **Un programa no puede salir del todo en verde con `--dev-core` si tiene tests sobre lo que
  fija.** Primer uso real de la opción, con los dos programas: sin ella el runner se niega y dice
  cómo seguir; con ella corre y lo avisa antes y después de los totales. Pero tres tests de FEM2D
  y cuatro de Slip2D fallan por construcción en una corrida así (§3), y no todos por lo mismo:
  unos comparan la versión importada con la fijada; otros relanzan el runner en otro proceso, y
  ese no recibe la opción; y uno lee `dev`, de `0.2.1.dev0`, como una palabra en inglés en
  pantalla. Queda para decidir con la forma de trabajar: o esos tests saben que la corrida es de
  desarrollo, o se aceptan como rojos conocidos, que es lo que no se quiere.
- **La regla 8 no dice cómo se corre la suite de cada programa, y «sin argumentos» se lee como
  «en serie».** Quiere decir sin filtrar. La primera corrida de Slip2D para esta versión se lanzó
  en serie y sin `QT_QPA_PLATFORM=offscreen`: abrió las ventanas del programa en pantalla y a los
  cuatro minutos nombraba una fuga que era de cómo se lanzó
  (`env:QT_QPA_PLATFORM: (absent) → offscreen`). Se paró y no cuenta; la que cuenta es la segunda
  (§3). El comando de cada programa está en su `AGENTS.md`: en Slip2D, `--jobs 4`, y en serie
  cada 100 commits.
- **Preparar una versión del núcleo en su árbol habitual habría dejado sin suite a los
  programas.** Sus entornos lo tienen instalado en editable: en cuanto ese árbol dice 0.2.1, sus
  runners se niegan (fijan 0.2.0). Esta versión se ha preparado en un `git worktree` aparte, con el
  árbol habitual en `main`.

## 1. Qué cambia

- `ogr_core/testing/leaks.py`:
  - una entrada nueva en la lista de la suite, `locale`, con la regla
    `ADOPTED_WITH_THE_FIRST_APPLICATION`: permitido solo en el archivo que crea la primera
    `QApplication`, y solo el paso de como arranca el intérprete al locale del entorno. El mismo
    cambio en cualquier otro archivo, otro locale, o partir de otro sitio, siguen siendo fuga; y
    también si no se puede medir. La lista pasa de 15 a 16 entradas;
  - `environment_locale()`: los dos valores, medidos en un intérprete nuevo;
  - `FIRST_APPLICATION`, entre lo que una regla recibe como «lo que este archivo trajo por primera
    vez». La instantánea apunta que la aplicación existe con una marca que no se compara.
- `ogr_core/testing/runner.py`: `_declared_tests` cuenta también los `async def`.
- Tests: 693 casos (682 en `main` tras la PR 2). Ocho nuevos de la entrada de locale en
  `tests/test_leaks_v020.py`, uno de ellos de extremo a extremo con el locale de la máquina que lo
  corre, sin ningún literal; tres nuevos del recuento en `tests/test_runner_exit_v10.py`. Los cinco
  del caso `async` de la PR 2 salen en una versión por primera vez.
- `AGENTS.md` y los README: ya no hay salvedad sobre Slip2D. Los dos programas fijan el núcleo, y
  el código de `ogr_core` solo se cambia en este repositorio.

## 2. Lo que tiene que cambiar cada programa (regla 10)

- **OGR Slip2D**: fijar `v0.2.1`. Con eso desaparece de su CI de Linux la fuga de locale. No tiene
  que cambiar nada más, y sus otros fallos de Linux no son de esto.
- **OGR FEM2D**: nada. Puede seguir en `v0.2.0` o subir.
- Ningún nombre desaparece ni cambia de firma: `diff()`, `snapshot()` y las reglas existentes
  reciben lo mismo. Una regla propia de un programa que quiera saber si la aplicación se creó en
  el archivo puede mirar `FIRST_APPLICATION in new`.

## 3. Pruebas

Windows, Python 3.14.7, de una en una.

| Qué | Resultado |
|---|---|
| Suite del núcleo, en serie | 693 de 693, código 0, ninguna fuga |
| Suite del núcleo, `--jobs 4` | 693 de 693, código 0, ninguna fuga |
| Suite del núcleo, con el Python del `.venv` de FEM2D (sin Qt ni matplotlib) | 693 de 693 |
| El test de extremo a extremo del locale, en esta máquina | Pasa: aquí el intérprete arranca en `LC_COLLATE=C;LC_CTYPE=English_United States.1252;…` y adopta `English_United States.1252`; con la aplicación creada no es fuga, sin ella y con otro locale sí |
| OGR FEM2D `d2e6fca` contra esta versión, como `0.2.1.dev0` y con `--dev-core` | 186 de 189, ninguna fuga; los tres que fallan, abajo |
| OGR Slip2D `dbc316c` contra esta versión, igual, entera y en serie, fuera de pantalla (PySide6 6.11.1) | 7525 de 7531, 2 saltados, ninguna fuga; los cuatro que fallan, abajo |

**Dientes.** Diez errores metidos a propósito, sobre una copia: nueve en `leaks.py` (no decir
nunca que la aplicación se creó aquí, decirlo en todo archivo posterior, no mirar si se creó, dejar
pasar cualquier locale, dejar pasar cuando no se puede medir, no mirar de dónde se parte, devolver
los dos valores cambiados de sitio, quitar la entrada, comparar la marca como un valor más) y uno
en `runner.py` (no contar los `async def`). Mueren los diez. El de la marca se rehízo: en su
primera forma no cambiaba nada, porque una clave vista por primera vez nunca es un cambio; la
forma que sí cambia el comportamiento es que la marca desaparezca, y esa la caza su test.

**OGR FEM2D con `--dev-core`.** Los 186 tests que pasan son los de siempre. Los tres que fallan
son de `test_project_setup_v001`, y los tres por lo mismo: comprueban el núcleo que el programa
fija.

- `test_the_core_is_the_pinned_distribution` y `test_the_banner_names_both_trees` esperan
  `ogr_core 0.2.0`, y la corrida va contra `0.2.1.dev0`. Es lo que esos tests deben decir.
- `test_a_python_without_the_core_is_refused` arranca un Python «sin núcleo», que en esta corrida
  hereda el `PYTHONPATH` con el que se le dio el de desarrollo: es de cómo se montó la prueba.

**OGR Slip2D con `--dev-core`.** Los 7525 que pasan y los 2 saltados son los de su última serie
en verde (7529 de 7531, en `07524e8`) menos estos cuatro, todos por correr con `0.2.1.dev0`:

- `test_the_imported_core_is_the_version_pyproject_pins` (`test_version_consistency_v176`) y
  `test_the_pin_is_the_core_that_is_imported` (`test_runner_wrapper_v1473`) comparan la versión
  importada con la fijada: `('0.2.1.dev0', '0.2.0')`.
- `test_a_file_that_left_a_dialog_ends_with_zero` (`test_shutdown_release_v1422`) relanza el
  runner en otro proceso, sin `--dev-core`, y ese runner se niega: `WRONG SHARED TREE`.
- `test_the_window_and_every_dialog_of_the_census` (`test_labels_spanish_v1321`): el diálogo
  «Acerca de» dice `ogr-core 0.2.1.dev0`, y el test cuenta `dev` como texto en inglés. Con
  `0.2.0` ese texto pasa.

La corrida no se apuntó como serie en verde de Slip2D, y no es evidencia para publicarlo: lo dice
ella misma (`DEV CORE … NOT evidence for a release`).

### Sin probar

- **La entrada de locale con Qt en Linux** (§0). La prueban la CI de este repositorio, que corre
  en Linux el test de extremo a extremo sin Qt, y la de Slip2D cuando fije esta versión.
- **Los programas contra la versión etiquetada.** Lo de arriba es contra `0.2.1.dev0`, que es el
  mismo código con otro número. La suite de cada programa con la `v0.2.1` fijada es de la versión
  del programa que la fije.

## 4. Queda abierto

- Qué hace un programa con sus tests de «el núcleo es el fijado» en una corrida con `--dev-core`,
  y cómo llega la opción a un runner que un test relanza.
- La regla 8, dicha de forma que no se confunda «sin filtrar» con «en serie», y con el comando de
  cada programa.
- La versión de desarrollo en `main` entre dos etiquetas (`0.3.0.dev0`), y qué changelog pide
  `test_version_consistency_v10` a una `.devN`.
- `ogr_core/report` usa matplotlib, que el núcleo no declara (viene de la v0.2.0).
