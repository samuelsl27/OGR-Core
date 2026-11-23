# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.7 — the DXF reader keeps the arcs as arcs (``keep_arcs=True``), and
reads right the two kinds of bulge it read wrong.

Asked by OGR FEM2D (decision D13 of its spec 004). A six-node mesh puts the
mid-side node of every side on the arc, so it needs each curved piece's two
ends, exact and shared with its neighbours, and its centre. Every number
here comes from closed-form geometry, never from what the code printed:

* a bulge b between two vertices at chord c is an arc of included angle
  θ = 4·atan|b|, anticlockwise when b > 0. Its centre is on the bisector
  of the chord, at signed distance d = c(1 − b²)/(4b) to the LEFT of the
  chord's direction (the DXF reference definition of the bulge). The test
  uses that formula; the reader computes it another way;
* the pieces are minor arcs of 90° at most, ``ceil(S / 90°)`` of them for a
  sweep S, and their sweeps add up to the arc's.

Found while doing it, and fixed in the flattened reading too (decision of
the owner, 2026-11-23):

* a bulge with |b| > 1 (more than half a circle) came as the MINOR arc of
  the mirrored circle. From (0, 0) to (2, 0) with b = tan 67.5° it gave 17
  points down to y = −0.414 instead of the 270° arc about (1, −1);
* the bulges of a 2-D ``POLYLINE`` were ignored: its arcs came as chords.
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


def _requires_ezdxf(cls):
    return cls if _HAS_EZDXF else type(cls.__name__, (), {})


T22 = math.tan(math.radians(22.5))     # bulge of a quarter circle
T67 = math.tan(math.radians(67.5))     # bulge of three quarters


def _doc():
    doc = ezdxf.new("R2010")
    return doc, doc.modelspace()


def _read(doc, tmp_path, name="d.dxf", **kw):
    path = tmp_path / name
    doc.saveas(str(path))
    return read_dxf(path, **kw)


def _only(cat):
    polys = [p for lay in cat.layers for p in lay.polylines]
    assert len(polys) == 1, polys
    return polys[0]


def _sweep(a, b, c):
    """Signed angle, in degrees, from a to b about c (anticlockwise > 0)."""
    ua = (a[0] - c[0], a[1] - c[1])
    ub = (b[0] - c[0], b[1] - c[1])
    return math.degrees(math.atan2(ua[0] * ub[1] - ua[1] * ub[0],
                                   ua[0] * ub[0] + ua[1] * ub[1]))


def _centre_of_bulge(p1, p2, b):
    """d = c(1 − b²)/(4b) to the left of p1 → p2, from the midpoint."""
    c = math.dist(p1, p2)
    d = c * (1.0 - b * b) / (4.0 * b)
    ux, uy = (p2[0] - p1[0]) / c, (p2[1] - p1[1]) / c
    mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    return mx - d * uy, my + d * ux


def _assert_pieces_on_circle(poly, tol=1e-12):
    """Every kept piece: both ends at one radius, minor, 90° at most."""
    for k, c in poly.arcs.items():
        assert 0 <= k < poly.n - 1, (k, poly.n)
        a, b = poly.points[k], poly.points[k + 1]
        ra, rb = math.dist(a, c), math.dist(b, c)
        assert abs(ra - rb) <= tol * max(ra, rb), (k, ra, rb)
        s = _sweep(a, b, c)
        assert 0.0 < abs(s) <= 90.0 + 1e-9, (k, s)


# ======================================================================
@_requires_ezdxf
class TestCircle:
    def test_four_quarters_about_the_exact_centre(self, tmp_path):
        doc, m = _doc()
        m.add_circle((3.0, -2.0), 5.0)
        p = _only(_read(doc, tmp_path, keep_arcs=True))
        assert p.closed and p.n == 5, (p.closed, p.n)
        assert p.points[-1] == p.points[0]
        assert p.arcs == {k: (3.0, -2.0) for k in range(4)}, p.arcs
        for k in range(4):
            a, b = p.points[k], p.points[k + 1]
            assert abs(math.dist(a, (3.0, -2.0)) - 5.0) < 1e-12
            assert abs(_sweep(a, b, (3.0, -2.0)) - 90.0) < 1e-9
        _assert_pieces_on_circle(p)

    def test_flattened_circle_has_no_arcs(self, tmp_path):
        doc, m = _doc()
        m.add_circle((3.0, -2.0), 5.0)
        p = _only(_read(doc, tmp_path, segments_per_circle=64))
        assert p.arcs == {} and p.n == 65, (p.arcs, p.n)


