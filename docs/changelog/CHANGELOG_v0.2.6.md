# OGR Core v0.2.6

> **En curso.** `main` dice `0.2.6.dev0` y esta versión no está etiquetada. Este archivo cuenta lo
> que ya ha entrado camino de ella.

Lo pide OGR FEM2D (decisión D14 de su spec 003, segunda petición del 2026-11-22): que el mallador
de calidad parta los tramos de arco **sobre el arco**, no sobre su cuerda. Su plan era llevar al
arco, después de mallar, los vértices que el refinado dejara en una cuerda (su D13). Su T12 vio que
no sirve: los triángulos finos pegados a la cuerda se dan la vuelta cuando la flecha pasa de unas
0.7 veces el tamaño local.

## 0. Lo que se encontró

- **Pav y Walkington, leído entero** (18 páginas, renderizadas con Poppler; la página del PDF es
  la impresa). Lo que importa:
  - **Ninguna variante tiene prueba de que termine con B = √2 si hay arcos.** El corolario 3
    (pág. 13) garantiza que su algoritmo termina si el ángulo pedido cumple
    κ < arcsin(1/(2μ√2)) ∧ arcsin(1/(2ζη)), con η y μ (pág. 6) y ζ (pág. 8) en función de τ,
    lo que gira la tangente de cada tramo. Esas constantes vienen de partir sobre la curva y
    proteger con el círculo de la cuerda; no dependen de las esquinas, así que pesan igual en su
    «corner lopping». Calculado aquí:

    | Tramos de | κ < | B > |
    |---|---|---|
    | 60° | 3.98° | 7.21 |
    | 45° | 6.74° | 4.26 |
    | 30° | 10.21° | 2.82 |
    | 10° | 16.48° | 1.76 |
    | 2° | 19.78° | 1.48 |

    A 20.7° (B = √2) solo se llega en el límite τ → 0 (pág. 14).
  - **El «corner lopping»** (algoritmo 1, pág. 5) es lo único con prueba para curvas y ángulos
    pequeños a la vez, con esa misma cota. Deja ángulos grandes junto a las esquinas (pág. 14 y
    fig. 5), no acota los triángulos cerca de una esquina (lema 6, pág. 14) y cambiaría la malla de
    la entrada recta.
  - Las capas concéntricas con curvas «no se generalizan de forma natural» (pág. 2), y con ellas
    no se ha mostrado un algoritmo que funcione.
- **La decisión de la propietaria** (2026-11-23), la variante (ii): el mallador de la 0.2.5 para
  los segmentos rectos, y los tramos de arco partidos sobre el arco. **Que termine no lo prueba
  ninguna fuente**: las capas y el Terminator sobre arcos no vienen de ninguna. Las notas de la
  malla lo dicen, y dan la cota del corolario 3 para la entrada.
- **Dos casos de la inserción fuera de la cuerda no salen en ninguna malla de las probadas.** Son
  cuando el triángulo del otro lado de la cuerda no tiene el vértice nuevo en su circunferencia
  circunscrita: la cuerda se queda como arista normal, o la cavidad sale vacía. Hace falta un
  triángulo junto a la cuerda con su vértice opuesto lejos (ángulo en él por debajo de τ/2), y
  antes de que nada invada la cuerda el refinado ya los ha partido. En el hueco, el disco, el
  anillo, el contacto oblicuo y el saliente, con y sin cota de tamaño, se contó línea a línea:
  cero veces. Se prueban partiendo a mano la cuerda de un saliente de radio 0.3, donde sí pasa, y
  comprobando la malla después (orientación, vecinos, Delaunay restringida, áreas exactas).
- **Lo que tenía que comprobar la entrada y la 0.2.5 no podía.** Un segmento recto puede cortar
  un arco dos veces sin tocar su cuerda, y dos arcos de circunferencias distintas pueden cortarse
  sin que ninguna cuerda entre en el otro. Se comprueban las dos cosas.
- **Un arco ya no se distingue de su cuerda en coma flotante** cuando la flecha queda por debajo
  del redondeo. Ahí el punto del arco caería en la cuerda o al otro lado; se sale con
  `refine.too_fine`, como con una arista demasiado corta. En las mallas probadas no pasa.

## 1. Qué cambia

- `ogr_core/fem/refine.py`:
  - `PSLG.arcs`: etiqueta → centro, vacío por defecto (el de OGR FEM2D tal cual). Un segmento
    con esa etiqueta es el arco menor entre sus extremos, de 60° como mucho.
  - Un tramo de arco se parte sobre el arco: donde el arco corta la mediatriz de la cuerda
    (corolarios 1 y 2, pág. 7), o, junto a un vértice compartido, en el punto del arco a la
    distancia de la capa, medida desde ese vértice como en un segmento. Solo + − × ÷ y √.
  - La invasión, por el círculo diametral de la cuerda (pág. 6). Los triángulos son rectos.
  - `insert_off`: la inserción de un vértice fuera de su cuerda, con cada triángulo nuevo
    comprobado antihorario en aritmética exacta; uno que no lo fuera es `refine.internal`.
  - Los ángulos de entrada en un vértice donde acaba un arco se miden con su tangente: los grupos
    del Terminator, φ y la cota del teorema 12.
  - La entrada se comprueba con el arco: centro, radios iguales, 60° como mucho, nada entre la
    cuerda y el arco, ningún segmento ni arco que entre ahí.
  - Notas nuevas: `arc_pieces`, `arc_turn` (τ en grados), `arc_bound` (κ y B del corolario 3, y
    si el B pedido la cumple) y `arc_unproven`, un mensaje con código. Sin arcos: 0 y `None`.
  - `arc_bound(tau)`, pública: el κ y el B del corolario 3.
