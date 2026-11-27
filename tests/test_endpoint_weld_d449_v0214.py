# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.14 — the endpoint welding no longer melts a thin layer (OGR Slip2D,
its D449, the owner's decision A + C of 2026-11-27).

In the region builder (``_build_regions_shapely``) an endpoint within
``weld_tol`` (diag × 8e-3) of a vertex jumped to it even when it was already
ON a segment. Two material contacts almost parallel ending on the External
jumped to the same vertex, and the layer between them vanished without a
word: a block of 100 × 30 with a layer of 0.1 to 0.8 m gave 2 regions
instead of 3, in both drawing orders and at ×10 (5 to 8 m)
(``_auditoria/P10_D449/medir_regla_a.py``, with 0.2.12).

* Rule A: an endpoint ON a segment (≤ 1e-9 × the diagonal) does not jump to
  a vertex; a vertex within 1e-12 still wins.
* Rule C: when the welding leaves two contacts with an end at one point
  where they had none, ``contacts_welded`` says so, with a code: it is the
  case A does not cover, contacts drawn past the External.

The reference is the geometry: the layer between two horizontal contacts
across a rectangle is a rectangle, 100 × its thickness.
"""
from __future__ import annotations

import pytest

THIN = (0.1, 0.5, 0.8)
THICK = (0.9, 2.0)


def _pl(pts, closed=False):
    from ogr_core.geometry import Polyline, Vertex
    return Polyline(vertices=[Vertex(x, y) for x, y in pts], closed=closed)


def _block(sep, outside, thin_first, k=1.0):
    """The block of the measurement: 100 × 30 (× k), a contact at y = 10 k
    and another ``sep`` below it, ending on the External or 5 k past it."""
    from ogr_core.geometry import Boundary, BoundaryType
    from ogr_core.materials import Material, MohrCoulomb
    from ogr_core.project import Project
    p = Project("D449")
    e = _pl([(0, 0), (100 * k, 0), (100 * k, 30 * k), (0, 30 * k)], True)
    e.ensure_ccw()
    p.add_boundary(Boundary(polyline=e, btype=BoundaryType.EXTERNAL))
    lo, th, up = (Material(name=n, unit_weight=20.0,
                           strength=MohrCoulomb(cohesion=5.0,
                                                friction_angle=30.0))
                  for n in ("Bottom", "Thin", "Top"))
    p.materials = [th, up, lo]
    x0, x1 = (-5.0 * k, 105.0 * k) if outside else (0.0, 100.0 * k)
    yu, yt = 10 * k, 10 * k - sep
    u = Boundary(polyline=_pl([(x0, yu), (x1, yu)]),
                 btype=BoundaryType.MATERIAL)
    t = Boundary(polyline=_pl([(x0, yt), (x1, yt)]),
                 btype=BoundaryType.MATERIAL)
    for b in ((t, u) if thin_first else (u, t)):
        p.add_boundary(b)
    p.assign_material_at(50 * k, 0.5 * yt, lo.id)
    p.assign_material_at(50 * k, 20 * k, up.id)
    return p


def _cases(outside):
    for k, seps in ((1.0, THIN + THICK), (10.0, (5.0, 8.0, 9.0))):
        for thin_first in (False, True):
            for sep in seps:
                yield k, sep, thin_first, _block(sep, outside, thin_first, k)


def _layer(p, k, sep):
    from ogr_core.geometry.regions import region_at_point
    r = region_at_point(p.resolve_regions(), 50 * k, 10 * k - sep / 2)
    assert r is not None
    return r


def _area(r):
    from ogr_core.geometry.regions import _ring_centroid
    return abs(_ring_centroid(r.polygon.vertices)[2])


class TestRuleA:
    def test_contacts_on_the_external_keep_the_layer(self):
        for k, sep, _first, p in _cases(outside=False):
            regions = p.resolve_regions()
            assert len(regions) == 3, (k, sep)
            layer = _layer(p, k, sep)
            # the closed solution: a rectangle 100 k × sep. Not to the last
            # bit: the builder's faces carry its snapping, and before this
            # version too the layer of 2 m came out 200.000046 m² and the
            # whole block 3000.000061 (2e-8 of it)
            assert _area(layer) == pytest.approx(100 * k * sep, rel=1e-5)
            assert sum(_area(r) for r in regions) == \
                pytest.approx(3000 * k * k, rel=1e-7)

    def test_and_no_note(self):
        from ogr_core.project.rules import contacts_welded
        for _k, _sep, _first, p in _cases(outside=False):
            assert contacts_welded(p) == []


class TestRuleC:
    def test_past_the_external_a_thin_layer_still_welds_and_is_said(self):
        from ogr_core.project import messages as M
        from ogr_core.project.rules import contacts_welded
        for k, sep, _first, p in _cases(outside=True):
            notes = contacts_welded(p)
            thin = sep < 0.85 * k
            assert len(p.resolve_regions()) == (2 if thin else 3), (k, sep)
            if not thin:
                assert notes == []
                continue
            # one note per pair of ends: the left and the right
            assert [n.code for n in notes] == [M.CONTACTS_WELDED] * 2
            for n in notes:
                assert abs(n.args["distance"] - sep) < 1e-9
                assert abs(abs(n.args["x"] - 50 * k) - 55 * k) < 1e-9

    def test_its_text(self):
        from ogr_core.project.rules import contacts_welded
        n = contacts_welded(_block(0.5, True, False))[0]
        assert str(n) == (
            "The material boundaries Material Boundary #1 and Material "
            "Boundary #2 end 0.500 m apart, within the welding tolerance, "
            "and were joined at (-5.000, 9.500): whatever lay between those "
            "two ends is not a region of its own. Move them apart, or end "
            "them on the same point.")

    def test_two_contacts_that_do_touch_give_none(self):
        from ogr_core.geometry import Boundary, BoundaryType
        from ogr_core.project.rules import contacts_welded
        p = _block(5.0, False, False)
        p.boundaries = [b for b in p.boundaries
                        if b.btype != BoundaryType.MATERIAL]
        # a polyline contact in two pieces that share their end exactly,
        # and a third that ends on the interior of the first
        for pts in (((0, 10), (50, 10)), ((50, 10), (100, 12)),
                    ((20, 10), (20, 0))):
            p.add_boundary(Boundary(polyline=_pl(pts),
                                    btype=BoundaryType.MATERIAL))
        assert contacts_welded(p) == []
        assert len(p.resolve_regions()) == 3

    def test_without_an_external_none(self):
        from ogr_core.project import Project
        from ogr_core.project.rules import contacts_welded
        assert contacts_welded(Project("empty")) == []


class TestTheBuilder:
    def test_welds_is_optional_and_moves_no_region(self):
        from ogr_core.geometry import BoundaryType
        from ogr_core.geometry.regions import build_regions
        p = _block(0.5, True, False)
        ext = p.external_boundary()
        mats = p.boundaries_of(BoundaryType.MATERIAL)
        welds = []
        a = build_regions(ext, mats)
        b = build_regions(ext, mats, welds=welds)
        assert [_area(r) for r in a] == [_area(r) for r in b]
        assert len(welds) == 2
        w = welds[0]
        assert sorted(map(id, (w.first, w.second))) == sorted(map(id, mats))
