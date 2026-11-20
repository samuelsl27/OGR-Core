# OGR Core v0.2.3

**La forma de trabajar con un núcleo y varios programas, segunda parte**: la CI de este
repositorio corre la suite entera de un programa contra el núcleo de cada commit, y compara lo que
fija cada programa con lo que dice `docs/consumidores.md`. Y dos cambios pequeños del runner: pone
la carpeta de cada archivo de test en la ruta de importación, se arranque como se arranque, y su
consejo ante un núcleo que no es el fijado deja de nombrar el árbol en editable. El código de
cálculo no cambia: `git diff v0.2.2 -- ogr_core` solo toca `ogr_core/testing/runner.py` y el
número de versión.

Es compatible: ningún programa tiene que cambiar nada.

## 0. Lo que se encontró

- **La tabla de programas se quedó atrás el mismo día que se escribió, con todos los tests en
  verde.** OGR FEM2D pasó a fijar la `v0.2.2` (su v0.0.4, `86c88e3`) y OGR Slip2D también (su
  v0.1.475, `55a1771`), y la tabla siguió diciendo `v0.2.0` y `v0.2.1`. Era lo esperado y estaba
  escrito: el test de la tabla comprueba su forma, y la verdad está en otro repositorio. Ahora lo
  comprueba la CI, que sí puede leerlo.
- **Lo que la v0.2.2 dejó sin probar está probado: los tests de los programas, cambiados de
  verdad, salen en verde de una corrida con `--dev-core`.**
  - OGR FEM2D v0.0.4: 202 de 202 contra la etiqueta instalada y 202 de 202 contra este árbol en
    `0.2.3.dev0` (`b804724`), con `DEV CORE` antes y después de los totales. Su CI (run
    44737259223, sobre `5bd33c0`): quince trabajos en verde, en Linux, Windows y macOS.
  - OGR Slip2D v0.1.475: 7539 de 7541, 0 fallos y 2 saltados de la máquina, sin fugas, en las dos
    corridas (lo dice el informe de su sesión; aquí no se han repetido).
- **Por qué el censo de Slip2D leía `ogr-core 0.2.2.dev0` como inglés**: la palabra `dev` está en
  su vocabulario inglés porque sale de la clave `std dev` de su ventana de estadística. Lo
  encontró su sesión. Una excepción por esa palabra habría cegado el censo justo ahí; la suya es
  la cadena exacta `ogr-core <versión del núcleo importado>`, acotada, y nada más.
- **El runner de un programa se niega con el commit que se etiqueta.** Ese commit dice `X.Y.Z`, y
  el programa todavía fija la versión anterior. Sin `--dev-core` no es su fijación; con
  `--dev-core` tampoco vale, porque la opción solo acepta una `.devN`. Es lo correcto en un
  programa (una versión con número final que nadie fija no es un núcleo en desarrollo), pero deja
  sin medir justo el commit que recibe la etiqueta. Por decisión de la propietaria, la CI corre
  entonces la suite contra una **copia** de `ogr_core` cuya única diferencia es la cadena de
  versión, `X.Y.Z.dev0`, y lo dice en el registro. La alternativa era no correr y fiarse de la
  corrida del commit anterior, sin nada que compruebe que el commit del número no lleva otra cosa.
- **Un rojo por una razón conocida enseña a no mirar.** La CI de Linux de OGR Slip2D tiene cinco
  fallos suyos, aparcados. Su trabajo aquí no se enciende hasta que estén resueltos, y eso queda
  escrito con su porqué donde un test lo lee (`NOT_YET`): el día que el trabajo exista, el test
  falla si la excusa sigue ahí.
- **La comparación de fijaciones no depende de eso.** Leer el `pyproject.toml` de Slip2D no
  necesita que su suite esté en verde en ningún sitio: se compara ya.
- **Anomalía: el test de las cabeceras de licencia no veía `.github/`.**
  `tests/test_license_v10.py` buscaba con `glob("**/*.py")`, que no entra en carpetas que empiezan
  por punto. El script nuevo (`.github/scripts/program_suite.py`) lleva su cabecera SPDX, pero
  ningún test habría fallado sin ella. Medido en ese commit: 169 archivos con el patrón del test,
  170 contando las carpetas ocultas. Hasta entonces no había ningún `.py` ahí. Se reportó antes de
  tocarlo y se arregla en un cambio aparte (§1, «Las carpetas ocultas»).
- **No era solo ese test.** Al mirarlo salieron otros dos con el mismo punto ciego:
  `test_python_floor_v10.py`, que busca con el mismo patrón la sintaxis que Python 3.11 no acepta,
  y `test_no_vendor_names_v10.py`, que solo recorría `ogr_core` y `tests`. Ninguno de los tres
  veía el script.
