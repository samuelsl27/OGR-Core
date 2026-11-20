# OGR Core v0.2.2

**La forma de trabajar con un núcleo y varios programas, primera parte**: una corrida con
`--dev-core` se lo dice a sus tests y a los runners que relanzan, `main` lleva una versión de
desarrollo entre dos etiquetas, y las reglas y el estado quedan escritos (`AGENTS.md`,
`docs/consumidores.md`). El código de cálculo no cambia: `git diff v0.2.1 -- ogr_core` solo toca
`ogr_core/testing/runner.py` y el número de versión.

Es compatible: ningún programa tiene que cambiar nada para seguir funcionando. Lo que cada uno
tiene que cambiar para salir en verde de una corrida con `--dev-core` está en §2.

## 0. Lo que se encontró

- **Confirmado: la entrada de locale de la v0.2.1 funciona con Qt real en Linux.** Era lo que esa
  versión dejó sin probar. La CI de OGR Slip2D v0.1.474 (`dba074c`, run 44696129877), con
  `ogr-core` v0.2.1 fijado e instalado desde la etiqueta, no nombra ninguna fuga en ninguno de sus
  tres trabajos de Linux (3.11, 3.12 y 3.13). Comprobado leyendo el log entero: ninguna línea
  `LEAK`, y las tres cabeceras dicen `shared: ogr_core 0.2.1 … (installed, no git tree)`. Con la
  v0.2.0 (`dbc316c`) cada trabajo terminaba con `Leaks: 1`. Los fallos que le quedan a esa CI son
  de Slip2D y no de esto.
- **`main` llevaba el número de su última etiqueta.** Después de etiquetar `v0.2.1`, `main` decía
  0.2.1, y lo habría seguido diciendo con el código cambiado. El runner de un programa compara
  números: un núcleo cambiado y sin etiquetar habría respondido por el etiquetado sin que nada lo
  dijera. La documentación del runner ya contaba, desde la 0.2.0, que «entre dos etiquetas `main`
  dice una versión de desarrollo»; no se había hecho nunca.
- **El test de versión no sabía qué es una versión de desarrollo.** Aceptaba casi cualquier cosa
  detrás de `X.Y.Z` (una candidata, una versión local) y pedía a una `.devN` un changelog con su
  propio nombre.
- **Los tests que fallan por construcción con `--dev-core` son de tres clases, y solo una era del
  runner.** Lo anotó la v0.2.1 (tres en FEM2D, cuatro en Slip2D):
  - los que relanzan el runner en otro proceso, que no recibe la opción y se niega. Esto sí era
    del runner, y se arregla aquí: el test de Slip2D (`test_a_file_that_left_a_dialog_ends_with_zero`)
    pasa con esta versión sin que Slip2D cambie nada (§3);
  - los que comparan el núcleo importado con el fijado. En una corrida así no lo es, y el test no
    tenía cómo saber en qué corrida estaba. Ahora puede preguntarlo; cambiarlo es de cada programa;
  - los que son de cómo está montado el test o el programa: un Python «sin núcleo» que hereda el
    `PYTHONPATH` de la corrida (FEM2D), y `dev` leído como una palabra en inglés en «Acerca de»
    (Slip2D). Son de cada programa.
- **La variable no puede parar una corrida.** La primera idea era que la variable de entorno
  valiera lo mismo que la opción. Pero la opción se para cuando no tiene nada que aceptar (regla
  7), y dentro de una corrida de desarrollo hay tests que corren una carpeta propia que no comparte
  nada, o cuyo núcleo sí es el fijado: todos se habrían parado con «nothing to accept». La variable
  se hereda, no se teclea; acepta lo mismo que la opción y nada más, y si no hay nada que aceptar
  la corrida es una corrida normal contra el núcleo fijado. La opción se sigue parando.
- **Una corrida lanzada desde un test habría convertido el resto de esa suite en una corrida de
  desarrollo.** `main()` deja la variable como la encontró al terminar, también si termina
  rechazando el núcleo.
- **El registro de programas de la suite estaba desfasado, y la CI no puede leerlo.** `suite.toml`,
  en el repositorio de la suite, decía que OGR Slip2D llevaba su propia copia del núcleo y que
  OGR FEM2D fijaba `v0.1.0`, dos días después de que ya no fuera así, y no falló nada. Además ese
  repositorio es privado: la CI de este, que es público, no puede leerlo sin una credencial. La
  lista que lee este repositorio vive en él (`docs/consumidores.md`), en una tabla con forma fija
  y con un test.
