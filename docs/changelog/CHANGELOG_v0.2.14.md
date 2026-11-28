# OGR Core v0.2.14

**La tanda P10 de OGR Slip2D: D433, D443, D444, D445, D446 y D449.** Lo pidió OGR Slip2D
(2026-11-27, su 0.1.503, que fija `v0.2.12`), con las decisiones de la propietaria del mismo día.
Cada ficha, en su rama y su PR; esta versión las reúne.


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

## D445 — `id` repetidos al leer, y Borrar por identidad

### Lo que se encontró

- `Project.from_dict` aceptaba sin decir nada dos `Boundary.id` iguales, dos `Polyline.id` iguales
  (todo `.ogr` con un Copiar contorno guardado entre Slip2D 0.1.59 y 0.1.455, su D425) y dos `id`
  de superficie del usuario iguales.
- `Project.remove_boundary(bid)` quitaba **todos** los contornos con ese `id`, y
  `RemoveBoundaryCommand.execute` guardaba el índice del **primero** con el `id`
  (`ids.index(self.boundary.id)`), no el del objeto. Con dos contornos de un mismo `id`, Borrar
  quitaba los dos y Deshacer devolvía uno, en el sitio del primero. Medido por Slip2D en su
  0.1.485: quedan 0 de 2, y deshacer devuelve 1 de 2.
- `AddBoundaryCommand.undo` también quitaba por `id`: deshacer el añadido de un contorno con el
  `id` de otro quitaba los dos.
- Nadie lee `Polyline.id` (ni el núcleo ni los programas, salvo para copiarlo).
- El núcleo no tenía ningún camino para que la lectura dijera algo sin rechazar el archivo.

### Qué cambia

- `Project.read_notes`: lista nueva de notas con código (`Coded`) que rellena `from_dict` y que no
  se guarda. Vacía en un modelo construido de otro modo.
- `ogr_core/project/rules.py`:
  - `duplicate_id_notes(project)`: una nota por cada `Boundary.id` repetido
    (`rule.duplicate_boundary_id`) y por cada `id` repetido entre las superficies del usuario, círculos y
    polilíneas juntos (`rule.duplicate_user_surface_id`). No renueva nada: los enlaces leen esos `id`.
    La lectura la pregunta, y un programa puede preguntarla también en su validación.
  - `renew_repeated_polyline_ids(project)`: da un `id` nuevo a cada polilínea de contorno cuyo
    `id` ya tiene otra anterior. La primera conserva el suyo. Devuelve una nota por `id`
    (`rule.polyline_id_renewed`).
  - `boundary_label(project, boundary)`: el contorno nombrado en una nota. Lleva su nombre si tiene
    uno propio (`boundary_has_given_name`), su tipo y su posición entre los de su tipo, contada
    desde 1.
- `ogr_core/project/messages.py`, en `RULES`: los tres códigos y sus cuatro etiquetas
  (`rule.boundary_label`, `rule.boundary_label_named`, `rule.user_circle_label` y
  `rule.user_polyline_label`). Los textos ingleses:

  ```
  The boundaries {boundaries} share the id '{id}': whatever refers to that id (the water surface or the anisotropic surface of a material, a support, a face of Sarma's method) may read either of them.
  The user surfaces {surfaces} share the id '{id}': whatever refers to that id may read either of them.
  The boundaries {boundaries} shared the polyline id '{id}'; it was renewed on reading for all but the first. Nothing reads it, so the model is the same.
  {kind} #{n}
  '{name}' ({kind} #{n})
  user circle #{n}
  user polyline #{n}
  ```
- `Project.remove_boundary(boundary)`: quita **un** contorno, el objeto dado (por identidad) o,
  si se le da un `id`, el primero con ese `id`.
- `RemoveBoundaryCommand.execute` guarda el índice del objeto y quita el objeto. Si el objeto ya no
  está en el modelo (un modelo restaurado de una copia), quita el primero con su `id`, uno solo.
  `undo` lo devuelve a ese sitio. `AddBoundaryCommand.undo` quita su objeto.
- `tests/test_duplicate_ids_v0214.py`: 13 tests. Son los dos casos del guion de Slip2D
  (`_auditoria/P10_D445/medir_d445.py`): Borrar deja 1 de 2 y Deshacer lo devuelve a su sitio, el
  segundo y también el primero. A ellos se suman dos superficies del usuario con un mismo `id`,
  un círculo y una polilínea con un mismo `id`, y un archivo sin repetidos que no cambia ni un bit
  al leer y guardar. Contra el núcleo de antes fallan 12.

