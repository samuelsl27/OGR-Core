# OGR Core v0.2.5

> **En curso.** `main` dice `0.2.5.dev0` y esta versión no está etiquetada. Este archivo cuenta lo
> que ya ha entrado camino de ella.

Lo pide OGR FEM2D (decisión D2 de su spec 003, petición del 2026-11-22): un mallador de calidad,
el refinado de Delaunay de Ruppert en la versión de Shewchuk (2002a), y las dos medidas exactas
de calidad de un triángulo de Shewchuk (2002b). Lo genérico del mallado va al núcleo porque la
filtración de OGR Slip2D lo necesita igual. `generate_mesh` no cambia.

## 0. Lo que se encontró

- **Las fuentes se pueden leer desde esta sesión.** La petición daba por hecho que no: están en
  `FEM2D/Referencias/Bibliografia`, fuera de los repositorios pero dentro de la carpeta de
  trabajo. El texto extraído de los PDF pierde los símbolos de las fórmulas, y en el PC no había
  con qué renderizar páginas. Se instaló Poppler (`pdftoppm`, una herramienta de la máquina, no
  una dependencia del núcleo), y todas las páginas citadas se leyeron renderizadas. En los dos
  PDF, la página del archivo es la impresa más cuatro.
- **Lo que la fuente dice distinto de la petición**, contado a OGR FEM2D antes de programar nada.
  La propietaria decidió seguir la fuente:
  - Lema 1 (2002a, pág. 9) no dice que la malla sea de Delaunay. Lo dice el texto de esa página,
    y solo si no queda ningún subsegmento invadido.
  - Las capas concéntricas de §6.2 (pág. 29) se aplican a todo subsegmento con un extremo
    compartido con otro segmento, no solo junto a un ángulo pequeño.
  - El teorema 12 (pág. 35) toma φ, el ángulo mínimo de todo el PSLG, y su cota vale para todo
    triángulo.
  - El teorema 8 (págs. 22–23) pide B > √2 y ángulos de entrada > 60°, los dos estrictos. Su
    D_S es la mayor de dos expresiones. El ejemplo de la fuente usa B = 1/(2 sin 15°), no 1.93.
  - La figura 20 (pág. 26) no trae coordenadas.
  - La variante de Shewchuk parte de la triangulación restringida, y la de Ruppert de una sin
    restringir; la petición mezclaba las dos.
  - La tabla 4 de 2002b da las medidas **sin normalizar** (pág. 45). Las constantes que las
    llevan a uno en el equilátero están en la tabla 6 (pág. 53).
- **El radicando de la medida de condicionamiento, tal como lo escribe la tabla, pierde la mitad
  de sus cifras junto al equilátero.** (Σℓ²)² − 48A² vale exactamente cero en el equilátero, y
  en coma flotante es la resta de dos números casi iguales; la raíz convierte su redondeo de
  1e-16 en un error de 1e-8. Medido: 0.99999998 en un equilátero girado, y debajo de cero, es
  decir NaN, si no se acota. La tabla 6 lo avisa a su manera («infinite gradient for an
  equilateral triangle»). Por la fórmula de Herón es el mismo número que
  2((a² − b²)² + (b² − c²)² + (c² − a²)²): una suma de cuadrados sin esa resta y nunca negativa.
  Es lo que se programa, y un test lo compara con la forma literal de la tabla en aritmética
  racional exacta.
- **Un punto medio no cae exactamente sobre un segmento oblicuo.** `a + (b − a)/2` se redondea
  al punto más próximo de la rejilla de coma flotante: queda exactamente sobre un segmento
  horizontal o vertical (y por eso un eje en x = 0 conserva x = 0 en cada vértice añadido, que
  es lo que necesita OGR FEM2D) y a un ulp de uno oblicuo. Ruppert ya avisa del redondeo de los
  puntos medios. El test de las cadenas lo mide en aritmética exacta y admite ese ulp
  (1e-13 de la longitud).
- **Dos mutantes del mallador solo los cazaba la huella**: no mirar si un subsegmento queda
  invadido al empezar o tras partirlo, y no mirarlo al insertar un vértice (NEWVERTEX, fig. 39).
  Ninguna de las propiedades que se comprobaban lo veía: faltaba la propia, que al terminar no
  queda ningún subsegmento invadido (pág. 9), que es en lo que se apoya que la malla sea de
  Delaunay. Se añadió ese test, y los caza.
