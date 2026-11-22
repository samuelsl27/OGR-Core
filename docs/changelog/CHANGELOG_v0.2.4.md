# OGR Core v0.2.4

> **En curso.** `main` dice `0.2.4.dev0` y esta versión no está etiquetada. Este archivo cuenta lo
> que ya ha entrado camino de ella.

## 0. Lo que se encontró

- **El repositorio acumulaba una rama por cada PR, ya fusionada.** Nueve ramas `dev/…` en GitHub
  y en local, todas enteras en `main` (comprobado una a una: 0 commits fuera de `main`). Se
  conservaban a propósito, por una regla de la propietaria durante la unificación del núcleo
  («nada de borrar ramas»), y con el borrado automático de GitHub apagado. No guardaban nada: los
  commits de una PR fusionada con un commit de fusión quedan en `main`, y la página de la PR
  conserva su historia. Sí confundían: dos de ellas se llamaban como una versión
  (`dev/v0.2.3`), y una versión es una etiqueta, no una rama.
- **En OGR Slip2D el mismo hábito sí escondía algo.** Cinco ramas, y solo en ellas, los cinco
  documentos de su spec 009 de la extracción, que su `main` cita en tres sitios. Leído desde aquí,
  no tocado: va escrito para su sesión, con la orden de archivar cada punta con una etiqueta antes
  de borrar. Lo hizo en su v0.1.477: tres etiquetas `archivo/…`, y encontró una cita más de las
  tres que se le dieron, en un comentario de su código.
- **Los cinco fallos de OGR Slip2D en Linux eran dos defectos, y solo uno era del programa.** Los
  diagnosticó su sesión, en su v0.1.476. El del programa: su servidor MCP mandaba la sangría de
  los docstrings, que Python solo quita desde 3.13, y por eso fallaba un test en 3.11 y 3.12 y no
  en 3.13. El otro era de un test, cuatro veces: leía una tabla partiéndola por una raya que en
  Linux es otra. Su suite sale entera en verde en Linux, en los tres Python, desde entonces: en su
  `main`, las corridas 44847262314 (`83a3421`) y 44854765063 (`45c5146`, su v0.1.477), con 7547
  casos, 7541 pasan, 0 fallan, 6 saltados y ninguna fuga. Con eso desaparece la razón escrita en
  la v0.2.3 para no correrla aquí.
- **El README solo enseñaba a montar el núcleo en Linux o macOS, y el núcleo no tenía entorno
  propio en el PC de desarrollo.** La única receta activaba el entorno con
  `source .venv/bin/activate`, que en Windows no existe. Y en ese PC la suite corría con el Python
  del sistema, que llevaba las dependencias instaladas a mano. Salió al escribir la guía para
  montar la suite en un PC nuevo (`DESARROLLO.md`, en la carpeta de trabajo `OGR_Suite`) y
  ensayarla el 2026-11-21: un clon nuevo de este repositorio, un `.venv` de Python 3.14.7 creado
  de cero y `pip install -e .`. Así la suite sale entera en verde, con las dependencias que pip
  resuelve hoy (numpy 2.5.5, scipy 1.18.1, shapely 2.2.0, ezdxf 1.4.5, h5py 3.16.0, reportlab
  5.1.0). Ese verde dependía, sin saberlo, de que aquel PC tuviera `C:\tmp`: en una máquina sin
  ella, la misma receta da 22 fallos (el hallazgo siguiente).

## 1. Qué cambia

- `AGENTS.md`, «Un núcleo y varios programas»: una rama se borra cuando su PR se fusiona; una sin
  fusionar no se borra sin el OK del propietario, y si lleva algo que `main` no tiene se archiva
  antes con una etiqueta `archivo/<nombre>`.
- Borradas, por decisión de la propietaria (2026-11-20), las nueve ramas ya fusionadas, en GitHub y
  en local: `dev/v0.2.0` (PR 1), `dev/test-async` (2), `dev/v0.2.1` (3), `dev/v0.2.2` (4),
  `dev/v0.2.3.dev0` (5), `dev/ci-programas` (6), `dev/fuentes-ocultas` (7), `dev/v0.2.3` (8) y
  `dev/v0.2.4.dev0` (9). Quedan `main` y las etiquetas `v0.1.0` a `v0.2.3`.

- `.github/workflows/tests.yml`: el trabajo `slip2d`, que corre la suite entera de OGR Slip2D
  contra el núcleo de cada commit, como el de OGR FEM2D desde la v0.2.3. Instala lo que instala la
  CI del programa (las bibliotecas de Qt y el programa con su extra `mcp`) y le pide el comando a
  la tabla: que va fuera de pantalla y en cuatro procesos lo dice `docs/consumidores.md`, no el
  flujo. Con Python 3.11, el mínimo declarado, como el de OGR FEM2D.
- `tests/test_ci_programs_v023.py`: la lista de programas sin trabajo (`NOT_YET`) queda vacía. El
  test ya exigía que una razón no sobreviva a su causa: con el trabajo puesto y la razón sin
  quitar, falla.
- `docs/consumidores.md` y `AGENTS.md` dicen que la CI corre los dos programas.
- `README.md` y `README.es.md`: la sección «Install for development» pasa a llamarse
  «Development» («Desarrollo»). Dice qué hace falta (Python 3.11 o posterior y git), añade la
  receta de Windows sin activar el entorno, que el núcleo va en editable solo en su propio
  entorno, y dónde está la guía para montar la suite entera. Solo documentación.

El código de `ogr_core` no cambia.

## 2. Lo que tiene que cambiar cada programa (regla 10)

Nada en su código. La regla de las ramas ya está en el `AGENTS.md` de cada uno: OGR FEM2D la
escribió en su v0.0.6 y OGR Slip2D en su v0.1.477, y en los dos solo queda `main`.

## 3. Pruebas

La regla no tiene test: lo que hay en GitHub no se ve desde la suite. Lo que la sostiene es el
borrado después de cada fusión, o el ajuste del repositorio que lo hace solo («Automatically
delete head branches»), que es de la propietaria.

| Qué | Resultado |
|---|---|
| Las nueve ramas, antes de borrarlas: cada una entera en `main`, y la local igual a la de GitHub | las nueve |
| El borrado local, con el que se niega si la rama no está fusionada (`git branch -d`) | las nueve, sin negarse |
| El test del flujo, con el trabajo `slip2d` quitado, y con el trabajo puesto y la razón sin quitar | falla en los dos |
| El comando que el guion saca de la tabla para OGR Slip2D, contra este núcleo y su fijación | modo de desarrollo: `QT_QPA_PLATFORM=offscreen` en el entorno y `tests/_runner.py --jobs 4 --dev-core` |
| Suite del núcleo, con `--jobs 4` (Windows) | 796 de 796, sin fugas |
| Suite del núcleo en un clon nuevo, con un `.venv` nuevo de Python 3.14.7 y las dependencias de hoy (Windows, en serie; el ensayo de `DESARROLLO.md`) | 796 de 796, código 0 |

**Sin medir desde aquí**: la suite de OGR Slip2D en Linux con `--jobs 4` y con `--dev-core`. Su
propia CI la corre en un proceso y contra la etiqueta, y tarda entre 25 y 40 minutos por trabajo.
La primera vez que corre así es en la CI de la PR que añade el trabajo.

## 4. Queda abierto

- Que GitHub borre la rama al fusionar, y la protección de `main`: ajustes de la propietaria.
- De antes siguen: si la corrida de la CI vale como regla 8 para OGR FEM2D, la regla única de «el
  núcleo no está copiado en el árbol del programa», y `matplotlib` sin declarar en
  `ogr_core/report`.