### Lo que tiene que cambiar cada programa (regla 10)

- **OGR Slip2D**:
  - mostrar `project.read_notes` al abrir un `.ogr`, en la ventana y en el `project_open` del
    agente;
  - llevar `duplicate_id_notes(project)` a `project_validate` como avisos;
  - en `tests/test_core_messages_v1333.py`, una muestra de los siete códigos nuevos de `RULES`, y su
    castellano en el diccionario;
  - su `_do_delete_boundary` ya pasa el objeto (`RemoveBoundaryCommand(boundary=b)`): no tiene que
    cambiar. El borrado del agente (`boundary_edit`, `op="delete"`) quita por índice y tampoco.
- **OGR FEM2D**: nada obligatorio. Si abre `.ogr` de Slip2D, puede mostrar `read_notes`.

## D443 — convertir un contorno que usan materiales (decisión B)

### Lo que se encontró

- `convert_boundary` copia el contorno con otro tipo y el mismo `id`. `Material.water_surface_id`
  y `Material.anisotropic_surface_id` se quedaban como estaban, y sus lectores filtran por tipo
  (`resolve_water_surface`, `material_surfaces`). En el talud de ejemplo, el nivel freático
  convertido en línea piezométrica dejaba u en (25; 0,5) en 0 kPa, cuando antes era 73,6, y el
  modelo seguía calculando. El test nuevo lo reproduce (`test_without_the_rule_it_was_zero`).
- La limpieza de enlaces al borrar vivía en el agente de Slip2D (`ogr_api/ops/model.py`), no en el
  núcleo.
- **Encontrado al escribirlo, y aplicado como parte de la regla B** («se trata como borrar el
  contorno»): borrar una superficie anisótropa que lee una junta de un material Generalized
  Anisotropic se rechaza (`surface_in_use_refusal`, desde Slip2D 0.1.249), pero convertirla en
  otro tipo no se rechazaba, y la junta se quedaba sin orientación. Ahora `conversion_refusal`
  la rechaza igual que el borrado. La propietaria lo confirmó el 2026-11-28.
- **Encontrado al escribirlo, y añadido por decisión de la propietaria (2026-11-28)**: un material
  con el modelo de nivel freático y **sin** `water_surface_id` lee el primer nivel freático del
  modelo (`resolve_water_surface`, la vuelta atrás heredada). Si ese nivel freático se convertía en
  línea piezométrica, el material perdía su presión de poros igual, porque no estaba enlazado por
  `id` y la regla no lo veía. Ahora la regla lo mueve igual que a uno enlazado. Si sigue al
  contorno, recibe el `id`, para seguir leyendo esa superficie. Si el contorno se borra o se
  convierte en un tipo sin lector, se limpia.

### Qué cambia

- `ogr_core/project/rules.py`:
  - `conversion_link_changes(project, boundary_id, new_type)` devuelve qué haría la conversión
    con los enlaces, sin hacerlo. Es una lista de `LinkChange(material_id, material_name, link,
    change)`, con `link` igual a `"water_surface"` o `"anisotropic_surface"` y `change` igual a
    `"followed"` o `"cleared"`.
    - Nivel freático ↔ línea piezométrica: el enlace sigue, y el modelo de poros pasa al del tipo
      nuevo.
    - Cualquier otro tipo: el enlace de agua se limpia y los poros pasan a `NONE`. El enlace
      anisótropo se limpia si el tipo nuevo no es una superficie anisótropa.
    - Solo los enlaces que el material lee. Un `water_surface_id` bajo Ru, una constante o un
      campo de elementos finitos no es de la conversión.
    - Los materiales que la leen por la vuelta atrás (`_water_readers`, con
      `materials_using_surface`), igual.
  - `relink_on_conversion(project, boundary, new_type)` aplica eso a los materiales y devuelve los
    cambios. **No sustituye el contorno**: eso lo hace quien llama, en su propio paso de deshacer.
  - `removal_link_changes(project, boundary_id)` y `unlink_on_removal(project, boundary_id)` son
    lo mismo para el borrado. `unlink_on_removal` quita también un `water_surface_id` que el
    material no lee, sin cambiarle el modelo, como hacía el agente. Una conversión sin lector y un
    borrado dan los mismos cambios, y un test lo comprueba.
  - `stale_surface_links(project)` da los avisos con código de los enlaces a un contorno de un
    tipo que no los lee, los que puede traer un `.ogr` viejo (`rule.stale_water_link` y
    `rule.stale_anisotropic_link`).
  - `conversion_refusal` rechaza convertir una superficie anisótropa que lee una junta.
