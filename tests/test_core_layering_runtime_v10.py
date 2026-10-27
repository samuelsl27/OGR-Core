# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.1.0 — the core runs without any program or layer above it, measured at
run time; and the two statistical runners it once held still say where they
went.

Moved from OGR Slip2D's ``test_core_layering_closed_v1346`` with the
extraction (spec 009). Two changes, because the core now has to stand on its
own:

* the model is built HERE, with the core alone. In Slip2D it came from the
  helpers of two of its tests (the Ej_1 slope of its validation bank, and the
  seepage field of ``test_coupling_v128``); the geometry, materials, mesh and
  seepage below are those, written out, and the seepage is solved by the
  core's own solver, which spec 009 moved into ``ogr_core.fem``;
* the check that the new paths of the runners work needs ``ogr_slip2d`` and
  stays in Slip2D.

The invariants:

* **the old paths fail loudly, with the new one**: importing
  ``ogr_core.statistics.probabilistic`` or ``.sensitivity``, or one of their
  names from ``ogr_core.statistics``, raises an ``ImportError`` that names
  the module of OGR Slip2D they moved to (v0.1.346) — never a re-export,
  which would be the core importing a program;
* **at run time**: in a fresh interpreter, importing every module of the
  core, loading a model with a mesh, a seepage field, focus objects and a
  user circle, and computing what the core computes for the programs (the
  effective stress and the equivalent strength along a support, the stress
  of the loads, a DXF with a drawn surface) leaves no module of
  ``ogr_slip2d``, ``ogr_fem2d``, ``ogr_api``, ``ogr_gui``, ``ogr_cli``,
  ``ogr_mcp``, ``PySide6`` or ``mcp`` in ``sys.modules``.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BANNED = ("ogr_slip2d", "ogr_fem2d", "ogr_api", "ogr_gui", "ogr_cli",
           "ogr_mcp", "PySide6", "mcp")
_STUBS = ("ogr_core.statistics.probabilistic",
          "ogr_core.statistics.sensitivity")


class TestTheOldPathsFailLoudly:

    def test_the_two_modules(self):
        for name, new in zip(_STUBS, ("ogr_slip2d.probabilistic",
                                      "ogr_slip2d.sensitivity")):
            sys.modules.pop(name, None)
            try:
                importlib.import_module(name)
            except ImportError as exc:
                assert new in str(exc), exc
            else:
                raise AssertionError(name + " imported")

    def test_a_moved_name_from_the_package(self):
        for name, new in (("run_global_minimum", "ogr_slip2d.probabilistic"),
                          ("run_sensitivity", "ogr_slip2d.sensitivity"),
                          ("ProbabilisticType", "ogr_slip2d.probabilistic")):
            try:
                exec("from ogr_core.statistics import " + name, {})
            except ImportError as exc:
                assert new in str(exc), exc
            else:
                raise AssertionError(name + " imported from the core")


def _ej1_project():
    """The three-layer slope of OGR Slip2D's ``test_slide_validation_ej1``,
    with the core alone."""
    from ogr_core.geometry import Boundary, BoundaryType, Polyline, Vertex
    from ogr_core.materials import Material
    from ogr_core.materials.builtin_models import MohrCoulomb
    from ogr_core.project import Project
    ext = Polyline(vertices=[
        Vertex(120, 0), Vertex(120, 25), Vertex(75, 25), Vertex(50, 50),
        Vertex(0, 50), Vertex(0, 30), Vertex(0, 20), Vertex(0, 0),
    ], closed=True)
    ext.ensure_ccw()
    p = Project("ej1")
    p.add_boundary(Boundary(polyline=ext, btype=BoundaryType.EXTERNAL))
    m1 = Material(name="Mat1", unit_weight=20, sat_unit_weight=21,
                  strength=MohrCoulomb(cohesion=15, friction_angle=25))
    m2 = Material(name="Mat2", unit_weight=20, sat_unit_weight=21,
                  strength=MohrCoulomb(cohesion=10, friction_angle=25))
    m3 = Material(name="Mat3", unit_weight=20, sat_unit_weight=21,
                  strength=MohrCoulomb(cohesion=19, friction_angle=30))
    p.materials = [m1, m2, m3]
    p.add_boundary(Boundary(polyline=Polyline(
        vertices=[Vertex(0, 30), Vertex(75, 25)], closed=False),
        btype=BoundaryType.MATERIAL))
    p.add_boundary(Boundary(polyline=Polyline(
        vertices=[Vertex(0, 20), Vertex(120, 10)], closed=False),
        btype=BoundaryType.MATERIAL))
    regs = p.resolve_regions()
    top = max(regs, key=lambda r: r.centroid()[1])
    bot = min(regs, key=lambda r: r.centroid()[1])
    mid = [r for r in regs if r not in (top, bot)][0]
    p.assign_material_at(*top.centroid(), m1.id)
    p.assign_material_at(*mid.centroid(), m2.id)
    p.assign_material_at(*bot.centroid(), m3.id)
    return p


