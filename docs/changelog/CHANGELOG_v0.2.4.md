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
  de borrar.

## 1. Qué cambia

- `AGENTS.md`, «Un núcleo y varios programas»: una rama se borra cuando su PR se fusiona; una sin
  fusionar no se borra sin el OK del propietario, y si lleva algo que `main` no tiene se archiva
  antes con una etiqueta `archivo/<nombre>`.
- Borradas, por decisión de la propietaria (2026-11-20), las nueve ramas ya fusionadas, en GitHub y
  en local: `dev/v0.2.0` (PR 1), `dev/test-async` (2), `dev/v0.2.1` (3), `dev/v0.2.2` (4),
  `dev/v0.2.3.dev0` (5), `dev/ci-programas` (6), `dev/fuentes-ocultas` (7), `dev/v0.2.3` (8) y
  `dev/v0.2.4.dev0` (9). Quedan `main` y las etiquetas `v0.1.0` a `v0.2.3`.

El código de `ogr_core` no cambia.

## 2. Lo que tiene que cambiar cada programa (regla 10)

Nada en su código. La misma regla va en el `AGENTS.md` de cada uno, desde su sesión.

## 3. Pruebas

La regla no tiene test: lo que hay en GitHub no se ve desde la suite. Lo que la sostiene es el
borrado después de cada fusión, o el ajuste del repositorio que lo hace solo («Automatically
delete head branches»), que es de la propietaria.

| Qué | Resultado |
|---|---|
| Las nueve ramas, antes de borrarlas: cada una entera en `main`, y la local igual a la de GitHub | las nueve |
| El borrado local, con el que se niega si la rama no está fusionada (`git branch -d`) | las nueve, sin negarse |

## 4. Queda abierto

- Que GitHub borre la rama al fusionar, y la protección de `main`: ajustes de la propietaria.
- El trabajo de OGR Slip2D en la CI, cuando su suite esté en verde en Linux.
- De antes siguen: si la corrida de la CI vale como regla 8 para OGR FEM2D, la regla única de «el
  núcleo no está copiado en el árbol del programa», y `matplotlib` sin declarar en
  `ogr_core/report`.