- **Un mutante es equivalente**: meter también en la cavidad de Bowyer–Watson los triángulos
  cuyo círculo pasa justo por el punto nuevo (incírculo ≥ 0 en vez de > 0). Las dos variantes dan
  una triangulación de Delaunay; ante cuatro puntos cocirculares, solo cambia cuál se elige. Se
  queda la estricta.
- **La huella del mallador salía distinta en Linux, y no era el mallador.** La CI de la PR 18
  dio `b3cd3ad7…` en Linux, igual con Python 3.11, 3.12 y 3.13, y en Windows salía
  `43e71727…`. En Windows, Python 3.12, 3.13, 3.14 y 3.15 dan la misma entrada y la misma
  malla, así que la diferencia era de plataforma. La entrada de ese caso (un hueco de 40 lados)
  salía de `math.cos` y `math.sin`, que la biblioteca matemática de cada sistema no redondea
  igual en la última cifra. Con las coordenadas escritas bit a bit en el test (las de
  Windows), la CI de Linux da la huella de Windows: el mallador da la misma malla en las dos
  plataformas. Para que siga así, ninguna decisión del algoritmo usa `sin`, `cos`, `atan2` ni
  `math.dist`, cuya implementación en C no tiene por qué redondear igual en todas partes (se
  cambió `math.dist` por √(dx² + dy²); no se vio que diera otra cosa). Quedan solo en las notas.
- **Ruppert solo, en la figura 20, no termina, y acababa en una división por cero.** Lo dice la
  fuente (pág. 27). Sin el Terminator, las aristas junto al ángulo de 5° se encogen sin fin, y
  junto al origen la coma flotante deja seguir hasta 1e-85 y más, sin llegar nunca a
  `max_triangles`; ahí salía un `ZeroDivisionError`. Ahora no se crea ninguna arista más corta
  que 2⁻⁴⁰ de la extensión de la entrada: se sale con el error `refine.too_fine`, que dice
  dónde. Una malla que termina no se acerca a ese umbral (los teoremas 4 y 11 acotan las aristas
  por los propios detalles de la entrada). Con el Terminator, la figura 20 termina, a 5° y a 1°.
- **Las capas concéntricas quedan fuera de la prueba del teorema 8.** La fuente lo prueba para la
  bisección (lema 7), y una capa parte junto a un vértice compartido hasta en un tercio. El test
  de la graduación se queda como una comprobación de la cota sobre estas mallas, no como un
  teorema, y lo dice. Su hipótesis es que *cualquier* par de segmentos incidentes forme más de
  60°, dentro del dominio o no, así que un dominio con una entalla en V (14° por fuera) no entra.
  El teorema 4 sí: con el exterior quitado antes de refinar, un ángulo pequeño en una concavidad
  «no tendrá efecto en el mallado» (pág. 48), y el test lo comprueba en ese dominio.
- **En un dominio no convexo, la malla es de Delaunay restringida, no de Delaunay a secas.** El
  exterior se quita antes de refinar y su invasión no cuenta (pág. 48), así que un vértice al otro
  lado de una entalla puede caer en el círculo de un triángulo que no lo ve. Lo que se comprueba
  en todos los dominios es el criterio local de Delaunay en cada arista que no es de segmento (la
  triangulación restringida), en aritmética exacta. El de todos contra todos, solo en los
  convexos.
- **Las condiciones A, C y E del Terminator no deciden en los casos de extremo a extremo.**
  Cuando un circuncentro invade un subsegmento junto a un ángulo pequeño, las piezas de su grupo
  ya miden potencias de dos e iguales, y A nunca permite. Sus mutantes no los veía nadie. La regla
  de la fig. 38, SPLITPERMITTED(s, d), queda en una función propia (`permitted`) y se prueba
  contra su tabla sobre una triangulación real. Además, las notas cuentan cada división
  rechazada, con lo que la decidió, y un test comprueba que en ninguna se cumplía A, C, D ni E.
  Un mutante sobrevive: el radio de inserción de un circuncentro a la mitad. Solo entra por la
  condición A, con un valor que la malla final ya no guarda.