def _model():
    """Ej_1 with the unsaturated seepage field of OGR Slip2D's
    ``test_coupling_v128`` (300 elements), two focus objects and a user
    circle — what ``test_focus_circle_in_core_v1343`` built there."""
    from ogr_core.fem import BCType, SeepageBoundaryConditions
    from ogr_core.fem.generator import generate_mesh_for_project
    from ogr_core.fem.seepage import UnsaturatedSeepageSolver
    from ogr_core.geometry.focus import FocusKind, FocusObject
    from ogr_core.geometry.slip_circle import SlipCircle
    from ogr_core.hydraulic import HydraulicProperties, PermeabilityModel
    from ogr_core.materials import PorePressureType
    p = _ej1_project()
    for m in p.materials:
        m.hydraulic = HydraulicProperties(
            ks=1e-5, model=PermeabilityModel.GARDNER,
            gardner_a=1.0, gardner_n=3.0)
        m.pore_pressure = PorePressureType.FEM_SEEPAGE
        m.phi_b = 0.0
        m.air_entry_value = 0.0
    p.fem_mesh = generate_mesh_for_project(p, target_elements=300)
    mesh = p.fem_mesh
    bnd = mesh.boundary_node_ids()
    xs = [mesh.nodes[i].x for i in bnd]
    ys = [mesh.nodes[i].y for i in bnd]
    x_min, x_max, y_min = min(xs), max(xs), min(ys)
    b = SeepageBoundaryConditions()
    for nid in sorted(bnd):
        nd = mesh.nodes[nid]
        if abs(nd.x - x_min) < 1e-6 and nd.y <= 40.0:
            b.add_node(nid, BCType.TOTAL_HEAD, 40.0)
        elif abs(nd.x - x_max) < 1e-6 and nd.y <= 27.0:
            b.add_node(nid, BCType.TOTAL_HEAD, 27.0)
        elif abs(nd.y - y_min) < 1e-6:
            b.add_node(nid, BCType.NODAL_FLOW, 0.0)
        else:
            b.add_node(nid, BCType.UNKNOWN)
    s = UnsaturatedSeepageSolver(
        mesh, {m.id: m.hydraulic for m in p.materials},
        relaxation=0.4, max_iterations=200, tolerance=1e-5)
    p.seepage_result = s.solve_unsaturated(b)
    p.focus_objects = [
        FocusObject(kind=FocusKind.POINT, points=[(60.0, 30.0)],
                    tolerance=1.5),
        FocusObject(kind=FocusKind.LINE, points=[(50.0, 25.0), (70.0, 28.0)])]
    p.user_surfaces = [SlipCircle(centre_x=88.0, centre_y=70.5,
                                  radius=47.212)]
    return p


_SCRIPT = r'''
import json, pkgutil, sys, tempfile, pathlib, importlib
import ogr_core
stubs = set(json.loads(sys.argv[2]))
names = []
for info in pkgutil.walk_packages(ogr_core.__path__, "ogr_core."):
    if info.name in stubs:
        continue
    importlib.import_module(info.name)
    names.append(info.name)
from ogr_core.project import Project
from ogr_core.dxf.exporter import ExportOptions, export_dxf
from ogr_core.hydraulic.excess_pore_pressure import load_delta_sigma_v
from ogr_core.support.bond import equivalent_c_phi_at, sigma_v_effective_at
p = Project.load(sys.argv[1])
xmin, ymin, xmax, ymax = p.bounding_box()
x, y = 0.5 * (xmin + xmax), ymin + 0.3 * (ymax - ymin)
sigma_v_effective_at(p, x, y)
equivalent_c_phi_at(p, x, y, 50.0)
load_delta_sigma_v(p, x)
out = pathlib.Path(tempfile.mkdtemp()) / "x.dxf"
rep = export_dxf(p, out, ExportOptions(unit="m"),
                 [("m", [(xmin, ymax), (x, y), (xmax, ymax)], 1.2)])
loaded = sorted(m for m in sys.modules
                if m.split(".")[0] in json.loads(sys.argv[3]))
print(json.dumps({"modules": len(names), "loaded": loaded,
                  "mesh": p.fem_mesh is not None,
                  "seepage": p.seepage_result is not None,
                  "focus": len(p.focus_objects),
                  "circles": len(p.user_surfaces),
                  "dxf": rep.ok}))
'''


class TestAtRunTime:

    def test_the_whole_core_without_the_layers_above(self):
        p = _model()
        assert p.seepage_result.converged
        tmp = Path(tempfile.mkdtemp(prefix="ogr_core_"))
        path = tmp / "model.ogr"
        try:
            p.save(path)
            env = dict(os.environ, PYTHONPATH=str(_ROOT))
            out = subprocess.run(
                [sys.executable, "-c", _SCRIPT, str(path),
                 json.dumps(list(_STUBS)), json.dumps(list(_BANNED))],
                cwd=str(_ROOT), env=env, capture_output=True, text=True,
                timeout=600)
        finally:
            path.unlink(missing_ok=True)
            tmp.rmdir()
        assert out.returncode == 0, out.stderr
        got = json.loads(out.stdout.strip().splitlines()[-1])
        assert got["loaded"] == [], got["loaded"]
        assert got["modules"] > 80, got["modules"]
        assert got["mesh"] and got["seepage"]
        assert got["focus"] == 2 and got["circles"] == 1
        assert got["dxf"]
