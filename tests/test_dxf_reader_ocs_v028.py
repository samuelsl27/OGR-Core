# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.8 — the DXF reader takes ARC, CIRCLE, LWPOLYLINE and 2-D POLYLINE
from their own coordinates (OCS) to the drawing's.

Those four entities store their coordinates in the system their extrusion
vector sets (the arbitrary axis algorithm of the DXF reference). Until
v0.2.7 the reader used them as they came, so an entity with extrusion
(0, 0, -1) — what a mirror leaves in some CAD — was read mirrored in x.
Measured with ezdxf 1.4.5: an ARC about (10, 0) from 0° to 90° came from
(11, 0) to (10, 1); in the drawing it goes from (-11, 0) to (-10, 1).

The references here are external to the reader:

* for extrusion (0, 0, -1), the closed form of the arbitrary axis
  algorithm: Ax = Wy × N = (-1, 0, 0) and Ay = N × Ax = (0, 1, 0), so the
  drawing's point is (-x, y);
* ezdxf's own conversion to the drawing's coordinates (``ARC.start_point``
  and ``end_point``, ``OCS.to_wcs``, and the arcs of
  ``LWPOLYLINE.virtual_entities``), which the reader does not use for
  them.

An extrusion that leans away from ±Z puts the entity out of the drawing's
plane: it is not read, and ``skipped`` counts it (decision of the owner,
2026-11-24, as recommended: skip and report rather than project).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    import ezdxf
    _HAS_EZDXF = True
except ImportError:  # pragma: no cover
    _HAS_EZDXF = False

from ogr_core.dxf import read_dxf  # noqa: E402

MINUS_Z = (0.0, 0.0, -1.0)
LEANING = (0.6, 0.0, 0.8)


def _requires_ezdxf(cls):
    return cls if _HAS_EZDXF else type(cls.__name__, (), {})


def _doc():
    doc = ezdxf.new("R2010")
    return doc, doc.modelspace()


def _read(doc, tmp_path, name="d.dxf", **kw):
    path = tmp_path / name
    doc.saveas(str(path))
    return read_dxf(path, **kw)


def _polys(cat):
    return [p for lay in cat.layers for p in lay.polylines]


def _only(cat):
    polys = _polys(cat)
    assert len(polys) == 1, polys
    return polys[0]


def _close(a, b, tol=1e-12):
    return math.dist((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))) <= tol


# ======================================================================
@_requires_ezdxf
class TestMinusZ:
    def test_arc(self, tmp_path):
        doc, m = _doc()
        e = m.add_arc((10.0, 0.0), 1.0, 0.0, 90.0, dxfattribs={"extrusion": MINUS_Z})
        start, end = (e.start_point.x, e.start_point.y), (e.end_point.x, e.end_point.y)
        assert _close(start, (-11.0, 0.0)) and _close(end, (-10.0, 1.0)), (start, end)
        for keep in (False, True):
            p = _only(_read(doc, tmp_path, keep_arcs=keep))
            assert _close(p.points[0], start) and _close(p.points[-1], end), (keep, p.points)
            for q in p.points:
                assert abs(math.dist(q, (-10.0, 0.0)) - 1.0) < 1e-12, (keep, q)
            assert p.arcs == ({0: (-10.0, 0.0)} if keep else {}), p.arcs

    def test_circle(self, tmp_path):
        doc, m = _doc()
        e = m.add_circle((5.0, 1.0), 2.0, dxfattribs={"extrusion": MINUS_Z})
        w = e.ocs().to_wcs(e.dxf.center)
        assert _close((w.x, w.y), (-5.0, 1.0))
        for keep in (False, True):
            p = _only(_read(doc, tmp_path, keep_arcs=keep))
            assert p.closed and p.points[-1] == p.points[0] or not keep
            for q in p.points:
                assert abs(math.dist(q, (-5.0, 1.0)) - 2.0) < 1e-12, (keep, q)
        assert set(p.arcs.values()) == {(-5.0, 1.0)} and len(p.arcs) == 4, p.arcs

    def _bulged(self, tmp_path, cls, keep, unit="m"):
        doc, m = _doc()
        attribs = {"extrusion": MINUS_Z}
        if cls == "lw":
            attribs["elevation"] = 3.0
            e = m.add_lwpolyline([(0, 0, 1.0), (2, 0, 0)], format="xyb", dxfattribs=attribs)
        else:
            e = m.add_polyline2d([(0, 0, 1.0), (2, 0, 0)], format="xyb", dxfattribs=attribs)
        ref = [v for v in e.virtual_entities() if v.dxftype() == "ARC"][0]
        c = ref.ocs().to_wcs(ref.dxf.center)
        return _only(_read(doc, tmp_path, keep_arcs=keep, unit=unit)), (c.x, c.y)

    def test_polylines_with_a_bulge(self, tmp_path):
        """Half a circle from (0,0) to (2,0) in the OCS: in the drawing, from
        (0,0) to (-2,0) about (-1,0), on the side y < 0."""
        for cls in ("lw", "2d"):
            for keep in (False, True):
                p, centre = self._bulged(tmp_path, cls, keep)
                assert _close(centre, (-1.0, 0.0)), (cls, centre)
                assert _close(p.points[0], (0.0, 0.0)) and _close(p.points[-1], (-2.0, 0.0))
                for q in p.points:
                    assert abs(math.dist(q, centre) - 1.0) < 1e-12, (cls, keep, q)
                assert min(float(q[1]) for q in p.points) < -0.999, (cls, keep)
                if keep:
                    assert p.n == 3 and p.arcs == {0: (-1.0, 0.0), 1: (-1.0, 0.0)}, p.arcs
                    assert all(type(v) is float for c in p.arcs.values() for v in c)
                else:
                    assert p.arcs == {} and p.n == 33, p.n

    def test_centres_in_metres(self, tmp_path):
        p, _c = self._bulged(tmp_path, "lw", True, unit="mm")
        assert p.arcs == {0: (-0.001, 0.0), 1: (-0.001, 0.0)}, p.arcs


