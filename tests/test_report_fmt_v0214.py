# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.14 — the report writes every real number with its decimals (OGR Slip2D,
its D446, the owner's decision B).

``_fmt`` wrote with ``nd`` decimals only a ``float`` and passed everything
else through ``str()``: an integer coordinate came out ``'0'`` where a real
one came out ``'0.000'``. The vertices of the demo slope are integers, and
with one vertex edited to (35.5, 15) the same row of the «List of
Coordinates» mixed ``'35.500'`` and ``'15'``.

Invariants:

* an ``int``, a ``float`` and a numpy scalar are written with ``nd``
  decimals; a ``bool`` is not a number here and keeps its ``str()``;
  ``None`` and NaN are a dash, as before;
* every coordinate of the «List of Coordinates» of the demo slope, and of
  the demo with a vertex at (35.5, 15), has three decimals;
* a count keeps no decimals: the slice number of the slice table.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np


def _fmt(*a, **k):
    from ogr_core.report.report_generator import _fmt as f
    return f(*a, **k)


class TestFmt:
    def test_an_int_has_its_decimals(self):
        assert _fmt(0) == "0.000"
        assert _fmt(15) == "15.000"
        assert _fmt(-3, 1) == "-3.0"
        assert _fmt(7, 0) == "7"

    def test_a_float_as_before(self):
        assert _fmt(35.5) == "35.500"
        assert _fmt(1.23456, 4) == "1.2346"

    def test_the_numpy_scalars(self):
        assert _fmt(np.int64(15)) == "15.000"
        assert _fmt(np.int32(2), 2) == "2.00"
        assert _fmt(np.float32(0.5), 1) == "0.5"
        assert _fmt(np.float64(35.5)) == "35.500"

    def test_a_bool_is_not_a_number(self):
        assert _fmt(True) == "True"
        assert _fmt(False) == "False"

    def test_none_and_nan_are_a_dash(self):
        assert _fmt(None) == "—"
        assert _fmt(math.nan) == "—"
        assert _fmt(np.float64("nan")) == "—"

    def test_any_other_thing_its_str(self):
        assert _fmt("abc") == "abc"


def _coordinates(project):
    from reportlab.lib.styles import getSampleStyleSheet
    from ogr_core.report.report_generator import _coordinates_flowables
    h = getSampleStyleSheet()["Heading4"]
    out = []
    for keep in _coordinates_flowables(project, h):
        table = [f for f in keep._content if hasattr(f, "_cellvalues")][0]
        rows = table._cellvalues
        assert rows[0] == ["X", "Y"]
        out.append(rows[1:])
    return out


def _three_decimals(text):
    whole, _, dec = text.lstrip("-").partition(".")
    return whole.isdigit() and len(dec) == 3 and dec.isdigit()


class TestListOfCoordinates:
    def test_the_demo_slope(self):
        from ogr_core.project.demo import build_demo_project
        p = build_demo_project()
        # the premise: the demo's vertices are integers
        assert any(isinstance(v.x, int) for b in p.boundaries
                   for v in b.polyline.vertices)
        tables = _coordinates(p)
        assert tables
        for rows in tables:
            for row in rows:
                assert all(_three_decimals(c) for c in row), row
        assert tables[0][0] == ["0.000", "0.000"]

    def test_a_vertex_edited_to_35_5(self):
        from ogr_core.geometry import BoundaryType, Vertex
        from ogr_core.project.demo import build_demo_project
        p = build_demo_project()
        ext = p.boundaries_of(BoundaryType.EXTERNAL)[0]
        verts = ext.polyline.vertices
        k = next(i for i, v in enumerate(verts) if (v.x, v.y) == (35, 15))
        verts[k] = Vertex(35.5, 15)
        tables = _coordinates(p)
        row = tables[p.boundaries.index(ext)][k]
        assert row == ["35.500", "15.000"]


class TestACountKeepsNoDecimals:
    def test_the_slice_number(self):
        from ogr_core.project import Project
        from ogr_core.report.report_generator import _slice_table
        slices = [SimpleNamespace(width=2, weight=10, material=None,
                                  base_angle=0.0, base_length=2.0, index=i,
                                  pore_pressure=0)
                  for i in range(3)]
        crit = SimpleNamespace(fos=1.2, details={},
                               slices=SimpleNamespace(slices=slices))
        rows = _slice_table(crit, Project("Slices"))._cellvalues[1:]
        assert [r[0] for r in rows] == ["1", "2", "3"]
        # and the integer magnitudes beside it, with their decimals
        assert rows[0][1:3] == ["2.000", "10.0"]
        assert rows[0][-1] == "0.0"
