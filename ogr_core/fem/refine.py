# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
Quality triangulation of a planar straight line graph by Delaunay
refinement (v0.2.5; asked for by OGR FEM2D, decision D2 of its spec 003,
because the seepage of OGR Slip2D needs the same thing).

Sources (page numbers are those printed on the preprints):

* Shewchuk, J. R. (2002a). "Delaunay refinement algorithms for triangular
  mesh generation". Computational Geometry 22, 21-74 (preprint of
  21-5-2001). Section 3.1, pp. 7-11; Lemma 1, p. 9; insertion radius and
  parent, pp. 13-14; Theorem 4, p. 16; section 6.2 (concentric shells),
  p. 29; section 6.3 (the Terminator), pp. 33-36, Theorems 11 and 12;
  Appendix A, figures 38 and 39, pp. 47-51.
* Ruppert, J. (1995). "A Delaunay refinement algorithm for quality
  2-dimensional mesh generation". J. Algorithms 18(3), 548-585: starting
  from an unconstrained Delaunay triangulation and recovering the missing
  segments by splitting them at their midpoints.
* Pav, S. E. and Walkington, N. J. "Delaunay refinement by corner
  lopping" (International Meshing Roundtable, about 2005): curved input
  (v0.2.6). Pieces of at most pi/3 of turn, p. 4; encroachment by the
  diametral circle of the chord and the split point on the curve, section
  3, p. 6; Lemma 1 and Corollaries 1 and 2, pp. 6-7; Lemma 2, p. 8;
  Corollary 3, p. 13.

``generate_mesh`` (``generator.py``) is NOT this: it stays as it was, so
that OGR Slip2D meshes as before, bit for bit.

What it does
------------
1. **Delaunay triangulation of the input vertices**, in their order, by
   Bowyer-Watson insertion inside a large enclosing triangle.
