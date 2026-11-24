# OGR Core v0.2.10

> **En curso.** `main` dice `0.2.10.dev0` y esta versión no está etiquetada. Este archivo cuenta lo
> que ya ha entrado camino de ella.

**La fila del informe del número de cuñas de Sarma dice que es el pedido, no el mínimo.**
«Least Number of Wedges» pasa a «Number of Wedges Asked For», y el docstring de `SarmaSettings`
dice la regla de las cuñas de OGR Slip2D v0.1.488 (su D454). Es compatible: solo cambia texto, nada
del cálculo ni del archivo.

Lo pidió OGR Slip2D (2026-11-24), después de preparar su suite para las dos filas en su `b02a2d5`.

## 0. Lo que se encontró

- **La fila decía lo contrario de la mitad de los casos.** Una superficie tiene más cuñas que las
  pedidas donde un vértice, un contacto o un corte con el nivel freático añade una frontera, y, desde
  Slip2D v0.1.488, menos solo donde se quita una división uniforme en un tramo recto de un único
  material de Mohr-Coulomb. «Least» no era ni lo uno ni lo otro.
- **El docstring de `SarmaSettings` estaba desfasado en dos viñetas** desde Slip2D v0.1.488:
  - `num_slices` decía «the LEAST number of wedges».
  - `slice_angles` decía que una cara de la política que corta a una vecina o no llega al terreno
    se quita con su frontera «where it is a uniform division». Ahora solo se quita en un tramo recto
    de un material de Mohr-Coulomb (bases a menos de 1e-9 rad, `droppable` y `_COLLINEAR` de
    `ogr_slip2d/sarma/wedges.py`). En cualquier otro sitio, por ejemplo en las cuerdas de un círculo,
    la cara se pone vertical y el número de cuñas se conserva. Esta viñeta no la nombraba la primera
    petición; la encontró la sesión de Slip2D, y aquí se ha comprobado leyendo su `build_wedges`
    (`b02a2d5`, solo lectura).
- La evidencia de Slip2D (su `b81352e`): un círculo del problema 002 de su banco, con 25 cuñas
  pedidas, acababa en 2 cuerdas con la regla de la 0.1.464. Daba F 2,21 con la bisectriz, frente a
  4,19 con caras verticales y 4,37 con Spencer, del lado inseguro.
- **Ningún test del núcleo miraba la fila.** Se añade uno.
- `grep -rn "Least Number of Wedges\|LEAST number" ogr_core tests docs`, fuera de los changelogs
  viejos: no queda nada.

## 1. Qué cambia

- `ogr_core/report/report_generator.py`, `_sarma_settings_rows`: `T("Number of Wedges Asked For")`
  en lugar de `T("Least Number of Wedges")`. El comentario de encima dice por qué.
- `ogr_core/project/settings.py`: las viñetas `num_slices` y `slice_angles` del docstring de
  `SarmaSettings`.
- `tests/test_sarma_report_row_v0210.py`: la fila, su valor y su traducción, y que el docstring no
  diga «least» del número de cuñas.

## 2. Lo que tiene que cambiar cada programa (regla 10)

- **OGR Slip2D**, al fijar `v0.2.10`:
  - quitar la clave `'Least Number of Wedges'` de `ogr_gui/i18n/__init__.py`;
  - quitar `_ASKED_OLD` y la rama por versión de `_asked_row` en
    `tests/test_sarma_report_v1468.py`;
  - quitar la clave vieja de `test_the_report_row_in_spanish` en
    `tests/test_sarma_wedge_count_v1488.py`;
  - `d454()` del banco deja de marcarlo como pendiente del núcleo.

  Hasta que suba la fijación, su suite exige «Least…» con un núcleo publicado hasta la 0.2.9, y
  acepta cualquiera de las dos filas con un `.devN`.
- **OGR FEM2D**: nada. Comprobado en su código: no usa `_sarma_settings_rows` ni traduce esa fila.

## 3. Pruebas

| Qué | Resultado |
|---|---|
| `tests/test_sarma_report_row_v0210.py` | 3 de 3 |
| Suite del núcleo entera, `--jobs 4` (Windows, Python 3.14.10) | 962 de 962, sin fugas |

**La regla 8**, el 2026-11-24 en Windows, contra la rama `sarma-cunas-pedidas` en `0.2.10.dev0`:

| Qué | Resultado |
|---|---|
| OGR Slip2D `b02a2d5` (fija `v0.2.7`) **entera**, con `--jobs 4`, `--dev-core` y fuera de pantalla, contra `793b812` | 7584 casos: 7582 pasan, 0 fallos, 2 saltados (los de la plataforma), ninguna fuga, código 0. `shared: ogr_core 0.2.10.dev0 … @ 793b812`, `DEV CORE` antes y después. Su árbol, limpio antes y sin un archivo cambiado durante la corrida (20:40–20:46). Con un `.devN` su suite acepta cualquiera de las dos filas, pero exactamente una: aquí, la nueva |
| OGR FEM2D | pendiente: su sesión trabaja en su árbol |
