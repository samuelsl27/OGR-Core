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
   a void, a rectangle with a V notch, which is a small angle OUTSIDE the
   domain that "will have no effect on meshing" when the exterior goes
   first, p. 48, and two layers), several B, with and without a size
   bound.
2. **The mesh is Delaunay** (p. 9: "A mesh produced by Ruppert's algorithm
   is Delaunay, and not just constrained Delaunay"): no node strictly
   inside the circumcircle of any triangle, all against all, with NumPy,
   in the convex domains. The exterior is removed before refining and its
   encroachment does not count (p. 48), so across a concavity it is the
   constrained Delaunay triangulation that holds: the local test at every
   edge that is not a piece of a segment, in exact arithmetic, everywhere.
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
11. **Small input angles** (sections 6.2 and 6.3): on the PSLG of figure
    20 at 5, 1 and 20 degrees and on a layer that pinches out at 10 and 3
    degrees, the Terminator ends (Theorem 11) and every triangle is within
    1 / (sqrt 2 sin(phi / 2)) (Theorem 12); no subsegment is left
    encroached and the mesh is Delaunay (p. 36); a triangle left above B
    has its circumcentre at a cluster of a small angle (p. 36); every split
    it declined met none of the conditions A, C, D, E (p. 34). Without it,
    figure 20 does not end (p. 27). The piece next to a shared vertex has
    a power-of-two length (p. 29), and the mesh depends on the unit of
    length (p. 29): twice as large, the same mesh exactly; in millimetres,
    another.
12. **Theorem 8** (p. 23), the grading, with B = 1 / (2 sin 15 deg): every
    vertex at least lfs(v) / (D_S + 1) from its nearest neighbour. A CHECK,
    not a theorem here: the source proves it for bisection, and the shells
    of section 6.2 split as unevenly as one third.
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
#: A rectangle with a V notch cut from its top: the notch is an angle of
#: 14.25 degrees OUTSIDE the domain (p. 33: "exterior" small angles are
#: ignored); every angle inside is 90 degrees or more.
NOTCH = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (5.5, 5.0), (5.0, 1.0),
         (4.5, 5.0), (0.0, 5.0)]
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
    b.ring(NOTCH, "notch")
    out.append(("notch", b.pslg([((2.0, 2.0), 0, "rock")]),
                {0: (NOTCH, [])}))
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


def _local_delaunay_violations(result):
    """Interior edges that are not pieces of a segment and fail the local
    Delaunay test: the vertex opposite on one side strictly inside the
    circumcircle of the triangle on the other, in exact rational
    arithmetic. None at all is the constrained Delaunay triangulation."""
    m = result.mesh
    pieces = {(min(a, b), max(a, b)) for c in result.segment_vertices
              for a, b in zip(c, c[1:])}
    q = [(Fraction(n.x), Fraction(n.y)) for n in m.nodes]
    bad = 0
    for (a, b), owners in m.edge_map().items():
        if len(owners) != 2 or (a, b) in pieces:
            continue
        t1, t2 = (m.elements[i].nodes for i in owners)
        w = next(i for i in t2 if i not in (a, b))
        (ax, ay), (bx, by), (cx, cy) = (q[i] for i in t1)
        dx, dy = q[w]
        adx, ady, bdx, bdy, cdx, cdy = ax - dx, ay - dy, bx - dx, by - dy, \
            cx - dx, cy - dy
        det = ((adx * adx + ady * ady) * (bdx * cdy - cdx * bdy)
               + (bdx * bdx + bdy * bdy) * (cdx * ady - adx * cdy)
               + (cdx * cdx + cdy * cdy) * (adx * bdy - bdx * ady))
        bad += det > 0
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
                    assert r.notes["min_input_angle"] >= 90.0 - 1e-9, name
                    assert r.notes["theorem_12_bound"] is None, name
                    assert r.notes["declined_splits"] == [], name
                    assert r.notes["unsplittable"] == 0, (name, b, size)