@_requires_ezdxf
class TestArcEntity:
    def _arc(self, tmp_path, start, end):
        doc, m = _doc()
        m.add_arc((1.0, 2.0), 3.0, start, end)
        return _only(_read(doc, tmp_path, keep_arcs=True))

    def test_270_degrees_in_three_quarters(self, tmp_path):
        p = self._arc(tmp_path, 30.0, 300.0)
        assert not p.closed and p.n == 4, p.n
        assert p.arcs == {0: (1.0, 2.0), 1: (1.0, 2.0), 2: (1.0, 2.0)}
        s0 = math.degrees(math.atan2(p.points[0][1] - 2.0, p.points[0][0] - 1.0))
        s1 = math.degrees(math.atan2(p.points[-1][1] - 2.0, p.points[-1][0] - 1.0))
        assert abs(s0 - 30.0) < 1e-9 and abs(s1 - (300.0 - 360.0)) < 1e-9, (s0, s1)
        for k in range(3):
            assert abs(_sweep(p.points[k], p.points[k + 1], (1.0, 2.0)) - 90.0) < 1e-9
        _assert_pieces_on_circle(p)

    def test_piece_count_is_ceil_of_sweep_over_90(self, tmp_path):
        for start, end, pieces in ((10.0, 20.0, 1), (0.0, 90.0, 1),
                                   (0.0, 90.5, 2), (0.0, 180.0, 2),
                                   (350.0, 100.0, 2), (0.0, 359.0, 4)):
            p = self._arc(tmp_path, start, end)
            assert len(p.arcs) == pieces == p.n - 1, (start, end, p.n, p.arcs)
            total = sum(_sweep(p.points[k], p.points[k + 1], (1.0, 2.0))
                        for k in range(p.n - 1))
            assert abs(total - (end - start) % 360.0) < 1e-9, (start, end, total)


@_requires_ezdxf
class TestBulgesKept:
    # (0,0) straight to (4,0); a quarter to (6,2); half a circle to (6,6);
    # three quarters CLOCKWISE to (10,6).
    RAW = [(0.0, 0.0, 0.0), (4.0, 0.0, T22), (6.0, 2.0, 1.0),
           (6.0, 6.0, -T67), (10.0, 6.0, 0.0)]

    def _poly(self, tmp_path, cls="lw", **kw):
        doc, m = _doc()
        if cls == "lw":
            m.add_lwpolyline(self.RAW, format="xyb")
        else:
            m.add_polyline2d(self.RAW, format="xyb")
        return _only(_read(doc, tmp_path, keep_arcs=True, **kw))

    def _check(self, p):
        # 1 straight + 1 + 2 + 3 pieces
        assert p.n == 8, (p.n, p.points)
        assert sorted(p.arcs) == [1, 2, 3, 4, 5, 6], p.arcs
        # The DXF vertices are the ends, exactly
        for i, j in ((0, 0), (1, 1), (2, 2), (3, 4), (4, 7)):
            assert p.points[j] == self.RAW[i][:2], (i, j, p.points[j])
        # The centres, by the closed formula
        expect = {1: _centre_of_bulge((4, 0), (6, 2), T22),
                  2: _centre_of_bulge((6, 2), (6, 6), 1.0),
                  4: _centre_of_bulge((6, 6), (10, 6), -T67)}
        assert math.dist(expect[2], (6.0, 4.0)) < 1e-15     # by hand
        assert math.dist(expect[4], (8.0, 8.0)) < 1e-12     # by hand
        for k, c in expect.items():
            assert math.dist(p.arcs[k], c) < 1e-12, (k, p.arcs[k], c)
        assert p.arcs[3] == p.arcs[2] and p.arcs[5] == p.arcs[6] == p.arcs[4]
        # Each bulge's pieces add up to 4·atan(b), with its sign
        for ks, b in (((1,), T22), ((2, 3), 1.0), ((4, 5, 6), -T67)):
            total = sum(_sweep(p.points[k], p.points[k + 1], p.arcs[k])
                        for k in ks)
            assert abs(total - math.degrees(4 * math.atan(b))) < 1e-9, (ks, total)
        _assert_pieces_on_circle(p)

    def test_lwpolyline(self, tmp_path):
        self._check(self._poly(tmp_path, "lw"))

    def test_polyline_2d(self, tmp_path):
        p = self._poly(tmp_path, "2d")
        assert p.source == "POLYLINE"
        self._check(p)

    def test_centres_in_metres(self, tmp_path):
        p = self._poly(tmp_path, "lw", unit="mm")
        assert math.dist(p.arcs[2], (0.006, 0.004)) < 1e-15, p.arcs[2]
        assert math.dist(p.points[2], (0.006, 0.002)) < 1e-15
        _assert_pieces_on_circle(p)

    def test_closing_piece_keeps_its_key(self, tmp_path):
        """The last vertex's bulge is the closing piece, (0,4) → (0,0)."""
        doc, m = _doc()
        m.add_lwpolyline([(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 1.0)],
                         format="xyb", close=True)
        p = _only(_read(doc, tmp_path, keep_arcs=True))
        assert p.closed and p.n == 6 and p.points[-1] == p.points[0]
        assert p.arcs == {3: (0.0, 2.0), 4: (0.0, 2.0)}, p.arcs
        _assert_pieces_on_circle(p)

    def test_a_repeated_vertex_does_not_shift_the_keys(self, tmp_path):
        doc, m = _doc()
        m.add_lwpolyline([(0, 0, 0), (2, 0, 0), (2, 0, 1.0), (4, 0, 0)],
                         format="xyb")
        p = _only(_read(doc, tmp_path, keep_arcs=True))
        assert p.n == 4 and p.points[1] == (2.0, 0.0), p.points
        assert p.arcs == {1: (3.0, 0.0), 2: (3.0, 0.0)}, p.arcs
        _assert_pieces_on_circle(p)