@_requires_ezdxf
class TestOutOfPlane:
    def test_leaning_entities_are_counted_not_read(self, tmp_path):
        doc, m = _doc()
        attribs = {"extrusion": LEANING}
        m.add_arc((0, 0), 1.0, 0.0, 90.0, dxfattribs=attribs)
        m.add_circle((0, 0), 1.0, dxfattribs=attribs)
        m.add_lwpolyline([(0, 0), (1, 0)], dxfattribs=attribs)
        m.add_polyline2d([(0, 0), (1, 0)], dxfattribs=attribs)
        m.add_line((0, 0), (1, 1))
        for keep in (False, True):
            cat = _read(doc, tmp_path, keep_arcs=keep)
            assert cat.skipped == {f"{t} (not in the XY plane)": 1 for t in
                                   ("ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE")}, cat.skipped
            assert [p.source for p in _polys(cat)] == ["LINE"]

    def test_a_lean_below_the_tolerance_is_the_plane(self, tmp_path):
        """(1e-12, 0, 1) is +Z for ezdxf too; (2e-10, 0, -1) is −Z within
        the tolerance; (1e-6, 0, 1) is out of the plane."""
        for extrusion, read, centre in (((1e-12, 0.0, 1.0), True, (10.0, 0.0)),
                                        ((2e-10, 0.0, -1.0), True, (-10.0, 0.0)),
                                        ((1e-6, 0.0, 1.0), False, None)):
            doc, m = _doc()
            m.add_arc((10.0, 0.0), 1.0, 0.0, 90.0, dxfattribs={"extrusion": extrusion})
            cat = _read(doc, tmp_path, keep_arcs=True)
            if read:
                p = _only(cat)
                assert _close(p.arcs[0], centre, 1e-8), (extrusion, p.arcs)
                assert cat.skipped == {}
            else:
                assert _polys(cat) == [] and cat.skipped == {"ARC (not in the XY plane)": 1}


@_requires_ezdxf
class TestWhatDoesNotChange:
    def test_plus_z_given_or_not_is_the_same(self, tmp_path):
        doc, m = _doc()
        m.add_arc((10.0, 0.0), 1.0, 0.0, 90.0)
        m.add_lwpolyline([(0, 0, 0.5), (3, 1, 0)], format="xyb")
        given, gm = _doc()
        gm.add_arc((10.0, 0.0), 1.0, 0.0, 90.0, dxfattribs={"extrusion": (0, 0, 1)})
        gm.add_lwpolyline([(0, 0, 0.5), (3, 1, 0)], format="xyb",
                          dxfattribs={"extrusion": (0, 0, 1)})
        for keep in (False, True):
            a = [(p.points, p.arcs) for p in _polys(_read(doc, tmp_path, "a.dxf", keep_arcs=keep))]
            b = [(p.points, p.arcs) for p in _polys(_read(given, tmp_path, "b.dxf", keep_arcs=keep))]
            assert a == b, keep

    def test_centres_are_plain_floats(self, tmp_path):
        """ezdxf gives an LWPOLYLINE's vertices as numpy floats; until v0.2.7
        its kept centres came as numpy floats too."""
        doc, m = _doc()
        m.add_lwpolyline([(0, 0, 1.0), (2, 0, 0)], format="xyb")
        p = _only(_read(doc, tmp_path, keep_arcs=True))
        assert p.arcs == {0: (1.0, 0.0), 1: (1.0, 0.0)}, p.arcs
        assert all(type(v) is float for c in p.arcs.values() for v in c), p.arcs

    def test_line_and_spline_are_already_in_the_drawing(self, tmp_path):
        """Their coordinates are the drawing's whatever their extrusion."""
        doc, m = _doc()
        m.add_line((1, 2), (3, 4), dxfattribs={"extrusion": MINUS_Z})
        cat = _read(doc, tmp_path)
        assert _only(cat).points == [(1.0, 2.0), (3.0, 4.0)]
