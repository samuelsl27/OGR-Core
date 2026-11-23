# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.6 -- the arcs of the quality triangulation (``ogr_core.fem.refine``):
a piece of an arc is split on the arc, not on its chord (OGR FEM2D,
decision D14 of its spec 003, 2026-11-22).

Source: Pav, S. E. and Walkington, N. J., "Delaunay refinement by corner
lopping" (International Meshing Roundtable, about 2005), pages as printed.
The owner chose (2026-11-23) to keep the mesher of v0.2.5 (Shewchuk 2002a)
for straight segments and to split the pieces of an arc on the arc. No
source proves that this ends with arcs: the tests say so where it matters.

What is checked, and against what
---------------------------------
1. **On the arc** (what OGR FEM2D asked for): every vertex of the chain of
   a piece of an arc is at the arc's radius from its centre, to rounding,
   on the arc's side of the input chord (so on the minor arc), in order
   along it, and the chain's ends are the input's. In a hole, a disc (the
   arcs bulge out of the domain), a lining between two circles (an arc
   between two regions), a contact that cuts a tunnel at 36.87 degrees,
   and a small bump on a straight side.
2. **No triangle inverted, and the refinement ends**, OGR FEM2D's T12: a
   hole of radius 1 in 6 and in 8 pieces, h = 0.1 and 0.05 (their test
   folded elements when vertices on the chords were moved onto the arc).
   Exact orientation of every element; the mesh is conforming; the
   element areas add up to the square minus the polygon of the final arc
   vertices (shoelace).
3. **What the end rests on** (Pav and Walkington, Lemma 6, p. 14): no
   subsegment is left encroached, and the triangulation is constrained
   Delaunay, in exact arithmetic.
4. **The split point** (Corollaries 1 and 2, p. 7): with no shared end, a
   piece is split where the arc meets the bisector of its chord, and that
   point keeps from the diametral circle the distances the corollaries
   give, with eta and mu (p. 6). **Lemma 1** (p. 6): every vertex z of an
   arc's chain sees the input piece's ends at an angle of at least
   pi - tau.
5. **The bound of Corollary 3** (p. 13) in the notes: it tends to
   arcsin(1/(2 sqrt 2)) as tau tends to 0 (p. 14), falls as tau grows, and
   is the one written out here from the formulas of pp. 6, 8 and 13. With
   pieces of 10 degrees and B = 1.8, above that bound, the mesh ends and
   no triangle is above B: a CHECK on these meshes, not a theorem (this is
   not exactly their algorithm).
6. **The shells on an arc**: next to the shared end it is split from, the
   chord of a piece has a power-of-two length (Shewchuk 2002a, section 6.2,
   extended here to arcs without a source).
7. **What cannot be meshed says why**, with its code.
8. **Without arcs, nothing changes**: ``arcs`` empty or about labels no
   segment has gives the mesh without it, bit for bit. With arcs the mesh
   is another one (rule 7).
9. **The two rare branches of the insertion off a chord** (the cavity does
   not cross the chord: the chord stays as an ordinary edge, or the
   cavity is empty), each on a triangulation where it happens, checked
   valid after it.
10. **Determinism**: an arc mesh in another process with another hash
    seed, and a fingerprint (SHA-256) written down on Windows: it
    validates NO number; the input is built with sqrt only, so that the
    fingerprint sees the mesher and not a maths library.