# ======================================================================
@_requires_ezdxf
class TestBulgesFlattened:
    def test_bulge_over_half_a_circle(self, tmp_path):
        """b = tan 67.5° from (0,0) to (2,0): 270° anticlockwise about
        (1, −1), radius √2, down to y = −1 − √2. 64 per circle gives 48
        pieces, one of them ending at 270°."""
        for b, centre, extreme in ((T67, (1.0, -1.0), -1.0 - math.sqrt(2)),
                                   (-T67, (1.0, 1.0), 1.0 + math.sqrt(2))):
            doc, m = _doc()
            m.add_lwpolyline([(0, 0, b), (2, 0, 0)], format="xyb")
            p = _only(_read(doc, tmp_path, segments_per_circle=64))
            assert p.n == 49, (b, p.n)
            for q in p.points:
                assert abs(math.dist(q, centre) - math.sqrt(2)) < 1e-12, (b, q)
            ys = [q[1] for q in p.points]
            got = min(ys) if b > 0 else max(ys)
            assert abs(got - extreme) < 1e-12, (b, got)
            assert p.points[0] == (0.0, 0.0) and p.points[-1] == (2.0, 0.0)

    def test_polyline_2d_bulge_is_an_arc(self, tmp_path):
        """Half a circle from (0,0) to (2,0) about (1,0): was a chord."""
        doc, m = _doc()
        m.add_polyline2d([(0, 0, 1.0), (2, 0, 0)], format="xyb")
        p = _only(_read(doc, tmp_path, segments_per_circle=64))
        assert p.n == 33, p.n
        assert p.arcs == {}
        for q in p.points:
            assert abs(math.dist(q, (1.0, 0.0)) - 1.0) < 1e-12, q
        assert min(q[1] for q in p.points) < -0.999

    def test_3d_polyline_is_unchanged(self, tmp_path):
        doc, m = _doc()
        m.add_polyline3d([(0, 0, 0), (2, 0, 1), (2, 3, 0)])
        p = _only(_read(doc, tmp_path, keep_arcs=True))
        assert p.points == [(0.0, 0.0), (2.0, 0.0), (2.0, 3.0)] and p.arcs == {}


# ======================================================================
@_requires_ezdxf
class TestTheOptionMovesTheOutput:
    """Rule 7: ``keep_arcs`` changes a drawing with arcs and leaves one
    without arcs as it was."""

    def test_with_arcs(self, tmp_path):
        doc, m = _doc()
        m.add_arc((0, 0), 2.0, 0.0, 135.0)
        m.add_lwpolyline([(0, 0, 0.5), (3, 1, 0)], format="xyb")
        flat = _read(doc, tmp_path, "a.dxf")
        kept = _read(doc, tmp_path, "b.dxf", keep_arcs=True)
        for f, k in zip((p for lay in flat.layers for p in lay.polylines),
                        (p for lay in kept.layers for p in lay.polylines)):
            assert f.arcs == {} and k.arcs, (f.source, k.arcs)
            assert k.n < f.n, (f.source, k.n, f.n)
            assert f.points[0] == k.points[0] and f.points[-1] == k.points[-1]

    def test_without_arcs(self, tmp_path):
        doc, m = _doc()
        m.add_line((0, 0), (1, 2))
        m.add_lwpolyline([(0, 0), (4, 0), (4, 4)], close=True)
        m.add_polyline2d([(1, 1), (2, 1), (2, 5)])
        m.add_spline([(10, 45), (30, 42), (50, 44), (70, 40)])
        flat = _read(doc, tmp_path, "a.dxf")
        kept = _read(doc, tmp_path, "b.dxf", keep_arcs=True)
        f = [(p.points, p.closed, p.source, p.arcs) for lay in flat.layers
             for p in lay.polylines]
        k = [(p.points, p.closed, p.source, p.arcs) for lay in kept.layers
             for p in lay.polylines]
        assert f == k and all(not a for *_x, a in k), k
