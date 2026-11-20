# OGR Core v0.2.3

> **En curso.** `main` dice `0.2.3.dev0` y esta versión no está etiquetada. Este archivo cuenta lo
> que ya ha entrado camino de ella.

**La forma de trabajar con un núcleo y varios programas, segunda parte**: la CI de este
repositorio corre la suite entera de un programa contra el núcleo de cada commit, y compara lo que
fija cada programa con lo que dice `docs/consumidores.md`. El código de `ogr_core` no cambia
todavía: `git diff v0.2.2 -- ogr_core` solo toca el número de versión.

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
- **Anomalía, sin corregir: el test de las cabeceras de licencia no ve `.github/`.**
  `tests/test_license_v10.py` busca con `glob("**/*.py")`, que no entra en carpetas que empiezan
  por punto. El script nuevo (`.github/scripts/program_suite.py`) lleva su cabecera SPDX, pero
  ningún test fallaría si no la llevara. Medido: 169 archivos con el patrón del test, 170 contando
  las carpetas ocultas. Hasta ahora no había ningún `.py` ahí.
- **Un diente que faltaba, encontrado al meter los errores.** El script mira de dónde sale
  `ogr_core` antes de arrancar la suite. Quitar esa comprobación no hacía fallar ningún test: con
  el `PYTHONPATH` bien ordenado nunca tiene nada que decir. Tiene ahora su caso propio (un
  programa con un núcleo suyo en su carpeta, con el mismo número).
- **El traspaso a OGR Slip2D decía que este árbol local estaba en la 0.2.0.** Era verdad cuando
  se escribió y dejó de serlo antes de que su sesión lo leyera (pasó a `main` cuando OGR FEM2D
  dejó de usarlo en editable). Su sesión lo miró en vez de creérselo, como pedía el propio
  traspaso, y lo reportó.

## 1. Qué cambia

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

**Documentos**

- `docs/consumidores.md`: las dos filas, en `v0.2.2`. Qué lee la CI de esta tabla y qué pasa
  cuando un programa sube su fijación. En «Cambios en curso» entran el mensaje «WRONG SHARED TREE»
  y el test de las acciones de la CI.
- `AGENTS.md`: qué corre la CI y qué sigue a mano.

## 2. Lo que tiene que cambiar cada programa (regla 10)

Nada.

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

### Sin probar

- **Los trabajos nuevos en GitHub.** Todo lo de arriba es el script, en Windows. Que el Rust del
  runner baste para construir OGR FEM2D con `pip`, que la bajada parcial de un repositorio ajeno
  funcione y que la suite de FEM2D salga en verde ahí lo dirá la primera corrida de la CI.
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
- **El test de las cabeceras de licencia y las carpetas ocultas** (§0).
- **El mensaje «WRONG SHARED TREE»** del runner, que todavía recomienda el árbol en editable. Lo
  pidió OGR FEM2D.
- De la v0.2.2 siguen: la regla única de «el núcleo no está copiado en el árbol del programa»,
  `suite.toml` y el README de la suite, la protección de `main`, y `matplotlib` sin declarar en
  `ogr_core/report`.
