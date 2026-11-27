# OGR Core v0.2.13

**El informe dice de la crítica de una corrida de Newmark con talud arriba lo que la corrida hace
(D437 de OGR Slip2D).** Con «Permitir desplazamiento talud arriba», Slip2D 0.1.499 publica como
crítica la superficie de **mayor desplazamiento neto**, y el PDF seguía escribiendo «the one with
the lowest Ky of this method». Es compatible: ningún programa tiene que cambiar código, pero Slip2D
necesita traducir una cadena nueva (sección 2).

Lo pidió OGR Slip2D (2026-11-27), después de su 0.1.499 (`0ecedea`).

## 0. Lo que se encontró

- **La premisa de la fila deja de valer con talud arriba.** Sin talud arriba, el desplazamiento de
  un bloque rígido no crece con su aceleración crítica (Newmark, 1965), así que la superficie de
  menor Ky, que es lo que minimiza la búsqueda, es la que más se mueve. Con talud arriba, el
  desplazamiento es neto (talud abajo menos talud arriba) y eso falla. Lo midió Slip2D en su talud
  de ejemplo (c = 12 kPa, rejilla 5×5×6, Bishop, sinusoide de 0,3 g y 2 Hz durante 4 s más 2 s de
  calma): la de menor Ky (0,1137) se movía 0,236 cm, y 4 de 152 se movían más; la que más,
  1,269 cm con Ky 0,1543.
- **Desde Slip2D 0.1.499 la crítica de esa corrida es la que más se mueve.** La elige
  `SearchResult.critical` cuando el resultado lleva `net_newmark = True`, un campo nuevo (False por
  defecto). `objective` sigue siendo `"ky"`, así que `reported_caption` sigue diciendo `NEWMARK`, y
  el desplazamiento y el Ky que imprimen las otras dos filas ya son los de la crítica publicada.
  Solo la tercera fila mentía.
- **Tres textos del núcleo decían lo contrario**: la fila y el docstring de `_seismic_rows`, que
  explicaba que no se afirmaba que se moviera más «porque con talud arriba no es verdad»; el
  docstring de `SeismicAnalysisSettings` («the surface that moves most is the surface with the
  lowest Ky»); y el del módulo `ogr_core/project/reported.py` («the critical surface is the one of
  the lowest Ky»).
- Ningún test del núcleo llamaba a `generate_report`. El test nuevo lo hace con un resultado de
  mentira y comprueba las cadenas que pasan por `translate`.

## 1. Qué cambia

- `ogr_core/report/report_generator.py`:
  - `_seismic_rows(crit, caption, project, T=_same, res=None)`: parámetro nuevo, el resultado del
    método. Con `getattr(res, "net_newmark", False)`, la fila de la crítica es

    ```
    the one with the largest net Newmark displacement of this method
    ```

    Si no (campo ausente, False o sin `res`), la de siempre, byte a byte:
    `the one with the lowest Ky of this method`. Por `getattr`, como `reported_caption` pregunta
    `objective`: el núcleo no importa el motor.
  - `generate_report` le pasa `res` desde el bucle de los métodos (sección «Global Minimums»).
  - El docstring de `_seismic_rows` y el comentario de esa llamada dicen la salvedad.
- `ogr_core/project/settings.py`, docstring de `SeismicAnalysisSettings`, y
  `ogr_core/project/reported.py`, docstring del módulo: con talud arriba la crítica es la de mayor
  desplazamiento neto.
- `tests/test_report_net_newmark_v0213.py`: 9 tests. Contra el núcleo de la 0.2.12 fallan 8; el
  que pasa es el de la llamada sin `res`, que es la fila de siempre.

No cambian las filas del desplazamiento y del Ky, la cabecera (`_headline`), los pies de figura ni
nada del informe en una corrida sin `net_newmark`.

## 2. Lo que tiene que cambiar cada programa (regla 10)

- **OGR Slip2D**, al subir su fijación:
  - la cadena nueva en su diccionario de castellano (`ogr_gui/i18n/__init__.py`, junto a «the one
    with the lowest Ky of this method»). La cadena inglesa exacta, para copiarla:

    ```
    the one with the largest net Newmark displacement of this method
    ```

    Sin ella, el PDF en castellano saldría con esa fila en inglés.
  - `tests/test_report_seismic_v1449.py`, un caso con talud arriba que compruebe la fila nueva.
- **OGR FEM2D**: nada. No usa el informe.

## 3. Pruebas

| Qué | Resultado |
|---|---|
| `tests/test_report_net_newmark_v0213.py` | 9 de 9; 8 fallan contra el núcleo de la 0.2.12 |
| Suite del núcleo entera, `--jobs 4` (Windows), en `e997b17` | 1005 de 1005, sin fugas, código 0 |

**La regla 8**, el 2026-11-27 en Windows, contra la rama `d437-newmark-neto`:

| Qué | Resultado |
|---|---|
| OGR Slip2D `cfaf5be` entera contra `e997b17` (19:12–19:19) | 7658 casos, 0 fallos. **No vale como evidencia**: su sesión cambió cuatro archivos de `ogr_gui` (`contours.py`, `dialogs/contour_options_dialog.py`, `interpret_window.py`, `i18n/__init__.py`) entre las 19:18:28 y las 19:19:13, en el último minuto de la corrida. Se repitió |
| OGR Slip2D `5eccc32` (su v0.1.502, fija `v0.2.12`) **entera**, con `--jobs 4`, `--dev-core` y fuera de pantalla, contra `70a041d` (19:38–19:44) | 7666 casos: 7664 pasan, 0 fallos, 2 saltados, ninguna fuga, código 0. `shared: ogr_core 0.2.13.dev0 … @ 70a041d`, `DEV CORE` antes y después. Su árbol, limpio antes y después. La corrió esta sesión |
| OGR FEM2D `14fafaa` (fija `v0.2.9`) **entera**, con `--dev-core` y fuera de pantalla, contra `70a041d` (19:42–19:52) | 840 casos: 839 pasan, **1 fallo**, código 1. Su árbol, limpio antes y después. El fallo es suyo y no de este cambio (abajo) |
| CI de la PR 48 (Linux) | En verde: las tres Python del núcleo y las suites de OGR Slip2D y OGR FEM2D contra este núcleo |

`70a041d` tiene el mismo `ogr_core` que `e997b17`; entre los dos solo cambia este changelog.

**El fallo de FEM2D**: `tests/test_project_setup_v001.py::test_and_given_back_the_core_of_the_run_it_runs`.
Relanza su runner con `python -S` y `PYTHONPATH` igual a la carpeta de donde sale el núcleo de la
corrida. Con `--dev-core`, esa carpeta es este árbol, no `site-packages`, y el hijo no encuentra
`ogr_ui`, que está instalado en `site-packages`: `ModuleNotFoundError: No module named 'ogr_ui'`
en `_install_gc_guard` (`tests/_runner.py`, línea 99). Falla igual contra `main` (`a8102b8`, sin
este cambio). En la CI pasa porque allí el núcleo va instalado en `site-packages`. Solo muerde
una corrida local con `--dev-core`, y se arregla en FEM2D.
