# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.5 -- the two exact, scale-invariant quality measures of a triangle,
from Shewchuk, J. R. (2002), "What is a good linear finite element?"
(preprint of 31-12-2002), asked for by OGR FEM2D (its spec 003).

What is checked, and against what
---------------------------------
Nothing here is a capture of what the code prints. Each test holds to a
property the source states or to an identity that follows from it:

1. **One on the equilateral triangle.** Table 6 (p. 53) gives each measure
   with the constant that makes it "fair" (section 6.3, p. 51): its maximum
   is one, and the equilateral triangle reaches it. Checked on equilateral
   triangles of several sizes, turned and moved, whose coordinates are NOT
   exact in floating point -- that is where the radicand of the
   conditioning measure falls a hair below zero.
2. **Never above one**, on many random triangles (the same section 6.3).
3. **Zero on a degenerate triangle** (property 1 of section 6.3): three
   collinear vertices, and two coincident ones.
4. **Negative on an inverted triangle**, of the same magnitude: A is the
   signed area (table 1, p. 3; appendix A.1, which says A is positive
   counterclockwise).
5. **Invariant with scale and with rotation** (property 2): the measures
   depend on lengths and on the area only. The test turns; it does not
   reflect, because a reflection inverts the triangle (point 4).
6. **The conditioning measure is the stiffness matrix's.** An identity,
   not in the source in this form: for the linear triangle of the Laplace
   equation, whose element matrix is K = |A| (b b^T + c c^T) with b, c the
   gradients of the shape functions, the largest eigenvalue is
   lambda_max = (S + sqrt(S^2 - 48 A^2)) / (8 |A|), S the sum of the
   squared edges, so the unnormalised measure of table 4 is
   1 / (8 lambda_max). Here K is built from ``Element.shape_gradients``
   and its eigenvalues come from NumPy, which shares no code with the
   formula. Table 6 says the measure is "implicated in the condition
   number of the stiffness matrix for Poisson's equation".
7. **The mesh summary** reads the same measures, element by element, and
   counts an inverted element.

8. **The radicand of the conditioning measure is table 4's.** The code
   evaluates S^2 - 48 A^2 as 2((a^2-b^2)^2 + (b^2-c^2)^2 + (c^2-a^2)^2), the
   same number by Heron's formula, because the literal form loses half
   its digits next to the equilateral triangle (point 1 caught it:
   0.99999998). Checked against the literal form of the table, evaluated
   here in exact rational arithmetic on the floating-point coordinates.