- `ogr_core/project/messages.py`, en `RULES`, los dos avisos:

  ```
  The material '{material}' takes its water surface from {boundary}, which its pore-pressure model does not read: assign it a water surface again.
  The material '{material}' takes its anisotropic surface from {boundary}, which is not an anisotropic surface: its strength does not read it.
  ```
- `tests/test_conversion_links_v0214.py`: 14 tests.
  - u en (25; 0,5) tras convertir el nivel freático en línea piezométrica es la solución
    hidrostática bajo la línea horizontal, γw·(8 − 0,5) = 73,6 kPa. Es también lo que da un
    material puesto con `assign_water_surface` en la misma línea: **medido**.
  - La ida y vuelta nivel freático → línea piezométrica → nivel freático devuelve la u de
    partida.
  - Una superficie anisótropa convertida en capa débil, y un nivel freático convertido en capa
    débil, limpian el enlace.
  - Un enlace que el material no lee se queda como está.
  - El borrado da los mismos cambios que la conversión sin lector.
  - Los avisos de los enlaces viejos salen con su texto.
  - La junta rechaza la conversión.
  - Un material que lee el nivel freático por la vuelta atrás sigue a la línea piezométrica y
    recibe el `id`, con u = 73,6 kPa; sin la regla, 0. Borrado o convertido en capa débil, se
    limpia.

  Son 18 tests con los de la vuelta atrás.

### Lo que tiene que cambiar cada programa (regla 10)

- **OGR Slip2D**:
  - en los dos Convertir de la ventana (`_apply_conversion`) y en el `change_type` del agente,
    llamar a `relink_on_conversion` en el mismo paso de deshacer que sustituye el contorno, y
    escribir la nota de cada cambio. Para `cleared`, los textos de borrar; para `followed`, uno
    nuevo;
  - en el borrado del agente, usar `unlink_on_removal` en lugar de su limpieza propia, y en el de
    la ventana igual;
  - llevar `stale_surface_links(project)` a `project_validate` como avisos;
  - las muestras de los dos códigos nuevos en `test_core_messages_v1333.py` y su castellano;
  - el rechazo nuevo de `conversion_refusal` (la junta) llega por el camino que ya tienen los dos
    Convertir.
- **OGR FEM2D**: nada.

## D444 — la autointersección y la importación, a la regla

### Lo que se encontró

- `boundary_refusal` recibía solo el tipo, y `conversion_refusal` no miraba la geometría salvo el
  exterior cerrado. Las dos comprobaciones con las que el agente de Slip2D rechaza lo que la
  ventana deja pasar estaban escritas a mano fuera del núcleo:
  - la autointersección, `has_self_intersections`, en `ogr_api/ops/model.py`;
  - los dos exteriores de una importación, en `ogr_api/ops/files.py`.
- **Una conversión cambia la polilínea**: un anillo cerrado pasa a abierto en los tipos que son
  líneas (nivel freático, línea piezométrica, capa débil…), y su segmento de cierre deja de
  contar. La pregunta va sobre la polilínea del contorno **convertido**.
- **Encontrado, informado y corregido por decisión de la propietaria (2026-11-28).** El saneador
  del DXF (`ogr_core/dxf/sanitiser.py`, `_validate`) se queda con el exterior más grande cuando hay
  varios. Si dos tenían **la misma área**, fallaba con
  `TypeError: '<' not supported between instances of 'DxfPolyline' and 'DxfPolyline'`, porque
  `areas.sort(reverse=True)` comparaba las polilíneas al empatar. Lo daba `preview()` con dos
  rectángulos iguales en la capa del exterior, y es anterior a esta versión. Ahora se ordena solo
  por el área. Como el orden es estable, de dos iguales se queda el primero dibujado, y el
  problema `external_multiple` se sigue anotando. Por ese saneador, además, dos polilíneas de
  exterior en el DXF nunca llegan a `apply_to_project`.
- **Ampliado por decisión de la propietaria (2026-11-28)**: importar sin sustituir el modelo una
  capa de nivel freático, grieta o línea de desembalse en un modelo que ya tiene uno dejaba dos,
  igual que el exterior. El agente tampoco lo comprobaba. Ahora `import_refusal` lo rechaza con
  `import_single_instance`.

