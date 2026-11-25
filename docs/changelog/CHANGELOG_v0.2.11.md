# OGR Core v0.2.11

**Un `.ogr` con un valor que esta versión no conoce, o con un peso o un nombre de otro tipo, se
rechaza al abrirlo, con su código (D429).** Hasta ahora cuatro lectores ponían otro valor sin
avisar: el factor de seguridad cambiaba y nada lo decía. Ningún `.ogr` válido cambia al abrirlo.
Es un cambio compatible para los archivos que escribe el programa y obliga a OGR Slip2D a traducir
dos códigos nuevos y dos enumeraciones (§2).

Lo pidió OGR Slip2D (2026-11-24). La propietaria eligió la opción (a) para todos: rechazar al
abrir, como D414 ya hace con las enumeraciones.

## 0. Lo que se encontró

Medido por la sesión de Slip2D con ogr-core 0.2.10, cambiando un solo valor del JSON del proyecto
de ejemplo:

| Lector | Valor | Se leía como |
|---|---|---|
| `_model_from_dict` (`hydraulic_properties.py`) | `model = "future_model"`, o un `unsaturated_model` heredado desconocido | `PermeabilityModel.CONSTANT` |
| `_envelope_from_dict` (`material.py`) | `drawdown_envelope.kind = "future"` | sin envolvente (`None`) |
| `WaterPressureGrid.from_dict` | `interpolation = "kriging"` | IDW: `value_at(3, 3)` daba 1,5745, frente a 1,9 con TPS |
| `SeismicRecord.from_dict` | `source_unit = "furlongs"` | `AccelerationUnit.G` |
| `Material.from_dict` | `unit_weight = "x"` (y `sat_unit_weight`) | abría; Slip2D fallaba al calcular con un `TypeError` |
| `Material.from_dict` | `name = 5` o `null` | abría con ese valor |

- **Censo del banco de Slip2D**, sobre el JSON en crudo de 30 800 `.ogr`: **0 afectados**. Hay 698
  envolventes, todas `r`; 234 rejillas, todas `tps`; los modelos de permeabilidad son `constant`,
  `gardner`, `simple`, `user_defined` y `van_genuchten`; no hay ningún registro sísmico ni ningún
  peso, γsat o nombre de otro tipo. El arreglo no mueve ninguna fila del banco.
- **Ningún código decía «un campo de otro tipo dentro de un elemento»**: `file_shape` comprobaba
  secciones y elementos, y su docstring dejaba el resto a D429.
- **`ENUM_UNKNOWN` no sirve para la envolvente ni para la interpolación.** No son enumeraciones, y
  su `{enum}` se traduce por el nombre de una clase (`ENUM_NAMES` de Slip2D). Poner ahí un nombre
  inventado rompería el censo de Slip2D, que exige que cada nombre de `ENUM_NAMES` lo lea un
  `read_enum`. Por eso llevan un código propio.
- **Un `null` explícito** (`"model": null`, `"interpolation": null`, `"source_unit": null`) daba el
  valor por defecto, aunque el escritor nunca escribe un `null` ahí. Decisión de la propietaria
  (2026-11-25): es un valor, no una ausencia, y se rechaza. La envolvente sigue leyendo un `null`
  como «sin envolvente», porque eso es lo que escribe `_envelope_to_dict`.
- El `pytest.raises` del runner no devuelve la excepción (`with … as info` da `None`). El test
  nuevo la captura con un `try`.

## 1. Qué cambia

- `ogr_core/file_messages.py`: dos códigos nuevos y la función `value_unknown`.
  - `file.value_unknown`: `Unknown value of '{field}': '{value}'. Known: {known}`. `value` es de
    tipo `file_value` (un `null` sale como `null`), `known` va como `Joined` y `field` es la clave
    del archivo, sin traducir, como `section` en D422.
  - `file.field_type`: `The field '{field}' of item {n} of the section '{section}' of the file must
    be {expected}, not {found}.`, con `expected` y `found` de tipo `json_shape`.
  - Los dos textos se construyen con su f-string (`file_refusal`), no desde la plantilla.
- `_model_from_dict`: `read_enum(PermeabilityModel, …)` para `model` y para un `unsaturated_model`
  heredado. Sin `model`, y con `unsaturated_model` ausente o `"saturated"`, sigue siendo constante.