- **La huella cambia a propósito con las capas**, de `43e71727…` a `d9764633…`: los vértices
  junto a las esquinas ya no caen en el punto medio.
- **El docstring de `ogr_core/fem/generator.py` dice «GPL-3.0 licence»**, y el proyecto es
  AGPL-3.0-or-later (la cabecera SPDX del mismo archivo lo dice bien). No se toca: el generador
  queda como está, y la petición pide expresamente no cambiarlo.

## 1. Qué cambia

- `ogr_core/fem/mesh.py`:
  - `triangle_gradient_quality` y `triangle_conditioning_quality`, las dos medidas exactas e
    invariantes con la escala de Shewchuk (2002b, tabla 4), con las constantes de su tabla 6.
    Valen uno en el equilátero, cero en el degenerado y son negativas en el invertido.
  - Sus métodos en `Element`.
  - `Mesh.quality_measures()`, el peor y la media de cada una, y cuántos elementos están
    invertidos.
  - `quality_stats` no cambia: su diccionario lo leen los dos programas.
- `ogr_core/fem/__init__.py` exporta las dos funciones.
- `ogr_core/fem/refine.py`, nuevo: `quality_triangulation(pslg, max_ratio=√2, size=None,
  max_triangles=1_000_000)`, el refinado de Delaunay de Shewchuk (2002a), §3.1 y las figuras 38 y
  39, con las capas concéntricas de §6.2 y el Terminator de §6.3. Entrada: `PSLG(vertices, segments=(u, v, etiqueta),
  seeds=((x, y), región, material), voids)`, o cualquier objeto con esos cuatro atributos (OGR
  FEM2D pasa el suyo). Salida: `QualityTriangulation` con el `Mesh` T3 (antihorario, material y
  región de cada elemento; el vértice i de la entrada es el nudo i), los nudos de cada segmento
  de u a v, sus etiquetas y las notas: B, el tope, los vértices añadidos en cada segmento, los
  triángulos que pasan de B y dónde, el ángulo de entrada más pequeño φ, la cota del teorema 12,
  las divisiones que el Terminator rechazó y que la malla depende de la unidad de longitud.
  - Triangulación propia, sin SciPy: Qhull cambia su salida con la versión. Predicados de
    orientación, incírculo y círculo diametral exactos (filtro en coma flotante y aritmética
    racional por debajo); los puntos nuevos, solo con + − × ÷. Misma entrada, misma malla, bit a
    bit.
  - Los segmentos que faltan se recuperan partiéndolos (Ruppert); el exterior y los vacíos se
    quitan antes de refinar (fig. 38, línea 2).
  - Un subsegmento con un extremo compartido con otro segmento se parte en la capa de radio
    potencia de dos que mejor equilibra (§6.2); con los dos extremos compartidos, desde el de
    índice menor. Los demás, por el punto medio.
  - El Terminator (§6.3) decide las divisiones que pide un circuncentro rechazado junto a un
    ángulo de 60° o menos, con las condiciones A, B, C, D y E de la pág. 34 (F no: la fuente la
    da por opcional y su autor no la implementó). Los grupos de subsegmentos solo cuentan los
    ángulos dentro del dominio, decididos en aritmética exacta. r_g, el radio de inserción de
    las págs. 13–14; el de los vértices de antes de refinar, su arista más corta al empezar.
  - Los triángulos malos salen el peor primero (págs. 50–51); los subsegmentos invadidos, en
    orden de llegada.
  - La cota de tamaño es una longitud de lado: el mínimo de `size(x, y)` en los tres vértices y el
    centroide. `math.inf` es «sin cota»; un valor ≤ 0 o NaN, un error.
  - Exige B ≥ √2 (teorema 4).
  - Lo que no se puede mallar sale como `QualityMeshError`, con su código. También el refinado
    que tendría que crear una arista de menos de 2⁻⁴⁰ de la extensión de la entrada
    (`refine.too_fine`).
- `ogr_core/fem/messages.py`: el catálogo `REFINE_MESSAGES`, con códigos `refine.*` (también
  `refine.too_fine` y la nota `refine.length_unit`) y `refine_note`. Va aparte de `SEEPAGE_NOTES`: los programas importan cada catálogo por su nombre,
  así que sus tablas de traducción no cambian hasta que lo añadan.