### Qué cambia

- `ogr_core/project/rules.py`:
  - `boundary_refusal(project, btype, *, ignoring=None, polyline=None)`. Con `polyline`, después de
    las reglas del tipo, pregunta las de su geometría (`polyline_refusal`). Sin ella, la respuesta
    de siempre, para quien llama solo con el tipo.
  - `polyline_refusal(btype, polyline)`:
    - `external_not_closed`, un exterior de una polilínea abierta, con el texto de siempre;
    - `self_intersecting`, una polilínea de 4 vértices o más que se cruza (`has_self_intersections`),
      con el texto del agente, `SELF_INTERSECTING = "The edit makes the boundary cross itself."`.
  - `conversion_refusal` pregunta también `polyline_refusal` sobre la polilínea convertida
    (`convert_boundary`), después de las reglas de siempre y en su orden.
  - `import_refusal(project, preview, options)` responde sin escribir nada. Da
    `import_two_external` si la importación deja más de un exterior, contado como lo cuenta
    `apply_to_project`: lo que quita «sustituir el modelo» (los tipos que define el DXF) y las
    polilíneas de dos puntos o más que añade. La importación se rechaza entera (decisión de la
    propietaria). El texto y el consejo del agente son constantes:

    ```
    IMPORT_TWO_EXTERNAL = "The import leaves two External boundaries."
    IMPORT_TWO_EXTERNAL_HINT = "Use replace_model=true, or map only one layer to 'external'."
    ```
- `import_refusal` pregunta lo mismo para los otros tipos de los que un modelo tiene uno solo:
  nivel freático, grieta y línea de desembalse. El código es `import_single_instance`, después
  del exterior. Los textos están en `IMPORT_TWO`, y el consejo, en `import_hint(btype)`, con el
  `layer_kinds` del agente:

  ```
  The import leaves two Water Tables.
  The import leaves two Tension Crack boundaries.
  The import leaves two Drawdown Lines.
  Use replace_model=true, or map only one layer to 'water_table'.   (y 'tension_crack', 'drawdown')
  ```
- `ogr_core/dxf/sanitiser.py`: dos exteriores de igual área ya no dan `TypeError`.
- `tests/test_boundary_rules_d444_v0214.py`, 15 tests: las filas de la tabla de la ficha a nivel de
  regla, con estos controles:
  - un nivel freático sin otro puesto se acepta;
  - una polilínea que no se cruza se acepta;
  - quien llama con el tipo solo recibe lo de siempre;
  - el anillo cuyo segmento de cierre lo cruza se acepta abierto como nivel freático y se rechaza
    cerrado como contorno de material;
  - con «sustituir el modelo», o en un modelo sin exterior, la importación se acepta;
  - una capa de material se acepta.

  Contra el núcleo de antes fallan 13. Con las decisiones del 2026-11-28 se añaden 5 más:
  - un segundo nivel freático, y su control (con «sustituir el modelo», o sin otro puesto);
  - dos grietas en el archivo;
  - el exterior se pregunta primero;
  - el empate del saneador.

  Son 20 en total.

### Lo que tiene que cambiar cada programa (regla 10)

- **OGR Slip2D**:
  - **Convertir herramienta en contorno**: `boundary_refusal(project, btype, polyline=…)` antes de
    añadir, y el motivo en la barra;
  - **Importar DXF**: `import_refusal` antes de `apply_to_project`. Si responde, la ventana no
    escribe nada y lo dice;
  - **Convertir contorno** ya pregunta `conversion_refusal`: la autointersección le llega sola;
  - el agente puede dejar sus dos comprobaciones propias y preguntar las del núcleo. Los textos
    son los mismos;
  - los códigos nuevos de `Refusal` son `self_intersecting`, `import_two_external` e
    `import_single_instance`. Para el último, el texto es `IMPORT_TWO[btype]` y el consejo,
    `import_hint(btype)`.
- **OGR FEM2D**: nada obligatorio. Si añade contornos o importa DXF, las mismas reglas.

## D449 — el soldado de extremos funde una capa fina (decisión A + C)

### Lo que se encontró

- En `_nearest_on_polyline` (`ogr_core/geometry/regions.py`, dentro de `_build_regions_shapely`),
  un vértice a menos de `weld_tol` (`diag × 8e-3`) ganaba a un segmento aunque el extremo ya
  estuviera **sobre** ese segmento. Dos contactos casi paralelos que acaban en el exterior saltaban
  al mismo vértice, y la capa entre ellos desaparecía sin aviso. En un bloque de 100 × 30, una capa
  de 0,1 a 0,8 m daba 2 regiones en lugar de 3, en los dos órdenes de dibujo y también a ×10 (5 a
  8 m).