- `SeismicRecord.from_dict`: `read_enum(AccelerationUnit, …)`. Sin `source_unit`, sigue siendo `g`.
- `_envelope_from_dict`: un `kind` fuera de `ENVELOPE_KINDS = ("r", "kc1")`, o que falta en un dict
  no vacío, da `file.value_unknown` con `field = "drawdown_envelope.kind"`. La ausencia, `{}` y
  `null` siguen dando `None`.
- `WaterPressureGrid.from_dict`: una `interpolation` fuera de `INTERPOLATIONS = ("tps", "idw")` da
  `file.value_unknown` con `field = "interpolation"`. Si falta, sigue siendo `tps`. `value_at` no
  cambia.
- `ogr_core/project/file_shape.py`: tabla `ITEM_FIELDS` (`materials`: `name` texto, `unit_weight` y
  `sat_unit_weight` número). La comprueba `check_shape`, que es donde está el número del elemento.
  Un número es `int` o `float` y nunca un booleano. Un campo ausente se deja como estaba.
- `tests/test_file_values_v0211.py`: 22 tests. Contra los lectores de la 0.2.10 fallan 12.

## 2. Lo que tiene que cambiar cada programa (regla 10)

- **OGR Slip2D**, antes de correr su suite contra este núcleo:
  - traducir `file.value_unknown` y `file.field_type` (los exige `TestEachCodeSaysItInSpanish`);
  - añadir `PermeabilityModel` y `AccelerationUnit` a `ENUM_NAMES` de `ogr_gui/labels.py`, porque
    ahora los lee `read_enum`;
  - dejar vacía `_TOLERANT` en `tests/test_import_messages_v1437.py`.
- **OGR FEM2D**: nada. Comprobado en su código: no usa ninguno de estos lectores ni
  `Project.from_dict`.

## 3. Pruebas

| Qué | Resultado |
|---|---|
| `tests/test_file_values_v0211.py` | 22 de 22; 12 fallan contra los lectores de la 0.2.10 |
| Suite del núcleo entera, `--jobs 4` (Windows) | 984 de 984, sin fugas |

**La regla 8**, el 2026-11-25 en Windows, contra la rama `d429-lectores` en `0.2.11.dev0`:

| Qué | Resultado |
|---|---|
| OGR Slip2D `c6ba3be` (su `3a2e4bb` más las traducciones de §2) **entera**, con `--jobs 4`, `--dev-core` y fuera de pantalla, contra `eec1912` | 7597 casos: 7595 pasan, 0 fallos, 2 saltados, ninguna fuga ni tramo muerto. El censo de D414 no falla por nada más. La corrió la sesión de Slip2D |
| OGR FEM2D | **No se corrió**: la propietaria la eximió esta vez (2026-11-25) |

**Una excepción a la regla 8, solo para esta versión.** La propietaria decidió etiquetar con la
suite de OGR Slip2D en verde y sin la de OGR FEM2D, por dos razones:

- FEM2D no usa ninguno de los lectores que cambian (§2);
- fija `v0.2.9`, así que esta etiqueta no le llega hasta que suba su fijación.

Además, su árbol tenía trabajo sin confirmar de su sesión: una corrida ahí no habría medido ningún
commit suyo. **Cuando FEM2D suba su fijación a esta versión o a una posterior, su suite entera
contra ella es la que lo comprueba.**

La CI de la PR 43, en `677173f`, en verde en todos sus trabajos (Linux):

- **OGR FEM2D** (su `main`) contra el núcleo de la PR, entera: pasa. Es la única corrida de FEM2D
  contra esta versión, y no es la de la regla 8, que se hace en Windows y a mano.
- **OGR Slip2D** (su `main` en `c6ba3be`) contra el núcleo de la PR, entera: 7597 casos, 7591
  pasan, 0 fallos, 6 saltados.
- La primera vez falló en 4 tests de Slip2D porque su `main` en GitHub (`94d2e9a`) todavía no
  tenía `c6ba3be`, que adapta justo esos 4. Se relanzó cuando Slip2D lo subió.

`ec1bc3b` y el commit de la etiqueta tienen el mismo `ogr_core` que `eec1912`, contra el que corrió
Slip2D: entre ellos solo cambian este changelog, `docs/consumidores.md` y el número de versión.