## 2. Lo que tiene que cambiar cada programa (regla 10)

Nada. OGR FEM2D puede usar las medidas nuevas y `quality_triangulation`. Para traducir los
mensajes del mallador, cada programa añade `REFINE_MESSAGES` a su tabla cuando lo use.

## 3. Pruebas

| Qué | Resultado |
|---|---|
| `tests/test_quality_measures_v025.py` | 8 casos, 8 pasan |
| Cinco mutantes, uno a uno, con `mesh.py` restaurado byte a byte después | mueren los cinco; la cabecera del test dice qué tests caza cada uno |
| `tests/test_quality_triangulation_v025.py`, con §3.1 | 16 casos, 16 pasan |
| Once mutantes de `refine.py` con §3.1, uno a uno, con el archivo restaurado byte a byte después | mueren diez (dos, solo con el test añadido, arriba); el otro es equivalente |
| `tests/test_quality_triangulation_v025.py`, con las capas y el Terminator | 28 casos, 28 pasan |
| Nueve mutantes de las capas y el Terminator | mueren ocho; el otro sobrevive (arriba) |
| La figura 20 a 5° y a 1° sin el Terminator | no termina: `refine.too_fine` (pág. 27) |
| CI de la PR 18 con la entrada de la huella fija (Linux, Python 3.11, 3.12 y 3.13) | la huella de Windows |
| Suite del núcleo entera, `--jobs 4` (Windows), con las medidas | 804 de 804, sin fugas |
| Suite del núcleo entera, `--jobs 4` (Windows), con §3.1 | 820 de 820, sin fugas |
| Suite del núcleo entera, `--jobs 4` (Windows), con las capas y el Terminator | 832 de 832, sin fugas |

Tiempos del mallador, en este PC (Windows, Python 3.14.10), sin otra corrida en la máquina, el
mejor de tres:

| Malla | Triángulos | Ángulo mínimo | Por encima de B | Tiempo |
|---|---|---|---|---|
| Sondeo de OGR FEM2D (cuadrado de 20 m, hueco de 40 lados como segunda región), h = 2 m | 699 | 20.79° | 0 | 0.02 s |
| Lo mismo, h = 1 m | 2202 | 20.79° | 0 | 0.05 s |
| Lo mismo, h = 0.5 m | 8195 | 20.79° | 0 | 0.17 s |
| Tamaño del caso 005 de OGR FEM2D (cuadrado de 100 m de semilado, hueco de radio 1 m en 128 lados), graduada sin cota | 556 | 20.99° | 0 | 0.04 s |
| Lo mismo, h = mín(3, 0.05 + 0.25 r) | 23 926 | 20.99° | 0 | 0.53 s |
| Lo mismo, h = mín(1.5, 0.05 + 0.25 r) | 90 771 | 20.99° | 0 | 2.22 s |
| Figura 20 a 5° (coordenadas construidas) | 64 | 5.00° | 2 | 0.00 s |
| Lo mismo, h = 0.2 | 13 247 | 5.00° | 2 | 0.30 s |
| Capa que se acuña a 3°, h = 0.5 | 3479 | 3.00° | 1 | 0.08 s |

Con §3.1 sola (la PR 18), el sondeo daba 706, 2174 y 8112 triángulos con 21.15°, y el caso 005,
562, 23 780 y 91 026 con 20.84°, en tiempos parecidos. Junto a un ángulo de entrada pequeño, el
ángulo mínimo de la malla es el propio ángulo de entrada, y los triángulos que pasan de B quedan
en ese vértice, dentro de la cota del teorema 12 (16.2 para 5°).

Con B = √2 el ángulo mínimo garantizado es arcsin(1/(2√2)) = 20.7° (pág. 5). En el sondeo, el
generador de siempre (`generate_mesh`) daba 6.8°, 4.9° y 17.2° con esos mismos h (lo midió OGR
FEM2D el 2026-11-22).

## 4. Queda abierto

- Que OGR Slip2D use `quality_triangulation` para su filtración: decisión de su sesión y de la
  propietaria. `generate_mesh` sigue como estaba.
- La regla 8 y la etiqueta de la 0.2.5.
