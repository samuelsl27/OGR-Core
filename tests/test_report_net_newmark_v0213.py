# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.13 — the report says of the critical surface of a Newmark run with
upslope sliding what the run did (OGR Slip2D 0.1.499, its D437).

Without upslope sliding the displacement of a rigid block does not increase
with its critical acceleration (Newmark, 1965), so the surface of the lowest
Ky — what the search minimises — is the one that moves the most. With upslope
sliding the displacement is net (downslope minus upslope) and that premise
fails: on Slip2D's demo slope (c = 12 kPa, 5×5×6 grid, Bishop, a 0.3 g 2 Hz
sine for 4 s and 2 s of calm) the surface of the lowest Ky (0.1137) moved
0.236 cm and 4 of 152 moved more, the most 1.269 cm with a Ky of 0.1543.
Since 0.1.499 such a run publishes the surface of the largest net
displacement and says so on its result, ``net_newmark = True``; the row
«the one with the lowest Ky of this method» was then false in the PDF.

Invariants:

* with ``net_newmark`` true the row says the largest NET displacement;
* with the field false, or absent (a result of an older program, a Ky run),
  the row is the one of always, byte for byte;
* rule 7: the field moves the row, and ``generate_report`` passes the
  method's result to the rows (asked through ``translate``, which every
  string of the PDF goes through);
* the three docstrings that said the critical surface is the lowest-Ky one
  carry the upslope exception.
"""
from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace

OLD_ROW = ("Critical surface", "the one with the lowest Ky of this method")
NEW_ROW = ("Critical surface",
           "the one with the largest net Newmark displacement of this method")


def _crit(newmark=True):
    details = {"ky": 0.1543}
    if newmark:
        details["newmark_displacement"] = 0.01269
    return SimpleNamespace(fos=1.3, details=details, surface=None,
                           slices=SimpleNamespace(slices=[],
                                                  wedge_fields=None))


def _result(newmark=True, **extra):
    return SimpleNamespace(critical=_crit(newmark), objective="ky",
                           valid_count=152, invalid_count=0, **extra)


def _rows(res, T=None):
    from ogr_core.project import Project
    from ogr_core.project.reported import reported_caption
    from ogr_core.report.report_generator import _seismic_rows
    caption = reported_caption(res)
    p = Project("Newmark")
    if T is None:
        return _seismic_rows(res.critical, caption, p, res=res)
    return _seismic_rows(res.critical, caption, p, T, res=res)


class TestTheRow:
    def test_net_newmark_says_the_largest_net_displacement(self):
        rows = _rows(_result(net_newmark=True))
        assert rows[-1] == NEW_ROW
        assert OLD_ROW not in rows

    def test_without_the_field_it_is_the_row_of_always(self):
        assert _rows(_result())[-1] == OLD_ROW

    def test_with_the_field_false_it_is_the_row_of_always(self):
        assert _rows(_result(net_newmark=False))[-1] == OLD_ROW

    def test_the_field_moves_the_row(self):
        # Rule 7: the same result but for the field gives another row, and
        # only that row changes.
        on = _rows(_result(net_newmark=True))
        off = _rows(_result(net_newmark=False))
        assert on[-1] != off[-1]
        assert on[:-1] == off[:-1]

    def test_without_a_result_it_is_the_row_of_always(self):
        # A caller of before this version passes no ``res``.
        from ogr_core.project import Project
        from ogr_core.report.report_generator import _seismic_rows
        rows = _seismic_rows(_crit(), "newmark", Project("Newmark"))
        assert rows[-1] == OLD_ROW

    def test_a_ky_run_keeps_its_rows(self):
        rows = _rows(_result(newmark=False))
        assert [r[0] for r in rows] == ["Critical seismic coefficient",
                                        "Critical surface"]
        assert rows[-1] == OLD_ROW

    def test_it_goes_through_the_translation(self):
        es = {NEW_ROW[1]: "la de mayor desplazamiento neto"}
        rows = _rows(_result(net_newmark=True), T=lambda t: es.get(t, t))
        assert rows[-1] == ("Critical surface",
                            "la de mayor desplazamiento neto")


class TestTheReport:
    @staticmethod
    def _strings(res):
        from ogr_core.project import Project
        from ogr_core.report.report_generator import generate_report
        seen = []

        def T(text):
            seen.append(text)
            return text
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "report.pdf")
            generate_report(Project("Newmark"), {"bishop": res}, out,
                            translate=T)
            assert os.path.getsize(out) > 0
        return seen

    def test_the_pdf_writes_the_row_of_the_result(self):
        on = self._strings(_result(net_newmark=True))
        off = self._strings(_result(net_newmark=False))
        assert NEW_ROW[1] in on and OLD_ROW[1] not in on
        assert OLD_ROW[1] in off and NEW_ROW[1] not in off


class TestTheDocstrings:
    def test_they_carry_the_upslope_exception(self):
        from ogr_core.project import reported
        from ogr_core.project.settings import SeismicAnalysisSettings
        from ogr_core.report.report_generator import _seismic_rows
        for doc in (SeismicAnalysisSettings.__doc__, reported.__doc__,
                    _seismic_rows.__doc__):
            assert "upslope" in doc
            assert "net" in doc and "D437" in doc
