# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.5 -- the quality triangulation (``ogr_core.fem.refine``): Delaunay
refinement after Shewchuk (2002a) section 3.1, asked for by OGR FEM2D.

What is checked, and against what
---------------------------------
Every check is a property the source proves, or a geometric identity
computed here by another road (NumPy, rational arithmetic, the shoelace
formula). None is a capture of what the code prints, but one: point 10,
which says so.

1. **Theorem 4** (p. 16): with no two input segments meeting at less than
   60 degrees and B >= sqrt 2, the refinement ends, and no triangle is
   skinny: circumradius / shortest edge <= B, so no angle is below
   arcsin(1/2B) (p. 5). The ratio is computed here from the circumcentre,
   not from the module's formula. Several domains (a rectangle, a square
   with a polygonal opening that is a second region, an L, a hexagon with
   a void, two layers), several B, with and without a size bound.
2. **The mesh is Delaunay** (p. 9: "A mesh produced by Ruppert's algorithm
   is Delaunay, and not just constrained Delaunay"): no node strictly
   inside the circumcircle of any triangle, all against all, with NumPy.
   And what that rests on: no subsegment is left encroached -- no vertex
   opposite a piece of a segment on or inside its diametral circle, in
   exact rational arithmetic (p. 9; the test of p. 49).
3. **Every input segment is a chain of mesh edges**, from its u to its v,
   every vertex of the chain on the segment, in order along it. "On" is
   measured in exact rational arithmetic and allows the rounding of a
   midpoint to the floating-point grid (an ulp), which puts it exactly on
   a horizontal or vertical segment and within 1e-13 of the length of an
   oblique one.
4. **The mesh covers the domain**: the areas of the elements of each region
   add up to the area of the region's polygon (shoelace formula), and
   the voids are empty. Every element lies in the region of its seed and
   carries its material; all are counterclockwise; the mesh is conforming.
5. **The size bound** (p. 11): no edge longer than the bound, as defined
   (the least of the bound at the three vertices and the centroid); with a
   constant bound, no edge longer than it. ``math.inf`` is no bound: the
   mesh is the one without it, bit for bit.
6. **The input is in the mesh**: input vertex i is node i, with the same
   coordinates; an isolated input vertex inside a region is a node of some
   element. A segment on x = 0 keeps x = 0 exactly at every vertex added
   on it (OGR FEM2D's axis of symmetry).
7. **What cannot be meshed says why**, with its code, one input per code.
8. **Each setting moves the mesh** (rule 7): B and the size bound change it.
9. **Determinism**: the same input twice, and in another process with
   another hash seed, gives the same mesh bit for bit.
10. **A fingerprint**: the SHA-256 of one mesh, written down on Windows
    and checked on every platform the suite runs on (the CI runs Linux).
    It validates NO number -- it is there so that a change of the mesh, on
    purpose or by a platform, is seen. If it changes on purpose, the new
    value goes into the changelog with the reason.

Teeth: the mutants put in by hand, and the tests that caught them, are in
the changelog of v0.2.5.
"""
from __future__ import annotations

import hashlib
import math
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

from ogr_core.fem import messages as M
from ogr_core.fem.refine import (MIN_RATIO, PSLG, QualityMeshError,
                                 quality_triangulation)

_ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------
# Domains
# ----------------------------------------------------------------------
class _Builder:
    """Vertices and segments of rings and open polylines."""

    def __init__(self):
        self.vertices, self.segments = [], []

    def vertex(self, xy):
        if xy in self.vertices:
            return self.vertices.index(xy)
        self.vertices.append(xy)
        return len(self.vertices) - 1

    def ring(self, pts, label):
        ids = [self.vertex(p) for p in pts]
        for k in range(len(ids)):
            self.segments.append((ids[k], ids[(k + 1) % len(ids)], label))
        return ids

    def line(self, pts, label):
        ids = [self.vertex(p) for p in pts]
        for a, b in zip(ids, ids[1:]):
            self.segments.append((a, b, label))

    def pslg(self, seeds, voids=()):
        return PSLG(tuple(self.vertices), tuple(self.segments),
                    tuple(seeds), tuple(voids))


def _polygon(n, r, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(2 * math.pi * k / n),
             cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _shoelace(pts):
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1]
                     - pts[(i + 1) % len(pts)][0] * pts[i][1]
                     for i in range(len(pts)))


def _inside(pt, ring):
    x, y = pt
    inside = False
    for i in range(len(ring)):
        (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % len(ring)]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


RECT = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
SQUARE = [(-10.0, -10.0), (10.0, -10.0), (10.0, 10.0), (-10.0, 10.0)]
#: The 40-sided opening (radius 1), written bit for bit: cos and sin come
#: from each platform's maths library, which need not round them the same
#: way, and the fingerprint (point 10) must see the mesher, not that
#: library. These are the values of Windows (MSVC) on 2026-11-23.
OPENING = [(float.fromhex(x), float.fromhex(y)) for x, y in (
    ("0x1.0000000000000p+0", "0x0.0p+0"),
    ("0x1.f9b24942fe45cp-1", "0x1.4060b67a85375p-3"),
    ("0x1.e6f0e134454ffp-1", "0x1.3c6ef372fe94fp-2"),
    ("0x1.c83201d3d2c6dp-1", "0x1.d0e2e2b44de00p-2"),
    ("0x1.9e3779b97f4a8p-1", "0x1.2cf2304755a5ep-1"),
    ("0x1.6a09e667f3bcdp-1", "0x1.6a09e667f3bcdp-1"),
    ("0x1.2cf2304755a5ep-1", "0x1.9e3779b97f4a8p-1"),
    ("0x1.d0e2e2b44de01p-2", "0x1.c83201d3d2c6cp-1"),
    ("0x1.3c6ef372fe950p-2", "0x1.e6f0e134454ffp-1"),
    ("0x1.4060b67a85377p-3", "0x1.f9b24942fe45cp-1"),
    ("0x1.1a62633145c07p-54", "0x1.0000000000000p+0"),
    ("-0x1.4060b67a8536bp-3", "0x1.f9b24942fe45cp-1"),
    ("-0x1.3c6ef372fe94ep-2", "0x1.e6f0e13445500p-1"),
    ("-0x1.d0e2e2b44de00p-2", "0x1.c83201d3d2c6dp-1"),
    ("-0x1.2cf2304755a5dp-1", "0x1.9e3779b97f4a8p-1"),
    ("-0x1.6a09e667f3bccp-1", "0x1.6a09e667f3bcdp-1"),
    ("-0x1.9e3779b97f4a7p-1", "0x1.2cf2304755a5fp-1"),
    ("-0x1.c83201d3d2c6cp-1", "0x1.d0e2e2b44de02p-2"),
    ("-0x1.e6f0e134454ffp-1", "0x1.3c6ef372fe951p-2"),
    ("-0x1.f9b24942fe45bp-1", "0x1.4060b67a85379p-3"),
    ("-0x1.0000000000000p+0", "0x1.1a62633145c07p-53"),
    ("-0x1.f9b24942fe45cp-1", "-0x1.4060b67a85370p-3"),
    ("-0x1.e6f0e13445501p-1", "-0x1.3c6ef372fe946p-2"),
    ("-0x1.c83201d3d2c6dp-1", "-0x1.d0e2e2b44ddfep-2"),
    ("-0x1.9e3779b97f4a8p-1", "-0x1.2cf2304755a5dp-1"),
    ("-0x1.6a09e667f3bcep-1", "-0x1.6a09e667f3bccp-1"),
    ("-0x1.2cf2304755a5fp-1", "-0x1.9e3779b97f4a7p-1"),
    ("-0x1.d0e2e2b44de03p-2", "-0x1.c83201d3d2c6cp-1"),
    ("-0x1.3c6ef372fe952p-2", "-0x1.e6f0e134454ffp-1"),
    ("-0x1.4060b67a8537bp-3", "-0x1.f9b24942fe45bp-1"),
    ("-0x1.a79394c9e8a0ap-53", "-0x1.0000000000000p+0"),
    ("0x1.4060b67a8536ep-3", "-0x1.f9b24942fe45cp-1"),
    ("0x1.3c6ef372fe94cp-2", "-0x1.e6f0e13445500p-1"),
    ("0x1.d0e2e2b44ddfep-2", "-0x1.c83201d3d2c6ep-1"),
    ("0x1.2cf2304755a5cp-1", "-0x1.9e3779b97f4a9p-1"),
    ("0x1.6a09e667f3bcbp-1", "-0x1.6a09e667f3bcep-1"),
    ("0x1.9e3779b97f4a7p-1", "-0x1.2cf2304755a60p-1"),
    ("0x1.c83201d3d2c6cp-1", "-0x1.d0e2e2b44de04p-2"),
    ("0x1.e6f0e134454ffp-1", "-0x1.3c6ef372fe954p-2"),
    ("0x1.f9b24942fe45bp-1", "-0x1.4060b67a8537dp-3"),
)]
ELL = [(0.0, 0.0), (6.0, 0.0), (6.0, 2.0), (2.0, 2.0), (2.0, 5.0), (0.0, 5.0)]
HEXAGON = _polygon(6, 5.0)
HEX_VOID = _polygon(6, 1.5)


def _domains():
    """(name, pslg, {region: (outer ring, [holes])}) -- domains whose input
    segments never meet at less than 60 degrees."""
    out = []
    b = _Builder()
    b.ring(RECT, "rect")
    out.append(("rectangle", b.pslg([((1.0, 1.0), 0, "rock")]),
                {0: (RECT, [])}))
    b = _Builder()
    b.ring(SQUARE, "outer")
    b.ring(OPENING, "opening")
    out.append(("square with opening",
                b.pslg([((5.0, 5.0), 0, "rock"), ((0.0, 0.0), 1, "exc")]),
                {0: (SQUARE, [OPENING]), 1: (OPENING, [])}))
    b = _Builder()
    b.ring(ELL, "ell")
    out.append(("L", b.pslg([((1.0, 1.0), 0, "soil")]), {0: (ELL, [])}))
    b = _Builder()
    b.ring(HEXAGON, "hexagon")
    b.ring(HEX_VOID, "void")
    out.append(("hexagon with a void",
                b.pslg([((3.0, 0.5), 0, "clay")], voids=[(0.0, 0.0)]),
                {0: (HEXAGON, [HEX_VOID])}))
    b = _Builder()
    top = [(0.0, 2.0), (8.0, 2.0), (8.0, 5.0), (0.0, 5.0)]
    bottom = [(0.0, 0.0), (8.0, 0.0), (8.0, 2.0), (0.0, 2.0)]
    b.ring(bottom, "bottom")
    b.line([(8.0, 2.0), (8.0, 5.0), (0.0, 5.0), (0.0, 2.0)], "top")
    out.append(("two layers",
                b.pslg([((4.0, 1.0), 0, 1), ((4.0, 4.0), 1, 2)]),
                {0: (bottom, []), 1: (top, [])}))
    return out


def _coords(mesh):
    return np.array([(n.x, n.y) for n in mesh.nodes])


def _ratios(mesh):
    """Circumradius / shortest edge of every element, from the
    circumcentre (not from the module's formula)."""
    out = []
    for e in mesh.elements:
        (ax, ay), (bx, by), (cx, cy) = e.coords(mesh)
        d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
              + (cx * cx + cy * cy) * (ay - by)) / d
        uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
              + (cx * cx + cy * cy) * (bx - ax)) / d
        r = math.hypot(ax - ux, ay - uy)
        lmin = min(math.hypot(ax - bx, ay - by), math.hypot(bx - cx, by - cy),
                   math.hypot(cx - ax, cy - ay))
        out.append(r / lmin)
    return out


def _delaunay_violations(mesh):
    xy = _coords(mesh)
    tri = np.array([e.nodes for e in mesh.elements])
    a, b, c = xy[tri[:, 0]], xy[tri[:, 1]], xy[tri[:, 2]]
    d = 2.0 * (a[:, 0] * (b[:, 1] - c[:, 1]) + b[:, 0] * (c[:, 1] - a[:, 1])
               + c[:, 0] * (a[:, 1] - b[:, 1]))
    a2, b2, c2 = (a ** 2).sum(1), (b ** 2).sum(1), (c ** 2).sum(1)
    ux = (a2 * (b[:, 1] - c[:, 1]) + b2 * (c[:, 1] - a[:, 1])
          + c2 * (a[:, 1] - b[:, 1])) / d
    uy = (a2 * (c[:, 0] - b[:, 0]) + b2 * (a[:, 0] - c[:, 0])
          + c2 * (b[:, 0] - a[:, 0])) / d
    r2 = (a[:, 0] - ux) ** 2 + (a[:, 1] - uy) ** 2
    bad = 0
    for k in range(0, len(tri), 256):
        dx = xy[None, :, 0] - ux[k:k + 256, None]
        dy = xy[None, :, 1] - uy[k:k + 256, None]
        inside = dx * dx + dy * dy < r2[k:k + 256, None] * (1.0 - 1e-9)
        bad += int(inside.sum())
    return bad


def _mesh_bytes(result):
    m = result.mesh
    text = [f"{n.x.hex()} {n.y.hex()}" for n in m.nodes]
    text += [f"{e.nodes} {e.material_id!r} {e.region_index!r}"
             for e in m.elements]
    text += [repr(c) for c in result.segment_vertices]
    return "\n".join(text).encode("utf-8")


# ----------------------------------------------------------------------
class TestTheorem4:

    def test_no_skinny_triangle_where_no_input_angle_is_below_60(self):
        for name, pslg, _regions in _domains():
            for b in (MIN_RATIO, 1.6, 2.5):
                for size in (None, 0.6):
                    r = quality_triangulation(
                        pslg, max_ratio=b,
                        size=(lambda x, y, h=size: h) if size else None)
                    worst = max(_ratios(r.mesh))
                    assert worst <= b * (1.0 + 1e-9), (name, b, size, worst)
                    floor = math.degrees(math.asin(1.0 / (2.0 * b)))
                    got = r.mesh.quality_stats()["min_angle"]
                    assert got >= floor - 1e-7, (name, b, size, got, floor)
                    assert r.notes["above_ratio"] == [], (name, b, size)
                    assert r.notes["unsplittable"] == 0, (name, b, size)


class TestTheMesh:

    def test_it_is_delaunay(self):
        for name, pslg, _regions in _domains():
            for size in (None, 0.8):
                r = quality_triangulation(
                    pslg, size=(lambda x, y, h=size: h) if size else None)
                assert _delaunay_violations(r.mesh) == 0, (name, size)

    def test_no_subsegment_is_left_encroached(self):
        # p. 9: refinement ends with no encroached subsegment, which is
        # what makes the mesh Delaunay; p. 49: in a constrained Delaunay
        # triangulation a subsegment is encroached if and only if one of
        # the vertices opposite it is, so those are the ones looked at
        for name, pslg, _regions in _domains():
            for size in (None, 0.7):
                r = quality_triangulation(
                    pslg, size=(lambda x, y, h=size: h) if size else None)
                m = r.mesh
                owners = m.edge_map()
                for chain in r.segment_vertices:
                    for a, b in zip(chain, chain[1:]):
                        pa = (Fraction(m.nodes[a].x), Fraction(m.nodes[a].y))
                        pb = (Fraction(m.nodes[b].x), Fraction(m.nodes[b].y))
                        for eid in owners[(min(a, b), max(a, b))]:
                            w = next(i for i in m.elements[eid].nodes
                                     if i not in (a, b))
                            pw = (Fraction(m.nodes[w].x),
                                  Fraction(m.nodes[w].y))
                            dot = ((pa[0] - pw[0]) * (pb[0] - pw[0])
                                   + (pa[1] - pw[1]) * (pb[1] - pw[1]))
                            assert dot > 0, (name, size, a, b, w)

    def test_every_segment_is_a_chain_of_edges_along_it(self):
        for name, pslg, _regions in _domains():
            r = quality_triangulation(pslg, size=lambda x, y: 0.7)
            m = r.mesh
            edges = set(m.edge_map())
            assert r.segment_labels == [s[2] for s in pslg.segments]
            for (u, v, _label), chain in zip(pslg.segments,
                                             r.segment_vertices):
                assert chain[0] == u and chain[-1] == v, (name, u, v)
                pu = (Fraction(m.nodes[u].x), Fraction(m.nodes[u].y))
                pv = (Fraction(m.nodes[v].x), Fraction(m.nodes[v].y))
                last = Fraction(-1)
                for a, b in zip(chain, chain[1:]):
                    assert (min(a, b), max(a, b)) in edges, (name, a, b)
                for w in chain:
                    pw = (Fraction(m.nodes[w].x), Fraction(m.nodes[w].y))
                    cross = ((pv[0] - pu[0]) * (pw[1] - pu[1])
                             - (pv[1] - pu[1]) * (pw[0] - pu[0]))
                    # a midpoint is rounded to the nearest point of the
                    # floating-point grid, which is ON a horizontal or
                    # vertical segment (test_a_segment_on_the_axis...) and
                    # within an ulp of an oblique one
                    length2 = (pv[0] - pu[0]) ** 2 + (pv[1] - pu[1]) ** 2
                    assert cross * cross <= Fraction(1e-26) * length2                         * length2, (name, u, v, w)
                    along = ((pw[0] - pu[0]) * (pv[0] - pu[0])
                             + (pw[1] - pu[1]) * (pv[1] - pu[1]))
                    assert along > last, (name, u, v, chain)
                    last = along

    def test_it_covers_the_regions_with_their_materials(self):
        for name, pslg, regions in _domains():
            r = quality_triangulation(pslg, size=lambda x, y: 0.9)
            m = r.mesh
            assert m.is_conforming(), name
            material = {s[1]: s[2] for s in pslg.seeds}
            area = {k: 0.0 for k in regions}
            for e in m.elements:
                (ax, ay), (bx, by), (cx, cy) = e.coords(m)
                signed = 0.5 * ((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))
                assert signed > 0.0, (name, e.id)
                outer, holes = regions[e.region_index]
                g = e.centroid(m)
                assert _inside(g, outer), (name, e.id)
                assert not any(_inside(g, h) for h in holes), (name, e.id)
                assert e.material_id == material[e.region_index], name
                area[e.region_index] += signed
            for k, (outer, holes) in regions.items():
                want = abs(_shoelace(outer)) - sum(abs(_shoelace(h))
                                                   for h in holes)
                assert abs(area[k] - want) <= 1e-9 * want, (name, k)


class TestTheSizeBound:

    def test_no_edge_longer_than_the_bound(self):
        def h(x, y):
            return 0.15 + 0.2 * math.hypot(x - 1.0, y - 1.0)

        for name, pslg, _regions in _domains():
            for bound in (h, lambda x, y: 0.5):
                m = quality_triangulation(pslg, size=bound).mesh
                for e in m.elements:
                    p = e.coords(m)
                    g = e.centroid(m)
                    limit = min([bound(*q) for q in p] + [bound(*g)])
                    lmax = max(math.dist(p[i], p[(i + 1) % 3])
                               for i in range(3))
                    assert lmax <= limit * (1.0 + 1e-12), (name, e.id)

    def test_infinity_is_no_bound(self):
        for name, pslg, _regions in _domains():
            free = quality_triangulation(pslg)
            inf = quality_triangulation(pslg, size=lambda x, y: math.inf)
            assert _mesh_bytes(free) == _mesh_bytes(inf), name


class TestTheInputIsInTheMesh:

    def test_input_vertex_i_is_node_i(self):
        b = _Builder()
        b.ring(RECT, "rect")
        loose = b.vertex((2.5, 1.25))
        r = quality_triangulation(b.pslg([((1.0, 1.0), 0, "rock")]),
                                  size=lambda x, y: 0.8)
        m = r.mesh
        for i, (x, y) in enumerate(b.vertices):
            assert (m.nodes[i].x, m.nodes[i].y) == (x, y), i
        assert any(loose in e.nodes for e in m.elements)

    def test_a_segment_on_the_axis_keeps_x_zero(self):
        b = _Builder()
        b.ring([(0.0, 0.0), (3.7, 0.0), (3.7, 9.1), (0.0, 9.1)], "half")
        r = quality_triangulation(b.pslg([((1.0, 1.0), 0, "rock")]),
                                  size=lambda x, y: 0.37)
        axis = r.segment_vertices[3]
        assert len(axis) > 10
        assert all(r.mesh.nodes[i].x == 0.0 for i in axis)

    def test_an_object_with_the_four_attributes_will_do(self):
        class Theirs:
            vertices = tuple(RECT)
            segments = tuple((i, (i + 1) % 4, 10 + i) for i in range(4))
            seeds = (((1.0, 1.0), 3, 7),)
            voids = ()
            arcs = {}
        r = quality_triangulation(Theirs())
        assert r.segment_labels == [10, 11, 12, 13]
        assert {(e.region_index, e.material_id)
                for e in r.mesh.elements} == {(3, 7)}


class TestWhatCannotBeMeshed:

    def _code(self, pslg, **kw):
        try:
            quality_triangulation(pslg, **kw)
        except QualityMeshError as exc:
            assert str(exc) == str(exc.note)
            return exc.code
        return None

    def test_each_input_says_its_code(self):
        sq = tuple((i, (i + 1) % 4, i) for i in range(4))
        seed = (((1.0, 1.0), 0, "m"),)
        ok = PSLG(tuple(RECT), sq, seed)
        cases = [
            (ok, {"max_ratio": 1.3}, M.REFINE_BAD_RATIO),
            (ok, {"max_ratio": float("nan")}, M.REFINE_BAD_RATIO),
            (ok, {"size": lambda x, y: 0.0}, M.REFINE_BAD_SIZE),
            (ok, {"size": lambda x, y: float("nan")}, M.REFINE_BAD_SIZE),
            (ok, {"max_triangles": 20, "size": lambda x, y: 0.2},
             M.REFINE_TOO_MANY_TRIANGLES),
            (PSLG(tuple(RECT), (), seed), {}, M.REFINE_EMPTY),
            (PSLG(tuple(RECT), sq, ()), {}, M.REFINE_EMPTY),
            (PSLG(tuple(RECT) + ((float("inf"), 0.0),), sq, seed), {},
             M.REFINE_BAD_VERTEX),
            (PSLG(tuple(RECT) + ((4.0, 3.0),), sq, seed), {},
             M.REFINE_DUPLICATE_VERTEX),
            (PSLG(tuple(RECT), sq + ((0, 9, "x"),), seed), {},
             M.REFINE_BAD_SEGMENT),
            (PSLG(tuple(RECT), sq + ((1, 1, "x"),), seed), {},
             M.REFINE_BAD_SEGMENT),
            (PSLG(tuple(RECT), sq + ((1, 0, "x"),), seed), {},
             M.REFINE_DUPLICATE_SEGMENT),
            (PSLG(tuple(RECT), sq + ((0, 2, "d"), (1, 3, "d")), seed), {},
             M.REFINE_CROSSING_SEGMENTS),
            (PSLG(tuple(RECT) + ((2.0, 0.0),), sq + ((0, 4, "o"),), seed),
             {}, M.REFINE_CROSSING_SEGMENTS),
            (PSLG(tuple(RECT) + ((2.0, 0.0),), sq, seed), {},
             M.REFINE_VERTEX_ON_SEGMENT),
            (PSLG(tuple(RECT), sq, (((0.0, 1.0), 0, "m"),)), {},
             M.REFINE_SEED_ON_SEGMENT),
            (PSLG(tuple(RECT), sq, (((9.0, 9.0), 0, "m"),)), {},
             M.REFINE_SEED_OUTSIDE),
            (PSLG(tuple(RECT), sq, (((1e9, 1e9), 0, "m"),)), {},
             M.REFINE_SEED_OUTSIDE),
            (PSLG(tuple(RECT), sq, seed, ((9.0, 9.0),)), {},
             M.REFINE_VOID_OUTSIDE),
            (PSLG(tuple(RECT), sq, seed, ((4.0, 1.0),)), {},
             M.REFINE_VOID_ON_SEGMENT),
            (PSLG(tuple(RECT), sq, seed + (((3.0, 2.0), 1, "n"),)), {},
             M.REFINE_SEEDS_SHARE_REGION),
            (PSLG(tuple(RECT) + ((2.0, 0.0), (2.0, 3.0)),
                  ((0, 4, 0), (4, 1, 0), (1, 2, 1), (2, 5, 2), (5, 3, 2),
                   (3, 0, 3), (4, 5, 4)), seed), {},
             M.REFINE_REGION_WITHOUT_SEED),
            (PSLG(tuple(RECT) + ((7.0, 1.0),), sq, seed), {},
             M.REFINE_VERTEX_OUTSIDE),
        ]
        for pslg, kw, code in cases:
            assert self._code(pslg, **kw) == code, (code, kw)
        assert self._code(ok) is None

    def test_every_code_has_its_english(self):
        for code, spec in M.REFINE_MESSAGES.items():
            assert code.startswith("refine.") and spec.english, code


class TestEachSettingMovesTheMesh:

    def test_the_ratio_and_the_size(self):
        _name, pslg, _regions = _domains()[1]
        base = quality_triangulation(pslg)
        looser = quality_triangulation(pslg, max_ratio=2.5)
        finer = quality_triangulation(pslg, size=lambda x, y: 1.0)
        assert _mesh_bytes(base) != _mesh_bytes(looser)
        assert len(finer.mesh.elements) > len(base.mesh.elements)
        assert max(_ratios(looser.mesh)) > MIN_RATIO


_PROBE = """
import hashlib, sys
sys.path.insert(0, {tests!r})
import test_quality_triangulation_v025 as T
name, pslg, regions = T._domains()[1]
r = T.quality_triangulation(pslg, size=lambda x, y: 1.0)
print(hashlib.sha256(T._mesh_bytes(r)).hexdigest())
"""


def _probe_mesh():
    _name, pslg, _regions = _domains()[1]
    return quality_triangulation(pslg, size=lambda x, y: 1.0)


#: The SHA-256 of ``_mesh_bytes(_probe_mesh())``, written down on Windows
#: (Python 3.14) on 2026-11-22. NOT a validation (see point 10 above).
FINGERPRINT = ("43e71727468e52d3deb46ca254c7f5f7"
               "cf040e899fdb1f6bbf8824bdb697907d")


class TestDeterminism:

    def test_the_same_input_gives_the_same_mesh(self):
        assert _mesh_bytes(_probe_mesh()) == _mesh_bytes(_probe_mesh())

    def test_another_process_and_hash_seed_give_the_same_mesh(self):
        here = hashlib.sha256(_mesh_bytes(_probe_mesh())).hexdigest()
        env = dict(os.environ, PYTHONHASHSEED="12345",
                   PYTHONPATH=str(_ROOT) + os.pathsep
                   + os.environ.get("PYTHONPATH", ""))
        out = subprocess.run(
            [sys.executable, "-c",
             _PROBE.format(tests=str(_ROOT / "tests"))],
            capture_output=True, text=True, env=env, timeout=300)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == here

    def test_the_fingerprint(self):
        got = hashlib.sha256(_mesh_bytes(_probe_mesh())).hexdigest()
        assert got == FINGERPRINT, got
