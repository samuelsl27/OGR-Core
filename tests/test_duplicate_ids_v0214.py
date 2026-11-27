# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.14 — ids two items of a file share, and Delete by identity (OGR Slip2D,
its D445, the owner's decision of 2026-11-27).

``Project.from_dict`` accepted without a word two boundaries with the same
``Boundary.id``, two with the same ``Polyline.id`` (every ``.ogr`` with a
Copy Boundary saved between Slip2D 0.1.59 and 0.1.455) and two user surfaces
with the same id. And ``remove_boundary`` filtered BY ID, so Delete in the
window took both boundaries away and Undo gave one back: measured in Slip2D
0.1.485, 0 of 2 left, 1 of 2 back (``_auditoria/P10_D445/medir_d445.py``).

Invariants:

* reading a file with a repeated id gives a coded note naming the id and
  its items, and never refuses it;
* a repeated ``Polyline.id`` is renewed for all but the first; a repeated
  ``Boundary.id`` or user-surface id is NOT (the links read it);
* Delete removes the boundary it is given, by identity, and Undo puts it
  back in its place;
* the ids of a file without repeats do not move by a bit through
  read and save.
"""
from __future__ import annotations

import json


def _lens_project():
    from ogr_core.geometry import Boundary, Polyline, Vertex
    from ogr_core.geometry import BoundaryType as BT
    from ogr_core.project.demo import build_demo_project
    p = build_demo_project()
    p.add_boundary(Boundary(
        polyline=Polyline([Vertex(30, 2), Vertex(32, 2), Vertex(32, 3),
                           Vertex(30, 3)], closed=True),
        btype=BT.MATERIAL, material_id=p.materials[0].id))
    return p


def _through_a_file(data):
    from ogr_core.project import Project
    return Project.from_dict(json.loads(json.dumps(data)))


def _codes(notes):
    return [n.code for n in notes]


def _twin_boundary_file():
    """The first case of the measurement: the lens and a twin of it, moved
    5 m to the right, with the lens's Boundary.id and its own polyline id."""
    d = _lens_project().to_dict()
    twin = json.loads(json.dumps(d["boundaries"][-1]))
    twin["polyline"]["vertices"] = [[x + 5, y]
                                    for x, y in twin["polyline"]["vertices"]]
    twin["polyline"]["id"] += "-twin"
    d["boundaries"].append(twin)
    return d, twin["id"]


class TestTwoBoundariesWithOneId:
    def test_the_reading_says_it_and_renews_nothing(self):
        from ogr_core.project import messages as M
        d, bid = _twin_boundary_file()
        p = _through_a_file(d)
        assert len(p.boundaries) == len(d["boundaries"])
        assert [b.id for b in p.boundaries] == [b["id"]
                                                for b in d["boundaries"]]
        assert _codes(p.read_notes) == [M.DUPLICATE_BOUNDARY_ID]
        note = p.read_notes[0]
        assert note.args["id"] == bid
        assert str(note) == (
            f"The boundaries Material Boundary #1, Material Boundary #2 "
            f"share the id '{bid}': whatever refers to that id (the water "
            "surface or the anisotropic surface of a material, a support, a "
            "face of Sarma's method) may read either of them.")

    def test_delete_takes_one_and_undo_puts_it_back_in_its_place(self):
        from ogr_core.project.commands import (CommandStack,
                                               RemoveBoundaryCommand)
        d, bid = _twin_boundary_file()
        p = _through_a_file(d)
        before = list(p.boundaries)
        second = before[-1]
        first = before[-2]
        stack = CommandStack()
        stack.do(p, RemoveBoundaryCommand(boundary=second))
        assert sum(b.id == bid for b in p.boundaries) == 1
        assert first in p.boundaries and second not in p.boundaries
        stack.undo(p)
        assert p.boundaries == before
        assert all(a is b for a, b in zip(p.boundaries, before))
        # and the first one, from the middle of the list, too
        stack.do(p, RemoveBoundaryCommand(boundary=first))
        assert [b for b in p.boundaries if b.id == bid] == [second]
        stack.undo(p)
        assert all(a is b for a, b in zip(p.boundaries, before))

    def test_remove_boundary_by_id_takes_only_the_first(self):
        d, bid = _twin_boundary_file()
        p = _through_a_file(d)
        second = p.boundaries[-1]
        p.remove_boundary(bid)
        assert [b for b in p.boundaries if b.id == bid] == [second]

    def test_the_rule_answers_on_a_live_model_too(self):
        from ogr_core.project import messages as M
        from ogr_core.project.rules import duplicate_id_notes
        d, _bid = _twin_boundary_file()
        p = _through_a_file(d)
        assert _codes(duplicate_id_notes(p)) == [M.DUPLICATE_BOUNDARY_ID]
        p.boundaries.pop()
        assert duplicate_id_notes(p) == []


