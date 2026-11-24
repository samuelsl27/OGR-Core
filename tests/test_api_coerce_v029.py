# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.9 — ``ogr_core.api.coerce`` turns a JSON value into the declared type
and refuses anything that would need a guess.

From OGR Slip2D's ``ogr_api/coerce.py`` (v0.1.486), whose tests exercised it
through Slip2D's settings. Here the dataclasses are the test's own.
Invariants:

* **no guess**: 2.5 is not an int (3.0 is), 0/1 are not booleans, NaN and
  infinity are not numbers a setting may hold, a string is not a list;
* an enum is found by itself, its value or its name in any case; a
  ``Literal`` only by one of its values; ``Optional`` lets null through
  and nothing else extra;
* **a dotted path walks dataclass fields only**: a typo is an error with
  the closest name, a retired name says what replaced it, a path through a
  value is refused;
* **each option of** ``resolve_field`` **moves its message** (rule 7):
  ``root_name``, ``noun``, ``example`` and ``lister``. With Slip2D's values
  the sentence is Slip2D's, byte for byte.
"""
from __future__ import annotations

import dataclasses
import enum
import math
from typing import Literal, Optional


class Kind(enum.Enum):
    ALPHA = "alpha"
    BETA = "beta"


@dataclasses.dataclass
class Methods:
    num_slices: int = 25
    tolerance: float = 1e-3


@dataclasses.dataclass
class Settings:
    methods: Methods = dataclasses.field(default_factory=Methods)
    verbose: bool = False
    kind: Kind = Kind.ALPHA


Wide = dataclasses.make_dataclass(
    "Wide", [(f"f{i:02d}", int, 0) for i in range(30)])


def _refused(fn):
    from ogr_core.api import InvalidArgument
    try:
        fn()
    except InvalidArgument as exc:
        return exc
    raise AssertionError("InvalidArgument was not raised")


class TestNoGuess:
    def test_int(self):
        from ogr_core.api.coerce import coerce_value
        assert coerce_value(3.0, int, "n") == 3
        assert coerce_value("4", int, "n") == 4
        err = _refused(lambda: coerce_value(2.5, int, "n"))
        assert err.message == "n must be an integer, got 2.5."
        assert err.message.code == "api.value.int"
        _refused(lambda: coerce_value(True, int, "n"))

    def test_bool(self):
        from ogr_core.api.coerce import coerce_value
        assert coerce_value("TRUE", bool, "b") is True
        err = _refused(lambda: coerce_value(1, bool, "b"))
        assert err.message == "b must be true or false, got 1."

    def test_float(self):
        from ogr_core.api.coerce import coerce_value
        assert coerce_value("2.5", float, "f") == 2.5
        err = _refused(lambda: coerce_value(math.nan, float, "f"))
        assert err.message == "f must be finite, got nan."
        _refused(lambda: coerce_value(math.inf, float, "f"))
        _refused(lambda: coerce_value(False, float, "f"))
        err = _refused(lambda: coerce_value("x", float, "f"))
        assert err.message == "f must be a number, got 'x'."

    def test_containers_and_strings(self):
        from ogr_core.api.coerce import coerce_value
        assert coerce_value([1, 2.0], list[int], "L") == [1, 2]
        assert coerce_value([1], tuple[int, ...], "T") == (1,)
        err = _refused(lambda: coerce_value("ab", list[int], "L"))
        assert err.message == "L must be a list, got 'ab'."
        err = _refused(lambda: coerce_value([1, 2.5], list[int], "L"))
        assert err.message == "L[1] must be an integer, got 2.5."
        _refused(lambda: coerce_value(3, dict, "d"))
        _refused(lambda: coerce_value(3, str, "s"))
        err = _refused(lambda: coerce_value({}, Methods, "methods"))
        assert err.message == ("methods is a whole section; set its fields "
                               "one by one (e.g. 'methods.<field>').")

    def test_enum_literal_and_optional(self):
        from ogr_core.api.coerce import coerce_enum, coerce_value
        assert coerce_value("beta", Kind, "k") is Kind.BETA
        assert coerce_value("ALPHA", Kind, "k") is Kind.ALPHA
        assert coerce_enum(Kind.BETA, Kind) is Kind.BETA
        err = _refused(lambda: coerce_value("alpa", Kind, "k"))
        assert err.message == "k: 'alpa' is not one of ['alpha', 'beta']."
        assert err.hint == "Did you mean 'alpha'?"
        assert coerce_value("a", Literal["a", "b"], "l") == "a"
        _refused(lambda: coerce_value("A", Literal["a", "b"], "l"))
        assert coerce_value(None, Optional[int], "o") is None
        err = _refused(lambda: coerce_value("z", Optional[int], "o"))
        assert err.message == "o: 'z' is not a integer | null."
        err = _refused(lambda: coerce_value(None, int, "n"))
        assert err.message == "n cannot be null."

    def test_points(self):
        from ogr_core.api.coerce import point, points
        assert point({"x": 1, "y": "2"}) == (1.0, 2.0)
        err = _refused(lambda: point([1], "p"))
        assert err.message == "p must be [x, y], got [1]."
        err = _refused(lambda: point([1, "x"], "p"))
        assert err.message == "p.y must be a number, got 'x'."
        assert points([[0, 0], [1, 1]]) == [(0.0, 0.0), (1.0, 1.0)]
        err = _refused(lambda: points([[0, 0]], "ps"))
        assert err.message == "ps needs at least 2 points, got 1."
        assert err.message.args["minimum"] == 2


class TestADottedPath:
    def test_it_resolves_to_the_field_and_its_type(self):
        from ogr_core.api.coerce import resolve_field
        s = Settings()
        parent, name, hint = resolve_field(s, "methods.num_slices")
        assert parent is s.methods and name == "num_slices" and hint is int

    def test_a_typo_names_the_closest(self):
        from ogr_core.api.coerce import resolve_field
        err = _refused(lambda: resolve_field(Settings(), "methods.num_slice"))
        assert err.message == "'num_slice' is not a field of methods."
        assert err.hint == "Did you mean 'num_slices'?"

    def test_nothing_close_lists_the_fields(self):
        from ogr_core.api.coerce import resolve_field
        err = _refused(lambda: resolve_field(Settings(), "methods.zzz"))
        assert err.hint == "Fields of methods: num_slices, tolerance."

    def test_a_path_through_a_value_and_a_retired_name(self):
        from ogr_core.api.coerce import resolve_field
        err = _refused(lambda: resolve_field(Settings(), "verbose.deeper"))
        assert err.message == ("'verbose' is a value, not a section; "
                               "'verbose.deeper' goes too deep.")
        err = _refused(lambda: resolve_field(
            Settings(), "methods.old", retired={"old": "Use tolerance."}))
        assert err.message == "'methods.old' is not a setting any more."
        assert err.hint == "Use tolerance."


class TestTheOptionsMoveTheMessage:
    def test_root_name(self):
        from ogr_core.api.coerce import resolve_field
        a = _refused(lambda: resolve_field(Settings(), "zzz"))
        b = _refused(lambda: resolve_field(Settings(), "zzz",
                                           root_name="model"))
        assert a.message == "'zzz' is not a field of settings."
        assert b.message == "'zzz' is not a field of model."

    def test_noun_and_example(self):
        from ogr_core.api.coerce import resolve_field
        a = _refused(lambda: resolve_field(Settings(), ""))
        assert a.message == "An empty setting path."
        assert a.hint == "Use 'section.field'."
        # Slip2D's values give Slip2D's sentence
        b = _refused(lambda: resolve_field(Settings(), "",
                                           example="methods.num_slices"))
        assert b.hint == "Use 'section.field', e.g. 'methods.num_slices'."
        c = _refused(lambda: resolve_field(Settings(), "", noun="property"))
        assert c.message == "An empty property path."
        d = _refused(lambda: resolve_field(
            Settings(), "old", retired={"old": "x"}, noun="property"))
        assert d.message == "'old' is not a property any more."

    def test_lister(self):
        from ogr_core.api.coerce import resolve_field
        shown = ", ".join(f"f{i:02d}" for i in range(25))
        a = _refused(lambda: resolve_field(Wide(), "qqq"))
        assert a.hint == f"Fields of settings: {shown} (+5 more)."
        b = _refused(lambda: resolve_field(Wide(), "qqq",
                                           lister="settings_get"))
        assert b.hint == (f"Fields of settings: {shown} (+5 more; "
                          f"settings_get lists them).")
        assert b.hint.code == "api.field.listing.more_tool"


class TestTypeNames:
    def test_describe_type(self):
        from ogr_core.api.coerce import describe_type
        for hint, name in [
                (int, "integer"), (float, "number"), (bool, "boolean"),
                (str, "string"), (Optional[float], "number | null"),
                (list[int], "list[integer]"), (dict, "object"),
                (Literal["a", 1], "'a' | 1"), (Kind, "enum(alpha | beta)")]:
            assert describe_type(hint) == name, hint
