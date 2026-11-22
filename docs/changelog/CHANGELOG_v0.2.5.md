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

## 2. Lo que tiene que cambiar cada programa (regla 10)

Nada. OGR FEM2D puede usar las medidas nuevas.

## 3. Pruebas

| Qué | Resultado |
|---|---|
| `tests/test_quality_measures_v025.py` | 8 casos, 8 pasan |
| Cinco mutantes, uno a uno, con `mesh.py` restaurado byte a byte después | mueren los cinco; la cabecera del test dice qué tests caza cada uno |
| Suite del núcleo entera, `--jobs 4` (Windows) | 804 de 804, sin fugas |

## 4. Queda abierto

- El mallador: la triangulación con §3.1 de Shewchuk (2002a), y después §6.2 y el Terminator.
