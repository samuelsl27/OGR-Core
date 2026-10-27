# OGR Core

**The shared core of the [OpenGeoRock](https://opengeorock.org) suite** — geometry, materials,
project model, loads, supports, hydraulics, statistics, annotations, DXF, reports, and the
finite-element mesh and groundwater seepage solver.

[Versión en español](README.es.md)

> **Status: first version, 0.1.0.** The code comes from the core of
> [OGR Slip2D](https://github.com/samuelsl27/OGR-Slip2D) (its commit `2d68c29`).

## Who uses it

| Program | Relation to this core |
|---|---|
| OGR FEM2D (in preparation) — 2D geotechnical finite-element analysis | **Its core.** It pins a tagged version |
| [OGR Slip2D](https://github.com/samuelsl27/OGR-Slip2D) — 2D slope stability by limit equilibrium | **Keeps its own copy for now**, which this repository started from. Whether and when the two become one is a later decision |

Until then there are two copies of the core, and every change here is recorded in the changelog
against that starting point. Slip2D and a program built on this core must not share a Python
environment: both install a package named `ogr_core`.

## Install for development

```bash
git clone https://github.com/samuelsl27/OGR-Core.git
cd OGR-Core
python -m venv .venv && source .venv/bin/activate
pip install -e .
python tests/_runner.py
```

To work on a program against a local core, install this repository in editable mode first and the
program after it. The program's test runner states which core tree, commit and version it is
measuring, and refuses to run when the version is not the one it pins.

## Rules

The working rules are in [`AGENTS.md`](AGENTS.md) (in Spanish), the same as in the rest of the suite.
The core imports no program and no interface: no Qt, no plotting.

## Licence

**GNU Affero General Public License v3.0 or later** (AGPL-3.0-or-later). The
full text is in [`LICENSE`](LICENSE).

In practice:

- You may use OGR Suite freely, **including for professional engineering
  work**, and bill that work without paying or publishing anything. Running a
  program is not a restricted activity.
- If you **modify** it and let others use your version **remotely over a
  network** (a web service or SaaS), you must offer them the source of your
  version. Charging for that service is allowed; keeping it closed is not.
- **There is no warranty of any kind.** Results must be checked against
  independent calculations before anything is based on them. A project is
  signed by a person, not by a program.

Every file carries its SPDX identifier, and a test fails if any is missing.
Contributions are accepted under the terms of [`CLA.md`](CLA.md); see
[`CONTRIBUTING.md`](CONTRIBUTING.md).

© 2026 Samuel Sáez López — Universidad Politécnica de Cartagena.