class TestTheMesh:

    def test_it_is_delaunay(self):
        # p. 9. The exterior is removed before refining, so the
        # encroachment of a subsegment from outside does not count (p. 48):
        # in a domain that is not convex, a vertex across a concavity may
        # be inside the circumcircle of a triangle that cannot see it. What
        # holds everywhere is the constrained Delaunay triangulation (the
        # local test at every edge that is not a piece of a segment); the
        # Delaunay triangulation of all the nodes, in the convex domains.
        convex = {"rectangle", "square with opening", "two layers"}
        for name, pslg, _regions in _domains():
            for size in (None, 0.8):
                r = quality_triangulation(
                    pslg, size=(lambda x, y, h=size: h) if size else None)
                assert _local_delaunay_violations(r) == 0, (name, size)
                if name in convex:
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


# ----------------------------------------------------------------------
# Small input angles (sections 6.2 and 6.3)
# ----------------------------------------------------------------------
def _fig20(phi_deg):
    """The PSLG of figure 20 (p. 26), with coordinates made up here: the
    figure has none. Three segments meet at o = (0, 0): the lower one at
    phi below the middle one, the middle one split by a vertex at its
    middle, and the left side at 90 degrees above it; the domain is closed
    by the right side and the top. The thin wedge is one region, the rest
    another."""
    t = math.tan(math.radians(phi_deg))
    v = ((0.0, 0.0), (10.0, -10.0 * t), (10.0, 0.0), (10.0, 10.0),
         (0.0, 10.0), (5.0, 0.0))
    s = ((0, 1, "low"), (1, 2, "right"), (2, 3, "right"), (3, 4, "top"),
         (4, 0, "left"), (0, 5, "middle"), (5, 2, "middle"))
    seeds = (((9.0, -2.5 * t), 0, "wedge"), ((5.0, 5.0), 1, "above"))
    return PSLG(v, s, seeds)


def _pinch(phi_deg):
    """A layer that pinches out at phi between two others, as a lens of
    soil at the end of a stratum."""
    t = math.tan(math.radians(phi_deg))
    v = ((0.0, 0.0), (20.0, 0.0), (20.0, 20.0 * t), (20.0, 8.0), (0.0, 8.0))
    s = ((0, 1, 0), (1, 2, 1), (2, 3, 1), (3, 4, 2), (4, 0, 3), (0, 2, 4))
    seeds = (((15.0, 7.5 * t), 0, "lens"), ((5.0, 6.0), 1, "soil"))
    return PSLG(v, s, seeds)


def _input_angles(pslg):
    """Every angle between two input segments at a shared vertex, in
    degrees, from the coordinates (atan2), both sides of each pair of
    neighbours around the vertex."""
    out = []
    pts = pslg.vertices
    for a in range(len(pts)):
        dirs = sorted(math.atan2(pts[w][1] - pts[a][1], pts[w][0] - pts[a][0])
                      for u, v, _l in pslg.segments if a in (u, v)
                      for w in ((v if u == a else u),))
        for i in range(len(dirs)):
            if len(dirs) > 1:
                gap = (dirs[(i + 1) % len(dirs)] - dirs[i]) % (2 * math.pi)
                out.append(math.degrees(gap))
    return out


SMALL = ((_fig20, 5.0, None), (_fig20, 1.0, None), (_fig20, 20.0, None),
         (_pinch, 10.0, None), (_pinch, 3.0, None), (_pinch, 10.0, 1.0),
         (_fig20, 5.0, 0.8))


