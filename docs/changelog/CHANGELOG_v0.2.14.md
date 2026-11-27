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

## D446 — `_fmt` del informe escribe un entero con sus decimales (decisión B)

### Lo que se encontró

- `_fmt` (`ogr_core/report/report_generator.py`) escribía con `nd` decimales solo un `float` y
  pasaba todo lo demás por `str()`. Una coordenada entera salía `'0'` donde una real sale
  `'0.000'`; los vértices del talud de ejemplo son enteros (`Vertex(0, 0)`…), y con uno editado a
  (35,5; 15) la misma fila de la «List of Coordinates» mezclaba `'35.500'` y `'15'`. Un `.ogr`
  guarda `0` como `0`, así que lo mismo pasa con cualquier modelo leído con números enteros.
- **El censo**: 52 llamadas a `_fmt` en 40 líneas (más la definición: las 41 líneas que contó
  Slip2D; las 52 de la ficha eran llamadas). **Las 52 son coordenadas o magnitudes; ninguna es una
  cuenta.** Las cuentas (el número de dovela, el de vértice de «Global Minimum Coordinates», el de
  cara de Sarma) ya se escribían con `str()` en su sitio, así que no hay ninguna que mover.

  | Bloque | Llamadas | Qué | Decimales |
  |---|---|---|---|
  | Factor y Ky de la crítica (`_fmt(crit.fos, 4)`, `ky`) | 5 | magnitud | 4 |
  | Geometría de la crítica: centro, radio, eje, extremos (de polilínea y de círculo), área total | 14 | coordenada / magnitud | 3 |
  | «Global Minimum Coordinates», X e Y de cada vértice | 2 | coordenada | 3 |
  | Tabla de materiales: γ, γ_sat, c, φ | 4 | magnitud | 1 |
  | Tabla de dovelas: ancho, peso, c, φ, α, σ, τ_f, u, factor del peso | 9 | magnitud | 3, 1, 0, 0, 1, 2, 2, 1, 3 |
  | Sarma: c y φ de las caras | 2 | magnitud | 3 |
  | Sarma: Kc, \|q\| mínimo, razón de fuerzas, F de partida | 4 | magnitud | 4, 3, 3, 4 |
  | Sarma: tabla de caras (x, y, θ, longitud, PW, c, φ, E, E′, X) | 10 | coordenada / magnitud | 2 o 1 |
  | «List of Coordinates», X e Y de cada contorno | 2 | coordenada | 3 |

### Qué cambia

- `_fmt` trata como real todo `numbers.Real` que no sea `bool`: `int`, `float` y los escalares de
  numpy, con `nd` decimales. `None` y NaN siguen siendo «—»; un `bool` (y cualquier otra cosa),
  `str()`.
- **No cambia** el número de decimales de ninguna columna ni ningún valor real. **Sí cambia el
  texto** donde llegaba un entero: las coordenadas enteras (el talud de ejemplo entero: `0` pasa a
  `0.000`) y, con un material escrito con enteros, la tabla de materiales (`20` pasa a `20.0`) y
  la c y la φ de las caras de Sarma. En la tabla de dovelas, c y φ van con 0 decimales: sin cambio.
- `tests/test_report_fmt_v0214.py`: 9 tests (`_fmt` con entero, real, numpy, `bool`, `None`, NaN y
  texto; la «List of Coordinates» del talud de ejemplo y con el vértice en (35,5; 15); el número de
  dovela sin decimales y las magnitudes enteras de su fila con ellos). Contra el `_fmt` de antes
  fallan 5.

### Lo que tiene que cambiar cada programa (regla 10)

- **OGR Slip2D**: solo tests, si alguno fija un texto del informe con un entero sin decimales. Lo
  dirá su corrida con `--dev-core` (sección de pruebas).
- **OGR FEM2D**: nada; no usa el informe.