Teeth (each one, put in by hand and taken out, fails the tests named):
dropping the 4 of 4|r_in| (1, 2 and 7); the radicand as the table writes
it, in floating point (1 and 8); abs() around A in the conditioning formula
(4 and 7); the exponent 2/3 as 1/2 (1, 2, 5 and 7); a factor 3 for the 2 of
the sum of squares (6 and 8: on the equilateral triangle the radicand is
zero, so point 1 cannot see it).
"""
from __future__ import annotations

import math
import random
from fractions import Fraction

import numpy as np

from ogr_core.fem import (Element, Mesh, Node, triangle_conditioning_quality,
                          triangle_gradient_quality)

MEASURES = (triangle_gradient_quality, triangle_conditioning_quality)


def _turned(points, angle, scale=1.0, dx=0.0, dy=0.0):
    c, s = math.cos(angle), math.sin(angle)
    return [(scale * (c * x - s * y) + dx, scale * (s * x + c * y) + dy)
            for x, y in points]


def _equilateral(side):
    return [(0.0, 0.0), (side, 0.0), (0.5 * side, 0.5 * math.sqrt(3.0) * side)]


def _random_triangles(n, seed):
    rnd = random.Random(seed)
    out = []
    while len(out) < n:
        p = [(rnd.uniform(-5.0, 5.0), rnd.uniform(-5.0, 5.0)) for _ in range(3)]
        (x1, y1), (x2, y2), (x3, y3) = p
        det = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)
        if abs(det) > 1e-3:
            out.append(p if det > 0 else [p[0], p[2], p[1]])
    return out


class TestTheFairProperties:
    def test_one_on_the_equilateral_triangle(self):
        for side in (1.0, 1e-3, 7.3, 2.5e4):
            for k in range(12):
                # moved by a few sides, not by a fixed distance: a triangle
                # of side 1e-3 at x = 15 is no longer equilateral in the
                # twelfth digit of its floating-point coordinates
                p = _turned(_equilateral(side), 0.37 * k,
                            dx=3.1 * k * side, dy=-1.7 * k * side)
                for measure in MEASURES:
                    q = measure(*p)
                    assert not math.isnan(q), (measure.__name__, side, k)
                    assert abs(q - 1.0) < 1e-12, (measure.__name__, side, k, q)

    def test_never_above_one(self):
        for p in _random_triangles(3000, seed=25):
            for measure in MEASURES:
                q = measure(*p)
                assert 0.0 < q <= 1.0 + 1e-12, (measure.__name__, p, q)

    def test_zero_on_a_degenerate_triangle(self):
        collinear = [(0.0, 0.0), (1.0, 1.0), (3.0, 3.0)]
        coincident = [(2.0, 1.0), (2.0, 1.0), (5.0, -4.0)]
        all_three = [(1.0, 1.0)] * 3
        for p in (collinear, coincident, all_three):
            for measure in MEASURES:
                assert measure(*p) == 0.0, (measure.__name__, p)

    def test_negative_on_an_inverted_triangle(self):
        for p in _random_triangles(500, seed=7):
            inverted = [p[0], p[2], p[1]]
            for measure in MEASURES:
                q, qi = measure(*p), measure(*inverted)
                assert q > 0.0 and qi < 0.0, (measure.__name__, p)
                assert abs(q + qi) <= 1e-12 * abs(q), (measure.__name__, p)

    def test_invariant_with_scale_and_rotation(self):
        for p in _random_triangles(300, seed=11):
            for measure in MEASURES:
                q = measure(*p)
                for scale, angle in ((1e-3, 0.0), (1e3, 1.1), (3.7, -2.4),
                                     (1.0, math.pi / 3)):
                    moved = _turned(p, angle, scale=scale, dx=10.0, dy=-4.0)
                    assert abs(measure(*moved) - q) <= 1e-9 * abs(q), (
                        measure.__name__, p, scale, angle)


class TestTheConditioningMeasure:
    def test_the_conditioning_measure_is_the_stiffness_matrix_s(self):
        for p in _random_triangles(400, seed=3):
            mesh = Mesh(nodes=[Node(i, x, y) for i, (x, y) in enumerate(p)],
                        elements=[Element(0, (0, 1, 2))])
            e = mesh.elements[0]
            dndx, dndy, area = e.shape_gradients(mesh)
            b, c = np.array(dndx), np.array(dndy)
            stiffness = area * (np.outer(b, b) + np.outer(c, c))
            lmax = float(max(np.linalg.eigvalsh(stiffness)))
            expected = 4.0 * math.sqrt(3.0) / (8.0 * lmax)
            assert abs(e.conditioning_quality(mesh) - expected) <= 1e-11 * expected

    def test_its_radicand_is_the_one_of_table_4(self):
        near_equilateral = [_turned(_equilateral(s), 0.37 * k,
                                    dx=k * s, dy=-k * s)
                            for s in (1.0, 7.3) for k in range(12)]
        for p in _random_triangles(400, seed=5) + near_equilateral:
            (ax, ay), (bx, by), (cx, cy) = [(Fraction(x), Fraction(y))
                                            for x, y in p]
            area = ((ax - cx) * (by - cy) - (bx - cx) * (ay - cy)) / 2
            s = ((bx - cx) ** 2 + (by - cy) ** 2 + (cx - ax) ** 2
                 + (cy - ay) ** 2 + (ax - bx) ** 2 + (ay - by) ** 2)
            literal = s * s - 48 * area * area            # table 4, exact
            assert literal >= 0
            expected = 4.0 * math.sqrt(3.0) * float(area) / (
                float(s) + math.sqrt(float(literal)))
            got = triangle_conditioning_quality(*p)
            assert abs(got - expected) <= 1e-13 * abs(expected), (p, got)


class TestTheMeshSummary:
    def test_the_mesh_summary_reads_the_element_measures(self):
        pts = [(0.0, 0.0), (2.0, 0.0), (1.0, math.sqrt(3.0)), (3.0, 1.5)]
        mesh = Mesh(nodes=[Node(i, x, y) for i, (x, y) in enumerate(pts)],
                    elements=[Element(0, (0, 1, 2)),     # equilateral, CCW
                              Element(1, (1, 2, 3))])    # clockwise: inverted
        s = mesh.quality_measures()
        g = [e.gradient_quality(mesh) for e in mesh.elements]
        c = [e.conditioning_quality(mesh) for e in mesh.elements]
        assert s["elements"] == 2 and s["inverted"] == 1
        assert s["min_gradient_quality"] == min(g) < 0.0
        assert s["mean_gradient_quality"] == sum(g) / 2
        assert s["min_conditioning_quality"] == min(c) < 0.0
        assert s["mean_conditioning_quality"] == sum(c) / 2
        assert abs(max(g) - 1.0) < 1e-12 and abs(max(c) - 1.0) < 1e-12
        assert Mesh().quality_measures() == {"elements": 0}