- **Pedirle a `glob` lo oculto no es el arreglo, y preguntarle a git tampoco.** Con
  `include_hidden` entra en todo: un `.venv` dentro del árbol, como el que tienen los programas,
  son miles de archivos ajenos sin cabecera. Y `git ls-files` no ve un archivo hasta que se añade,
  que es justo el caso que el test de licencia quiere cazar. Queda una lista declarada, con un
  test que impide que una carpeta oculta con código se quede sin decidir.
- **Que un test pueda importar a otro depende de cómo se arranque el runner, y nada lo
  garantiza.** Con `python tests/_runner.py` el intérprete pone `tests/` la primera en la ruta de
  importación; arrancado de otra manera, no. Salió al hacer el cambio de las carpetas ocultas: la
  suite entera dio 783 de 784, porque `test_runner_shutdown_v020.py` relanza el runner con `runpy`
  sobre `test_license_v10`, que ahora importa `test_project_sources_v023` y allí no lo encontraba
  (`ModuleNotFoundError`). Es determinista y más viejo que ese cambio: el test de la CI de los
  programas (arriba) ya importaba `test_consumers_v022` de la misma manera, y no falló porque
  nadie relanza ese archivo. Se reportó antes de tocarlo. Arreglado donde estaba la diferencia, en
  el lanzamiento de ese test, que ahora pone la carpeta como la pone el intérprete. Que lo
  garantice el runner compartido queda pendiente (§4): lo necesitan los tres repositorios.
- **El problema de la ruta era más ancho que el test que falló.** Leyendo el runner salieron tres
  formas de arrancar en las que un test no podía importar a otro: con `runpy`; en los trozos de
  `--jobs` de una carpeta sin `_runner.py` propio, que arrancan por la ruta del módulo del runner;
  y en un `main()` conducido por un test sobre una carpeta suya. El runner pone ahora la carpeta
  de cada archivo, la primera, mientras ese archivo carga y corre, y la quita con el resto de la
  ruta al terminar el archivo, como ya hacía. En una corrida normal la carpeta ya está y no se
  añade nada. La línea que se había puesto en `test_runner_shutdown_v020` sobra y se quita: ese
  test pasa a ser una prueba más.
- **Error propio, cazado por un test de la v0.2.0.** La primera redacción del consejo de
  «WRONG SHARED TREE» nombraba `--dev-core` en todos los rechazos. La suite entera dio 794 de 795:
  `test_and_the_message_names_the_option` (`test_runner_dev_core_v020`) protege que la opción solo
  se nombre donde serviría, y un núcleo anterior al fijado no debe recibir esa pista. El test
  tenía razón y no se tocó. El consejo dice ahora solo cómo conseguir la versión fijada; la
  opción sigue nombrada en la línea del paquete al que le serviría, como desde la v0.2.0.
- **Los programas tienen el mismo patrón.** OGR FEM2D busca igual
  (`tests/test_project_setup_v001.py`) y tiene un `.py` en una carpeta oculta,
  `.github/scripts/wheel_check.py`, que lleva su cabecera sin que nada lo compruebe. OGR Slip2D
  busca igual (`tests/test_license_v143.py`) y hoy no tiene ningún `.py` oculto. Leído, no
  tocado: es de sus sesiones. OGR FEM2D lo arregló el mismo día en su v0.0.5 (`a4965b7`).
- **Un diente que faltaba, encontrado al meter los errores.** El script mira de dónde sale
  `ogr_core` antes de arrancar la suite. Quitar esa comprobación no hacía fallar ningún test: con
  el `PYTHONPATH` bien ordenado nunca tiene nada que decir. Tiene ahora su caso propio (un
  programa con un núcleo suyo en su carpeta, con el mismo número).
- **El traspaso a OGR Slip2D decía que este árbol local estaba en la 0.2.0.** Era verdad cuando
  se escribió y dejó de serlo antes de que su sesión lo leyera (pasó a `main` cuando OGR FEM2D
  dejó de usarlo en editable). Su sesión lo miró en vez de creérselo, como pedía el propio
  traspaso, y lo reportó.

## 1. Qué cambia

**`ogr_core/testing/runner.py`**

- La carpeta de cada archivo de test está en `sys.path`, la primera, mientras ese archivo carga y
  corre (`_on_path` decide si ya estaba, se escriba como se escriba esa entrada). Se quita al
  devolver la ruta, al final de cada archivo.