class TestTheTerminator:

    def test_it_ends_and_holds_the_bound_of_theorem_12(self):
        # Theorem 11 (p. 34): it terminates; Theorem 12 (p. 35): every
        # triangle has circumradius / shortest edge at most
        # 1 / (sqrt 2 sin(phi/2)), phi the smallest angle of the PSLG, so
        # no angle below arcsin(sin(phi/2) / sqrt 2)
        for build, phi, size in SMALL:
            pslg = build(phi)
            r = quality_triangulation(
                pslg, size=(lambda x, y, h=size: h) if size else None)
            small = min(_input_angles(pslg))
            assert abs(small - phi) < 1e-9, (phi, small)
            bound = 1.0 / (math.sqrt(2.0) * math.sin(math.radians(phi) / 2))
            worst = max(_ratios(r.mesh))
            assert worst <= bound * (1.0 + 1e-9), (phi, size, worst, bound)
            floor = math.degrees(math.asin(
                math.sin(math.radians(phi) / 2) / math.sqrt(2.0)))
            assert r.mesh.quality_stats()["min_angle"] >= floor - 1e-7
            assert abs(r.notes["min_input_angle"] - phi) < 1e-9
            assert abs(r.notes["theorem_12_bound"] - bound) <= 1e-9 * bound
            assert r.notes["unsplittable"] == 0

    def test_each_declined_split_met_none_of_the_conditions(self):
        # p. 34: the vertex is inserted "if and only if one or more of the
        # following six conditions hold"; F is left out. A split declined
        # must therefore have met none of A, C, D, E (B is the size, and
        # these meshes have none or a large one): r_min < r_g (A), the
        # subsegment's length a power of two (C), a cluster at one end only
        # (D: its other end is no apex), and no piece of its cluster shorter
        # (E). And r_min is |s| sin(phi_min / 2) with the angle of its
        # cluster (p. 34), here the small angle of the PSLG.
        seen = 0
        for build, phi, size in SMALL:
            pslg = build(phi)
            r = quality_triangulation(
                pslg, size=(lambda x, y, h=size: h) if size else None)
            apexes = {tuple(pslg.vertices[a]) for a in range(len(pslg.vertices))
                      if min(_input_angles(_PSLG_at(pslg, a)) or [360.0])
                      <= 60.0}
            for d in r.notes["declined_splits"]:
                seen += 1
                (x1, y1), (x2, y2) = d["subsegment"]
                length = math.hypot(x2 - x1, y2 - y1)
                assert abs(length - d["length"]) <= 1e-12 * length
                k = round(math.log2(length))
                assert abs(length / 2.0 ** k - 1.0) < 1e-9, d          # C
                assert d["r_min"] < d["r_g"], d                       # A
                ends = {(x1, y1), (x2, y2)}
                assert tuple(d["apex"]) in ends, d
                assert len(ends & apexes) == 1, d                     # D
                assert d["cluster_shortest"] is None or \
                    d["cluster_shortest"] >= length * (1 - 1e-9), d   # E
                want = length * math.sin(math.radians(phi) / 2.0)
                assert abs(d["r_min"] - want) <= 1e-9 * want, (d, want)
        assert seen > 0

    def test_it_leaves_no_subsegment_encroached(self):
        # p. 36: "The Terminator eliminates all encroached subsegments, and
        # is suitable for applications that require the final mesh to be
        # Delaunay"
        for build, phi, size in SMALL:
            r = quality_triangulation(
                build(phi), size=(lambda x, y, h=size: h) if size else None)
            assert _delaunay_violations(r.mesh) == 0, (phi, size)   # convex
            assert _local_delaunay_violations(r) == 0, (phi, size)
            m = r.mesh
            owners = m.edge_map()
            for chain in r.segment_vertices:
                for a, b in zip(chain, chain[1:]):
                    for eid in owners[(min(a, b), max(a, b))]:
                        w = next(i for i in m.elements[eid].nodes
                                 if i not in (a, b))
                        pa, pb, pw = (tuple(map(Fraction, (m.nodes[i].x,
                                                           m.nodes[i].y)))
                                      for i in (a, b, w))
                        assert ((pa[0] - pw[0]) * (pb[0] - pw[0])
                                + (pa[1] - pw[1]) * (pb[1] - pw[1])) > 0

    def test_skinny_triangles_are_only_at_small_angles(self):
        # p. 36: "Every skinny triangle's circumcenter encroaches upon a
        # subsegment cluster bearing a small input angle": a triangle left
        # above B has its circumcentre on or inside the diametral circle of
        # a piece of segment that ends at a vertex with an angle of 60
        # degrees or less
        for build, phi, size in SMALL:
            pslg = build(phi)
            r = quality_triangulation(
                pslg, size=(lambda x, y, h=size: h) if size else None)
            m = r.mesh
            apexes = set()
            for a in range(len(pslg.vertices)):
                sub = _PSLG_at(pslg, a)
                if min(_input_angles(sub) or [360.0]) <= 60.0:
                    apexes.add(a)
            pieces = [(c[k], c[k + 1]) for c in r.segment_vertices
                      for k in range(len(c) - 1)
                      if c[k] in apexes or c[k + 1] in apexes]
            for item in r.notes["above_ratio"]:
                e = m.elements[item["element"]]
                (ax, ay), (bx, by), (cx, cy) = e.coords(m)
                d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
                ux = ((ax * ax + ay * ay) * (by - cy)
                      + (bx * bx + by * by) * (cy - ay)
                      + (cx * cx + cy * cy) * (ay - by)) / d
                uy = ((ax * ax + ay * ay) * (cx - bx)
                      + (bx * bx + by * by) * (ax - cx)
                      + (cx * cx + cy * cy) * (bx - ax)) / d
                assert any(
                    (m.nodes[p].x - ux) * (m.nodes[q].x - ux)
                    + (m.nodes[p].y - uy) * (m.nodes[q].y - uy)
                    <= 1e-9 * math.dist((m.nodes[p].x, m.nodes[p].y),
                                        (m.nodes[q].x, m.nodes[q].y)) ** 2
                    for p, q in pieces), (phi, size, item)

    def test_without_it_figure_20_does_not_end(self):
        # p. 27: "Ruppert's algorithm fails to terminate on PSLGs like that
        # of Figure 20"; with every split permitted, the edges at o shrink
        # until floating point cannot go on
        from ogr_core.fem import refine as R
        saved = R._Refiner._split_permitted
        try:
            R._Refiner._split_permitted = lambda self, key, t: True
            for phi in (5.0, 1.0):
                try:
                    quality_triangulation(_fig20(phi))
                except QualityMeshError as exc:
                    assert exc.code in (M.REFINE_TOO_FINE,
                                        M.REFINE_TOO_MANY_TRIANGLES)
                else:
                    raise AssertionError(f"figure 20 at {phi} ended")
        finally:
            R._Refiner._split_permitted = saved
        assert R._Refiner._split_permitted is saved



