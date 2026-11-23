# OGR Core v0.2.7

**El lector DXF conserva los arcos, si se le pide.** Con `read_dxf(..., keep_arcs=True)`, cada
`ARC`, `CIRCLE` y *bulge* de polilínea llega en tramos de 90° como mucho, y `DxfPolyline.arcs` da
el centro de cada tramo curvo. Es compatible: por defecto el lector aplana como siempre. **Se
arreglan además dos lecturas de bulge que estaban mal**, y eso cambia la salida aplanada solo en
los DXF que traen uno de esos dos casos.

Lo pide OGR FEM2D (decisión D13 de su spec 004, petición del 2026-11-23). Su malla T6 pone el nudo
intermedio de cada lado sobre el arco, y para eso necesita el arco verdadero de cada tramo curvo:
sus dos extremos, exactos y compartidos con los tramos vecinos, y su centro. Un túnel que llega
como polilínea de cuerdas queda poligonal, y reconocer el círculo a partir de los vértices sería
adivinar (su spec 003 lo descartó).

## 0. Lo que se encontró

- **Un bulge con |b| > 1, es decir, un arco de más de media vuelta, se leía mal.** `_bulge_points`
  ponía el centro a `h = √(r² − (c/2)²) ≥ 0`, siempre del lado del arco menor. Medido: de (0, 0) a
  (2, 0) con b = tan 67.5°, que es un arco de 270° antihorario de centro (1, −1) y que baja hasta
  y = −1 − √2 = −2.414, salían 17 puntos que bajaban solo hasta y = −0.414. Eso es el arco de 90°
  de la circunferencia simétrica respecto a la cuerda. Con 64 por vuelta deben salir 48 tramos.
  Reportado antes de corregirlo; **la propietaria decidió arreglarlo también en la salida
  aplanada** (2026-11-23).
- **La `POLYLINE` antigua (2-D) ignoraba el bulge de sus vértices**: sus arcos llegaban como
  cuerdas, sin ningún aviso. Mismo trato que el anterior, por la misma decisión.
- **El lector ignora la extrusión (OCS)** de `ARC`, `CIRCLE` y `LWPOLYLINE`, y usa sus
  coordenadas tal cual. Medido con `ezdxf` 1.4.5: un `ARC` de centro (10, 0), radio 1, de 0° a 90°
  y con extrusión (0, 0, −1) se lee de (11, 0) a (10, 1). En el dibujo está de (−11, 0) a (−10, 1),
  reflejado en x. Ese tipo de arco es lo que deja una simetría en algunos CAD. **No se arregla en
  esta versión**: está reportado y queda abierto (§4).
- **La salida aplanada no cambia fuera de esos dos casos, bit a bit.** Se comparó el lector de
  `main` (`445446f`) con el nuevo sobre 1002 polilíneas aleatorias: `LWPOLYLINE` con bulges
  |b| ≤ 1, abiertas y cerradas; `POLYLINE` 2-D sin bulge; `ARC`; `CIRCLE`; `LINE`; `SPLINE`; y un
  bulge de exactamente ±1. Con 8, 64 y 129 por vuelta, en m y en mm, salen los mismos puntos, bit a
  bit (también el signo de los ceros), y los mismos `skipped` y `notes`. Para |b| ≤ 1, el centro
  se calcula con la misma aritmética que antes.

## 1. Qué cambia

- `ogr_core/dxf/reader.py`:
  - `read_dxf(path, unit="m", segments_per_circle=64, keep_arcs=False)`. Con `keep_arcs`,
    `segments_per_circle` solo afecta a las `SPLINE`.
  - `DxfPolyline.arcs: dict[int, tuple[float, float]]`, vacío por defecto. La clave `k` dice que
    el tramo `points[k] → points[k + 1]` es el **arco menor** de ese centro, en metros. Tiene la
    forma de `PSLG.arcs` (etiqueta → centro) y del `Arc(centre)` de OGR FEM2D. El radio y el
    sentido se deducen de los extremos.
  - Con `keep_arcs`, un arco de barrido S se parte en `ceil(S / 90°)` tramos iguales
    (`ARC_PIECE_MAX_DEG = 90`). Es decisión de la propietaria: cerca de 180° el centro está casi
    sobre la cuerda, y cuál de los dos arcos se quiere decir queda mal condicionado. Un `CIRCLE`
    sale en 4 cuartos, cerrado y con el último punto igual al primero. Un semicírculo sale en 2.
  - Los extremos de un bulge son los vértices del DXF, exactos. Los de un `ARC` salen de sus
    ángulos de inicio y fin. Los tramos rectos, `LINE` y la `POLYLINE` 3-D salen como antes.
    `SPLINE` se sigue aplanando.
  - En una polilínea cerrada, el tramo de cierre lleva su clave (`n − 2`, con el primer punto
    repetido al final).
  - Al quitar los vértices duplicados consecutivos, las claves se renumeran. Los centros se pasan
    a metros como los puntos.
  - Arreglos: el centro de un bulge con |b| > 1 va al lado del arco mayor (`_bulge_arc`), y la
    `POLYLINE` 2-D lee el bulge de cada vértice. `LWPOLYLINE` y `POLYLINE` comparten ahora el
    recorrido de sus vértices (`_polyline_with_bulges`).