- El consejo de «WRONG SHARED TREE» pasa de «Install the pinned version, or check out its tag in
  the editable tree» a decir cómo se instala la versión que fija `pyproject.toml`. Lo pidió
  OGR FEM2D. «WRONG TREE», que habla de los paquetes del propio programa, no cambia.
- `tests/test_runner_v023.py`, nuevo (12 casos): un test que importa a otro carga en las cuatro
  formas de arrancar; en la normal no se añade nada; la ruta queda como estaba; y el consejo.

**`.github/scripts/program_suite.py`**, nuevo. Lee `docs/consumidores.md` con el lector de
`tests/test_consumers_v022.py` y hace dos cosas:

- `pins "Programa=carpeta" …`: cada programa de la tabla fija, en su `pyproject.toml`, la etiqueta
  que dice la tabla. También falla si un programa de la tabla no se le da, si se le da uno que no
  está, o si un programa no fija una versión exacta.
- `run "Programa" carpeta`: la suite entera de ese programa, **con el comando de la tabla**, con
  el núcleo de este árbol por delante del instalado (`PYTHONPATH`). Antes compara su fijación con
  la tabla y comprueba que `ogr_core` sale del núcleo de la corrida. Qué le pide al runner del
  programa depende de lo que diga este árbol:

  | Este árbol dice | El programa fija | Qué hace |
  |---|---|---|
  | `X.Y.Z.devN`, de una versión posterior | `vA.B.C` | `--dev-core` |
  | `X.Y.Z` | la misma | nada: es el núcleo que el programa pide |
  | `X.Y.Z` | una anterior | copia con `X.Y.Z.dev0` y `--dev-core`, con un aviso en el registro |
  | cualquier otra cosa (un núcleo anterior al fijado, una candidata) | | se para, con el porqué |

**`.github/workflows/tests.yml`**, dos trabajos nuevos:

- `pins`: baja el `pyproject.toml` de la rama principal de cada programa y lo compara con la
  tabla. No instala nada.
- `fem2d`: baja OGR FEM2D, construye su wheel con el Rust del runner, lo instala (con el núcleo
  de su etiqueta), pone el módulo compilado en el árbol con el script del propio programa y corre
  su suite contra el núcleo del commit. Linux, Python 3.11.

Los dos usan las acciones que ya estaban vigiladas (`checkout@v7`, `setup-python@v7`).

**`tests/test_ci_programs_v023.py`**, nuevo (39 casos): cada programa de la tabla tiene su
trabajo o una razón escrita, y la razón no sobrevive al trabajo; el trabajo le pide el comando a
la tabla y no corre `tests/_runner.py` ni dice `--dev-core` él mismo; la comparación de
fijaciones cubre a todos; cada forma de correr es lo que `runner.shared_problems` acepta de
verdad, preguntado sobre núcleos inventados; la copia cambia la cadena de versión y nada más; y
una corrida con un programa inventado hace lo que dice.

**Las carpetas ocultas** (cambio aparte, solo tests)

- `tests/test_project_sources_v023.py`, nuevo (11 casos). `python_files()` da todos los `.py`
  del proyecto: los de siempre, más los de las carpetas ocultas que llevan código, que se nombran
  por su ruta (`HIDDEN_WITH_CODE`, hoy `.github`). `undecided()` da las carpetas ocultas con algún
  `.py`, a cualquier profundidad, que ni se leen ni están en `HIDDEN_NOT_OURS` con su porqué
  (`.git`, `.venv`); un test exige que no haya ninguna.
- `test_license_v10.py`, `test_python_floor_v10.py` y `test_no_vendor_names_v10.py` toman sus
  archivos de `python_files()`. Comparado archivo a archivo: cada uno lee lo mismo que antes y uno
  más, el script de la CI. El de marcas deja de nombrar dos carpetas: contenían todos los demás
  `.py` del repositorio, así que no entra nada más.
- Solo usa la biblioteca estándar: el trabajo de licencia de la CI importa `test_license_v10` en
  un Python sin nada instalado.
- `tests/test_runner_shutdown_v020.py`: el proceso que relanza pone `tests/` la primera en la
  ruta, como una corrida real (§0). Lo que el test protege no cambia.

**Documentos**

- `docs/consumidores.md`: las dos filas, en `v0.2.2`. Qué lee la CI de esta tabla y qué pasa
  cuando un programa sube su fijación. En «Cambios en curso» entran el mensaje «WRONG SHARED TREE»
  y el test de las acciones de la CI.
- `AGENTS.md`: qué corre la CI y qué sigue a mano.

## 2. Lo que tiene que cambiar cada programa (regla 10)

