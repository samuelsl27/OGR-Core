# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.10 — the report's row for Sarma's number of wedges says it is the
number ASKED FOR, not the least (OGR Slip2D, its D454, v0.1.488).

A surface may get more wedges than asked for (a vertex, a contact or a
water-table cut adds a boundary) and, since Slip2D v0.1.488, fewer only
where a uniform division is dropped on a straight stretch of one
Mohr-Coulomb material. «Least Number of Wedges» said the opposite of the
first half. Invariants:

* the row is «Number of Wedges Asked For», with the setting's value, and
  it goes through the program's translation like every other row;
* neither the row nor the docstring of ``SarmaSettings`` says «least» of
  the number of wedges any more.
"""
from __future__ import annotations


def _rows(n, T=None):
    from ogr_core.project import Project
    from ogr_core.report.report_generator import _sarma_settings_rows
    p = Project("Sarma")
    p.settings.sarma.num_slices = n
    return _sarma_settings_rows(p) if T is None else _sarma_settings_rows(p, T)


class TestTheRow:
    def test_it_is_the_number_asked_for_with_its_value(self):
        rows = _rows(7)
        assert rows[0] == ("Number of Wedges Asked For", 7)
        assert _rows(31)[0][1] == 31
        assert not any("Least" in str(r[0]) for r in rows)

    def test_it_goes_through_the_translation(self):
        es = {"Number of Wedges Asked For": "Número de cuñas pedido"}
        rows = _rows(7, T=lambda t: es.get(t, t))
        assert rows[0] == ("Número de cuñas pedido", 7)


class TestTheDocstring:
    def test_it_says_asked_for_and_not_least(self):
        from ogr_core.project.settings import SarmaSettings
        doc = SarmaSettings.__doc__
        assert "ASKED FOR" in doc
        assert "LEAST number" not in doc and "least number" not in doc
