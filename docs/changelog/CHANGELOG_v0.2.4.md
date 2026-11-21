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

**Sin medir desde aquí**: la suite de OGR Slip2D en Linux con `--jobs 4` y con `--dev-core`. Su
propia CI la corre en un proceso y contra la etiqueta, y tarda entre 25 y 40 minutos por trabajo.
La primera vez que corre así es en la CI de la PR que añade el trabajo.

## 4. Queda abierto

- Que GitHub borre la rama al fusionar, y la protección de `main`: ajustes de la propietaria.
- De antes siguen: si la corrida de la CI vale como regla 8 para OGR FEM2D, la regla única de «el
  núcleo no está copiado en el árbol del programa», y `matplotlib` sin declarar en
  `ogr_core/report`.