Nada.

Un test de un programa que arrancaba el runner de otra manera y por eso ponía él mismo `tests/` en
la ruta ya no necesita hacerlo; puede dejarlo como está.

Una recomendación, que no obliga: el test de cabeceras de licencia de cada programa busca con el
mismo patrón que el de aquí y tampoco entra en las carpetas ocultas (§0). OGR FEM2D tiene ya un
`.py` en una.

Lo que cambia para quien trabaja en un programa: **cuando sube la versión que fija, el trabajo
`pins` de este repositorio se pone en rojo** hasta que aquí se corrige su fila. Es el aviso, no
un fallo del programa. Y la CI de este repositorio baja la rama principal del programa: si esa
rama tiene la suite en rojo, el trabajo de ese programa aquí también.

## 3. Pruebas

Windows, Python 3.14.7, de una en una.

| Qué | Resultado |
|---|---|
| Suite del núcleo, `--jobs 4` | 773 de 773, código 0, ninguna fuga (734 de la v0.2.2 y 39 nuevos) |
| `pins` contra las carpetas de los dos programas (`55a1771` y `86c88e3`, lo que hay en GitHub) | los dos fijan lo que dice la tabla, código 0. Sin la carpeta de Slip2D: código 1 |
| OGR FEM2D `86c88e3` entera a través del script, con su `.venv` | 202 de 202, código 0. `shared: ogr_core 0.2.3.dev0 …`, `DEV CORE` antes y después |
| Lo mismo contra una copia de este núcleo que dice `0.2.3` (el caso del commit del número) | 202 de 202, código 0. El aviso, `shared: ogr_core 0.2.3.dev0 … (installed, no git tree)`, y la copia borrada al terminar |

**Dientes.** Veintiocho errores metidos a propósito, de uno en uno, y mueren los veintiocho.
Cuatro en la forma de correr (aceptar una `.devN` de la versión fijada, correr sin copia una
versión que nadie fija, pedir `--dev-core` con el núcleo fijado, correr contra un núcleo
anterior). Cuatro en la copia (que traiga `__pycache__`, que toque otro archivo, que cambie el
original, que acepte una versión dicha dos veces). Cuatro en el comando (no añadir `--dev-core`,
perder las variables, aceptar una suite filtrada, aceptar otro programa en vez de `python`).
Cuatro en la comparación de fijaciones. Seis en la corrida (no comparar la fijación, el núcleo
por detrás de lo que ya había en el `PYTHONPATH`, no mirar de dónde sale, perder el código de
salida, dejar la copia, no avisar de ella). Seis en el flujo y en la lista de excusas. Uno salió
vivo la primera vez, y es el hallazgo de §0: no mirar de dónde sale el núcleo.

**Los trabajos nuevos en GitHub** (CI de la PR 6 sobre `78bdc3b`, run 44756012590): los seis en
verde. El Rust del runner basta para construir OGR FEM2D con `pip`, sin añadir ninguna acción.
OGR FEM2D `86c88e3`, 202 de 202 en Linux con Python 3.11, con
`shared: ogr_core 0.2.3.dev0 …/core/ogr_core` y `DEV CORE` antes y después; las dos fijaciones,
iguales a la tabla; la suite del núcleo, 773 de 773 en 3.11, 3.12 y 3.13.

**Las carpetas ocultas** (cambio aparte).

| Qué | Resultado |
|---|---|
| Suite del núcleo, `--jobs 4`, antes de corregir el lanzamiento de `test_runner_shutdown_v020` | 783 de 784: el fallo de §0 |
| Suite del núcleo, `--jobs 4`, corregido | 784 de 784, código 0, ninguna fuga (773 y 11 nuevos) |
| Qué lee cada uno de los tres tests, antes y después, archivo a archivo | lo mismo y uno más: `.github/scripts/program_suite.py` |
| Las comprobaciones del trabajo de licencia de la CI, en un Python sin nada (`python -I`) | 0 fallos |

Dieciocho errores metidos a propósito, de uno en uno, y mueren los dieciocho. Tres devuelven cada
test a su búsqueda de antes. Dos en la lista (ninguna carpeta oculta con código; `.github`
excusada en vez de leída). Tres en la lectura (entrar en toda carpeta oculta, tomar una carpeta
por su nombre en cualquier sitio, leer `__pycache__`). Cinco en las carpetas sin decidir. Uno en
la comprobación de cabeceras. Y cuatro sobre el script de la CI, que son el caso real: sin su
cabecera, sin su línea de copyright, con una marca comercial y con sintaxis que Python 3.11 no
tiene; cada uno hace fallar el test que le toca.