- `ogr_core/fem/messages.py`: códigos `refine.bad_arc`, `refine.arc_radii`, `refine.arc_turn`,
  `refine.vertex_in_arc`, `refine.seed_in_arc`, `refine.void_in_arc`, `refine.segment_in_arc`,
  `refine.internal` y la nota `refine.arc_unproven`.
- `docs/consumidores.md`: OGR FEM2D fija `v0.2.5` desde su `702a618`, después de su v0.0.8
  (PR 23). Al subirla, el trabajo `pins` de la CI se puso en rojo en la PR 22, como debe.
- **Sin arcos, la malla no cambia**: la huella de la 0.2.5 sigue igual, y un PSLG con `arcs`
  vacío, con etiquetas que no tiene ningún segmento o sin el atributo da la misma malla bit a bit.

## 2. Lo que tiene que cambiar cada programa (regla 10)

Nada obligatorio. **Aviso**: un PSLG que trae `arcs` (el de OGR FEM2D) da otra malla que en la
0.2.5, que los ignoraba. Para traducir los mensajes nuevos, `REFINE_MESSAGES` ya trae los suyos.

## 3. Pruebas

| Qué | Resultado |
|---|---|
| `tests/test_quality_triangulation_arcs_v026.py` | 19 casos, 19 pasan, en 6 s |
| Catorce mutantes de `refine.py`, uno a uno, con el archivo restaurado byte a byte después (SHA-256 igual) | mueren los catorce |
| `tests/test_quality_triangulation_v025.py`, con la huella de la 0.2.5 | 28 de 28 |
| Suite del núcleo entera, `--jobs 4` (Windows) | 851 de 851, sin fugas |

Los mutantes, y quién los caza:

| Mutante | Lo caza |
|---|---|
| El punto medio de la cuerda, no del arco | sobre el arco, T12, corolarios, lema 1, capas, huella |
| Sin capas en los arcos | las capas, la huella |
| La inserción recta para un arco | los dos casos raros, la huella |
| El triángulo de la cuerda que se queda, en la región equivocada | el caso raro de la cuerda que se queda |
| La cavidad vacía sin su triángulo | el caso raro de la cavidad vacía |
| El triángulo de enfrente siempre en la cavidad | la Delaunay restringida del caso raro |
| Sin comprobar vértices, segmentos, cruces de arcos, giro o radios | la entrada mala, cada uno con su código |
| La dirección de la cuerda en vez de la tangente | el ángulo de entrada con un arco |
| tan(τ) por tan(τ/2) en la cota | la cota escrita de nuevo y las notas |
| Un radio un 0.1 % mayor | sobre el arco, corolarios, huella |

Tiempos, en este PC (Windows, Python 3.14.10), sin otra corrida en la máquina, el mejor de tres
(de una, las de 90 000 triángulos):

| Malla | Triángulos | Ángulo mínimo | Por encima de B | Tiempo |
|---|---|---|---|---|
| T12 de OGR FEM2D: cuadrado de lado 4, hueco de radio 1 en 6 tramos, h = 0.1 | 6557 | 24.23° | 0 | 0.16 s |
| Lo mismo, h = 0.05 | 26 341 | 26.76° | 0 | 0.64 s |
| Lo mismo en 8 tramos, h = 0.1 | 6525 | 24.86° | 0 | 0.16 s |
| Lo mismo en 8 tramos, h = 0.05 | 26 052 | 27.94° | 0 | 0.67 s |
| Caso 005 de OGR FEM2D (100 m de semilado), hueco de radio 1 en 128 cuerdas (como en la 0.2.5), h = mín(1.5, 0.05 + 0.25 r) | 90 771 | 20.99° | 0 | 2.39 s |
| Lo mismo, el hueco en 6 arcos | 90 911 | 24.85° | 0 | 2.34 s |

En ninguna de estas mallas, todas con B = √2, queda un triángulo por encima de B, ni se invierte
ninguno. Es lo medido, no una garantía.

## 4. Queda abierto

- La regla 8 y la etiqueta de la 0.2.6.
- El escrito de vuelta para OGR FEM2D con la API cerrada (las notas se llaman distinto de lo que
  se le propuso: `arc_bound` con `met`, y `arc_unproven` en vez de `arc_guarantee`).
