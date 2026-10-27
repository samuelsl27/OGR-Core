# OGR Core

**El núcleo compartido de la suite [OpenGeoRock](https://opengeorock.org)**: geometría, materiales,
modelo de proyecto, cargas, soportes, hidráulica, estadística, anotaciones, DXF, informes, y la
malla y el solver de filtración por elementos finitos.

[English version](README.md)

> **Estado: primera versión, 0.1.0.** El código viene del núcleo de
> [OGR Slip2D](https://github.com/samuelsl27/OGR-Slip2D) (su commit `2d68c29`).

## Quién lo usa

| Programa | Relación con este núcleo |
|---|---|
| OGR FEM2D (en preparación): análisis geotécnico 2D por elementos finitos | **Es su núcleo.** Fija una versión etiquetada |
| [OGR Slip2D](https://github.com/samuelsl27/OGR-Slip2D): estabilidad de taludes 2D por equilibrio límite | **Conserva por ahora su propia copia**, de la que salió este repositorio. Si los dos se unen, y cuándo, se decidirá más adelante |

Hasta entonces hay dos copias del núcleo, y cada cambio de este se anota en el changelog respecto a
ese punto de partida. Slip2D y un programa construido sobre este núcleo no deben compartir un entorno
de Python: los dos instalan un paquete llamado `ogr_core`.

## Instalar para desarrollar

```bash
git clone https://github.com/samuelsl27/OGR-Core.git
cd OGR-Core
python -m venv .venv && source .venv/bin/activate
pip install -e .
python tests/_runner.py
```

Para trabajar en un programa con un núcleo local, se instala primero este repositorio en editable y
después el programa. El runner del programa dice de qué árbol, de qué commit y de qué versión sale
el núcleo, y se niega a ejecutar si la versión no es la que fija.

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