**El runner** (los dos cambios de `ogr_core`).

| Qué | Resultado |
|---|---|
| Suite del núcleo, `--jobs 4`, con la primera redacción del consejo | 794 de 795: el error propio de §0 |
| Suite del núcleo, `--jobs 4`, corregido | 796 de 796, código 0, ninguna fuga (784 y 12 nuevos) |
| OGR FEM2D `7de973a` (su v0.0.5, en su rama, sin fusionar) entera contra este árbol, con `--dev-core` | 205 de 205, código 0, ninguna fuga. `shared: ogr_core 0.2.3.dev0 …`, `DEV CORE` antes y después |

Catorce errores metidos a propósito en el runner, de uno en uno, y mueren los catorce. Cinco en la
ruta (no poner la carpeta, que es el runner de la v0.2.2; ponerla siempre; ponerla la última; no
quitarla; poner otra carpeta). Tres en `_on_path`. Seis en el consejo y en la pista (el texto de
la v0.2.2, `--dev-core` en todos los rechazos, no decir cómo instalar, no nombrar la opción donde
sirve, nombrarla para un núcleo anterior, y seguir corriendo después del rechazo).

**La regla 8, sobre el commit `112d388`** (el árbol en `0.2.3.dev0`, con los dos cambios del
runner).

| Qué | Resultado |
|---|---|
| OGR Slip2D `55a1771` (su v0.1.475) **entera** contra ese commit, con `--jobs 4`, `--dev-core` y fuera de pantalla | 7541 casos: 7539 pasan, 0 fallos, 2 saltados, ninguna fuga, código 0. `shared: ogr_core 0.2.3.dev0 … @ 112d388`, `DEV CORE` antes y después |
| OGR FEM2D entera contra ese árbol, con `--dev-core` | 205 de 205 sobre `7de973a` (su v0.0.5, entonces en su rama), a mano en Windows; 202 de 202 sobre `86c88e3` (su `main` entonces), en la CI en Linux |
| CI de este repositorio sobre `112d388` (run 44772275432) | los seis trabajos en verde: 796 de 796 en Python 3.11, 3.12 y 3.13; licencia, 0 fallos; las dos fijaciones, iguales a la tabla |
| Suite del núcleo con el número `0.2.3` ya puesto, `--jobs 4` | 796 de 796, código 0, ninguna fuga |

Los dos saltados de OGR Slip2D son de la máquina, los de siempre: uno es de POSIX y el otro pide
el banco de verificación, que no está aquí. Es la primera suite entera de OGR Slip2D que sale sin
ningún fallo contra un núcleo sin etiquetar con cambios en el runner: con la v0.2.2 fallaban tres
por construcción.

### Sin probar

- **Los programas contra la versión con su número final**, a mano: todo lo de arriba es contra
  `0.2.3.dev0`. El commit que pone `0.2.3` solo cambia el número y los documentos, y es la CI
  quien lo mide, con la copia `.dev0` (abajo).
- **El caso del commit del número, en GitHub.** La copia con `.dev0` solo se ha probado en
  Windows; se da por primera vez en la CI de ese commit.
- **OGR Slip2D a través del script.** Su trabajo no está encendido y su suite entera no se ha
  corrido por aquí; lo que el script hace con su comando (la variable de Qt, `--jobs 4`) está
  probado con un programa inventado.
- **El núcleo fijado sin `--dev-core`** con un programa real: no hay hoy ningún commit de este
  repositorio que diga la versión que los programas fijan salvo la etiqueta.

## 4. Queda abierto

- **Si el trabajo de la CI vale como la corrida de la regla 8** para OGR FEM2D, o si antes de
  etiquetar se sigue corriendo también a mano. La CI corre en Linux; la corrida a mano, en
  Windows. No se ha cambiado la regla.
- **El trabajo de OGR Slip2D**, cuando su suite esté en verde en Linux.
- **Nada avisa aquí cuando un programa sube su fijación** hasta el siguiente commit o PR de este
  repositorio: la CI no corre sola.
- **Las carpetas ocultas en los programas**: los dos tienen el patrón que aquí se ha cambiado
  (§0). Si la lista de `test_project_sources_v023.py` debe vivir en el núcleo para los tres, sin
  decidir.
- De la v0.2.2 siguen: la regla única de «el núcleo no está copiado en el árbol del programa», la
  protección de `main`, y `matplotlib` sin declarar en `ogr_core/report`. `suite.toml` y el README
  de la suite están hechos (`samuelsl27/OGR-Suite`, `077ecb0`).