- **Un árbol del núcleo en editable para todos los programas impide que fijen versiones
  distintas.** Pasó con esta misma versión: Slip2D fijó la v0.2.1 mientras FEM2D seguía en la
  v0.2.0, los dos `.venv` apuntaban al mismo árbol, y ese árbol tuvo que quedarse en la 0.2.0, tres
  commits por detrás de `main`. Slip2D ya instala la etiqueta en su `.venv` (su v0.1.474), como
  hace la CI. Es la regla que queda escrita.
- **«El núcleo no está copiado en el árbol del programa» lo dicen dos tests, y no dicen lo
  mismo.** Al instalar la etiqueta en su `.venv`, Slip2D encontró que su test tomaba por copia un
  núcleo instalado en un entorno que vive dentro del repositorio, y lo corrigió allí. El de FEM2D
  solo rechaza `<repositorio>/ogr_core`. Es una regla que necesitan dos programas y que debería
  vivir aquí; queda abierta (§4).
- **La regla 8 decía «sin argumentos».** Ya anotado en la v0.2.1: se leyó como «en serie» y sin
  mirar el comando del programa. Queda dicha como «sin filtrar», con dónde está el comando de cada
  uno.
- **Antes de esta versión no había ninguna suite de programa en la CI de este repositorio, y la de
  OGR Slip2D nacería en rojo.** Su CI de Linux tiene cinco fallos suyos, aparcados por su
  propietaria. Un trabajo siempre rojo tapa el rojo siguiente: por decisión de la propietaria, el
  trabajo de Slip2D se enciende cuando su suite esté en verde en Linux. Los trabajos van en un
  cambio posterior (§4).

## 1. Qué cambia

**`ogr_core/testing/runner.py`**

- `DEV_CORE_ENV = "OGR_DEV_CORE"` y `dev_core_run()`: si este proceso es de una corrida que aceptó
  una versión de desarrollo. Solo `"1"` cuenta.
- `main()`: una corrida que acepta una versión de desarrollo pone la variable a `"1"` mientras
  dura, y al terminar la deja como estaba. Una corrida que arranca con la variable puesta acepta
  lo mismo que aceptaría con `--dev-core` y lo dice igual (`DEV CORE`, antes y después de los
  totales); si no hay nada que aceptar, corre como siempre. Los trozos de `--jobs` reciben la
  opción solo cuando hay algo que aceptar.
- `--dev-core` no cambia: acepta solo una `.devN` de una versión posterior a la fijada, y se para
  con código 2 si no tiene nada que aceptar.

**Versión**

- `tests/test_version_consistency_v10.py`: el número es `X.Y.Z` o `X.Y.Z.devN`, y nada más. Una
  versión publicada tiene su changelog; una de desarrollo no tiene uno propio (se escribe el de la
  versión a la que lleva); y ningún changelog es de una versión posterior a la del árbol.
- Después de etiquetar `v0.2.2`, `main` pasa a `0.2.3.dev0`.

**Documentos**

- `docs/consumidores.md`, nuevo: qué fija cada programa, qué cambios están en curso y para quién,
  cómo pide un programa un cambio, cómo sube la versión que fija, y qué significa cada número.
- `tests/test_consumers_v022.py`, nuevo: lee esa tabla. Cada versión fijada existe y no es
  posterior a la del árbol, ningún comando filtra, y el lector se niega con una tabla que no
  entiende en vez de devolver menos programas.
- `AGENTS.md`: la regla 8 (sin filtrar, con el comando de cada programa), la regla 9 (versión de
  desarrollo, y qué número sube con qué cambio), cómo se prueba un programa contra el núcleo en
  curso, y una sección nueva, «Un núcleo y varios programas».
- `README.md` y `README.es.md`: un programa instala el núcleo desde su etiqueta; lo de instalar
  los dos en editable deja de ser la recomendación.

## 2. Lo que tiene que cambiar cada programa (regla 10)

Nada desaparece ni cambia de firma. Para seguir funcionando, ningún programa tiene que cambiar
nada. Para **salir en verde de una corrida con `--dev-core`**, que es lo que hace falta para que
la CI de este repositorio pueda correr su suite:

- **Los dos**: fijar `v0.2.2`. Sus tests de «el núcleo importado es el fijado» pasan a comprobar
  lo mismo a lo que se sujetó la corrida:
  `runner.shared_problems(origins, pinned, dev_core=runner.dev_core_run()) == []`. Un test que
  compare la cabecera de una corrida con la versión fijada tiene que esperar la versión importada.
