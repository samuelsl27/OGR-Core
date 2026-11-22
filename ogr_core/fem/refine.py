# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
Quality triangulation of a planar straight line graph by Delaunay
refinement (v0.2.5; asked for by OGR FEM2D, decision D2 of its spec 003,
because the seepage of OGR Slip2D needs the same thing).

Sources (page numbers are those printed on the preprints):

* Shewchuk, J. R. (2002a). "Delaunay refinement algorithms for triangular
  mesh generation". Computational Geometry 22, 21-74 (preprint of
  21-5-2001). Section 3.1, pp. 7-11; Lemma 1, p. 9; Theorem 4, p. 16;
  Appendix A, figures 38 and 39, pp. 47-51.
* Ruppert, J. (1995). "A Delaunay refinement algorithm for quality
  2-dimensional mesh generation". J. Algorithms 18(3), 548-585: starting
  from an unconstrained Delaunay triangulation and recovering the missing
  segments by splitting them at their midpoints.

``generate_mesh`` (``generator.py``) is NOT this: it stays as it was, so
that OGR Slip2D meshes as before, bit for bit.

What it does
------------
1. **Delaunay triangulation of the input vertices**, in their order, by
   Bowyer-Watson insertion inside a large enclosing triangle.
2. **Segment recovery** (Ruppert): a segment that is not an edge of the
   triangulation is split at its midpoint until all its pieces are edges.
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
4. **Refinement** (section 3.1 and figure 38, without the Terminator):
   encroached subsegments are split first, at their midpoint. A subsegment
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

Determinism
-----------
The same input gives the same mesh, bit for bit, on every platform. The
geometric predicates (orientation, in-circle, in-diametral-circle) are
exact: a floating-point filter whose threshold is several orders above the
rounding of the expression, and exact rational arithmetic
(``fractions.Fraction``) below it. The new points (midpoints,
circumcentres) use only + - * /, which IEEE 754 rounds the same everywhere.
No queue or loop depends on the order of a ``set``.

Author: Samuel Sáez López (UPCT)
"""
from __future__ import annotations

import bisect
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

    Any object with these four attributes will do (OGR FEM2D passes its
    own).
    """
    vertices: Sequence = ()
    segments: Sequence = ()
    seeds: Sequence = ()
    voids: Sequence = ()


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
        bnd = self.boundary(cav, through)
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
        if through is not None:
            seg = self.sub.pop(through)
            self.sub[_key(through[0], q)] = seg
            self.sub[_key(q, through[1])] = seg
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


# ======================================================================
# The algorithm
# ======================================================================
class _Refiner:

    def __init__(self, pts, pairs, seeds, voids, max_ratio, size,
                 max_triangles):
        self.n_input = len(pts)
        self.pairs = pairs
        self.seeds = seeds
        self.voids = voids
        self.b2 = max_ratio * max_ratio
        self.size = size
        self.max_triangles = max_triangles
        self.unsplittable = 0
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx, cy = 0.5 * (min(xs) + max(xs)), 0.5 * (min(ys) + max(ys))
        span = max(max(xs) - min(xs), max(ys) - min(ys))
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
        return sq[1] * sq[2] / (4.0 * det * det)

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
            pa, pb = T.p[a], T.p[b]
            m = T.add_point((pa[0] + 0.5 * (pb[0] - pa[0]),
                             pa[1] + 0.5 * (pb[1] - pa[1])))
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

    def split_point(self, key):
        """Where subsegment ``key`` is split: its midpoint (section 3.1),
        as a + (b - a)/2, so a segment on x = 0 keeps x = 0."""
        a, b = (self.T.p[i] for i in key)
        return (a[0] + 0.5 * (b[0] - a[0]), a[1] + 0.5 * (b[1] - a[1]))

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
            v = T.add_point(self.split_point(key))
            new = T.insert(v, T.cavity(T.p[v], tris[0], through=key),
                           through=key)
            self._check_count()
            self._new_vertex(v, new)
            for half in (_key(key[0], v), _key(v, key[1])):
                if self._encroached(half):
                    self._queue_sub(half)

    def _split_permitted(self, key, t) -> bool:
        """Figure 38, SPLITPERMITTED: always, in Ruppert's algorithm."""
        return True

    def refine(self) -> None:
        """Figure 38, lines 3-25."""
        T = self.T
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
            cc = _circumcentre(a, b, c)
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
        }
        mesh = Mesh(nodes=nodes, elements=elements)
        mesh.notes["quality_triangulation"] = notes
        return QualityTriangulation(mesh=mesh, segment_vertices=chains,
                                    segment_labels=list(labels), notes=notes)


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

    The guarantee of the source holds when no two segments meet at less
    than 60 degrees (Theorem 4); below that, the refinement may not end,
    and ``max_triangles`` stops it with a ``QualityMeshError``.
    """
    try:
        b = float(max_ratio)
    except (TypeError, ValueError):
        b = float("nan")
    if not (math.isfinite(b) and b >= MIN_RATIO):
        raise QualityMeshError(M.REFINE_BAD_RATIO, ratio=b)
    pts, pairs, labels, seeds, voids = _read(pslg)
    r = _Refiner(pts, pairs, seeds, voids, b, size, int(max_triangles))
    r.triangulate()
    r.recover()
    r.classify()
    r.refine()
    return r.result(labels)
