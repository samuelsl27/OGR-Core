# OGR Core v0.2.12 (sin etiquetar)

**Un patrón que no casa con ningún archivo hace salir al runner con código 2, aunque otros patrones
casen (D431).** Antes el runner lo descartaba sin decir nada, y una errata en una lista de patrones
se leía como un área probada. Es compatible: ningún programa tiene que cambiar código.

Lo pidió OGR Slip2D (2026-11-24). La propietaria eligió la opción (a): salir con 2 antes de
ejecutar nada.

## 0. Lo que se encontró

- **`select_files` es una unión, y el único aviso era la selección vacía.** Un patrón muerto junto
  a otro que casa desaparecía. Lo midió Slip2D con la 0.2.10:
  - `--list transient zz_no_casa_d431` daba `EXIT=0` y «125 test(s) in 5 file(s) of 503», sin
    nombrar el segundo patrón;
  - `--list zz_no_casa_d431`, solo, daba `EXIT=2`.
- **Cuándo mordió**, en Slip2D:
  - en su 0.1.439, la lista de vecinos de un changelog llevaba `support_type`, `support_dialog` y
    `define_support`, y ninguno casaba con nada. La corrida dio 255 casos de 14 archivos sin decir
    nada, y el changelog afirmó que se habían probado tres áreas que no corrió nadie;
  - volvió a pasar en su 0.1.445, con `interpret_window`.
- **El mismo agujero en los nombres de test, sin cambiar aquí.** Con `alpha` y `geometry` y
  `-k two`, `--list` da código 0 y «1 test(s) in 2 file(s) of 3». El archivo `geometry` entra en la
  selección sin aportar ningún test, y nada lo dice. Solo sale código 2 si el `-k` no casa en
  ningún archivo. Queda para decidir.
- El patrón que normalizado queda vacío (`""`, `/`, `.py`) se descartaba a propósito, y sigue
  igual. Solo, deja la selección vacía y acaba en el aviso de siempre. Junto a uno que casa, la
  corrida es la de ese patrón.
- Ningún test de los tres repositorios pasaba un patrón muerto junto a otros que casan.

## 1. Qué cambia

- `ogr_core/testing/runner.py`:
  - función nueva `unmatched_patterns(tests_dir, patterns)`: los patrones, tal como se escribieron,
    cuya forma normalizada no está vacía y no casa con el `stem` de ningún archivo;
  - `main` la consulta justo después de `select_files`, antes de `--fast`, de `-k` y de `--list`.
    Si la selección no está vacía y hay patrones muertos, sale con 2 sin ejecutar nada:

    ```
    No test file matches ['zz_no_casa_d431'] — the other pattern(s) select 5 file(s); nothing was run.
    Did you mean: …
    503 files available — `python tests/_runner.py --list` shows them all.
    ```

    Las sugerencias son las de `_suggest`, solo para los patrones muertos. Vale igual con `--list`
    y con `--jobs`.
  - Con todos los patrones muertos, la salida es la de siempre, byte a byte.
- `tests/test_runner_dead_pattern_v0212.py`: 12 tests. Contra el runner de la 0.2.11 fallan 9.

No cambian la unión, el orden y el `FILTERED RUN` de los patrones que casan, el código 2 de un `-k`
sin casos, ni la corrida sin patrones.

## 2. Lo que tiene que cambiar cada programa (regla 10)

Nada. El `_runner.py` de cada programa solo pasa configuración, y la regla vive en el núcleo. El
`AGENTS.md` de OGR Slip2D ya prometía esto. Cuando un programa suba su fijación, las dos órdenes
del informe tienen que dar `EXIT=2`, y la primera tiene que nombrar `zz_no_casa_d431`.

## 3. Pruebas

| Qué | Resultado |
|---|---|
| `tests/test_runner_dead_pattern_v0212.py` | 12 de 12; 9 fallan contra el runner de la 0.2.11 |
| Suite del núcleo entera, `--jobs 4` (Windows) | 996 de 996, sin fugas |

**Pendiente (regla 8):** la suite entera de OGR Slip2D y la de OGR FEM2D contra este árbol, con
`--dev-core`.