class TestTwoPolylinesWithOneId:
    @staticmethod
    def _old_copy_file():
        """The second case: a copy as Slip2D 0.1.455 saved it, with its own
        Boundary.id and the polyline id of the original."""
        from ogr_core.geometry import Boundary, Vertex
        p = _lens_project()
        lens = p.boundaries[-1]
        copy = Boundary.from_dict(lens.to_dict())
        copy.id = "copy-of-0.1.455"
        copy.polyline.vertices = [Vertex(v.x + 2.0, v.y + 2.0)
                                  for v in lens.polyline.vertices]
        p.add_boundary(copy)
        return p.to_dict(), lens.polyline.id

    def test_it_is_renewed_on_reading_with_the_note(self):
        from ogr_core.project import messages as M
        d, pid = self._old_copy_file()
        p = _through_a_file(d)
        pids = [b.polyline.id for b in p.boundaries]
        assert len(set(pids)) == len(pids)
        # the first keeps its id, the copy gets a new one
        assert p.boundaries[-2].polyline.id == pid
        assert p.boundaries[-1].polyline.id != pid
        assert _codes(p.read_notes) == [M.POLYLINE_ID_RENEWED]
        assert p.read_notes[0].args["id"] == pid
        assert "Material Boundary #2" in p.read_notes[0]

    def test_nothing_else_moves(self):
        d, _pid = self._old_copy_file()
        out = _through_a_file(d).to_dict()
        d["boundaries"][-1]["polyline"].pop("id")
        out["boundaries"][-1]["polyline"].pop("id")
        assert json.dumps(out, sort_keys=True) == json.dumps(
            d, sort_keys=True)

    def test_saved_again_it_reads_without_a_note(self):
        d, _pid = self._old_copy_file()
        again = _through_a_file(_through_a_file(d).to_dict())
        assert again.read_notes == []


class TestTwoUserSurfacesWithOneId:
    def test_the_note_and_the_ids_kept(self):
        from ogr_core.geometry.user_polyline import UserPolylineSurface
        from ogr_core.project import messages as M
        p = _lens_project()
        a = UserPolylineSurface.from_points([(5, 25), (20, 10), (40, 15)])
        b = UserPolylineSurface.from_points([(6, 25), (21, 9), (40, 15)],
                                            id=a.id)
        p.user_polylines = [a, b]
        r = _through_a_file(p.to_dict())
        assert [s.id for s in r.user_polylines] == [a.id, a.id]
        assert _codes(r.read_notes) == [M.DUPLICATE_USER_SURFACE_ID]
        assert str(r.read_notes[0]) == (
            f"The user surfaces user polyline #1, user polyline #2 share "
            f"the id '{a.id}': whatever refers to that id may read either of "
            "them.")

    def test_a_circle_and_a_polyline_too(self):
        from ogr_core.geometry.slip_circle import SlipCircle
        from ogr_core.geometry.user_polyline import UserPolylineSurface
        from ogr_core.project import messages as M
        p = _lens_project()
        c = SlipCircle(centre_x=25, centre_y=40, radius=30)
        p.user_surfaces = [c]
        p.user_polylines = [UserPolylineSurface.from_points(
            [(5, 25), (20, 10), (40, 15)], id=c.id)]
        r = _through_a_file(p.to_dict())
        assert _codes(r.read_notes) == [M.DUPLICATE_USER_SURFACE_ID]
        assert "user circle #1, user polyline #1" in r.read_notes[0]


class TestAFileWithoutRepeats:
    def test_no_note_and_not_a_bit_moves(self):
        p = _lens_project()
        d = json.loads(json.dumps(p.to_dict()))
        r = _through_a_file(d)
        assert r.read_notes == []
        assert json.dumps(r.to_dict(), sort_keys=True) == json.dumps(
            d, sort_keys=True)

    def test_a_model_not_read_has_no_notes(self):
        from ogr_core.project import Project
        assert Project("x").read_notes == []
        assert "read_notes" not in Project("x").to_dict()


class TestTheNotesAreCoded:
    def test_they_render_from_their_template(self):
        from ogr_core.messages import render
        from ogr_core.project.messages import RULES
        d, _bid = _twin_boundary_file()
        note = _through_a_file(d).read_notes[0]
        assert render(RULES, note.code, note.args, "") == str(note)

    def test_a_name_of_its_own_is_said(self):
        d, _bid = _twin_boundary_file()
        d["boundaries"][-1]["name"] = "Clay lens"
        note = _through_a_file(d).read_notes[0]
        assert "Material Boundary #1, 'Clay lens' (Material Boundary #2)" \
            in note