- `ogr_core/dxf/sanitiser.py`: solo el docstring. `GeometrySanitiser` trabaja con polilíneas
  aplanadas y **no conserva `arcs`**, porque suelda, parte y simplifica vértices.
  `importer.preview` lee con el modo por defecto, así que nada cambia para él.

## 2. Lo que tiene que cambiar cada programa (regla 10)

**OGR Slip2D**: nada en el código. **Aviso**: su importación de DXF da otra geometría, la
correcta, en los dibujos que traen un bulge de más de media vuelta o una `POLYLINE` 2-D con bulge.
Antes, el primero llegaba como el arco menor de la circunferencia simétrica, y el segundo como
cuerdas. En los demás dibujos no cambia nada, bit a bit.

**OGR FEM2D**: nada obligatorio. Para conservar los arcos en `ogr_fem2d/model/import_dxf.py`:

```python
cat = reader.read_dxf(Path(path), unit=unit, keep_arcs=True)
for layer in cat.layers:
    for poly in layer.polylines:
        pts = list(poly.points)
        # poly.arcs[k] = centre of the minor arc points[k] -> points[k + 1]
        if len(pts) > 2 and pts[0] == pts[-1]:
            pts.pop()            # the closing piece keeps its index: len(pts) - 1
        segments = tuple(md.SegmentAttr(k, arc=c) for k, c in sorted(poly.arcs.items()))
        # ... md.Boundary(..., tuple(pts), closed, segments=segments, ...)
```

- Los tramos son el arco menor y de 90° como mucho, así que la regla `arc` de FEM2D, que pide que
  el centro no esté sobre la cuerda, se cumple con margen. Los extremos de cada tramo están sobre su
  circunferencia a redondeo; en los tests, con 1e-12 relativo.
- Con `keep_arcs=True`, `entity_counts` sigue contando `ARC` y `CIRCLE`, pero ya no llegan
  aplanados. El aviso de la importación debería quedar solo para `SPLINE`, que se sigue aplanando,
  y para `ELLIPSE`, que el lector no lee (va a `skipped`).
- Dos entidades distintas que se tocan, como un `ARC` y una `LINE`, comparten un extremo solo si el
  dibujo los da iguales: el lector no suelda. Dentro de una misma polilínea, los extremos son los
  mismos puntos.

## 3. Pruebas

| Qué | Resultado |
|---|---|
| `tests/test_dxf_reader_arcs_v027.py`, contra geometría cerrada: el centro de un bulge por d = c(1 − b²)/(4b) sobre la normal izquierda, y los casos hechos a mano | 14 casos, 14 pasan |
| `tests/test_dxf_reader_v144.py` y `tests/test_dxf_sanitiser_v145.py`, sin tocar | pasan enteros |
| Ocho mutantes de `reader.py`, uno a uno, con el archivo restaurado byte a byte después (SHA-256 igual) | mueren los ocho |
| La salida aplanada de `main` frente a la nueva (§0) | idéntica, bit a bit |
| Suite del núcleo entera, `--jobs 4` (Windows, Python 3.14.10) | 865 de 865, sin fugas |

Los mutantes, y el número de tests que falla con cada uno:

| Mutante | Fallan |
|---|---|
| El centro de \|b\| > 1 del lado menor, como antes | 3 |
| Tramos de 180° en vez de 90° | 8 |
| Sin renumerar las claves tras quitar duplicados | 1 |
| Los centros sin pasar a metros | 1 |
| El bulge del tramo de cierre ignorado con `keep_arcs` | 1 |
| La `POLYLINE` sin bulge, como antes | 2 |
| El bulge horario barrido en sentido antihorario | 2 |
| Una vuelta entera que no acaba en su primer punto | 1 |

**La regla 8**: pendiente; se anota aquí con lo que salga.

## 4. Queda abierto

- **La extrusión (OCS)** de `ARC`, `CIRCLE` y `LWPOLYLINE` (§0). Arreglarlo cambia la salida de
  los dibujos con extrusión negativa, y lo decide la propietaria.
- `ELLIPSE` no se lee; se cuenta en `skipped`.