- **Con A, la tabla de Slip2D sale fila a fila** (`_auditoria/P10_D449/medir_regla_a_0.1.503.log`):
  - acabando en el borde, 3 regiones en todos los casos;
  - acabando fuera del modelo, las capas finas se siguen fundiendo, porque el extremo no está sobre
    ningún segmento. Es el caso del aviso C.
- **El censo del banco**, repetido aquí con un guion propio sobre los mismos 230 modelos: el 02 y
  los manuales 03 a 07, sin instantáneas, `_auditoria` ni `Evaluaciones`. Se compara el
  `ogr_core 0.2.12` instalado en Slip2D con este árbol, por material y área de cada región, y da
  0 errores.
  - **Cambian 3 modelos**, los mismos que contó Slip2D: la presa de Talbingo,
    `02/Problema005/modelo.ogr`, `02/Problema005/modelo_aguas_arriba.ogr` y
    `02/Problema006/modelo.ogr`.
  - Con 0.2.12 hay una astilla de 262,27 m² y *Transition* tiene 5331,80 m². Con A, la astilla
    desaparece, *Transition* baja a 5096,72 m² y aparece el filtro, de 497,35 m². Son los números
    de la ficha al sexto decimal.
  - Con A, `contacts_welded` no da ninguna nota en los 230.
- **Encontrado, anterior y menor**: las caras del constructor no embaldosan el exterior al último
  bit. El bloque de 100 × 30 suma 3000,000061 m², 2e-8 de más, y la capa de 2 m mide 200,000046 m².
  Pasaba igual con 0.2.12. El test compara con tolerancia relativa 1e-5 por eso, y lo dice.
- El constructor sin Shapely (`_build_regions_pure`) no tiene soldado: ni A ni C le tocan.

### Qué cambia

- `ogr_core/geometry/regions.py`:
  - **regla A**: en `_nearest_on_polyline`, un extremo a ≤ `ON_SEGMENT × diag` (1e-9) de un
    segmento no salta a un vértice. Un vértice a ≤ `SAME_POINT` (1e-12) sigue ganando, porque ya es
    el mismo punto;
  - `build_regions(..., welds=None)`: con una lista, recibe un `EndpointWeld` por cada par de
    extremos de dos contactos abiertos distintos que el soldado deja en el mismo punto y que antes
    estaban a más de 1e-12. Lleva los dos contornos, sus extremos, el punto y la distancia. Las
    regiones son las mismas con lista y sin ella.
- `ogr_core/project/rules.py`: **regla C**, `contacts_welded(project)`, una nota con código
  (`rule.contacts_welded`) por par de extremos fundidos. Es para la validación de un programa, como
  aviso. El texto:

  ```
  The material boundaries {first} and {second} end {distance:.3f} m apart, within the welding tolerance, and were joined at ({x:.3f}, {y:.3f}): whatever lay between those two ends is not a region of its own. Move them apart, or end them on the same point.
  ```
- `tests/test_endpoint_weld_d449_v0214.py`, 7 tests:
  - el bloque en sus dos formas, en los dos órdenes y a ×1 y ×10;
  - acabando en el borde, 3 regiones, con la capa igual a 100·k × espesor, la solución cerrada, y
    sin nota;
  - acabando fuera, las capas finas en 2 regiones con dos notas C, cada una con la distancia igual
    al espesor, y las gruesas en 3 sin nota;
  - el control: dos tramos que comparten extremo exacto y un tercero en T no dan nota;
  - `welds` no mueve ninguna región.

  Contra el núcleo de antes fallan los 7.

### Lo que tiene que cambiar cada programa (regla 10)

- **OGR Slip2D**:
  - **cambian las regiones de 005 y 006** (la presa de Talbingo). Es el arreglo: lo declara en su
    changelog y en la ficha del banco. Los factores no cambian ni un bit, según su
    `ab_factores_regla_a.py`;
  - el aviso C en la barra y en `project_validate` (`contacts_welded`);
  - la muestra del código nuevo en `test_core_messages_v1333.py` y su castellano.
- **OGR FEM2D**: las regiones de un modelo con dos contactos así cambian igual, y su malla con
  ellas. Su suite contra este núcleo lo dirá.
