# OGR Core

**El núcleo compartido de la suite [OpenGeoRock](https://opengeorock.org)**: geometría, materiales,
modelo de proyecto, cargas, soportes, hidráulica, estadística, anotaciones, DXF, informes, y la
malla y el solver de filtración por elementos finitos.

[English version](README.md)

> **Última versión publicada: 0.2.3.** El código es el núcleo de
> [OGR Slip2D](https://github.com/samuelsl27/OGR-Slip2D) tal como estaba en ese programa en su commit
> `d48e2b3` (v0.1.471), con su malla y su filtración por elementos finitos dentro de `ogr_core.fem`.
> Desde la 0.2.0 hay un solo núcleo para todos los programas de la suite, y se cambia solo aquí.

## Quién lo usa

| Programa | Relación con este núcleo |
|---|---|
| [OGR Slip2D](https://github.com/samuelsl27/OGR-Slip2D): estabilidad de taludes 2D por equilibrio límite | De donde sale este código. **Es su núcleo** desde su v0.1.473: fija una versión etiquetada. Hasta su v0.1.471 llevaba su propia copia (y un paquete llamado `ogr_fem2d`, que ahora es `ogr_core.fem`) |
| OGR FEM2D (en preparación): análisis geotécnico 2D por elementos finitos | **Es su núcleo** desde su v0.0.3. Fija una versión etiquetada |

Un Slip2D hasta la v0.1.471 y un programa construido sobre este núcleo no deben compartir un entorno
de Python: los dos instalan un paquete llamado `ogr_core`, y ese Slip2D instala además uno llamado
`ogr_fem2d`, que es el nombre del paquete del programa de elementos finitos.

## Instalar para desarrollar

```bash
git clone https://github.com/samuelsl27/OGR-Core.git
cd OGR-Core
python -m venv .venv && source .venv/bin/activate
pip install -e .
python tests/_runner.py
```

Cada programa fija una versión etiquetada de este núcleo y la instala desde su etiqueta. El runner
del programa dice de qué árbol, de qué commit y de qué versión sale el núcleo, y se niega a
ejecutar si la versión no es la que fija. Para probar un programa contra un núcleo que se está
cambiando, se pone ese árbol en `PYTHONPATH` y se le pide al runner con `--dev-core`. Qué versión
fija cada programa y cómo se pide un cambio: [`docs/consumidores.md`](docs/consumidores.md).

## Reglas

Las reglas de trabajo están en [`AGENTS.md`](AGENTS.md), las mismas que en el resto de la suite. El
núcleo no importa ningún programa ni ninguna interfaz: ni Qt ni gráficas.

## Licencia

**GNU Affero General Public License v3.0 o posterior**
(AGPL-3.0-or-later). El texto íntegro está en [`LICENSE`](LICENSE).

En la práctica:

- Puedes usar OGR Suite libremente, **incluso para trabajo profesional de
  ingeniería**, y facturar ese trabajo sin pagar nada ni publicar nada.
  Ejecutar un programa no es una actividad restringida.
- Si lo **modificas** y dejas que otros usen tu versión **en remoto a
  través de una red** (un servicio web o SaaS), debes ofrecerles el código
  de tu versión. Cobrar por ese servicio está permitido; mantenerlo cerrado
  no.
- **No hay garantía de ningún tipo.** Los resultados deben contrastarse con
  cálculos independientes antes de basarse en ellos. Quien firma un
  proyecto es una persona, no un programa.

Cada archivo lleva su identificador SPDX, y un test falla si a alguno le
falta. Las contribuciones se aceptan en los términos de [`CLA.md`](CLA.md);
ver [`CONTRIBUTING.md`](CONTRIBUTING.md).

© 2026 Samuel Sáez López — Universidad Politécnica de Cartagena.
