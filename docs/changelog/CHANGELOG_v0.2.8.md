# OGR Core v0.2.8

> **En curso.** `main` dice `0.2.8.dev0` y esta versión no está etiquetada. Este archivo cuenta lo
> que ya ha entrado camino de ella.

**El lector DXF lee las entidades en sus propias coordenadas (OCS).** `ARC`, `CIRCLE`,
`LWPOLYLINE` y la `POLYLINE` 2-D guardan sus coordenadas en el sistema que fija su vector de
extrusión, y hasta la 0.2.7 el lector las usaba tal cual. Con extrusión (0, 0, −1) se leían
reflejadas en x. Ahora se pasan a las coordenadas del dibujo, y una entidad fuera del plano XY se
cuenta en `skipped` en vez de leerse mal. Es compatible: con extrusión +Z, que es lo normal, la
salida no cambia, bit a bit.

Visto al hacer la 0.2.7 (su §0 y §4) y reportado antes de corregirlo. Decisión de la propietaria
(2026-11-24): arreglarlo, y que una entidad inclinada se cuente y no se lea, como se recomendó.

## 0. Lo que se encontró

- **Medido con `ezdxf` 1.4.5, tomando como referencia su propia conversión a las coordenadas del
  dibujo**, con extrusión (0, 0, −1):

  | Entidad | El lector daba | En el dibujo |
  |---|---|---|
  | `ARC` de centro (10, 0), r = 1, de 0° a 90° | de (11, 0) a (10, 1) | de (−11, 0) a (−10, 1) |
  | `CIRCLE` de centro (5, 1) | centro (5, 1) | centro (−5, 1) |
  | `LWPOLYLINE` de (0, 0) a (2, 0) con bulge 1 | arco de centro (1, 0) | de (0, 0) a (−2, 0), centro (−1, 0) |
  | `POLYLINE` 2-D, igual | lo mismo | lo mismo |
  | `LINE`, `SPLINE` | bien | están ya en las coordenadas del dibujo |

- **Para (0, 0, −1), el algoritmo del eje arbitrario de la referencia DXF da una forma cerrada.**
  Ax = Wy × N = (−1, 0, 0) y Ay = N × Ax = (0, 1, 0), así que el punto del dibujo es (−x, y). Las
  operaciones son con 0 y ±1, así que el resultado es exacto. Un reflejo lleva una circunferencia a
  una circunferencia y un arco menor a un arco menor, así que `keep_arcs` sigue valiendo: solo
  cambia el sentido de recorrido.
- **Una extrusión inclinada saca la entidad del plano.** Con (0.6, 0, 0.8), un `ARC` de centro
  (0, 0), r = 1, de 0° a 90°, acaba en el dibujo en (−0.8, 0, 0.6), y el lector lo daba acabando en
  (0, 1). Proyectado sobre XY sería una elipse.
- **La salida con extrusión +Z no cambia, bit a bit.** El lector de `main` (`3bcb611`, la 0.2.7) y
  el nuevo se compararon sobre 1002 polilíneas aleatorias. Había `LWPOLYLINE` y `POLYLINE` 2-D con
  bulges entre −3 y 3, abiertas y cerradas, `ARC`, `CIRCLE`, `LINE` y `SPLINE`. Con 8, 64 y 129
  por vuelta, en m y en mm, y también con `keep_arcs` (3914 tramos de arco), salen los mismos
  puntos, los mismos centros y los mismos `skipped`.
- **Los centros de `keep_arcs` de una `LWPOLYLINE` salían como `numpy.float64`**, porque `ezdxf`
  da así sus vértices. Ahora son `float`. El valor no cambia.
- **Un camino equivocado, de la sesión:** el primer parche se escribió con `Path.write_text`, que en
  Windows pone CRLF. El repositorio fija LF (`.gitattributes`), y los mutantes, que buscan el texto
  con `\n`, no lo encontraban. Se devolvió el archivo a LF antes de seguir.

## 1. Qué cambia

- `ogr_core/dxf/reader.py`:
  - `_plane_of(e)` da el OCS de un `ARC`, `CIRCLE`, `LWPOLYLINE` o `POLYLINE` 2-D (`ezdxf`, el
    algoritmo del eje arbitrario), o `None` con extrusión +Z. Con +Z no se transforma nada.
  - Los puntos y los centros pasan del OCS a la x y la y del dibujo (`_ocs_to_wcs`) antes de las
    unidades y de quitar los duplicados. La elevación no cuenta, como antes.
  - `PLANE_TOL = 1e-9`: una extrusión unitaria con |x| o |y| por encima de eso no está en el plano
    del dibujo. Con 1e-9, la proyección de una circunferencia es una elipse cuyos ejes difieren en
    5e-19. Una entidad así no se lee, y `skipped` la cuenta como `"<TIPO> (not in the XY plane)"`,
    con la forma de `"<TIPO> (unreadable)"`. El `import_dxf` de OGR FEM2D, que suma `skipped` por el
    prefijo del tipo, la cuenta ya.
  - Los centros de `arcs`, como `float`.

## 2. Lo que tiene que cambiar cada programa (regla 10)

Nada en el código. **Aviso para los dos**: la importación de DXF da otra geometría, la correcta, en
los dibujos con alguna `ARC`, `CIRCLE`, `LWPOLYLINE` o `POLYLINE` 2-D de extrusión distinta de +Z.
Con −Z, antes llegaba reflejada en x. Inclinada, antes llegaba como si estuviera en el plano, y
ahora no llega y se cuenta en `skipped`. Con +Z no cambia nada, bit a bit.

Un censo como el de la 0.2.7 en OGR Slip2D, que contara las entidades con extrusión distinta de +Z,
diría si alguno de sus DXF cambia.

## 3. Pruebas

| Qué | Resultado |
|---|---|
| `tests/test_dxf_reader_ocs_v028.py`, contra la forma cerrada (−x, y) y la conversión propia de `ezdxf` (`ARC.start_point`/`end_point`, `OCS.to_wcs`, los arcos de `virtual_entities`) | 9 casos, 9 pasan |
| `tests/test_dxf_reader_v144.py`, `tests/test_dxf_reader_arcs_v027.py` y `tests/test_dxf_sanitiser_v145.py`, sin tocar | pasan enteros |
| Nueve mutantes de `reader.py`, uno a uno, con el archivo restaurado byte a byte después (SHA-256 igual) | mueren los nueve |
| La salida de `main` frente a la nueva con +Z (§0) | idéntica, bit a bit |
| Suite del núcleo entera, `--jobs 4` (Windows, Python 3.14.10) | 874 de 874, sin fugas |

| Mutante | Fallan |
|---|---|
| El OCS ignorado, como antes | 6 |
| Las inclinadas proyectadas en vez de contadas | 2 |
| Los centros en el OCS | 5 |
| La `POLYLINE` 2-D sin su OCS | 2 |
| El `ARC` sin su OCS | 3 |
| El `CIRCLE` sin su OCS | 2 |
| La `LWPOLYLINE` sin su OCS | 3 |
| `PLANE_TOL` de 1e-5 | 1 |
| Los centros sin pasar a `float` | 1 |

El último sobrevivió en la primera tanda: con −Z los centros ya salen `float` de la transformación,
y el test solo lo miraba ahí. Se añadió el caso con +Z.

**La regla 8**: pendiente; se anota aquí con lo que salga.

## 4. Queda abierto

- La regla 8 y la etiqueta de la 0.2.8.
- `ELLIPSE` no se lee; se cuenta en `skipped`.
