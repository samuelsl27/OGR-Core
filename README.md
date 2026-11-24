# OGR Core

**The shared core of the [OpenGeoRock](https://opengeorock.org) suite** — geometry, materials,
project model, loads, supports, hydraulics, statistics, annotations, DXF, reports, the
finite-element mesh and groundwater seepage solver, and the framework of each program's operations
layer (`ogr_core.api`: registry, coded errors, jobs in a child process, the live bridge), without
Qt.

[Versión en español](README.es.md)

> **Latest release: 0.2.9.** The code is the core of
> [OGR Slip2D](https://github.com/samuelsl27/OGR-Slip2D) as it stood in that program at its commit
> `d48e2b3` (v0.1.471), with its finite-element mesh and seepage inside `ogr_core.fem`. Since 0.2.0
> there is one core for every program of the suite, and it changes here and nowhere else.

## Who uses it

| Program | Relation to this core |
|---|---|
| [OGR Slip2D](https://github.com/samuelsl27/OGR-Slip2D) — 2D slope stability by limit equilibrium | Where this code comes from. **Its core** since its v0.1.473: it pins a tagged version. Up to its v0.1.471 it carried its own copy (and a package named `ogr_fem2d`, now `ogr_core.fem`) |
| OGR FEM2D (in preparation) — 2D geotechnical finite-element analysis | **Its core** since its v0.0.3. It pins a tagged version |

A Slip2D up to v0.1.471 and a program built on this core must not share a Python environment: both
install a package named `ogr_core`, and that Slip2D also installs one named `ogr_fem2d`, the name
of the finite-element program's own package.

## Development

You need Python 3.11 or newer (CI runs 3.11, 3.12 and 3.13) and git. Nothing else: the core has
no Qt and no compiled code.

```bash
git clone https://github.com/samuelsl27/OGR-Core.git
cd OGR-Core
python -m venv .venv && source .venv/bin/activate
pip install -e .
python tests/_runner.py
```

On Windows, without activating the environment:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python tests\_runner.py
```

The suite is green when its totals say `Failed: 0`. It uses the suite's own runner
(`ogr_core/testing/`), which brings a stand-in `pytest`: the real pytest is not needed.

The core goes in editable mode in this environment only. A program never installs this tree in
editable mode: it installs the tag it pins (below).

To work on the whole suite (this core and the programs side by side, each in its own
environment), this repository lives inside the `OGR_Suite` workspace, and `DESARROLLO.md` at the
root of that workspace says what to install on a Windows machine and how to set it all up (in
Spanish; from this folder it is `../../DESARROLLO.md`).

Each program pins a tagged version of this core and installs it from its tag. The program's test
runner states which core tree, commit and version it is measuring, and refuses to run when the
version is not the one it pins. To test a program against a core that is being changed, put that
tree on `PYTHONPATH` and ask the runner for it with `--dev-core`. Which version each program pins
and how a change is requested: [`docs/consumidores.md`](docs/consumidores.md) (in Spanish).

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
