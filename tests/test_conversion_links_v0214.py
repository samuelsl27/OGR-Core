# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.14 — converting a boundary that materials point at (OGR Slip2D, its
D443, the owner's decision B of 2026-11-27).

``convert_boundary`` copies the boundary with another type and the same id,
and ``Material.water_surface_id`` / ``anisotropic_surface_id`` stayed as
they were, while their readers filter by type. Measured by Slip2D on the
demo slope: the water table converted into a piezometric line left u at
(25, 0.5) at 0 kPa where it was 73.6, and the model still computed
(``_auditoria/P10_D443_D444/medir_d443_d444.py``).

Invariants:

* a water table into a piezometric line, and back: the link follows and the
  pore-pressure model goes to the new type's. u at (25, 0.5) is then the
  hydrostatic pressure under the line, γw·(8 − 0.5), the closed solution,
  and what a material set to the piezometric model on the same line gives;
* any other conversion that leaves a link without a reader clears it, as a
  deletion does; deleting clears with the same rule;
* the changes are returned, material by material, for the program's note;
* ``stale_surface_links`` says the links an old file brings;
* an anisotropic surface a joint reads is not converted, as it is not
  deleted.
"""
from __future__ import annotations

import json

X, Y = 25.0, 0.5


def _demo():
    from ogr_core.geometry import BoundaryType as BT
    from ogr_core.project.demo import build_demo_project
    p = build_demo_project()
    wt = next(b for b in p.boundaries if b.btype == BT.WATER_TABLE)
    return p, wt, p.materials[0]


def _convert(p, b, new_type):
    """What a program does: the links, then the boundary replaced by its
    converted copy at its place."""
    from ogr_core.geometry.transforms import convert_boundary
    from ogr_core.project.rules import conversion_refusal, relink_on_conversion
    assert conversion_refusal(p, b, new_type) is None
    changes = relink_on_conversion(p, b, new_type)
    new = convert_boundary(b, new_type)
    i = next(i for i, x in enumerate(p.boundaries) if x is b)
    p.boundaries[i] = new
    return new, changes


def _u(p, m):
    from ogr_core.geometry import Vertex
    from ogr_core.hydraulic.pore_pressure import pore_pressure_at
    return pore_pressure_at(p, Vertex(X, Y), m)


def _hydrostatic(p, level):
    return p.settings.groundwater.pore_fluid_unit_weight * (level - Y)


class TestWaterTableAndPiezometricLine:
    def test_the_premise_of_the_demo(self):
        from ogr_core.materials import PorePressureType as PP
        p, wt, m = _demo()
        assert m.water_surface_id == wt.id
        assert m.pore_pressure == PP.WATER_TABLE
        assert {v.y for v in wt.polyline.vertices} == {8}
        assert abs(_u(p, m) - _hydrostatic(p, 8.0)) < 1e-9

    def test_into_a_piezometric_line_the_link_follows(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.materials import PorePressureType as PP
        from ogr_core.project.rules import (FOLLOWED, WATER_SURFACE_LINK,
                                            LinkChange)
        p, wt, m = _demo()
        new, changes = _convert(p, wt, BT.PIEZOMETRIC)
        assert changes == [LinkChange(m.id, m.name, WATER_SURFACE_LINK,
                                      FOLLOWED)]
        assert m.water_surface_id == new.id == wt.id
        assert m.pore_pressure == PP.PIEZO_LINE
        # measured, not supposed: the closed solution under a horizontal
        # line at y = 8 (73.6 kPa), where it was 0
        assert abs(_u(p, m) - _hydrostatic(p, 8.0)) < 1e-9
        assert _u(p, m) > 73.0

    def test_it_is_what_a_material_set_on_the_line_gives(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.materials import Material
        from ogr_core.project.rules import assign_water_surface
        p, wt, m = _demo()
        new, _ = _convert(p, wt, BT.PIEZOMETRIC)
        fresh = Material.from_dict(json.loads(json.dumps(m.to_dict())))
        fresh.id, fresh.name = "fresh", "Fresh"
        fresh.water_surface_id = None
        p.materials.append(fresh)
        assign_water_surface(p, new.id, [fresh.id])
        assert _u(p, fresh) == _u(p, m)

    def test_there_and_back(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.materials import PorePressureType as PP
        p, wt, m = _demo()
        before = _u(p, m)
        pl, _ = _convert(p, wt, BT.PIEZOMETRIC)
        back, changes = _convert(p, pl, BT.WATER_TABLE)
        assert [c.change for c in changes] == ["followed"]
        assert m.pore_pressure == PP.WATER_TABLE
        assert m.water_surface_id == back.id == wt.id
        assert _u(p, m) == before

    def test_without_the_rule_it_was_zero(self):
        # the defect, as Slip2D measured it: the boundary converted and the
        # material left as it was
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.geometry.transforms import convert_boundary
        p, wt, m = _demo()
        p.boundaries[p.boundaries.index(wt)] = convert_boundary(
            wt, BT.PIEZOMETRIC)
        assert _u(p, m) == 0.0
        from ogr_core.project import messages as M
        from ogr_core.project.rules import stale_surface_links
        notes = stale_surface_links(p)
        assert [n.code for n in notes] == [M.STALE_WATER_LINK]
        assert str(notes[0]) == (
            "The material 'Silty clay' takes its water surface from "
            "Piezometric Line #1, which its pore-pressure model does not "
            "read: assign it a water surface again.")


class TestALinkLeftWithoutAReader:
    def test_a_water_table_into_a_material_boundary_is_cleared(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.materials import PorePressureType as PP
        from ogr_core.project.rules import CLEARED, stale_surface_links
        p, wt, m = _demo()
        _new, changes = _convert(p, wt, BT.WEAK_LAYER)
        assert [(c.link, c.change) for c in changes] == [
            ("water_surface", CLEARED)]
        assert m.water_surface_id is None
        assert m.pore_pressure == PP.NONE
        assert stale_surface_links(p) == []

    @staticmethod
    def _with_surface():
        from ogr_core.geometry import Boundary, Polyline, Vertex
        from ogr_core.geometry import BoundaryType as BT
        p, _wt, m = _demo()
        s = Boundary(btype=BT.ANISOTROPIC_SURFACE,
                     polyline=Polyline([Vertex(0, 8), Vertex(50, 4)]))
        p.add_boundary(s)
        m.anisotropic_surface_id = s.id
        return p, s, m

    def test_an_anisotropic_surface_into_a_weak_layer_is_cleared(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.geometry.anisotropic_surface import material_surfaces
        from ogr_core.project.rules import stale_surface_links
        p, s, m = self._with_surface()
        assert material_surfaces(p)
        _new, changes = _convert(p, s, BT.WEAK_LAYER)
        assert [(c.link, c.change) for c in changes] == [
            ("anisotropic_surface", "cleared")]
        assert m.anisotropic_surface_id is None
        assert stale_surface_links(p) == []

    def test_left_as_it_was_it_is_said(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.geometry.transforms import convert_boundary
        from ogr_core.project import messages as M
        from ogr_core.project.rules import stale_surface_links
        p, s, _m = self._with_surface()
        p.boundaries[p.boundaries.index(s)] = convert_boundary(
            s, BT.WEAK_LAYER)
        assert [n.code for n in stale_surface_links(p)] == [
            M.STALE_ANISOTROPIC_LINK]

    def test_a_surface_into_a_surface_changes_nothing(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import conversion_link_changes
        p, s, _m = self._with_surface()
        assert conversion_link_changes(p, s.id,
                                       BT.ANISOTROPIC_SURFACE) == []
        p, wt, _m = _demo()
        assert conversion_link_changes(p, wt.id, BT.WATER_TABLE) == []

    def test_a_link_the_material_does_not_read_stays(self):
        # a water surface id under the Ru model: never the conversion's
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.materials import PorePressureType as PP
        p, wt, m = _demo()
        m.pore_pressure = PP.RU_COEFFICIENT
        _new, changes = _convert(p, wt, BT.WEAK_LAYER)
        assert changes == []
        assert m.pore_pressure == PP.RU_COEFFICIENT
        assert m.water_surface_id == wt.id


class TestDeletingSaysTheSame:
    def test_unlink_on_removal(self):
        from ogr_core.materials import PorePressureType as PP
        from ogr_core.project.rules import (removal_link_changes,
                                            unlink_on_removal)
        p, wt, m = _demo()
        planned = removal_link_changes(p, wt.id)
        assert unlink_on_removal(p, wt.id) == planned
        assert [(c.link, c.change) for c in planned] == [
            ("water_surface", "cleared")]
        assert m.water_surface_id is None and m.pore_pressure == PP.NONE

    def test_the_same_change_as_a_conversion_without_a_reader(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.project.rules import (conversion_link_changes,
                                            removal_link_changes)
        p, s, _m = TestALinkLeftWithoutAReader._with_surface()
        for b in (s, next(b for b in p.boundaries
                          if b.btype == BT.WATER_TABLE)):
            assert conversion_link_changes(p, b.id, BT.MATERIAL) == \
                removal_link_changes(p, b.id)

    def test_an_unread_id_is_dropped_without_a_change(self):
        from ogr_core.materials import PorePressureType as PP
        from ogr_core.project.rules import unlink_on_removal
        p, wt, m = _demo()
        m.pore_pressure = PP.CONSTANT
        assert unlink_on_removal(p, wt.id) == []
        assert m.water_surface_id is None
        assert m.pore_pressure == PP.CONSTANT


class TestAJointReadsTheSurface:
    def test_it_is_not_converted(self):
        from ogr_core.geometry import BoundaryType as BT
        from ogr_core.materials.builtin_models import GeneralizedAnisotropic
        from ogr_core.project.rules import (conversion_refusal,
                                            surface_in_use_refusal)
        p, s, m = TestALinkLeftWithoutAReader._with_surface()
        m.strength = GeneralizedAnisotropic(joints=[{"surface_id": s.id}])
        why = conversion_refusal(p, s, BT.WEAK_LAYER)
        assert why is not None
        assert why == surface_in_use_refusal(p, s.id)
        assert conversion_refusal(p, s, BT.ANISOTROPIC_SURFACE) is None
