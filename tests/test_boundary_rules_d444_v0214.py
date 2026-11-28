# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.14 — the rule of a boundary's geometry, and the DXF import, in the core
(OGR Slip2D, its D444).

Three paths of Slip2D's window added boundaries without asking the rule of
their type, and its agent refused the same edits with two checks of its own
written by hand, outside the core (``_auditoria/P10_D443_D444``, measured
with 0.1.455):

| path | window | agent |
|---|---|---|
| Convert Tool to Boundary, a water table with one in place | two | «Only one Water Table is allowed…» |
| Convert Tool to Boundary, an open one into an External | two, the second open | refused |
| Convert Tool to Boundary, a tension crack twice | two | the second refused |
| DXF with an External layer, without Replace Model | two Externals | «The import leaves two External boundaries.» |
| Convert into a piezometric line or a weak layer a polyline that crosses itself | converted | «The edit makes the boundary cross itself.» |

Here, at the level of the rule: ``boundary_refusal`` with the polyline,
``conversion_refusal`` and ``import_refusal``. The control: a water table
with none in place is accepted, and a caller that passes the type alone gets
the answer of always.
"""
from __future__ import annotations

import os
import tempfile


def _demo():
    from ogr_core.project.demo import build_demo_project
    return build_demo_project()


def _line(*pts, closed=False):
    from ogr_core.geometry import Polyline, Vertex
    return Polyline([Vertex(x, y) for x, y in pts], closed=closed)


BOW = ((10, 2), (20, 6), (20, 2), (10, 6))


class TestATool:
    def test_a_second_water_table(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import boundary_refusal
        why = boundary_refusal(_demo(), BT.WATER_TABLE,
                               polyline=_line((0, 12), (25, 11), (50, 10)))
        assert why.code == "single_instance"

    def test_the_control_a_water_table_with_none_in_place(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import boundary_refusal
        p = _demo()
        p.boundaries = [b for b in p.boundaries
                        if b.btype != BT.WATER_TABLE]
        assert boundary_refusal(p, BT.WATER_TABLE, polyline=_line(
            (0, 12), (25, 11), (50, 10))) is None

    def test_an_open_external(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import (EXTERNAL_NOT_CLOSED,
                                            boundary_refusal)
        p = _demo()
        open_line = _line((0, 12), (25, 11), (50, 10))
        # with the demo's External in place, the type refuses first
        assert boundary_refusal(p, BT.EXTERNAL,
                                polyline=open_line).code == "single_instance"
        p.boundaries = [b for b in p.boundaries if b.btype != BT.EXTERNAL]
        why = boundary_refusal(p, BT.EXTERNAL, polyline=open_line)
        assert (why.code, why.message) == ("external_not_closed",
                                           EXTERNAL_NOT_CLOSED)
        assert boundary_refusal(p, BT.EXTERNAL, polyline=_line(
            (0, 0), (50, 0), (50, 20), (0, 20), closed=True)) is None

    def test_a_tension_crack_twice(self):
        from ogr_core.geometry import Boundary
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import boundary_refusal
        p = _demo()
        line = _line((5, 20), (45, 20))
        assert boundary_refusal(p, BT.TENSION_CRACK, polyline=line) is None
        p.add_boundary(Boundary(polyline=line, btype=BT.TENSION_CRACK))
        assert boundary_refusal(p, BT.TENSION_CRACK, polyline=_line(
            (5, 21), (45, 21))).code == "single_instance"

    def test_a_polyline_that_crosses_itself(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import SELF_INTERSECTING, boundary_refusal
        why = boundary_refusal(_demo(), BT.MATERIAL, polyline=_line(*BOW))
        assert (why.code, why.message) == ("self_intersecting",
                                           SELF_INTERSECTING)
        assert SELF_INTERSECTING == ("The edit makes the boundary cross "
                                     "itself.")
        assert boundary_refusal(_demo(), BT.MATERIAL, polyline=_line(
            (10, 2), (20, 6), (30, 2), (40, 6))) is None

    def test_with_the_type_alone_the_answer_of_always(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import boundary_refusal
        p = _demo()
        assert boundary_refusal(p, BT.MATERIAL) is None
        assert boundary_refusal(p, BT.WATER_TABLE).code == "single_instance"
        p.boundaries = [b for b in p.boundaries if b.btype != BT.EXTERNAL]
        assert boundary_refusal(p, BT.EXTERNAL) is None


class TestAConversion:
    def _bow(self, closed=False, pts=BOW):
        from ogr_core.geometry import Boundary
        from ogr_core.geometry import BoundaryType as BT
        p = _demo()
        b = Boundary(btype=BT.MATERIAL, polyline=_line(*pts, closed=closed))
        p.add_boundary(b)
        return p, b

    def test_a_crossing_polyline_is_not_converted(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import conversion_refusal
        for target in (BT.PIEZOMETRIC, BT.WEAK_LAYER):
            p, b = self._bow()
            assert conversion_refusal(p, b, target).code == \
                "self_intersecting"

    def test_the_line_asked_is_the_converted_one(self):
        # a ring whose CLOSING segment crosses it: as a closed material
        # boundary it crosses itself; opened into a water table, it does not
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import conversion_refusal
        ring = ((0, 0), (2, 0), (0, 2), (2, 2))
        p, b = self._bow(closed=True, pts=ring)
        p.boundaries = [x for x in p.boundaries
                        if x.btype != BT.WATER_TABLE]
        assert conversion_refusal(p, b, BT.WATER_TABLE) is None
        assert conversion_refusal(p, b, BT.MATERIAL).code == \
            "self_intersecting"

    def test_the_order_of_always(self):
        # the type first: a crossing polyline into a second water table
        # says the water table
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import conversion_refusal
        p, b = self._bow()
        assert conversion_refusal(p, b, BT.WATER_TABLE).code == \
            "single_instance"


def _dxf(tmp, *layers):
    import ezdxf
    path = os.path.join(tmp, "ground.dxf")
    doc = ezdxf.new()
    for layer, pts, *closed in layers:
        doc.modelspace().add_lwpolyline(pts, close=closed != [False],
                                        dxfattribs={"layer": layer})
    doc.saveas(path)
    return path


EXT = [(0, 0), (60, 0), (60, 20), (0, 30)]


class TestAnImport:
    def _ask(self, project, replace, *layers, kinds=None):
        from ogr_core.dxf.importer import ImportOptions, preview
        from ogr_core.dxf.reader import DxfEntityKind
        from ogr_core.project.rules import import_refusal
        kinds = kinds or {"GROUND": DxfEntityKind.EXTERNAL}
        with tempfile.TemporaryDirectory() as tmp:
            opts = ImportOptions(replace_model=replace, layer_kinds=kinds)
            pv = preview(_dxf(tmp, *layers), opts)
            assert pv.ok
            n = len(project.boundaries)
            why = import_refusal(project, pv, opts)
            assert len(project.boundaries) == n      # it writes nothing
            return why, pv, opts

    def test_an_external_without_replacing_the_model(self):
        from ogr_core.project.rules import (IMPORT_TWO_EXTERNAL,
                                            IMPORT_TWO_EXTERNAL_HINT)
        why, _pv, _o = self._ask(_demo(), False, ("GROUND", EXT))
        assert (why.code, why.message) == ("import_two_external",
                                           IMPORT_TWO_EXTERNAL)
        assert IMPORT_TWO_EXTERNAL == ("The import leaves two External "
                                       "boundaries.")
        assert IMPORT_TWO_EXTERNAL_HINT == (
            "Use replace_model=true, or map only one layer to 'external'.")

    def test_it_counts_what_apply_to_project_writes(self):
        from ogr_core.dxf.importer import apply_to_project
        from ogr_core.geometry import BoundaryType as BT
        p = _demo()
        why, pv, opts = self._ask(p, False, ("GROUND", EXT))
        apply_to_project(p, pv, opts)
        assert why is not None and len(p.boundaries_of(BT.EXTERNAL)) == 2

    def test_replacing_the_model_is_accepted(self):
        why, _pv, _o = self._ask(_demo(), True, ("GROUND", EXT))
        assert why is None

    def test_two_external_polylines_replacing_the_model(self):
        # the sanitiser keeps the largest External and reports the rest
        # (``external_multiple``), so the import writes one
        from ogr_core.dxf.reader import DxfEntityKind
        why, pv, _o = self._ask(
            _demo(), True, ("GROUND", EXT),
            ("GROUND", [(100, 0), (150, 0), (150, 20), (100, 30)]))
        assert len(pv.sanitised[DxfEntityKind.EXTERNAL]) == 1
        assert why is None

    def test_a_model_without_an_external(self):
        from ogr_core.geometry import BoundaryType as BT
        p = _demo()
        p.boundaries = [b for b in p.boundaries if b.btype != BT.EXTERNAL]
        why, _pv, _o = self._ask(p, False, ("GROUND", EXT))
        assert why is None

    def test_a_material_layer_without_replacing(self):
        from ogr_core.dxf.reader import DxfEntityKind
        why, _pv, _o = self._ask(
            _demo(), False, ("LENS", [(30, 2), (32, 2), (32, 3), (30, 3)]),
            kinds={"LENS": DxfEntityKind.MATERIAL})
        assert why is None


class TestTheOtherSingleTypes:
    """OGR Core 0.2.14, the owner's decision of 2026-11-28: a second water
    table, tension crack or drawdown line by an import is refused too."""

    WT = ("WT", [(0, 12), (25, 11), (50, 10)], False)

    def _ask(self, project, replace, *layers, kinds):
        return TestAnImport._ask(self, project, replace, *layers,
                                 kinds=kinds)

    def test_a_second_water_table(self):
        from ogr_core.dxf.reader import DxfEntityKind as K
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import IMPORT_TWO, import_hint
        why, _pv, _o = self._ask(_demo(), False, self.WT,
                                 kinds={"WT": K.WATER_TABLE})
        assert (why.code, why.message) == (
            "import_single_instance", "The import leaves two Water Tables.")
        assert IMPORT_TWO[BT.WATER_TABLE] == why.message
        assert import_hint(BT.WATER_TABLE) == (
            "Use replace_model=true, or map only one layer to "
            "'water_table'.")

    def test_the_control_replacing_or_with_none_in_place(self):
        from ogr_core.dxf.reader import DxfEntityKind as K
        from ogr_core.geometry import BoundaryType as BT
        kinds = {"WT": K.WATER_TABLE}
        assert self._ask(_demo(), True, self.WT, kinds=kinds)[0] is None
        p = _demo()
        p.boundaries = [b for b in p.boundaries
                        if b.btype != BT.WATER_TABLE]
        assert self._ask(p, False, self.WT, kinds=kinds)[0] is None

    def test_two_tension_cracks_in_the_file(self):
        from ogr_core.dxf.reader import DxfEntityKind as K
        kinds = {"TC": K.TENSION_CRACK}
        one = ("TC", [(5, 20), (45, 20)], False)
        two = ("TC", [(5, 22), (45, 22)], False)
        assert self._ask(_demo(), False, one, kinds=kinds)[0] is None
        why, _pv, _o = self._ask(_demo(), False, one, two, kinds=kinds)
        assert (why.code, why.message) == (
            "import_single_instance",
            "The import leaves two Tension Crack boundaries.")

    def test_the_external_is_asked_first(self):
        from ogr_core.dxf.reader import DxfEntityKind as K
        why, _pv, _o = self._ask(
            _demo(), False, ("GROUND", EXT), self.WT,
            kinds={"GROUND": K.EXTERNAL, "WT": K.WATER_TABLE})
        assert why.code == "import_two_external"


class TestTheSanitiserTie:
    """OGR Core 0.2.14 -- two External polylines of the same area raised a
    TypeError in the sanitiser (the sort compared the polylines)."""

    def test_two_of_the_same_area(self):
        from ogr_core.dxf.importer import ImportOptions, preview
        from ogr_core.dxf.reader import DxfEntityKind as K
        same = [(100, 0), (160, 0), (160, 20), (100, 30)]
        with tempfile.TemporaryDirectory() as tmp:
            opts = ImportOptions(replace_model=True,
                                 layer_kinds={"GROUND": K.EXTERNAL})
            pv = preview(_dxf(tmp, ("GROUND", EXT), ("GROUND", same)), opts)
        assert pv.ok
        kept = pv.sanitised[K.EXTERNAL]
        assert len(kept) == 1
        # the first drawn is kept
        assert min(x for x, _y in kept[0].points) == 0
        assert "external_multiple" in [p["kind"]
                                       for p in pv.report.problems]