- **Un test que lea la salida de un runner relanzado** tiene ahora, en una corrida de desarrollo,
  las líneas `DEV CORE` antes y después de los totales.
- **OGR Slip2D**: además, el test del censo de textos en español no debe contar como inglés el
  `dev` de la versión del núcleo en «Acerca de». Su test que relanza el runner no necesita nada.
- **OGR FEM2D**: además, su test del «Python sin núcleo» tiene que arrancar ese Python sin el
  `PYTHONPATH` de la corrida. Y su `.venv` pasa del núcleo en editable a la etiqueta instalada,
  como el de Slip2D.
- Las reglas de «Un núcleo y varios programas» van también en el `AGENTS.md` de cada programa.

## 3. Pruebas

Windows, Python 3.14.7, de una en una. El árbol decía `0.2.2.dev0`: es la primera versión que se
prueba en los programas desde su propio árbol y no desde una copia con otro número.

| Qué | Resultado |
|---|---|
| Suite del núcleo, en serie | 734 de 734, código 0, ninguna fuga (693 de la v0.2.1 y 41 nuevos) |
| Suite del núcleo, `--jobs 4` | 734 de 734, código 0, ninguna fuga |
| OGR FEM2D `d2e6fca` contra este árbol, con `--dev-core` | 186 de 189, ninguna fuga; los tres de siempre, abajo |
| OGR Slip2D `302a97c`, solo `test_shutdown_release_v1422`, con `--dev-core` y fuera de pantalla | 3 pasan, 1 saltado, 0 fallos: el test que relanza el runner pasa sin cambiar Slip2D. Corrida filtrada |

**Dientes.** Veintidós errores metidos a propósito, de uno en uno, y mueren los veintidós. Nueve
en el runner: no dejar la variable, no devolverla, quitarla siempre al devolverla, que la variable
pare la corrida, que cuente cualquier valor, dar la opción a los trozos sin nada que aceptar, no
atender la variable, que la variable deje pasar cualquier núcleo, y que la opción deje de pararse.
Seis en la versión: una candidata como publicada, el changelog propio como posterior, un árbol que
dice una candidata, un changelog de una versión posterior, una versión de desarrollo con changelog
propio y una publicada sin él. Siete en la tabla de programas: una versión que no existe, un
comando con `--fast`, un programa de menos, un lector que se salta la fila que no entiende, fijar
la versión a la que lleva la de desarrollo, aceptar una rama como fijación, y que `--fast` no
cuente como filtro. El último salió como vivo la primera vez por un error del ensayo: el cambio
estaba mal sangrado y el archivo no cargaba. Rehecho, muere.

**OGR FEM2D con `--dev-core`.** Fallan los mismos tres tests de `test_project_setup_v001` que con
la v0.2.1, que es lo esperado mientras FEM2D no cambie (§2). Uno falla ahora de otra manera:
`test_a_python_without_the_core_is_refused` ya no ve un runner que se niega, sino uno que hereda
la variable y acepta el núcleo de desarrollo que encuentra por el `PYTHONPATH`. Un ensayo aparte,
sin tocar FEM2D, hace lo que esos tres tests tendrían que comprobar, con el runner de esta versión:
`shared_problems` sin problemas al decirle que la corrida es de desarrollo, la cabecera con la
versión importada, y el Python sin `PYTHONPATH` rechazado con su razón. Los tres salen.

### Sin probar

- **La suite entera de OGR Slip2D contra esta versión** (regla 8). Se corre antes de etiquetar, y
  su resultado se anota aquí.
- **Linux y la CI de este repositorio**: se ven con la PR.
- **Los tres tests de cada programa, cambiados de verdad**: es de la versión de cada programa que
  fije esta. Lo de arriba es un ensayo en FEM2D y un razonamiento en Slip2D.

## 4. Queda abierto

- **La CI de este repositorio con las suites de los programas**, que es para lo que sirve esta
  versión. Y dentro de eso, qué hace el trabajo de un programa con el commit que solo pone el
  número de la versión: el runner del programa se niega con un `X.Y.Z` que no es el que fija, y
  `--dev-core` no lo acepta porque no es una `.devN`.
- Una sola regla, aquí, para «el núcleo no está copiado en el árbol del programa».
- `suite.toml` y el `README.md` de la suite, que son de otro repositorio.
- `main` de este repositorio no tiene protección de rama: nada obliga a que la CI esté en verde
  antes de fusionar. Es un ajuste de la propietaria en GitHub.
- `ogr_core/report` usa matplotlib, que el núcleo no declara (viene de la v0.2.0).