class TestSplitPermitted:
    """Figure 38, SPLITPERMITTED(s, d), against its table: the split is
    permitted if s has no cluster or two (line 27; D), if its length is
    not a power of two (line 27; C), if its cluster has a shorter
    subsegment (line 30; E), or if r_min = |s| sin(phi_min / 2) >= d
    (lines 32-34; A); otherwise not. On a real triangulation: at o, a
    segment A of length 8 (a power of two) along x and a segment B at 10
    degrees above it (a cluster with A), and the left side at 90 degrees
    (no cluster). The lengths of the pieces at o are read, not assumed:
    the recovery may already have split a segment."""

    def _refiner(self, b_length):
        from ogr_core.fem import refine as R
        t = math.radians(10.0)
        b_end = (b_length * math.cos(t), b_length * math.sin(t))
        v = [(0.0, 0.0), (8.0, 0.0), (12.0, 0.0), (12.0, 6.0), (0.0, 6.0),
             b_end]
        s = [(0, 1, "A"), (1, 2, "x"), (2, 3, "x"), (3, 4, "x"), (4, 0, "left"),
             (0, 5, "B")]
        pts, pairs, labels, seeds, voids = R._read(
            PSLG(v, s, (((6.0, 4.0), 0, "m"),)))
        r = R._Refiner(pts, pairs, seeds, voids, MIN_RATIO, None, 10 ** 6)
        r.triangulate()
        r.recover()
        r.classify()
        r.analyse_angles()
        return r

    def _key(self, r, k):
        y = r._piece(0, k)
        return (0, y) if 0 < y else (y, 0), math.dist(r.T.p[0], r.T.p[y])

    def test_condition_a_decides_on_d(self):
        r = self._refiner(8.0)
        key, length = self._key(r, 0)                   # A, 8 long
        assert length == 8.0
        assert self._key(r, 5)[1] == 8.0                # B: not shorter
        # r_min = |s| sin(phi_min / 2), phi_min the 10 degrees of the
        # cluster (line 32); the code takes sin(phi/2) = sqrt((1 - cos)/2)
        # from the coordinates, equal to sin 5 deg within rounding
        r_min = 8.0 * r.clusters[(0, 0)][1]
        assert abs(r_min - 8.0 * math.sin(math.radians(5.0))) <= 1e-12 * r_min
        assert r.permitted(key, r_min * 0.999) is True
        assert r.permitted(key, r_min) is True          # ">=" (line 33)
        assert r.permitted(key, r_min * 1.001) is False
        d = r.declined[-1]
        assert d["r_min"] == r_min and d["r_g"] > r_min

    def test_condition_c_a_length_that_is_not_a_power_of_two(self):
        r = self._refiner(6.0)
        key, length = self._key(r, 5)                   # B, 6 long
        assert abs(length - 6.0) < 1e-12
        assert r.permitted(key, 1e9) is True
        r = self._refiner(8.0)
        key, _length = self._key(r, 5)                  # B, 8 long: no
        assert r.permitted(key, 1e9) is False

    def test_condition_e_a_shorter_subsegment_in_the_cluster(self):
        r = self._refiner(3.0)
        key, length = self._key(r, 0)                   # A, 8; B is 3
        assert length == 8.0 and abs(self._key(r, 5)[1] - 3.0) < 1e-12
        assert r.permitted(key, 1e9) is True
        r = self._refiner(8.0)
        key, _length = self._key(r, 0)                  # B is 8: no
        assert r.permitted(key, 1e9) is False

    def test_no_cluster_is_ruppert(self):
        r = self._refiner(8.0)
        key, _length = self._key(r, 4)                  # the left side
        assert r.permitted(key, 1e9) is True

