# OGR Core v0.2.14

**La tanda P10 de OGR Slip2D: D433, D443, D444, D445, D446 y D449.** Lo pidió OGR Slip2D
(2026-11-27, su 0.1.503, que fija `v0.2.12`), con las decisiones de la propietaria del mismo día.
Cada ficha, en su rama y su PR; esta versión las reúne.

*(En curso: las secciones se añaden con cada PR.)*

## D433 — la fuerza del retroanálisis es horizontal a propósito (documental)

### Lo que se encontró

- `BackAnalysisSettings` (`ogr_core/project/settings.py`) tiene objetivo, cota y método, y ningún
  ángulo. Su docstring decía de dónde sale la independencia del cálculo principal, pero no que la
  fuerza es horizontal ni por qué; el comentario del campo `elevation` («y of the horizontal
  force») era lo único que lo decía.
- Ninguna fila publicada del banco pide un ángulo: el único modelo con retroanálisis, el 037 del
  02, da una fuerza concentrada a un tercio de la altura, sin ángulo. Un anclaje o un muro a una
  cota se modela con un soporte, que ya tiene ángulo.

### Qué cambia

- Solo el docstring de `BackAnalysisSettings`: la fuerza es horizontal a propósito, las dos
  razones, y por qué una fuerza inclinada no es una proyección de esta (su componente vertical
  cambia la normal de la dovela que la recibe y su momento pide un punto, no una cota): sería una
  formulación nueva, de su fuente (Bishop, 1955; Janbu, 1954) y validada contra la cuña plana.
- Ni un número, ni un campo, ni el `.ogr`.

El falso «no hace falta soporte» de Bishop con la cota por encima del centro no es de este pedido:
va a la ficha D467 de Slip2D.

### Lo que tiene que cambiar cada programa (regla 10)

Nada.