2. **Segment recovery** (Ruppert): a segment that is not an edge of the
   triangulation is split (where step 4 would split it) until all its
   pieces are edges.
   Every recovered piece (a *subsegment*) is constrained from then on: no
   later insertion removes it (Shewchuk p. 7, "simply by never flipping or
   removing any subsegment"). When all are in, the triangulation is the
   constrained Delaunay triangulation from which Shewchuk's version starts.
3. **The domain**: triangles reachable from the enclosing triangle without
   crossing a subsegment are outside; those reachable from a void point
   are in a hole; those reachable from a seed belong to its region and
   material. Exterior and holes are removed BEFORE refining (figure 38,
   line 2; p. 48: so that small exterior features do not bring forth
   unnecessarily small triangles), so the encroachment of a subsegment from
   its exterior side never counts.
4. **Refinement** (section 3.1, figures 38 and 39): encroached
   subsegments are split first: at their midpoint, or, next to an input
   vertex shared by two segments, on the circle of radius a power of two
   around it that splits best (section 6.2). A subsegment
   is encroached when a vertex other than its endpoints lies ON or inside
   its diametral circle and is visible from it (p. 7); in a constrained
   Delaunay triangulation only the one or two vertices opposite it need to
   be looked at, and the test is (x - w).(y - w) <= 0 (p. 49). Then the
   bad triangles: skinny (circumradius-to-shortest-edge ratio GREATER than
   B, p. 7) or larger than the size bound (p. 11), the worst first, are
   split at their circumcentre. The circumcentre is first located by
   walking from the triangle's centroid towards it; a subsegment on the way
   is encroached by it (p. 50). Otherwise the subsegments it would encroach
   are the subsegments of the boundary of its Bowyer-Watson cavity whose
   diametral circle holds it (the edges that would face it once inserted,
   p. 50), found without touching the mesh. If there are any, the
   circumcentre is not inserted, all of them are split (p. 9) and the
   triangle goes back to the queue (line 24).
5. **The Terminator** (section 6.3) decides those last splits when the
   subsegment ends at a vertex where segments meet at 60 degrees or less
   (its *cluster*): it splits only if one of the conditions A (the
   shortest edge the split would make is no shorter than the insertion
   radius of the vertex that caused it), B (the triangle is too large),
   C (the subsegment's length is not a power of two), D (it has a cluster
   at each end) or E (a subsegment of its cluster is shorter) holds; a
   triangle it declines to split is never tried again. F is left out (the
   source: optional, possibly slow, not implemented by its author). It
   always ends (Theorem 11), and every triangle then has circumradius /
   shortest edge at most 1 / (sqrt 2 sin(phi / 2)), phi the smallest
   input angle (Theorem 12); with no input angle of 60 degrees or less it
   never declines, and every triangle is within B. The notes say phi, that
   bound, and which triangles are left above B, and where.

Arcs (v0.2.6)
-------------
A segment whose label is in ``PSLG.arcs`` is the minor arc, of at most 60
degrees, between its ends around the centre given there (asked for by OGR
FEM2D, decision D14 of its spec 003). The owner chose (2026-11-23) to keep
everything above for straight segments and to split the pieces of an arc
on the arc:

* **Encroachment** is by the diametral circle of the chord (Pav and
  Walkington, p. 6); the triangles stay straight, and the boundary of the
  mesh is the chords of the final pieces.
* **The split point** is on the arc: where it meets the bisector of the
  chord (Corollaries 1 and 2, p. 7), or, next to a shared input vertex, at
  the distance of the shell, measured from that vertex as on a segment.
* **The input angles** at a vertex where an arc ends are measured on its
  tangent there: the clusters of the Terminator, phi and the bound of
  Theorem 12.
* **The insertion** of a vertex off its chord (``insert_off``): the region
  between a chord and its arc holds no vertex, so the cavity always takes
  the triangle on the vertex's side; the chord is kept as an ordinary edge
  where the triangle across it does not hold the vertex in its
  circumcircle; every new triangle is checked counterclockwise in exact
  arithmetic.
* **The input** is checked with the arc, not with the chord: no vertex,
  seed or void between a chord and its arc, and no other segment or arc
  entering that region.

**What is not proven.** Pav and Walkington prove that THEIR algorithm ends
with curves for B > 1/(2 sin kappa), kappa their Corollary 3 (p. 13):
B > 7.2 with pieces of 60 degrees, B > 1.76 with pieces of 10, and
sqrt 2 only as the turn tends to 0 (p. 14); the notes give that bound for
the input (``arc_bound``). This mesher is not exactly their algorithm: the
shells and the Terminator on arcs come from no source (the shells rest on
powers of two, which "do not generalize naturally" to curves, p. 2). No
source proves that it ends with arcs, and the notes say so
(``arc_unproven``). If it does not end, it stops with ``refine.too_fine``
or ``refine.too_many_triangles``.

Choices the source leaves open, fixed here
------------------------------------------
* **The order** of the queues: the source calls it arbitrary, and it
  changes the mesh (pp. 50-51: splitting the worst triangle first gave 290
  triangles where a first-in first-out queue gave 450). Bad triangles come
  out worst first, ties in the order they were queued; encroached
  subsegments first in, first out.
* **The size bound** is a length: no edge of a triangle longer than
  ``size(x, y)``, evaluated at the three vertices and the centroid, the
  least of the four. The source allows a bound on areas or edge lengths,
  "a function of each triangle's location", as long as it stays above a
  positive constant (p. 11). ``math.inf`` is no bound.
* **B >= sqrt(2)** is required: Theorem 4 guarantees the end only from
  there (p. 16).
* **Two shared endpoints**: the shells of the endpoint of the smaller
  index (the source: "choose one endpoint's shells arbitrarily"). The
  shells are powers of two of the unit of length, so the mesh depends on
  that unit (p. 29), and the notes say so.
* **The insertion radius** of the vertices there before refinement (input
  vertices and those of the recovery) is the shortest edge they have when
  it starts; the source's definition (p. 13) assumes it starts from the
  constrained Delaunay triangulation of the input alone. Line 19 of
  figure 38 takes r_g, not its alternative (the shortest edge of t).
* **"Within some tolerance"** (figure 38, lines 27 and 30): 1e-9,
  relative.
* **No edge shorter than 2**-40 of the extent of the input** is made; a
  refinement that would need one stops with an error. One that ends never
  comes near it; one that cannot end (Ruppert's algorithm alone on a small
  angle, p. 27) would otherwise shrink its edges to the smallest numbers
  floating point has.

Determinism
-----------
The same input gives the same mesh, bit for bit, on every platform. The
geometric predicates (orientation, in-circle, in-diametral-circle) are
exact: a floating-point filter whose threshold is several orders above the
rounding of the expression, and exact rational arithmetic
(``fractions.Fraction``) below it. The new points and every length a
decision reads use only + - * / and sqrt, which IEEE 754 rounds the same
everywhere, and powers of two by ``frexp`` and ``ldexp``, which are exact:
no sin, cos, atan2 or ``math.dist``, whose results each platform's library
rounds its own way (they appear only in the notes). No queue or loop
depends on the order of a ``set``.

Author: Samuel Sáez López (UPCT)
"""
from __future__ import annotations

import bisect
import functools
import heapq
import math
from collections import deque
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Callable, Optional, Sequence

from . import messages as M
from .mesh import Element, Mesh, Node

#: The bound below which Delaunay refinement is not guaranteed to end
#: (Shewchuk 2002a, Theorem 4, p. 16).
MIN_RATIO = math.sqrt(2.0)

#: The floating-point filter of the predicates: a result whose magnitude is
#: above this fraction of the sum of the magnitudes of its terms has the
#: sign its floating-point value says. The rounding of each expression is a
#: few units of 2**-53 (1.1e-16) of that sum, four orders below; under the
#: threshold the predicate is evaluated again in exact rational arithmetic.
_FILTER = 1e-12

#: How close to a power of two a length must be to count as one (figure 38,
#: line 27: "within some tolerance"), relative; the same for "shorter"
#: (line 30). A split on a shell leaves a length of 2**i up to the rounding
#: of a + t (b - a).
_TOLERANCE = 1e-9

#: The labels of a triangle before the regions are known.
_UNKNOWN, _OUTSIDE, _VOID = -1, -2, -3


class QualityMeshError(ValueError):
    """The input cannot be meshed: the message says why, with its code
    (``ogr_core.fem.messages.REFINE_MESSAGES``)."""

    def __init__(self, code: str, **args):
        self.note = M.refine_note(code, **args)
        super().__init__(str(self.note))

    @property
    def code(self) -> str:
        return self.note.code


@dataclass(frozen=True)
class PSLG:
    """A planar straight line graph with what to mesh in it.

    * ``vertices``: points (x, y). Input vertex ``i`` is node ``i`` of the
      mesh. A vertex that is no segment's endpoint is a point the mesh must
      have.
    * ``segments``: (u, v, label), joining vertices u and v; the label is
      the caller's and comes back with the segment's vertices.
    * ``seeds``: ((x, y), region, material), a point strictly inside each
      region; the elements of that region carry its ``region`` as
      ``region_index`` and its ``material`` as ``material_id``.
    * ``voids``: points inside the holes, which are not meshed.
    * ``arcs`` (v0.2.6): label -> centre (x, y). A segment whose label is
      here is the minor arc between its u and v around that centre, which
      may turn 60 degrees at most (Pav and Walkington, p. 4): it is split
      on the arc, and every vertex of its chain lies on the arc.

    Any object with these attributes will do (OGR FEM2D passes its own);
    without ``arcs``, every segment is straight.
    """
    vertices: Sequence = ()
    segments: Sequence = ()
    seeds: Sequence = ()
    voids: Sequence = ()
    arcs: Any = field(default_factory=dict)


@dataclass
class QualityTriangulation:
    """The result: the mesh, the vertices of each input segment in order
    from its ``u`` to its ``v`` (node ids), the label of each, and the
    notes (also in ``mesh.notes["quality_triangulation"]``)."""
    mesh: Mesh
    segment_vertices: list = field(default_factory=list)
    segment_labels: list = field(default_factory=list)
    notes: dict = field(default_factory=dict)


# ======================================================================
# Exact predicates
# ======================================================================
def _sign(value) -> int:
    return (value > 0) - (value < 0)


def _orient(a, b, c) -> int:
    """+1 if a, b, c turn counterclockwise, -1 clockwise, 0 collinear."""
    left = (b[0] - a[0]) * (c[1] - a[1])
    right = (b[1] - a[1]) * (c[0] - a[0])
    det = left - right
    if abs(det) > _FILTER * (abs(left) + abs(right)):
        return 1 if det > 0.0 else -1
    ax, ay, bx, by, cx, cy = (Fraction(v) for v in (*a, *b, *c))
    return _sign((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))


def _incircle(a, b, c, d) -> int:
    """+1 if d is inside the circle through the counterclockwise a, b, c,
    0 on it, -1 outside."""
    adx, ady = a[0] - d[0], a[1] - d[1]
    bdx, bdy = b[0] - d[0], b[1] - d[1]
    cdx, cdy = c[0] - d[0], c[1] - d[1]
    al, bl, cl = adx * adx + ady * ady, bdx * bdx + bdy * bdy, \
        cdx * cdx + cdy * cdy
    t1, t2 = bdx * cdy, cdx * bdy
    t3, t4 = cdx * ady, adx * cdy
    t5, t6 = adx * bdy, bdx * ady
    det = al * (t1 - t2) + bl * (t3 - t4) + cl * (t5 - t6)
    perm = (al * (abs(t1) + abs(t2)) + bl * (abs(t3) + abs(t4))
            + cl * (abs(t5) + abs(t6)))
    if abs(det) > _FILTER * perm:
        return 1 if det > 0.0 else -1
    ax, ay, bx, by, cx, cy, dx, dy = (Fraction(v) for v in (*a, *b, *c, *d))
    adx, ady, bdx, bdy, cdx, cdy = ax - dx, ay - dy, bx - dx, by - dy, \
        cx - dx, cy - dy
    return _sign((adx * adx + ady * ady) * (bdx * cdy - cdx * bdy)
                 + (bdx * bdx + bdy * bdy) * (cdx * ady - adx * cdy)
                 + (cdx * cdx + cdy * cdy) * (adx * bdy - bdx * ady))


def _in_diametral_circle(a, b, w) -> bool:
    """w on or inside the circle whose diameter is ab: the angle at w is
    90 degrees or more, (a - w).(b - w) <= 0 (Shewchuk 2002a, p. 49)."""
    p = (a[0] - w[0]) * (b[0] - w[0])
    q = (a[1] - w[1]) * (b[1] - w[1])
    s = p + q
    if abs(s) > _FILTER * (abs(p) + abs(q)):
        return s < 0.0
    ax, ay, bx, by, wx, wy = (Fraction(v) for v in (*a, *b, *w))
    return (ax - wx) * (bx - wx) + (ay - wy) * (by - wy) <= 0


def _circumcentre(a, b, c):
    """The circumcentre of a, b, c, computed from a (only + - * /)."""
    bx, by = b[0] - a[0], b[1] - a[1]
    cx, cy = c[0] - a[0], c[1] - a[1]
    b2, c2 = bx * bx + by * by, cx * cx + cy * cy
    d = 2.0 * (bx * cy - by * cx)
    return (a[0] + (cy * b2 - by * c2) / d, a[1] + (bx * c2 - cx * b2) / d)


def _power_of_two(length: float) -> bool:
    m, _e = math.frexp(length)              # length = m 2**e, 0.5 <= m < 1
    return abs(m - 0.5) <= 0.5 * _TOLERANCE or abs(m - 1.0) <= _TOLERANCE


def _dist(p, q) -> float:
    """The distance from p to q as sqrt(dx**2 + dy**2): operations that
    IEEE 754 rounds the same on every platform. Not ``math.dist``, whose C
    implementation need not."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    return math.sqrt(dx * dx + dy * dy)


def _key(a: int, b: int) -> tuple:
    return (a, b) if a < b else (b, a)


# ======================================================================
# The triangulation
# ======================================================================
class _Triangulation:
    """Triangles as vertex triples, counterclockwise, with the neighbour
    across the edge opposite each vertex (-1: none). Slots are never
    reused: a triangle that dies stays dead, so a queued slot can be told
    to be gone."""

    def __init__(self, points: list):
        self.p = points
        self.tv: list = []          # [a, b, c]
        self.tn: list = []          # [n0, n1, n2], n_i across (v[i+1], v[i+2])
        self.alive: list = []
        self.region: list = []      # index of the seed, or a _label
        self.vt = [-1] * len(points)
        self.sub: dict = {}         # (min, max) -> input segment index
        self.n_alive = 0

    # -- basic ----------------------------------------------------------
    def add_point(self, xy) -> int:
        self.p.append(xy)
        self.vt.append(-1)
        return len(self.p) - 1

    def _make(self, a, b, c, region) -> int:
        t = len(self.tv)
        self.tv.append([a, b, c])
        self.tn.append([-1, -1, -1])
        self.alive.append(True)
        self.region.append(region)
        self.vt[a] = self.vt[b] = self.vt[c] = t
        self.n_alive += 1
        return t

    def edge(self, t, i) -> tuple:
        v = self.tv[t]
        return v[(i + 1) % 3], v[(i + 2) % 3]

    def is_sub(self, a, b) -> bool:
        return _key(a, b) in self.sub

    def centroid(self, t):
        a, b, c = (self.p[i] for i in self.tv[t])
        return ((a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0)

    def around(self, a) -> list:
        """The live triangles that have vertex a, in a fixed order."""
        start = self.vt[a]
        if start < 0 or not self.alive[start] or a not in self.tv[start]:
            start = next((t for t in range(len(self.tv)) if self.alive[t]
                          and a in self.tv[t]), -1)
            if start < 0:
                return []
        out, seen, todo = [], {start}, deque([start])
        while todo:
            t = todo.popleft()
            out.append(t)
            v = self.tv[t]
            i = v.index(a)
            for j in ((i + 1) % 3, (i + 2) % 3):    # the edges through a
                n = self.tn[t][j]
                if n >= 0 and n not in seen and self.alive[n]:
                    seen.add(n)
                    todo.append(n)
        return out

    def edge_triangles(self, a, b) -> list:
        return [t for t in self.around(a) if b in self.tv[t]]

    # -- locating ---------------------------------------------------------
    def locate(self, q, start) -> int:
        """A live triangle that holds q (inside or on its boundary), by a
        visibility walk from ``start``; -1 if q is outside them all."""
        t = start
        limit = 4 * len(self.tv) + 16
        for step in range(limit):
            v = self.tv[t]
            moved = False
            for j in range(3):
                i = (step + j) % 3
                a, b = v[(i + 1) % 3], v[(i + 2) % 3]
                if _orient(self.p[a], self.p[b], q) < 0:
                    n = self.tn[t][i]
                    if n < 0:
                        return -1
                    t, moved = n, True
                    break
            if not moved:
                return t
        for t in range(len(self.tv)):                # a walk that cycled
            if self.alive[t] and all(
                    _orient(self.p[self.tv[t][(i + 1) % 3]],
                            self.p[self.tv[t][(i + 2) % 3]], q) >= 0
                    for i in range(3)):
                return t
        return -1

    def toward(self, t, q):
        """Walk in a straight line from the centroid of t towards q
        (Shewchuk 2002a, p. 50). ('in', t) when q is reached without
        crossing a subsegment; ('blocked', key) when a subsegment is on
        the way or q lies on one; ('stuck', t) if the line runs through a
        vertex, which a constrained Delaunay triangulation does not allow
        for a circumcentre (the vertex would be inside the circle)."""
        g = self.centroid(t)
        for _ in range(4 * len(self.tv) + 16):
            v = self.tv[t]
            o = [_orient(self.p[v[(i + 1) % 3]], self.p[v[(i + 2) % 3]], q)
                 for i in range(3)]
            out = [i for i in range(3) if o[i] < 0]
            if not out:
                zeros = [i for i in range(3) if o[i] == 0]
                if len(zeros) >= 2:
                    return ("stuck", t)
                if zeros and self.is_sub(*self.edge(t, zeros[0])):
                    return ("blocked", _key(*self.edge(t, zeros[0])))
                return ("in", t)
            if len(out) == 1:
                i = out[0]
            else:
                k = 3 - out[0] - out[1]
                side = _orient(g, q, self.p[v[k]])
                if side == 0:
                    return ("stuck", t)
                i = (k + 1) % 3 if side > 0 else (k + 2) % 3
            a, b = self.edge(t, i)
            if self.is_sub(a, b):
                return ("blocked", _key(a, b))
            n = self.tn[t][i]
            if n < 0:
                return ("stuck", t)
            t = n
        return ("stuck", t)

    # -- Bowyer-Watson ------------------------------------------------------
    def cavity(self, q, t0, through=None) -> list:
        """The triangles whose circumcircle holds q strictly, connected to
        t0 without crossing a subsegment (but ``through``, the one being
        split)."""
        cav, inside, todo = [t0], {t0}, deque([t0])
        while todo:
            t = todo.popleft()
            for i in range(3):
                n = self.tn[t][i]
                if n < 0 or n in inside:
                    continue
                k = _key(*self.edge(t, i))
                if k in self.sub and k != through:
                    continue
                a, b, c = (self.p[j] for j in self.tv[n])
                if _incircle(a, b, c, q) > 0:
                    inside.add(n)
                    cav.append(n)
                    todo.append(n)
        return cav

    def boundary(self, cav, through=None) -> list:
        """The edges of the cavity's boundary, counterclockwise, as
        (a, b, triangle outside or -1, triangle of the cavity it was on);
        the subsegment ``through`` is left out when q lies on it."""
        inside = set(cav)
        out = []
        for t in cav:
            for i in range(3):
                n = self.tn[t][i]
                if n >= 0 and n in inside:
                    continue
                a, b = self.edge(t, i)
                if through is not None and _key(a, b) == through:
                    continue
                out.append((a, b, n, t))
        return out

    def insert(self, q, cav, through=None) -> list:
        """Replace the cavity by the fan from vertex q; returns the new
        triangles. With ``through``, q splits that subsegment in two."""
        new = self._fan(q, cav, self.boundary(cav, through))
        if through is not None:
            seg = self.sub.pop(through)
            self.sub[_key(through[0], q)] = seg
            self.sub[_key(q, through[1])] = seg
        return new

    def insert_off(self, q, key, tris) -> list:
        """Split subsegment ``key`` by vertex q off its chord: a vertex on
        an arc, on the side the arc bulges to. ``tris`` are the triangles
        of the chord. The cavity grows from the triangle on q's side, whose
        circumcircle always holds q (the region between the chord and its
        arc holds no vertex, so the angle there is less than the angle
        a q b); across the chord it takes the other triangle only if its
        circumcircle holds q too, and otherwise the chord stays as an
        ordinary edge of a new triangle (a, b, q) that goes to the other
        side's region. When there is nothing on one side (the exterior or
        a void) the region between the chord and the arc goes to it. Every
        new triangle is checked counterclockwise in exact arithmetic."""
        a, b = key
        pq = self.p[q]
        side = _orient(self.p[a], self.p[b], pq)
        mine = other = -1
        for t in tris:
            w = next(x for x in self.tv[t] if x != a and x != b)
            if _orient(self.p[a], self.p[b], self.p[w]) == side:
                mine = t
            else:
                other = t
        if mine >= 0:
            cav = self.cavity(pq, mine, through=key)
        elif other >= 0 and _incircle(*(self.p[i] for i in self.tv[other]),
                                      pq) > 0:
            cav = self.cavity(pq, other, through=key)
        else:
            cav = []
        inside = set(cav)
        bnd = []
        for t in cav:
            for i in range(3):
                n = self.tn[t][i]
                if n >= 0 and n in inside:
                    continue
                x, y = self.edge(t, i)
                if _key(x, y) == key:
                    if n >= 0:              # the chord stays, on n's side
                        bnd.append((x, y, n, n))
                    continue
                bnd.append((x, y, n, t))
        if not cav:
            i = next(i for i in range(3)
                     if _key(*self.edge(other, i)) == key)
            x, y = self.edge(other, i)
            bnd = [(y, x, other, other)]
        new = self._fan(q, cav, bnd)
        for t in new:
            u, v, _ = self.tv[t]
            if _orient(self.p[u], self.p[v], pq) <= 0:
                raise QualityMeshError(M.REFINE_INTERNAL, x=pq[0], y=pq[1])
        seg = self.sub.pop(key)
        self.sub[_key(a, q)] = seg
        self.sub[_key(q, b)] = seg
        return new

    def _fan(self, q, cav, bnd) -> list:
        """Kill the cavity and fan vertex q over its boundary ``bnd``,
        (a, b, triangle outside or -1, triangle whose region it takes)."""
        for t in cav:
            self.alive[t] = False
            self.n_alive -= 1
        new, starts, ends = [], {}, {}
        for a, b, n, src in bnd:
            t = self._make(a, b, q, self.region[src])
            self.tn[t][2] = n
            if n >= 0:
                nv = self.tv[n]
                for j in range(3):
                    if nv[(j + 1) % 3] == b and nv[(j + 2) % 3] == a:
                        self.tn[n][j] = t
                        break
            starts[a] = t
            ends[b] = t
            new.append(t)
        for t in new:
            a, b, _ = self.tv[t]
            self.tn[t][0] = starts.get(b, -1)
            self.tn[t][1] = ends.get(a, -1)
        return new

    def has_edge(self, a, b) -> bool:
        return any(b in self.tv[t] for t in self.around(a))


# ======================================================================
# Input
# ======================================================================
def _point(xy):
    return (float(xy[0]), float(xy[1]))


def _segments_cross(p, a, b, c, d) -> bool:
    """Whether segments ab and cd (indices into p) meet anywhere but at a
    shared endpoint, or overlap."""
    shared = {a, b} & {c, d}
    if len(shared) == 2:
        return True
    pa, pb, pc, pd = p[a], p[b], p[c], p[d]
    if shared:
        s = shared.pop()
        x = b if a == s else a          # the other end of ab
        y = d if c == s else c          # the other end of cd
        ps, px, py = p[s], p[x], p[y]
        if _orient(ps, px, py) != 0:
            return False
        return ((px[0] - ps[0]) * (py[0] - ps[0])
                + (px[1] - ps[1]) * (py[1] - ps[1])) > 0
    o1, o2 = _orient(pa, pb, pc), _orient(pa, pb, pd)
    o3, o4 = _orient(pc, pd, pa), _orient(pc, pd, pb)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True

    def on(u, v, w):        # w on the closed segment uv, collinear
        return (min(u[0], v[0]) <= w[0] <= max(u[0], v[0])
                and min(u[1], v[1]) <= w[1] <= max(u[1], v[1]))
    return ((o1 == 0 and on(pa, pb, pc)) or (o2 == 0 and on(pa, pb, pd))
            or (o3 == 0 and on(pc, pd, pa)) or (o4 == 0 and on(pc, pd, pb)))


def _read(pslg):
    """The input, checked: points, segments (u, v), labels, seeds, voids.
    Raises QualityMeshError on what cannot be meshed."""
    verts = list(getattr(pslg, "vertices", ()) or ())
    segs = list(getattr(pslg, "segments", ()) or ())
    seeds = list(getattr(pslg, "seeds", ()) or ())
    voids = [_point(v) for v in (getattr(pslg, "voids", ()) or ())]
    if len(verts) < 3 or not segs or not seeds:
        raise QualityMeshError(M.REFINE_EMPTY)
    pts = []
    where = {}
    for i, v in enumerate(verts):
        try:
            xy = _point(v)
        except (TypeError, ValueError, IndexError):
            raise QualityMeshError(M.REFINE_BAD_VERTEX, i=i) from None
        if not (math.isfinite(xy[0]) and math.isfinite(xy[1])):
            raise QualityMeshError(M.REFINE_BAD_VERTEX, i=i)
        if xy in where:
            raise QualityMeshError(M.REFINE_DUPLICATE_VERTEX, i=where[xy],
                                   j=i, x=xy[0], y=xy[1])
        where[xy] = i
        pts.append(xy)
    n = len(pts)
    pairs, labels, seen = [], [], {}
    for k, s in enumerate(segs):
        u, v, label = s[0], s[1], (s[2] if len(s) > 2 else None)
        if not (isinstance(u, int) and isinstance(v, int)
                and 0 <= u < n and 0 <= v < n and u != v):
            raise QualityMeshError(M.REFINE_BAD_SEGMENT, k=k, u=u, v=v)
        if _key(u, v) in seen:
            raise QualityMeshError(M.REFINE_DUPLICATE_SEGMENT,
                                   k=seen[_key(u, v)], j=k)
        seen[_key(u, v)] = k
        pairs.append((u, v))
        labels.append(label)
    # crossings: a sweep along x
    order = sorted(range(len(pairs)),
                   key=lambda k: (min(pts[pairs[k][0]][0],
                                      pts[pairs[k][1]][0]), k))
    for idx, k in enumerate(order):
        u, v = pairs[k]
        xmax = max(pts[u][0], pts[v][0])
        ylo, yhi = sorted((pts[u][1], pts[v][1]))
        for j in order[idx + 1:]:
            c, d = pairs[j]
            if min(pts[c][0], pts[d][0]) > xmax:
                break
            if max(pts[c][1], pts[d][1]) < ylo or \
                    min(pts[c][1], pts[d][1]) > yhi:
                continue
            if _segments_cross(pts, u, v, c, d):
                raise QualityMeshError(M.REFINE_CROSSING_SEGMENTS,
                                       k=min(k, j), j=max(k, j))
    # a vertex inside a segment
    by_x = sorted(range(n), key=lambda i: (pts[i][0], i))
    xs = [pts[i][0] for i in by_x]
    for k, (u, v) in enumerate(pairs):
        lo = bisect.bisect_left(xs, min(pts[u][0], pts[v][0]))
        hi = bisect.bisect_right(xs, max(pts[u][0], pts[v][0]))
        ylo, yhi = sorted((pts[u][1], pts[v][1]))
        for i in by_x[lo:hi]:
            if i in (u, v) or not ylo <= pts[i][1] <= yhi:
                continue
            if _orient(pts[u], pts[v], pts[i]) == 0:
                raise QualityMeshError(M.REFINE_VERTEX_ON_SEGMENT, i=i, k=k)
    out_seeds = []
    for s in seeds:
        point, region, material = s[0], s[1], s[2]
        out_seeds.append((_point(point), region, material))
    return pts, pairs, labels, out_seeds, voids


def _in_disc(c, u, z) -> int:
    """+1 if z is strictly inside the circle of centre c through u, 0 on
    it, -1 outside; exact."""
    zx, zy = z[0] - c[0], z[1] - c[1]
    ux, uy = u[0] - c[0], u[1] - c[1]
    dz, du = zx * zx + zy * zy, ux * ux + uy * uy
    if abs(dz - du) > _FILTER * (dz + du):
        return 1 if dz < du else -1
    cx, cy, px, py, qx, qy = (Fraction(v) for v in (*c, *z, *u))
    return _sign((qx - cx) ** 2 + (qy - cy) ** 2
                 - (px - cx) ** 2 - (py - cy) ** 2)


def _in_cap(pu, pv, c, side, z) -> bool:
    """z in the closed region between chord uv and its arc around c (on
    the side ``side`` of u -> v): on that side of the chord's line and in
    the closed disc through u. The chord itself is the segment's, checked
    elsewhere."""
    return _orient(pu, pv, z) == side and _in_disc(c, pu, z) >= 0


def _enters_cap(pu, pv, c, side, pa, pb) -> bool:
    """Whether segment ab has a point in the closed disc on the arc's side
    of chord uv, in exact arithmetic. Segment ab neither crosses the chord
    nor has an end inside that region (checked before), so its part in the
    disc lies on one side of the chord's line: its point nearest to c
    tells which."""
    cx, cy = Fraction(c[0]), Fraction(c[1])
    ax, ay, bx, by = (Fraction(v) for v in (*pa, *pb))
    ux, uy, vx, vy = (Fraction(v) for v in (*pu, *pv))
    dx, dy = bx - ax, by - ay
    A = dx * dx + dy * dy
    B = dx * (ax - cx) + dy * (ay - cy)
    C = (ax - cx) ** 2 + (ay - cy) ** 2 - (ux - cx) ** 2 - (uy - cy) ** 2
    t = min(max(-B / A, Fraction(0)), Fraction(1))
    if A * t * t + 2 * B * t + C > 0:
        return False
    px, py = ax + t * dx, ay + t * dy
    return _sign((vx - ux) * (py - uy) - (vy - uy) * (px - ux)) == side


def _arcs_cross(arc1, arc2, shared, scale) -> bool:
    """Whether two arcs of different circles meet away from their shared
    ends: a point of both circles on the arc's side of each chord. The two
    points are computed in floating point (+ - * / and sqrt); one within
    1e-9 of ``scale`` from a shared end is that end."""
    (pu1, pv1, c1, r1, s1), (pu2, pv2, c2, r2, s2) = arc1, arc2
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    d = math.sqrt(dx * dx + dy * dy)
    if d == 0.0 or d > r1 + r2 or d < abs(r1 - r2):
        return False
    along = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d)
    h = math.sqrt(max(0.0, r1 * r1 - along * along))
    bx, by = c1[0] + along * dx / d, c1[1] + along * dy / d
    for sgn in (1.0, -1.0):
        x = (bx - sgn * h * dy / d, by + sgn * h * dx / d)
        if any(_dist(x, e) <= 1e-9 * scale for e in shared):
            continue
        if _orient(pu1, pv1, x) == s1 and _orient(pu2, pv2, x) == s2:
            return True
    return False


def _read_arcs(pslg, pts, pairs, labels, seeds, voids) -> dict:
    """The arcs of the input, checked: input segment -> (centre, radius).
    The radius is the distance from the centre to the segment's u."""
    raw = getattr(pslg, "arcs", None) or {}
    if not raw:
        return {}
    arcs = {}
    for k, (u, v) in enumerate(pairs):
        try:
            if labels[k] not in raw:
                continue
        except TypeError:
            continue
        try:
            c = _point(raw[labels[k]])
        except (TypeError, ValueError, IndexError):
            raise QualityMeshError(M.REFINE_BAD_ARC, k=k) from None
        if not (math.isfinite(c[0]) and math.isfinite(c[1])):
            raise QualityMeshError(M.REFINE_BAD_ARC, k=k)
        pu, pv = pts[u], pts[v]
        r1, r2 = _dist(pu, c), _dist(pv, c)
        if r1 == 0.0 or abs(r1 - r2) > _TOLERANCE * max(r1, r2):
            raise QualityMeshError(M.REFINE_ARC_RADII, k=k, r1=r1, r2=r2)
        chord = _dist(pu, pv)
        if chord > r1 * (1.0 + _TOLERANCE):         # more than 60 degrees
            raise QualityMeshError(
                M.REFINE_ARC_TURN, k=k, angle=math.degrees(
                    2.0 * math.asin(min(1.0, 0.5 * chord / r1))))
        arcs[k] = (c, r1)
    # nothing between a chord and its arc, and no other segment across it
    caps = {}
    for k, (c, r) in arcs.items():
        u, v = pairs[k]
        pu, pv = pts[u], pts[v]
        side = -_orient(pu, pv, c)
        m = (0.5 * (pu[0] + pv[0]), 0.5 * (pu[1] + pv[1]))
        half = 0.5 * _dist(pu, pv) * (1.0 + 1e-9)
        box = (m[0] - half, m[0] + half, m[1] - half, m[1] + half)
        caps[k] = (pu, pv, c, r, side, box)

    def near(box, xy):
        return box[0] <= xy[0] <= box[1] and box[2] <= xy[1] <= box[3]

    def overlap(b1, b2):
        return not (b1[1] < b2[0] or b2[1] < b1[0] or b1[3] < b2[2]
                    or b2[3] < b1[2])

    seg_box = [(min(pts[u][0], pts[v][0]), max(pts[u][0], pts[v][0]),
                min(pts[u][1], pts[v][1]), max(pts[u][1], pts[v][1]))
               for u, v in pairs]
    for k, (pu, pv, c, r, side, box) in caps.items():
        u, v = pairs[k]
        for i, xy in enumerate(pts):
            if i not in (u, v) and near(box, xy) and \
                    _in_cap(pu, pv, c, side, xy):
                raise QualityMeshError(M.REFINE_VERTEX_IN_ARC, i=i, k=k)
        for xy, region, _material in seeds:
            if near(box, xy) and _in_cap(pu, pv, c, side, xy):
                raise QualityMeshError(M.REFINE_SEED_IN_ARC, region=region,
                                       x=xy[0], y=xy[1], k=k)
        for xy in voids:
            if near(box, xy) and _in_cap(pu, pv, c, side, xy):
                raise QualityMeshError(M.REFINE_VOID_IN_ARC, x=xy[0],
                                       y=xy[1], k=k)
        for j, (a, b) in enumerate(pairs):
            if j == k or not overlap(box, seg_box[j]):
                continue
            if _enters_cap(pu, pv, c, side, pts[a], pts[b]):
                raise QualityMeshError(M.REFINE_SEGMENT_IN_ARC, j=j, k=k)
            if j in caps:
                pu2, pv2, c2, r2, side2, box2 = caps[j]
                if c2 != c or r2 != r:
                    shared = [pts[e] for e in sorted({u, v} & {a, b})]
                    if overlap(box, box2) and _arcs_cross(
                            (pu, pv, c, r, side), (pu2, pv2, c2, r2, side2),
                            shared, max(r, r2)):
                        raise QualityMeshError(M.REFINE_SEGMENT_IN_ARC,
                                               j=j, k=k)
    return arcs


# ======================================================================
# The algorithm
# ======================================================================
class _Refiner:

    def __init__(self, pts, pairs, seeds, voids, max_ratio, size,
                 max_triangles, arcs=None):
        self.n_input = len(pts)
        self.pairs = pairs
        #: input segment -> (centre, radius) of its arc
        self.arcs = dict(arcs or {})
        self.seeds = seeds
        self.voids = voids
        self.b2 = max_ratio * max_ratio
        self.size = size
        self.max_triangles = max_triangles
        self.unsplittable = 0
        #: the input segments at each input vertex
        self.incident = [[] for _ in range(len(pts))]
        for k, (u, v) in enumerate(pairs):
            self.incident[u].append(k)
            self.incident[v].append(k)
        #: insertion radius of each mesh vertex (pp. 13-14)
        self.r: dict = {}
        #: (apex, input segment) -> (segments of its cluster, sin(phi_min/2))
        self.clusters: dict = {}
        #: the smallest angle between two input segments inside the domain
        self.min_angle = None
        #: the splits the Terminator declined, and what it read
        self.declined: list = []
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx, cy = 0.5 * (min(xs) + max(xs)), 0.5 * (min(ys) + max(ys))
        span = max(max(xs) - min(xs), max(ys) - min(ys))
        #: no edge shorter than this is made (see _too_fine)
        self.shortest = math.ldexp(span, -40)
        enc = [(cx - 20.0 * span, cy - 10.0 * span),
               (cx + 20.0 * span, cy - 10.0 * span),
               (cx, cy + 20.0 * span)]
        self.T = _Triangulation(list(pts) + enc)
        self.enclosing = (self.n_input, self.n_input + 1, self.n_input + 2)
        self.hsize: dict = {}
        self.qs: deque = deque()
        self.queued: set = set()
        self.qt: list = []
        self.counter = 0

    # -- the size bound ----------------------------------------------------
    def _h(self, xy) -> float:
        h = self.size(xy[0], xy[1])
        h = float(h)
        if math.isnan(h) or h <= 0.0:
            raise QualityMeshError(M.REFINE_BAD_SIZE, x=xy[0], y=xy[1], h=h)
        return h

    def _vertex_h(self, v) -> float:
        h = self.hsize.get(v)
        if h is None:
            h = self.hsize[v] = self._h(self.T.p[v])
        return h

    # -- what is bad -------------------------------------------------------
    def _oversized(self, t) -> bool:
        if self.size is None:
            return False
        T = self.T
        v = T.tv[t]
        a, b, c = (T.p[i] for i in v)
        lmax2 = max((b[0] - c[0]) ** 2 + (b[1] - c[1]) ** 2,
                    (c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2,
                    (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)
        h = min(self._vertex_h(v[0]), self._vertex_h(v[1]),
                self._vertex_h(v[2]), self._h(T.centroid(t)))
        return lmax2 > h * h

    def ratio2(self, t) -> float:
        """The square of circumradius / shortest edge: (lmed lmax / 2|2A|)^2
        (the circumradius is l1 l2 l3 / 4A, appendix A.2 of Shewchuk
        2002b)."""
        a, b, c = (self.T.p[i] for i in self.T.tv[t])
        sq = sorted(((b[0] - c[0]) ** 2 + (b[1] - c[1]) ** 2,
                     (c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2,
                     (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2))
        det = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        den = 4.0 * det * det
        if den == 0.0:          # flat in floating point: see _too_fine
            return math.inf
        return sq[1] * sq[2] / den

    def _skinny(self, t) -> Optional[float]:
        """The squared ratio if t is skinny and its smallest angle does not
        separate two subsegments (figure 38, line 8), else None."""
        T = self.T
        r2 = self.ratio2(t)
        if r2 <= self.b2:
            return None
        v = T.tv[t]
        p = [T.p[i] for i in v]
        # the smallest angle is at the vertex opposite the shortest edge
        sq = [(p[(i + 1) % 3][0] - p[(i + 2) % 3][0]) ** 2
              + (p[(i + 1) % 3][1] - p[(i + 2) % 3][1]) ** 2
              for i in range(3)]
        i = min(range(3), key=lambda j: (sq[j], j))
        if T.is_sub(v[i], v[(i + 1) % 3]) and T.is_sub(v[i], v[(i + 2) % 3]):
            return None
        return r2

    def _queue_if_bad(self, t) -> None:
        r2 = self._skinny(t)
        if r2 is None and not self._oversized(t):
            return
        self.counter += 1
        heapq.heappush(self.qt, (-(r2 or 0.0), self.counter, t))

    def _encroached(self, key) -> bool:
        T = self.T
        a, b = key
        for t in T.edge_triangles(a, b):
            w = next(i for i in T.tv[t] if i != a and i != b)
            if _in_diametral_circle(T.p[a], T.p[b], T.p[w]):
                return True
        return False

    def _queue_sub(self, key) -> None:
        if key not in self.queued:
            self.queued.add(key)
            self.qs.append(key)

    def _too_fine(self, xy) -> None:
        """The refinement is about to make an edge shorter than
        ``shortest`` (2**-40 of the extent of the input), or a triangle flat
        in floating point. A refinement that ends does not come near it
        (Theorems 4 and 11 bound the edges from below by the input's own
        features); it is how one fails to end where it cannot, as Ruppert's
        algorithm on a small input angle (Shewchuk 2002a, p. 27): its edges
        shrink without end, next to the origin down to the smallest numbers
        floating point has, never reaching ``max_triangles``. It is said
        rather than run into a division by zero."""
        raise QualityMeshError(M.REFINE_TOO_FINE, x=xy[0], y=xy[1])

    def _check_count(self) -> None:
        if self.T.n_alive > self.max_triangles:
            raise QualityMeshError(M.REFINE_TOO_MANY_TRIANGLES,
                                   limit=self.max_triangles)

    # -- the steps ---------------------------------------------------------
    def triangulate(self) -> None:
        T = self.T
        s0, s1, s2 = self.enclosing
        last = T._make(s0, s1, s2, _UNKNOWN)
        for i in range(self.n_input):
            t = T.locate(T.p[i], last)
            new = T.insert(i, T.cavity(T.p[i], t))
            last = new[0]
            self._check_count()

    def recover(self) -> None:
        """Ruppert: split every missing segment at its midpoint until all
        its pieces are edges; each piece is constrained once it is in."""
        T = self.T
        todo = deque((u, v, k) for k, (u, v) in enumerate(self.pairs))
        while todo:
            a, b, k = todo.popleft()
            if T.has_edge(a, b):
                T.sub[_key(a, b)] = k
                continue
            m = T.add_point(self.split_point(_key(a, b), k))
            t = T.locate(T.p[m], T.vt[a])
            T.insert(m, T.cavity(T.p[m], t))
            self._check_count()
            todo.appendleft((m, b, k))
            todo.appendleft((a, m, k))

    def _flood(self, t0, label) -> None:
        T = self.T
        T.region[t0] = label
        todo = deque([t0])
        while todo:
            t = todo.popleft()
            for i in range(3):
                n = T.tn[t][i]
                if n < 0 or T.region[n] != _UNKNOWN or \
                        T.is_sub(*T.edge(t, i)):
                    continue
                T.region[n] = label
                todo.append(n)

    def _point_triangle(self, xy, on_segment_code, outside_code,
                        **args) -> int:
        """The live triangle that holds xy strictly inside or on an edge
        that is not a subsegment."""
        T = self.T
        start = next(t for t in range(len(T.tv)) if T.alive[t])
        t = T.locate(xy, start)
        if t < 0:
            raise QualityMeshError(outside_code, x=xy[0], y=xy[1], **args)
        v = T.tv[t]
        o = [_orient(T.p[v[(i + 1) % 3]], T.p[v[(i + 2) % 3]], xy)
             for i in range(3)]
        zeros = [i for i in range(3) if o[i] == 0]
        if len(zeros) >= 2 or (zeros and T.is_sub(*T.edge(t, zeros[0]))):
            raise QualityMeshError(on_segment_code, x=xy[0], y=xy[1], **args)
        return t

    def classify(self) -> None:
        T = self.T
        enc = set(self.enclosing)
        for t in range(len(T.tv)):
            if T.alive[t] and T.region[t] == _UNKNOWN and \
                    enc.intersection(T.tv[t]):
                self._flood(t, _OUTSIDE)
        for xy in self.voids:
            t = self._point_triangle(xy, M.REFINE_VOID_ON_SEGMENT,
                                     M.REFINE_VOID_OUTSIDE)
            if T.region[t] == _OUTSIDE:
                raise QualityMeshError(M.REFINE_VOID_OUTSIDE, x=xy[0],
                                       y=xy[1])
            if T.region[t] == _UNKNOWN:
                self._flood(t, _VOID)
        for k, (xy, region, _material) in enumerate(self.seeds):
            t = self._point_triangle(xy, M.REFINE_SEED_ON_SEGMENT,
                                     M.REFINE_SEED_OUTSIDE, region=region)
            here = T.region[t]
            if here in (_OUTSIDE, _VOID):
                raise QualityMeshError(M.REFINE_SEED_OUTSIDE, region=region,
                                       x=xy[0], y=xy[1])
            if here >= 0:
                if self.seeds[here][1] != region:
                    raise QualityMeshError(M.REFINE_SEEDS_SHARE_REGION,
                                           first=self.seeds[here][1],
                                           second=region)
                continue
            self._flood(t, k)
        for t in range(len(T.tv)):
            if T.alive[t] and T.region[t] == _UNKNOWN:
                x, y = T.centroid(t)
                raise QualityMeshError(M.REFINE_REGION_WITHOUT_SEED, x=x, y=y)
        for t in range(len(T.tv)):
            if T.alive[t] and T.region[t] < 0:
                T.alive[t] = False
                T.n_alive -= 1
        for t in range(len(T.tv)):
            if T.alive[t]:
                for i in range(3):
                    n = T.tn[t][i]
                    if n >= 0 and not T.alive[n]:
                        T.tn[t][i] = -1
        T.vt = [-1] * len(T.p)
        for t in range(len(T.tv)):
            if T.alive[t]:
                for v in T.tv[t]:
                    if T.vt[v] < 0:
                        T.vt[v] = t
        for i in range(self.n_input):
            if T.vt[i] < 0:
                raise QualityMeshError(M.REFINE_VERTEX_OUTSIDE, i=i,
                                       x=T.p[i][0], y=T.p[i][1])

    def _apex(self, v) -> bool:
        """An input vertex shared by two or more input segments."""
        return v < self.n_input and len(self.incident[v]) >= 2

    def split_point(self, key, seg=None):
        """Where subsegment ``key`` is split. Its midpoint (section 3.1),
        unless an endpoint is an input vertex shared with another segment:
        then on the concentric circle of radius a power of two around that
        vertex that gives the best-balanced split (section 6.2, p. 29), so
        that the piece next to it has a power-of-two length; with both
        endpoints shared, the one of the smaller index (the source: "choose
        one endpoint's shells arbitrarily"). A power of two of the unit of
        length: the mesh depends on that unit. The point is a + t (b - a),
        so a segment on x = 0 keeps x = 0. On an arc, the point of the arc:
        see ``_arc_point``."""
        T = self.T
        a, b = key
        apex = a if self._apex(a) else (b if self._apex(b) else None)
        if seg is None:
            seg = T.sub.get(key)
        if seg in self.arcs:
            return self._arc_point(seg, key, apex)
        if apex is None:
            pa, pb = T.p[a], T.p[b]
            return (pa[0] + 0.5 * (pb[0] - pa[0]),
                    pa[1] + 0.5 * (pb[1] - pa[1]))
        far = b if apex == a else a
        ps, pf = T.p[apex], T.p[far]
        length = math.sqrt((pf[0] - ps[0]) ** 2 + (pf[1] - ps[1]) ** 2)
        half = 0.5 * length
        _m, e = math.frexp(half)            # half = m 2**e, 0.5 <= m < 1
        lo, hi = math.ldexp(1.0, e - 1), math.ldexp(1.0, e)
        shell = lo if half - lo <= hi - half else hi
        t = shell / length
        return (ps[0] + t * (pf[0] - ps[0]), ps[1] + t * (pf[1] - ps[1]))

    def _arc_point(self, seg, key, apex):
        """Where a piece of an arc is split, on the arc (Pav and Walkington,
        section 3, p. 6). With no shared endpoint, where the arc meets the
        perpendicular bisector of the chord, c + R (m - c) / |m - c|, m the
        midpoint of the chord: the point of their Corollaries 1 and 2
        (p. 7). Next to a shared input vertex s, the point of the arc at
        the distance of the shell (section 6.2 of Shewchuk 2002a, measured
        from s as on a segment, so the chord next to s has a power-of-two
        length): s + (rho**2 / 2R) u + rho sqrt(1 - rho**2 / 4R**2) w, u
        the unit vector from s to the centre and w the one across it
        towards the other end. No source proves this one: the shells rest
        on powers of two, which "do not generalize naturally" to curves
        (Pav and Walkington, p. 2). Only + - * / and sqrt."""
        T = self.T
        (cx, cy), R = self.arcs[seg]
        a, b = key
        if apex is None:
            pa, pb = T.p[a], T.p[b]
            mx, my = (pa[0] + 0.5 * (pb[0] - pa[0]),
                      pa[1] + 0.5 * (pb[1] - pa[1]))
            dx, dy = mx - cx, my - cy
            d = math.sqrt(dx * dx + dy * dy)
            return (cx + R * (dx / d), cy + R * (dy / d))
        far = b if apex == a else a
        ps, pf = T.p[apex], T.p[far]
        half = 0.5 * _dist(ps, pf)
        _m, e = math.frexp(half)            # half = m 2**e, 0.5 <= m < 1
        lo, hi = math.ldexp(1.0, e - 1), math.ldexp(1.0, e)
        rho = lo if half - lo <= hi - half else hi
        ux, uy = (cx - ps[0]) / R, (cy - ps[1]) / R
        wx, wy = -uy, ux
        if wx * (pf[0] - ps[0]) + wy * (pf[1] - ps[1]) < 0.0:
            wx, wy = -wx, -wy
        along = rho * rho / (2.0 * R)
        across = rho * math.sqrt(max(0.0, 1.0 - rho * rho / (4.0 * R * R)))
        return (ps[0] + along * ux + across * wx,
                ps[1] + along * uy + across * wy)

    # -- the small input angles (section 6.3) -------------------------------
    def _piece(self, a, k) -> Optional[int]:
        """The other end of the piece of input segment k that touches
        vertex a."""
        T = self.T
        for t in T.around(a):
            v = T.tv[t]
            i = v.index(a)
            for y in (v[(i + 1) % 3], v[(i + 2) % 3]):
                if T.sub.get(_key(a, y)) == k:
                    return y
        return None

    def _far(self, a, k):
        u, v = self.pairs[k]
        return self.T.p[v if u == a else u]

    def _dir(self, a, k):
        """The direction in which input segment k leaves vertex a: towards
        its other end, or, for an arc, its tangent at a (perpendicular to
        the radius, towards the other end)."""
        pa, f = self.T.p[a], self._far(a, k)
        if k not in self.arcs:
            return (f[0] - pa[0], f[1] - pa[1])
        (cx, cy), _r = self.arcs[k]
        rx, ry = pa[0] - cx, pa[1] - cy
        if -ry * (f[0] - pa[0]) + rx * (f[1] - pa[1]) < 0.0:
            return (ry, -rx)
        return (-ry, rx)

    def analyse_angles(self) -> None:
        """The input angles at each shared input vertex, inside the domain
        ("exterior" small angles are ignored, p. 33), and the subsegment
        clusters: the segments at a vertex joined, one to the next, by
        angles of 60 degrees or less (p. 33; figure 29). Whether an angle
        is 60 degrees or less is decided in exact arithmetic on the input
        coordinates. For an arc, its tangent at the vertex (v0.2.6; no
        source covers the clusters of arcs)."""
        T = self.T
        for a in range(self.n_input):
            if not self._apex(a):
                continue
            pa = T.p[a]

            def upper(k):
                d = self._dir(a, k)
                return d[1] > 0.0 or (d[1] == 0.0 and d[0] > 0.0)

            def ccw(k1, k2):
                h1, h2 = upper(k1), upper(k2)
                if h1 != h2:
                    return -1 if h1 else 1
                if k1 not in self.arcs and k2 not in self.arcs:
                    return -_orient(pa, self._far(a, k1), self._far(a, k2))
                d1, d2 = self._dir(a, k1), self._dir(a, k2)
                x1, y1, x2, y2 = (Fraction(c) for c in (*d1, *d2))
                return -_sign(x1 * y2 - y1 * x2)
            ring = sorted(self.incident[a], key=functools.cmp_to_key(ccw))
            n = len(ring)
            owner = {k: k for k in ring}

            def root(k):
                while owner[k] != k:
                    k = owner[k]
                return k
            cos_link: dict = {}
            for j in range(n):
                k1, k2 = ring[j], ring[(j + 1) % n]
                y1 = self._piece(a, k1)
                inside = any(T.tv[t][(T.tv[t].index(a) + 1) % 3] == y1
                             for t in T.around(a))
                if not inside:
                    continue
                d1, d2 = self._dir(a, k1), self._dir(a, k2)
                cross = d1[0] * d2[1] - d1[1] * d2[0]
                dot = d1[0] * d2[0] + d1[1] * d2[1]
                angle = math.degrees(math.atan2(cross, dot)) % 360.0
                if self.min_angle is None or angle < self.min_angle:
                    self.min_angle = angle
                x1, y1f, x2, y2f = (Fraction(c) for c in (*d1, *d2))
                cr = x1 * y2f - y1f * x2
                dt = x1 * x2 + y1f * y2f
                small = (cr > 0 and dt > 0 and 4 * dt * dt
                         >= (x1 * x1 + y1f * y1f) * (x2 * x2 + y2f * y2f))
                if small:
                    owner[root(k2)] = root(k1)
                    c = dot / math.sqrt((d1[0] ** 2 + d1[1] ** 2)
                                        * (d2[0] ** 2 + d2[1] ** 2))
                    cos_link[(k1, k2)] = c
            groups: dict = {}
            for k in ring:
                groups.setdefault(root(k), []).append(k)
            for members in groups.values():
                if len(members) < 2:
                    continue
                cmax = max(c for (k1, k2), c in cos_link.items()
                           if k1 in members)
                sin_half = math.sqrt(max(0.0, 0.5 * (1.0 - cmax)))
                for k in members:
                    self.clusters[(a, k)] = (tuple(members), sin_half)

    def _split_permitted(self, key, t) -> bool:
        """Line 21 of figure 38 for a subsegment encroached by the
        circumcentre of t: d is the insertion radius of g, the youngest
        endpoint of the shortest edge of t (line 19)."""
        T = self.T
        v = T.tv[t]
        sq = [_dist(T.p[v[(i + 1) % 3]], T.p[v[(i + 2) % 3]])
              for i in range(3)]
        i = min(range(3), key=lambda j: (sq[j], j))
        g = max(v[(i + 1) % 3], v[(i + 2) % 3])
        return self.permitted(key, self.r[g])

    def permitted(self, key, d) -> bool:
        """Figure 38, SPLITPERMITTED(s, d) (lines 27-35), with the
        conditions A, C, D and E of section 6.3 (p. 34; B, the size, is the
        caller's). F is left out: the source calls it optional and possibly
        slow, and its author did not implement it (p. 50)."""
        T = self.T
        seg = T.sub[key]
        mine = [(e, self.clusters[(e, seg)]) for e in key
                if (e, seg) in self.clusters]
        if len(mine) != 1:                  # no cluster (Ruppert), or D
            return True
        a, b = key
        length = _dist(T.p[a], T.p[b])
        if not _power_of_two(length):       # C
            return True
        apex, (members, sin_half) = mine[0]
        shortest = None
        for k in members:                   # E
            if k != seg:
                y = self._piece(apex, k)
                if y is None:
                    continue
                piece = _dist(T.p[apex], T.p[y])
                shortest = piece if shortest is None else min(shortest, piece)
                if piece < length * (1.0 - _TOLERANCE):
                    return True
        # A: r_min, the shortest edge the split of the cluster would make
        # (line 32), against d
        if length * sin_half >= d:
            return True
        self.declined.append({
            "subsegment": [list(T.p[a]), list(T.p[b])],
            "apex": list(T.p[apex]),
            "length": length,
            "r_min": length * sin_half,
            "r_g": d,
            "cluster_shortest": shortest,
        })
        return False

    def _new_vertex(self, v, new) -> None:
        """Figure 39, NEWVERTEX: the subsegments the new vertex encroaches
        and the bad triangles it made."""
        T = self.T
        for t in new:
            i = T.tv[t].index(v)
            a, b = T.edge(t, i)
            if T.is_sub(a, b) and _in_diametral_circle(T.p[a], T.p[b],
                                                       T.p[v]):
                self._queue_sub(_key(a, b))
            else:
                self._queue_if_bad(t)

    def split_encroached(self) -> None:
        """Figure 39, SPLITENCROACHEDSUBSEGMENTS."""
        T = self.T
        while self.qs:
            key = self.qs.popleft()
            self.queued.discard(key)
            if key not in T.sub:
                continue
            tris = T.edge_triangles(*key)
            xy = self.split_point(key)
            pa, pb = T.p[key[0]], T.p[key[1]]
            near = [_dist(xy, T.p[w]) for tt in tris for w in T.tv[tt]
                    if w not in key and _in_diametral_circle(pa, pb, T.p[w])]
            if min(_dist(xy, pa), _dist(xy, pb)) < self.shortest:
                self._too_fine(xy)
            arc = self.arcs.get(T.sub[key])
            if arc is not None and _orient(pa, pb, xy) != -_orient(
                    pa, pb, arc[0]):
                # the arc is its chord in floating point here
                self._too_fine(xy)
            v = T.add_point(xy)
            # p. 13: the distance to the nearest encroaching mesh vertex,
            # or the radius of the diametral circle if only a rejected
            # circumcentre encroached
            self.r[v] = min(near) if near else 0.5 * _dist(pa, pb)
            if arc is not None:
                new = T.insert_off(v, key, tris)
            else:
                new = T.insert(v, T.cavity(T.p[v], tris[0], through=key),
                               through=key)
            self._check_count()
            self._new_vertex(v, new)
            for half in (_key(key[0], v), _key(v, key[1])):
                if self._encroached(half):
                    self._queue_sub(half)

    def refine(self) -> None:
        """Figure 38, lines 3-25."""
        T = self.T
        # the insertion radius of the vertices already there: the shortest
        # edge they have when refinement starts (p. 13: the length of the
        # shortest edge connected to v immediately after v is introduced)
        for t in range(len(T.tv)):
            if T.alive[t]:
                v = T.tv[t]
                for i in range(3):
                    a, b = v[(i + 1) % 3], v[(i + 2) % 3]
                    d = _dist(T.p[a], T.p[b])
                    for w in (a, b):
                        if d < self.r.get(w, math.inf):
                            self.r[w] = d
        for key in list(T.sub):
            if self._encroached(key):
                self._queue_sub(key)
        self.split_encroached()
        for t in range(len(T.tv)):
            if T.alive[t]:
                self._queue_if_bad(t)
        given_up: set = set()
        while self.qt:
            _, _, t = heapq.heappop(self.qt)
            if not T.alive[t] or t in given_up:
                continue
            a, b, c = (T.p[i] for i in T.tv[t])
            if (b[0] - a[0]) * (c[1] - a[1]) == (b[1] - a[1]) * (c[0] - a[0]):
                self._too_fine(T.centroid(t))
            cc = _circumcentre(a, b, c)
            if _dist(cc, a) < self.shortest:
                self._too_fine(cc)
            kind, where = T.toward(t, cc)
            if kind == "stuck":
                self.unsplittable += 1
                given_up.add(t)
                continue
            if kind == "blocked":
                hit = [where]
                cav = None
            else:
                cav = T.cavity(cc, where)
                hit = [_key(x, y) for x, y, _n, _s in T.boundary(cav)
                       if T.is_sub(x, y)
                       and _in_diametral_circle(T.p[x], T.p[y], cc)]
            if not hit:
                v = T.add_point(cc)
                self.r[v] = _dist(cc, a)        # the circumradius
                new = T.insert(v, cav)
                self._check_count()
                self._new_vertex(v, new)
                continue
            big = self._oversized(t)
            for key in hit:
                if big or self._split_permitted(key, t):
                    self._queue_sub(key)
            if self.qs:
                self.counter += 1
                heapq.heappush(self.qt, (-self.ratio2(t), self.counter, t))
                self.split_encroached()
            else:
                given_up.add(t)

    # -- the result --------------------------------------------------------
    def _arc_notes(self) -> dict:
        """The arcs: how many input pieces, the largest turn tau, and the
        bound of Pav and Walkington's Corollary 3 (p. 13) for that tau:
        their algorithm ends for an angle bound kappa < arcsin(1/(2 mu
        sqrt 2)) and arcsin(1/(2 zeta eta)), with eta, mu (p. 6) and zeta
        (Lemma 2, p. 8) functions of tau; as a ratio, B > 1/(2 sin kappa).
        Notes only (sin, tan): nothing is decided with them."""
        if not self.arcs:
            return {"arc_pieces": 0, "arc_turn": None, "arc_bound": None,
                    "arc_unproven": None}
        T = self.T
        tau = 0.0
        for k, (_c, r) in self.arcs.items():
            u, v = self.pairs[k]
            chord = _dist(T.p[u], T.p[v])
            tau = max(tau, 2.0 * math.asin(min(1.0, 0.5 * chord / r)))
        kappa, ratio = arc_bound(tau)
        return {
            "arc_pieces": len(self.arcs),
            "arc_turn": math.degrees(tau),
            "arc_bound": {"kappa": math.degrees(kappa), "ratio": ratio,
                          "met": math.sqrt(self.b2) > ratio},
            "arc_unproven": M.refine_note(M.REFINE_ARC_UNPROVEN,
                                          turn=math.degrees(tau),
                                          ratio=ratio),
        }

    def result(self, labels) -> QualityTriangulation:
        T = self.T
        skip = set(self.enclosing)
        node_of = {}
        nodes = []
        for i in range(len(T.p)):
            if i in skip:
                continue
            node_of[i] = len(nodes)
            nodes.append(Node(len(nodes), T.p[i][0], T.p[i][1]))
        elements = []
        above = []
        for t in range(len(T.tv)):
            if not T.alive[t]:
                continue
            seed = self.seeds[T.region[t]]
            e = Element(id=len(elements),
                        nodes=tuple(node_of[i] for i in T.tv[t]),
                        material_id=seed[2], region_index=seed[1])
            elements.append(e)
            r2 = self.ratio2(t)
            if r2 > self.b2:
                cx, cy = T.centroid(t)
                above.append({"element": e.id, "ratio": math.sqrt(r2),
                              "centroid": [cx, cy]})
        chains = []
        for k, (u, v) in enumerate(self.pairs):
            nbr: dict = {}
            for (a, b), seg in T.sub.items():
                if seg == k:
                    nbr.setdefault(a, []).append(b)
                    nbr.setdefault(b, []).append(a)
            chain, prev = [u], None
            while chain[-1] != v:
                here = chain[-1]
                nxt = next(x for x in nbr[here] if x != prev)
                prev = here
                chain.append(nxt)
            chains.append(tuple(node_of[i] for i in chain))
        notes = {
            "max_ratio": math.sqrt(self.b2),
            "size_bound": self.size is not None,
            "max_triangles": self.max_triangles,
            "input_vertices": self.n_input,
            "vertices": len(nodes),
            "triangles": len(elements),
            "vertices_added": [len(c) - 2 for c in chains],
            "above_ratio": above,
            "unsplittable": self.unsplittable,
            "min_input_angle": self.min_angle,
            "theorem_12_bound": (
                1.0 / (math.sqrt(2.0)
                       * math.sin(math.radians(self.min_angle) / 2.0))
                if self.min_angle is not None and self.min_angle <= 60.0
                else None),
            "length_unit": M.refine_note(M.REFINE_LENGTH_UNIT),
            "declined_splits": self.declined,
        }
        notes.update(self._arc_notes())
        mesh = Mesh(nodes=nodes, elements=elements)
        mesh.notes["quality_triangulation"] = notes
        return QualityTriangulation(mesh=mesh, segment_vertices=chains,
                                    segment_labels=list(labels), notes=notes)


def arc_bound(tau: float) -> tuple:
    """(kappa, B) of Pav and Walkington's Corollary 3 (p. 13) for curve
    pieces whose tangent turns at most ``tau`` radians: their algorithm
    ends if its angle bound is below kappa = min(arcsin(1/(2 mu sqrt 2)),
    arcsin(1/(2 zeta eta))), that is, for B > 1/(2 sin kappa). eta =
    (1 + tan(tau/2)) / (1 - tan(tau/2)) and mu = 1 / (1 - tan(tau/2))
    (p. 6); zeta = sqrt 2 sin(tau/2) / (sqrt(1 + sin tau) - 1) (Lemma 2,
    p. 8), which tends to sqrt 2 as tau tends to 0."""
    h = math.tan(0.5 * tau)
    eta, mu = (1.0 + h) / (1.0 - h), 1.0 / (1.0 - h)
    if tau > 0.0:
        zeta = (math.sqrt(2.0) * math.sin(0.5 * tau)
                / (math.sqrt(1.0 + math.sin(tau)) - 1.0))
    else:
        zeta = math.sqrt(2.0)
    kappa = min(math.asin(1.0 / (2.0 * mu * math.sqrt(2.0))),
                math.asin(1.0 / (2.0 * zeta * eta)))
    return kappa, 1.0 / (2.0 * math.sin(kappa))


def quality_triangulation(pslg, *, max_ratio: float = MIN_RATIO,
                          size: Optional[Callable[[float, float], float]]
                          = None,
                          max_triangles: int = 1_000_000
                          ) -> QualityTriangulation:
    """Mesh ``pslg`` (see :class:`PSLG`) with triangles whose
    circumradius-to-shortest-edge ratio is at most ``max_ratio`` (B; the
    smallest angle is then at least arcsin(1/2B), 20.7 degrees for the
    default sqrt 2; Shewchuk 2002a, p. 5) and whose edges are no longer
    than ``size(x, y)`` where it is given.

    Where two input segments meet at 60 degrees or less, the triangles
    next to that vertex may stay above B: the Terminator bounds every
    triangle by 1 / (sqrt 2 sin(phi / 2)), phi the smallest input angle
    (Theorem 12), and the notes list those left above B. ``max_triangles``
    stops a mesh that would grow beyond it, with a ``QualityMeshError``.

    The pieces of an arc (``PSLG.arcs``) are split on the arc; with arcs,
    no source proves that the refinement ends (see the module's notes on
    arcs, and ``arc_bound``/``arc_unproven`` in the notes).
    """
    try:
        b = float(max_ratio)
    except (TypeError, ValueError):
        b = float("nan")
    if not (math.isfinite(b) and b >= MIN_RATIO):
        raise QualityMeshError(M.REFINE_BAD_RATIO, ratio=b)
    pts, pairs, labels, seeds, voids = _read(pslg)
    arcs = _read_arcs(pslg, pts, pairs, labels, seeds, voids)
    r = _Refiner(pts, pairs, seeds, voids, b, size, int(max_triangles),
                 arcs)
    r.triangulate()
    r.recover()
    r.classify()
    r.analyse_angles()
    r.refine()
    return r.result(labels)