def _PSLG_at(pslg, a):
    """The segments of pslg at vertex a only."""
    return PSLG(pslg.vertices, tuple(s for s in pslg.segments if a in s[:2]),
                pslg.seeds)


class TestTheShells:

    def test_the_piece_next_to_a_shared_vertex_has_a_power_of_two_length(self):
        # p. 29: an encroached subsegment with an endpoint shared with
        # another segment is split on a circle of radius 2**i around it,
        # "so that one of resulting subsegments has a power-of-two length";
        # with both ends shared, the end of the smaller index (our choice)
        cases = [(build(phi), size) for build, phi, size in SMALL]
        cases += [(pslg, 0.7) for _n, pslg, _r in _domains()]
        for pslg, size in cases:
            r = quality_triangulation(
                pslg, size=(lambda x, y, h=size: h) if size else None)
            m = r.mesh
            count = {}
            for u, v, _l in pslg.segments:
                count[u] = count.get(u, 0) + 1
                count[v] = count.get(v, 0) + 1
            checked = 0
            for (u, v, _l), chain in zip(pslg.segments, r.segment_vertices):
                ends = [e for e in (u, v) if count[e] >= 2]
                if len(chain) < 3 or not ends:
                    continue
                apex = min(ends)
                near = chain[1] if apex == u else chain[-2]
                length = math.dist((m.nodes[apex].x, m.nodes[apex].y),
                                   (m.nodes[near].x, m.nodes[near].y))
                k = round(math.log2(length))
                assert abs(length / 2.0 ** k - 1.0) < 1e-9, (u, v, length)
                checked += 1
            assert checked > 0

    def test_the_mesh_depends_on_the_unit_of_length(self):
        # p. 29: "Clearly, the final mesh will depend on the unit of
        # measurement chosen to represent lengths". A factor of two keeps
        # every power of two a power of two, and floating point multiplies
        # by it exactly: the same mesh, twice as large, bit for bit. A
        # factor of a thousand (metres to millimetres) does not.
        def scaled(pslg, f):
            return PSLG(tuple((f * x, f * y) for x, y in pslg.vertices),
                        pslg.segments,
                        tuple(((f * p[0], f * p[1]), g, mat)
                              for p, g, mat in pslg.seeds),
                        tuple((f * x, f * y) for x, y in pslg.voids))
        pslg = _fig20(5.0)
        base = quality_triangulation(pslg, size=lambda x, y: 0.9)
        two = quality_triangulation(scaled(pslg, 2.0),
                                    size=lambda x, y: 1.8)
        assert [(2.0 * n.x, 2.0 * n.y) for n in base.mesh.nodes] == \
            [(n.x, n.y) for n in two.mesh.nodes]
        assert [e.nodes for e in base.mesh.elements] == \
            [e.nodes for e in two.mesh.elements]
        milli = quality_triangulation(scaled(pslg, 1000.0),
                                      size=lambda x, y: 900.0)
        assert sorted((round(1000.0 * n.x, 6), round(1000.0 * n.y, 6))
                      for n in base.mesh.nodes) != \
            sorted((round(n.x, 6), round(n.y, 6)) for n in milli.mesh.nodes)
        assert "unit of length" in base.notes["length_unit"]
        assert base.notes["length_unit"].code == M.REFINE_LENGTH_UNIT