Teeth: the mutants and the tests that caught them are in the changelog of
v0.2.6.
"""
from __future__ import annotations

import hashlib
import math
import os
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

from ogr_core.fem import messages as M
from ogr_core.fem import refine as R
from ogr_core.fem.refine import (MIN_RATIO, PSLG, QualityMeshError,
                                 arc_bound, quality_triangulation)

_ROOT = Path(__file__).resolve().parent.parent
S3 = math.sqrt(3.0) / 2.0
S2 = math.sqrt(0.5)


# ----------------------------------------------------------------------
# Domains
# ----------------------------------------------------------------------
def _circle(n, r=1.0):
    """n points of the circle of radius r about the origin, from (r, 0)
    counterclockwise; 6 and 8 with sqrt only, others with cos and sin."""
    if n == 6:
        pts = [(1.0, 0.0), (0.5, S3), (-0.5, S3), (-1.0, 0.0), (-0.5, -S3),
               (0.5, -S3)]
    elif n == 8:
        pts = [(1.0, 0.0), (S2, S2), (0.0, 1.0), (-S2, S2), (-1.0, 0.0),
               (-S2, -S2), (0.0, -1.0), (S2, -S2)]
    else:
        pts = [(math.cos(2 * math.pi * k / n), math.sin(2 * math.pi * k / n))
               for k in range(n)]
    return [(r * x, r * y) for x, y in pts]


def _hole(n, half=2.0):
    """A square of side 2 half with a hole of radius 1 in n arcs."""
    v = [(-half, -half), (half, -half), (half, half), (-half, half)]
    seg = [(0, 1, "s"), (1, 2, "s"), (2, 3, "s"), (3, 0, "s")]
    v += _circle(n)
    for k in range(n):
        seg.append((4 + k, 4 + (k + 1) % n, ("arc", k)))
    return PSLG(v, seg, (((0.0, 0.5 * (1.0 + half)), 0, 1),), ((0.0, 0.0),),
                {("arc", k): (0.0, 0.0) for k in range(n)})


def _disc():
    """A disc: the arcs bulge out of the domain."""
    seg = [(k, (k + 1) % 6, k) for k in range(6)]
    return PSLG(_circle(6), seg, (((0.0, 0.0), 0, 1),), (),
                {k: (0.0, 0.0) for k in range(6)})


def _lining():
    """A void of radius 1, a lining to radius 1.25 (its own region) and
    the ground to a square of side 6: arcs between two regions."""
    v = [(-3.0, -3.0), (3.0, -3.0), (3.0, 3.0), (-3.0, 3.0)]
    seg = [(0, 1, "s"), (1, 2, "s"), (2, 3, "s"), (3, 0, "s")]
    arcs = {}
    for r, tag in ((1.0, "in"), (1.25, "out")):
        base = len(v)
        v += _circle(6, r)
        for k in range(6):
            seg.append((base + k, base + (k + 1) % 6, (tag, k)))
            arcs[(tag, k)] = (0.0, 0.0)
    return PSLG(v, seg, (((0.0, 2.5), 0, 1), ((1.12, 0.0), 1, 2)),
                ((0.0, 0.0),), arcs)


#: The unit circle at Pythagorean points, exact in two decimals.
PYTH = [(1.0, 0.0), (0.8, 0.6), (0.6, 0.8), (0.0, 1.0), (-0.6, 0.8),
        (-0.8, 0.6), (-1.0, 0.0), (-0.8, -0.6), (-0.6, -0.8), (0.0, -1.0),
        (0.6, -0.8), (0.8, -0.6)]


def _oblique():
    """A contact at y = 0.8 that cuts a tunnel of radius 1: it meets the
    circle at 36.87 degrees (a small input angle with an arc)."""
    v = [(-3.0, -3.0), (3.0, -3.0), (3.0, 3.0), (-3.0, 3.0), (-3.0, 0.8),
         (3.0, 0.8)]
    seg = [(0, 1, "s"), (1, 5, "s"), (5, 2, "s"), (2, 3, "s"), (3, 4, "s"),
           (4, 0, "s")]
    base = len(v)
    v += PYTH
    n = len(PYTH)
    for k in range(n):
        seg.append((base + k, base + (k + 1) % n, ("arc", k)))
    seg += [(5, base + 2, "c"), (base + 4, 4, "c")]
    return PSLG(v, seg, (((0.0, 2.5), 0, 1), ((0.0, -2.5), 1, 2)),
                ((0.0, 0.0),), {("arc", k): (0.0, 0.0) for k in range(n)})


def _bump(two_regions, r=0.3):
    """A square of side 4 whose top side has a half-disc bump of radius r
    at x = 2 in three arcs of 60 degrees; with ``two_regions``, a second
    region above it up to y = 8."""
    cx, cy = 2.0, 4.0
    arc = [(cx + r, cy), (cx + 0.5 * r, cy + S3 * r),
           (cx - 0.5 * r, cy + S3 * r), (cx - r, cy)]
    v = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0)] + arc + [(0.0, 4.0)]
    seg = [(0, 1, "s"), (1, 2, "s"), (2, 3, "s"), (3, 4, 0), (4, 5, 1),
           (5, 6, 2), (6, 7, "s"), (7, 0, "s")]
    seeds = [((1.0, 1.0), 0, 1)]
    if two_regions:
        v += [(4.0, 8.0), (0.0, 8.0)]
        seg += [(2, 8, "t"), (8, 9, "t"), (9, 7, "t")]
        seeds.append(((1.0, 7.0), 1, 2))
    return PSLG(v, seg, seeds, (), {0: (cx, cy), 1: (cx, cy), 2: (cx, cy)})


def _domains():
    return [("hole", _hole(6)), ("disc", _disc()), ("lining", _lining()),
            ("oblique", _oblique()), ("bump", _bump(False)),
            ("bump, two regions", _bump(True))]


def _h(h):
    return None if h is None else (lambda x, y: h)


# ----------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------
def _fr(p):
    return (Fraction(p[0]), Fraction(p[1]))


def _orient(a, b, c):
    (ax, ay), (bx, by), (cx, cy) = _fr(a), _fr(b), _fr(c)
    d = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    return (d > 0) - (d < 0)


def _xy(mesh):
    return [(n.x, n.y) for n in mesh.nodes]


def _arc_pieces(pslg):
    """(k, u, v, centre, radius) of every piece of an arc."""
    out = []
    for k, (u, v, label) in enumerate(pslg.segments):
        if label in pslg.arcs:
            c = pslg.arcs[label]
            pu = pslg.vertices[u]
            out.append((k, u, v, c, math.hypot(pu[0] - c[0], pu[1] - c[1])))
    return out


def _inverted(mesh):
    xy = _xy(mesh)
    return sum(_orient(*(xy[i] for i in e.nodes)) <= 0 for e in mesh.elements)


def _area(mesh):
    xy = _xy(mesh)
    total = Fraction(0)
    for e in mesh.elements:
        (ax, ay), (bx, by), (cx, cy) = (_fr(xy[i]) for i in e.nodes)
        total += ((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2
    return total


def _shoelace(pts):
    q = [_fr(p) for p in pts]
    return sum(q[i][0] * q[(i + 1) % len(q)][1]
               - q[(i + 1) % len(q)][0] * q[i][1]
               for i in range(len(q))) / 2


def _conforming(mesh):
    """Every edge in one or two elements, and in two with opposite
    directions."""
    seen = {}
    for e in mesh.elements:
        a, b, c = e.nodes
        for x, y in ((a, b), (b, c), (c, a)):
            if (x, y) in seen:
                return False
            seen[(x, y)] = e.id
    return True


def _encroached(result):
    """Subsegments with a vertex opposite on or inside their diametral
    circle, in exact arithmetic (p. 49 of Shewchuk 2002a)."""
    m = result.mesh
    xy = _xy(m)
    owners = m.edge_map()
    bad = 0
    for chain in result.segment_vertices:
        for a, b in zip(chain, chain[1:]):
            pa, pb = _fr(xy[a]), _fr(xy[b])
            for eid in owners[(min(a, b), max(a, b))]:
                w = next(i for i in m.elements[eid].nodes if i not in (a, b))
                pw = _fr(xy[w])
                bad += ((pa[0] - pw[0]) * (pb[0] - pw[0])
                        + (pa[1] - pw[1]) * (pb[1] - pw[1])) <= 0
    return bad


def _local_delaunay_violations(result):
    m = result.mesh
    pieces = {(min(a, b), max(a, b)) for c in result.segment_vertices
              for a, b in zip(c, c[1:])}
    q = [_fr(p) for p in _xy(m)]
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


def _ratios(mesh):
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


def _mesh_bytes(result):
    m = result.mesh
    text = [f"{n.x.hex()} {n.y.hex()}" for n in m.nodes]
    text += [f"{e.nodes} {e.material_id!r} {e.region_index!r}"
             for e in m.elements]
    text += [repr(c) for c in result.segment_vertices]
    return "\n".join(text).encode("utf-8")


def _power_of_two(x):
    m, _e = math.frexp(x)
    return abs(m - 0.5) <= 1e-9 or abs(m - 1.0) <= 1e-9


# ----------------------------------------------------------------------
class TestOnTheArc:

    def test_every_vertex_of_a_piece_is_on_its_arc_in_order(self):
        for name, pslg in _domains():
            for h in (None, 0.25):
                r = quality_triangulation(pslg, size=_h(h))
                xy = _xy(r.mesh)
                added = 0
                for k, u, v, c, rad in _arc_pieces(pslg):
                    chain = r.segment_vertices[k]
                    assert chain[0] == u and chain[-1] == v, (name, k)
                    pu, pv = pslg.vertices[u], pslg.vertices[v]
                    side = -_orient(pu, pv, c)
                    tol = 1e-14 * (abs(c[0]) + abs(c[1]) + rad)
                    for i in chain[1:-1]:
                        added += 1
                        d = math.hypot(xy[i][0] - c[0], xy[i][1] - c[1])
                        assert abs(d - rad) <= tol, (name, h, k, d - rad)
                        assert _orient(pu, pv, xy[i]) == side, (name, k, i)
                    turn = [_orient(c, xy[a], xy[b])
                            for a, b in zip(chain, chain[1:])]
                    assert len(set(turn)) == 1 and turn[0] != 0, (name, k)
                assert added > 0 or h is None, (name, h)

    def test_the_arcs_are_in_the_notes(self):
        r = quality_triangulation(_hole(8))
        n = r.notes
        assert n["arc_pieces"] == 8
        assert abs(n["arc_turn"] - 45.0) <= 1e-9
        assert n["arc_bound"]["met"] is False
        assert n["arc_unproven"].code == M.REFINE_ARC_UNPROVEN
        plain = quality_triangulation(PSLG(_hole(8).vertices[:4],
                                           _hole(8).segments[:4],
                                           (((0.0, 0.0), 0, 1),)))
        assert plain.notes["arc_pieces"] == 0
        assert plain.notes["arc_unproven"] is None


class TestNoTriangleInverted:
    """OGR FEM2D's T12: moving the vertices of the chords onto the arc
    folded elements once the sagitta passed about 0.7 h."""

    def test_a_hole_in_6_and_8_pieces_fine(self):
        for n in (6, 8):
            pslg = _hole(n)
            for h in (0.1, 0.05):
                r = quality_triangulation(pslg, size=_h(h))
                m = r.mesh
                assert r.notes["unsplittable"] == 0, (n, h)
                assert _inverted(m) == 0, (n, h)
                assert _conforming(m), (n, h)
                ring = []
                for k, *_rest in _arc_pieces(pslg):
                    ring += list(r.segment_vertices[k][:-1])
                xy = _xy(m)
                expected = 16 - _shoelace([xy[i] for i in ring])
                assert _area(m) == expected, (n, h)

    def test_every_domain_is_conforming_and_covered(self):
        for name, pslg in _domains():
            r = quality_triangulation(pslg, size=_h(0.3))
            assert _inverted(r.mesh) == 0, name
            assert _conforming(r.mesh), name
            assert r.notes["unsplittable"] == 0, name


class TestWhatTheEndRestsOn:

    def test_no_subsegment_encroached_and_constrained_delaunay(self):
        # Pav and Walkington, Lemma 6 (p. 14): at the end every subcurve
        # has an empty diametral circle and is an edge
        for name, pslg in _domains():
            for h in (None, 0.3):
                r = quality_triangulation(pslg, size=_h(h))
                assert _encroached(r) == 0, (name, h)
                assert _local_delaunay_violations(r) == 0, (name, h)


class TestTheSplitPoint:

    def test_corollaries_1_and_2(self):
        # p. 7: the point where the curve meets the bisector of the chord
        # keeps |p - Cd(c)| >= r (1 - tan(tau/2)) and, for z in the
        # diametral circle, |p - Cd(c)| >= |p - z| / eta
        for n in (6, 8, 12, 36):
            pslg = _hole(n, half=3.0)
            pts, pairs, labels, seeds, voids = R._read(pslg)
            arcs = R._read_arcs(pslg, pts, pairs, labels, seeds, voids)
            ref = R._Refiner(pts, pairs, seeds, voids, MIN_RATIO, None,
                             10 ** 6, arcs)
            for k, u, v, c, rad in _arc_pieces(pslg):
                pu, pv = pts[u], pts[v]
                p = ref._arc_point(k, (u, v), None)
                assert abs(math.dist(p, pu) - math.dist(p, pv)) <= \
                    1e-14 * rad, (n, k)
                assert abs(math.dist(p, c) - rad) <= 1e-14 * rad, (n, k)
                r = 0.5 * math.dist(pu, pv)
                tau = 2.0 * math.asin(r / rad)
                m = ((pu[0] + pv[0]) / 2, (pu[1] + pv[1]) / 2)
                gap = r - math.dist(p, m)       # p is inside Cd(c)
                h = math.tan(tau / 2)
                eta = (1 + h) / (1 - h)
                assert gap >= r * (1 - h) - 1e-12, (n, k)
                assert gap >= (math.dist(p, m) + r) / eta - 1e-12, (n, k)

    def test_lemma_1_the_lens(self):
        # p. 6: a point z of a curve of total variation tau sees its ends
        # at an angle of at least pi - tau
        for name, pslg in _domains():
            r = quality_triangulation(pslg, size=_h(0.2))
            xy = _xy(r.mesh)
            for k, u, v, c, rad in _arc_pieces(pslg):
                pu, pv = pslg.vertices[u], pslg.vertices[v]
                tau = 2.0 * math.asin(min(1.0, math.dist(pu, pv) / (2 * rad)))
                for i in r.segment_vertices[k][1:-1]:
                    z = xy[i]
                    x = (pu[0] - z[0], pu[1] - z[1])
                    y = (pv[0] - z[0], pv[1] - z[1])
                    cosang = (x[0] * y[0] + x[1] * y[1]) / (
                        math.hypot(*x) * math.hypot(*y))
                    assert cosang <= math.cos(math.pi - tau) + 1e-9, \
                        (name, k, i)


class TestTheBoundInTheNotes:

    def test_corollary_3_written_out(self):
        # pp. 6, 8, 13, written out again here from the paper
        def kappa(tau):
            t = math.tan(tau / 2)
            eta, mu = (1 + t) / (1 - t), 1 / (1 - t)
            zeta = math.sqrt(2) * math.sin(tau / 2) / (
                math.sqrt(1 + math.sin(tau)) - 1)
            return min(math.asin(1 / (2 * mu * math.sqrt(2))),
                       math.asin(1 / (2 * zeta * eta)))
        for deg in (60, 45, 30, 10, 2):
            k, ratio = arc_bound(math.radians(deg))
            assert abs(k - kappa(math.radians(deg))) <= 1e-12, deg
            assert abs(ratio - 1 / (2 * math.sin(k))) <= 1e-12, deg
        # p. 14: as tau tends to 0, the bound of the straight case
        k0, b0 = arc_bound(1e-9)
        assert abs(k0 - math.asin(1 / (2 * math.sqrt(2)))) <= 1e-6
        assert abs(b0 - math.sqrt(2)) <= 1e-6
        # and the bound falls as tau grows
        last = math.inf
        for deg in range(1, 61):
            k, _ = arc_bound(math.radians(deg))
            assert k < last, deg
            last = k

    def test_with_the_bound_met_no_triangle_above_b(self):
        # a CHECK on these meshes: pieces of 10 degrees, B = 1.8 > 1.76
        pslg = _hole(36)
        for h in (None, 0.15):
            r = quality_triangulation(pslg, max_ratio=1.8, size=_h(h))
            assert r.notes["arc_bound"]["met"] is True
            assert r.notes["above_ratio"] == [], h
            assert max(_ratios(r.mesh)) <= 1.8 * (1 + 1e-9), h


class TestTheAnglesAtAnArc:

    def test_the_input_angle_is_the_tangents(self):
        # where the contact y = 0.8 meets the circle at (0.6, 0.8), the
        # curves make the angle between the horizontal and the tangent
        # (-0.8, 0.6): atan(0.6 / 0.8) = 36.87 degrees, not the angle of a
        # chord
        r = quality_triangulation(_oblique())
        want = math.degrees(math.atan2(0.6, 0.8))
        assert abs(r.notes["min_input_angle"] - want) <= 1e-9,             r.notes["min_input_angle"]
        assert abs(r.notes["theorem_12_bound"]
                   - 1 / (math.sqrt(2) * math.sin(math.radians(want) / 2)))             <= 1e-9
        assert _inverted(r.mesh) == 0 and _encroached(r) == 0


class TestTheShellsOnArcs:

    def test_the_chord_next_to_the_shared_end_is_a_power_of_two(self):
        for name, pslg in (("hole", _hole(6)), ("lining", _lining())):
            r = quality_triangulation(pslg, size=_h(0.15))
            xy = _xy(r.mesh)
            checked = 0
            for k, u, v, c, rad in _arc_pieces(pslg):
                chain = r.segment_vertices[k]
                if len(chain) < 3:
                    continue
                apex, nxt = (chain[0], chain[1]) if u < v else \
                    (chain[-1], chain[-2])
                assert _power_of_two(math.dist(xy[apex], xy[nxt])), (name, k)
                checked += 1
            assert checked > 0, name


class TestWhatCannotBeMeshed:

    def _expect(self, pslg, code):
        try:
            quality_triangulation(pslg)
        except QualityMeshError as exc:
            assert exc.code == code, (exc.code, code)
        else:
            raise AssertionError(f"no {code}")

    def _square_with(self, extra_v, extra_s, arcs, seeds=None, voids=()):
        v = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)] + extra_v
        s = [(0, 1, "s"), (1, 2, "s"), (2, 3, "s"), (3, 0, "s")] + extra_s
        return PSLG(v, s, seeds or (((0.5, 0.5), 0, 1),), voids, arcs)

    def test_each_bad_arc_has_its_code(self):
        a, b = (1.0, 2.0), (3.0, 2.0)
        top = (2.0, 2.0 + math.sqrt(3.0))       # 60 degrees above ab
        # the ends at different distances from the centre
        self._expect(self._square_with([a, b], [(4, 5, "a")],
                                       {"a": (2.5, 1.0)}), M.REFINE_ARC_RADII)
        # 90 degrees
        self._expect(self._square_with([a, b], [(4, 5, "a")],
                                       {"a": (2.0, 3.0)}), M.REFINE_ARC_TURN)
        # a centre that is not a point
        self._expect(self._square_with([a, b], [(4, 5, "a")],
                                       {"a": (float("nan"), 0.0)}),
                     M.REFINE_BAD_ARC)
        # 60 degrees around `top`, bulging down to y = 2 - 0.268
        arc = {"a": top}
        self._expect(self._square_with([a, b, (2.0, 1.9)], [(4, 5, "a")],
                                       arc), M.REFINE_VERTEX_IN_ARC)
        self._expect(self._square_with([a, b], [(4, 5, "a")], arc,
                                       seeds=(((2.0, 1.9), 0, 1),)),
                     M.REFINE_SEED_IN_ARC)
        self._expect(self._square_with([a, b], [(4, 5, "a")], arc,
                                       voids=((2.0, 1.9),)),
                     M.REFINE_VOID_IN_ARC)
        # a segment that crosses the arc twice, under the chord
        self._expect(self._square_with([a, b, (0.5, 1.85), (3.5, 1.85)],
                                       [(4, 5, "a"), (6, 7, "x")], arc),
                     M.REFINE_SEGMENT_IN_ARC)
        # two arcs that cross: the same chord shape, one 0.1 lower and
        # bulging up into the first
        c, d = (1.0, 1.9), (3.0, 1.9)
        self._expect(self._square_with(
            [a, b, c, d], [(4, 5, "a"), (6, 7, "b")],
            {"a": top, "b": (2.0, 1.9 - math.sqrt(3.0))}),
            M.REFINE_SEGMENT_IN_ARC)
        # two arcs that cross with neither chord in the other's arc: two
        # vertical chords 0.4 apart, bulging 0.268 towards each other
        e, f, g, k = (1.8, 1.0), (1.8, 3.0), (2.2, 1.0), (2.2, 3.0)
        self._expect(self._square_with(
            [e, f, g, k], [(4, 5, "a"), (6, 7, "b")],
            {"a": (1.8 - math.sqrt(3.0), 2.0),
             "b": (2.2 + math.sqrt(3.0), 2.0)}), M.REFINE_SEGMENT_IN_ARC)
        # 0.6 apart they do not meet
        e, f, g, k = (1.7, 1.0), (1.7, 3.0), (2.3, 1.0), (2.3, 3.0)
        r = quality_triangulation(self._square_with(
            [e, f, g, k], [(4, 5, "a"), (6, 7, "b")],
            {"a": (1.7 - math.sqrt(3.0), 2.0),
             "b": (2.3 + math.sqrt(3.0), 2.0)}))
        assert r.notes["arc_pieces"] == 2

    def test_a_good_arc_is_accepted(self):
        a, b = (1.0, 2.0), (3.0, 2.0)
        top = (2.0, 2.0 + math.sqrt(3.0))
        r = quality_triangulation(self._square_with(
            [a, b, (0.5, 1.6), (3.5, 1.6)], [(4, 5, "a"), (6, 7, "x")],
            {"a": top}))
        assert r.notes["arc_pieces"] == 1


class TestWithoutArcs:

    def test_no_arcs_is_the_mesh_of_v025(self):
        base = _hole(6)
        plain = PSLG(base.vertices, base.segments, base.seeds, base.voids)
        unused = PSLG(base.vertices, base.segments, base.seeds, base.voids,
                      {"nobody": (0.0, 0.0)})
        empty = PSLG(base.vertices, base.segments, base.seeds, base.voids, {})

        class Old:                              # no attribute ``arcs``
            vertices, segments = base.vertices, base.segments
            seeds, voids = base.seeds, base.voids
        ref = _mesh_bytes(quality_triangulation(plain, size=_h(0.3)))
        for other in (unused, empty, Old()):
            assert _mesh_bytes(quality_triangulation(other, size=_h(0.3))) \
                == ref

    def test_the_arcs_move_the_mesh(self):
        # rule 7: with arcs, the added vertices are on the circle; without
        # them, on the chords, inside it
        base = _hole(6)
        plain = PSLG(base.vertices, base.segments, base.seeds, base.voids)
        with_arcs = quality_triangulation(base, size=_h(0.3))
        without = quality_triangulation(plain, size=_h(0.3))
        assert _mesh_bytes(with_arcs) != _mesh_bytes(without)
        xy = _xy(without.mesh)
        inner = [math.hypot(*xy[i]) for k, *_r in _arc_pieces(base)
                 for i in without.segment_vertices[k][1:-1]]
        assert inner and max(inner) < 1.0 - 1e-3


class TestTheRareBranches:
    """The insertion of a vertex off a chord, where the triangle across the
    chord does not hold it in its circumcircle: on the bump of radius 0.3,
    the chord of its third piece, (5, 6), has a triangle below with a far
    apex (its angle there is below tau/2 = 30 degrees). Split directly."""

    def _split(self, two_regions):
        pslg = _bump(two_regions)
        pts, pairs, labels, seeds, voids = R._read(pslg)
        arcs = R._read_arcs(pslg, pts, pairs, labels, seeds, voids)
        ref = R._Refiner(pts, pairs, seeds, voids, MIN_RATIO, None, 10 ** 6,
                         arcs)
        ref.triangulate()
        ref.recover()
        ref.classify()
        ref.analyse_angles()
        T = ref.T
        key = (5, 6)
        tris = T.edge_triangles(*key)
        q = ref.split_point(key)
        side = R._orient(T.p[5], T.p[6], q)
        below = [t for t in tris if R._orient(
            T.p[5], T.p[6], T.p[next(i for i in T.tv[t] if i not in key)])
            != side]
        assert len(below) == 1
        assert R._incircle(*(T.p[i] for i in T.tv[below[0]]), q) < 0
        assert len(tris) == (2 if two_regions else 1)
        ref.r = {i: 1.0 for i in range(len(T.p))}
        ref._queue_sub(key)
        ref._queue_sub = lambda k: None         # this split, and no other
        ref.split_encroached()
        return pslg, ref

    def _valid(self, ref):
        T = ref.T
        live = [t for t in range(len(T.tv)) if T.alive[t]]
        for t in live:
            a, b, c = (T.p[i] for i in T.tv[t])
            assert R._orient(a, b, c) > 0, t
            for i in range(3):
                n = T.tn[t][i]
                if n >= 0:
                    assert T.alive[n]
                    x, y = T.edge(t, i)
                    assert T.tn[n][[j for j in range(3)
                                    if set(T.edge(n, j)) == {x, y}][0]] == t
        for (a, b) in T.sub:
            assert T.has_edge(a, b), (a, b)
        # constrained Delaunay: the local test at every edge that is not a
        # subsegment, in exact arithmetic (here, not the module's predicate)
        for t in live:
            for i in range(3):
                n = T.tn[t][i]
                x, y = T.edge(t, i)
                if n < 0 or (min(x, y), max(x, y)) in T.sub:
                    continue
                w = next(j for j in T.tv[n] if j not in (x, y))
                (ax, ay), (bx, by), (cx, cy) = (_fr(T.p[j]) for j in T.tv[t])
                dx, dy = _fr(T.p[w])
                adx, ady, bdx, bdy, cdx, cdy = (ax - dx, ay - dy, bx - dx,
                                                by - dy, cx - dx, cy - dy)
                det = ((adx * adx + ady * ady) * (bdx * cdy - cdx * bdy)
                       + (bdx * bdx + bdy * bdy) * (cdx * ady - adx * cdy)
                       + (cdx * cdx + cdy * cdy) * (adx * bdy - bdx * ady))
                assert det <= 0, (t, n)
        return live

    def test_the_chord_stays_on_the_other_side(self):
        pslg, ref = self._split(True)
        live = self._valid(ref)
        T = ref.T
        q = len(T.p) - 1
        assert (5, q) in T.sub and (6, q) in T.sub and (5, 6) not in T.sub
        assert T.has_edge(5, 6)                     # an ordinary edge now
        lower = Fraction(0)
        for t in live:
            if T.region[t] == 0:
                (ax, ay), (bx, by), (cx, cy) = (_fr(T.p[i]) for i in T.tv[t])
                lower += ((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2
        ring = [T.p[i] for i in (0, 1, 2, 3, 4, 5, q, 6, 7)]
        assert lower == _shoelace(ring)

    def test_the_cavity_is_empty(self):
        pslg, ref = self._split(False)
        live = self._valid(ref)
        T = ref.T
        q = len(T.p) - 1
        assert (5, q) in T.sub and (6, q) in T.sub
        total = Fraction(0)
        for t in live:
            (ax, ay), (bx, by), (cx, cy) = (_fr(T.p[i]) for i in T.tv[t])
            total += ((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2
        ring = [T.p[i] for i in (0, 1, 2, 3, 4, 5, q, 6, 7)]
        assert total == _shoelace(ring)


_PROBE = """
import hashlib, sys
sys.path.insert(0, {tests!r})
import test_quality_triangulation_arcs_v026 as T
print(hashlib.sha256(T._mesh_bytes(T._probe_mesh())).hexdigest())
"""


def _probe_mesh():
    return quality_triangulation(_lining(), size=lambda x, y: 0.2)


#: The SHA-256 of ``_mesh_bytes(_probe_mesh())``, written down on Windows
#: (Python 3.14) on 2026-11-23. NOT a validation (see point 10 above).
FINGERPRINT = ("376fa7e13c775992c5a72aa064f8fee0"
               "12a7ea6518f6f89e78cabd06729aabac")


class TestDeterminism:

    def test_another_process_and_hash_seed_give_the_same_mesh(self):
        here = hashlib.sha256(_mesh_bytes(_probe_mesh())).hexdigest()
        env = dict(os.environ, PYTHONHASHSEED="54321",
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