def _lfs(p, pslg):
    """The local feature size at p (p. 11): the radius of the smallest disk
    centred at p that meets two nonincident features (vertices or
    segments) of the PSLG; two features are incident if they meet. By
    brute force over the pairs."""
    pts = pslg.vertices

    def d_seg(q, a, b):
        ax, ay = a
        dx, dy = b[0] - ax, b[1] - ay
        t = max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy)
                         / (dx * dx + dy * dy)))
        return math.dist(q, (ax + t * dx, ay + t * dy))
    feats = [("v", i, math.dist(p, pts[i])) for i in range(len(pts))]
    feats += [("s", (u, v), d_seg(p, pts[u], pts[v]))
              for u, v, _l in pslg.segments]

    def incident(f, g):
        if f[0] == "v" and g[0] == "v":
            return False
        if f[0] == "s" and g[0] == "s":
            return bool(set(f[1]) & set(g[1]))
        vert, seg = (f, g) if f[0] == "v" else (g, f)
        return vert[1] in seg[1]
    best = math.inf
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            if feats[i][0] == "v" and feats[j][0] == "v" and \
                    feats[i][1] == feats[j][1]:
                continue
            if not incident(feats[i], feats[j]):
                best = min(best, max(feats[i][2], feats[j][2]))
    return best


class TestTheorem8:

    def test_the_spacing_of_vertices_is_bounded_by_the_local_feature_size(self):
        # Theorem 8 (p. 23), for B > sqrt 2 and input angles > 60 degrees,
        # both strictly (Lemma 7, p. 22): the nearest neighbour of every
        # vertex v is at least lfs(v) / (D_S + 1) away, with D_S the larger
        # of (1 + sqrt 2) B / (B - sqrt 2) and 1 / (1 - 2 cos alpha_min)
        # (p. 23; the larger one satisfies the three inequalities). The
        # source's example: B = 1 / (2 sin 15 deg), no acute angle, D_S =
        # 9.01. The source proves it for bisection; the shells of section
        # 6.2 split next to a shared vertex as unevenly as one third, which
        # its proof does not cover, so this is a CHECK of the bound on
        # these meshes, not a theorem about them.
        b = 1.0 / (2.0 * math.sin(math.radians(15.0)))
        checked = 0
        for name, pslg, _regions in _domains():
            alpha = min(_input_angles(pslg))
            if alpha <= 60.0:
                # the hypothesis is ANY two incident segments, inside the
                # domain or not: the notch (14.25 degrees outside) is out
                continue
            checked += 1
            ds = max((1.0 + math.sqrt(2.0)) * b / (b - math.sqrt(2.0)),
                     1.0 / (1.0 - 2.0 * math.cos(math.radians(alpha))))
            if name == "rectangle":
                assert abs(ds - 9.01) < 0.005, ds
            m = quality_triangulation(pslg, max_ratio=b).mesh
            xy = [(n.x, n.y) for n in m.nodes]
            for i, p in enumerate(xy):
                nearest = min(math.dist(p, q) for j, q in enumerate(xy)
                              if j != i)
                assert nearest >= _lfs(p, pslg) / (ds + 1.0) * (1 - 1e-12), \
                    (name, i)
        assert checked == 5


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
FINGERPRINT = ("d976463359b62f8296501fe5a74226a9"
               "26c4bfb187810deb44f61e84e0cfd8ed")


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
