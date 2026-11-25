# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
OGR Core 0.2.11 (D429) — four readers put another value in place of one
they did not know, said nowhere, and a unit weight or a name of another
JSON type opened.

Measured with 0.2.10 by the session of OGR Slip2D, changing one value of a
project's JSON: a permeability model ``"future_model"`` was read as
constant k, a drawdown envelope of kind ``"future"`` as none, a grid
interpolated by ``"kriging"`` as IDW, a record in ``"furlongs"`` as g; a
unit weight ``"x"`` opened and failed in the analysis, a name ``5`` opened
with it. The owner's decision: refused when the file is read, by a code.

Invariants:

* each of those values is refused with a ``ValueError`` that carries its
  code and its values; the reference is the list of values of each
  enumeration or field, not a capture;
* a key that is absent reads as it always did (constant k, no envelope,
  TPS, g); ``unsaturated_model`` absent or ``"saturated"`` is constant k;
* a null written where the writer never writes one is a value, not an
  absence, and is refused (the owner's decision, 2026-11-25); the envelope,
  which the writer does write as null, keeps reading null as none;
* a unit weight, a saturated unit weight and a name of another JSON type
  are refused by ``check_shape`` with the item's number; numbers and text
  open, and a valid file opens with the same JSON.
"""
from __future__ import annotations

import copy
import json


# ----------------------------------------------------------------------
def _project():
    """A project with every reader of D429 in it: a material with a
    permeability model and a drawdown envelope, a grid and a record."""
    from ogr_core.hydraulic.hydraulic_properties import (
        HydraulicProperties, PermeabilityModel)
    from ogr_core.hydraulic.water_pressure_grid import WaterPressureGrid
    from ogr_core.loads.seismic_record import AccelerationUnit, SeismicRecord
    from ogr_core.materials import Material, MohrCoulomb
    from ogr_core.materials.drawdown_envelopes import REnvelope
    from ogr_core.project import Project

    p = Project("D429")
    m = Material(name="Clay", strength=MohrCoulomb(cohesion=10,
                                                     friction_angle=25),
                 unit_weight=19.0, sat_unit_weight=20.0,
                 drawdown_envelope=REnvelope(c_r=5.0, phi_r_deg=20.0))
    m.hydraulic = HydraulicProperties(model=PermeabilityModel.GARDNER)
    p.materials = [m]
    p.water_pressure_grid = WaterPressureGrid(
        points=[(0.0, 0.0, 1.0), (10.0, 0.0, 2.0), (0.0, 10.0, 3.0),
                (10.0, 10.0, 1.5)], interpolation="tps")
    p.seismic_records = [SeismicRecord(
        name="R", dt=0.01, accelerations=[0.0, 0.1, -0.1],
        source_unit=AccelerationUnit.CM_S2)]
    return p


def _data():
    # through JSON, as a file is
    return json.loads(json.dumps(_project().to_dict()))


def _open(data):
    from ogr_core.project import Project
    return Project.from_dict(data)


def _refused(data):
    """The ``ValueError`` opening ``data`` raises (the runner's
    ``pytest.raises`` does not hand the exception back)."""
    try:
        _open(data)
    except ValueError as exc:
        return exc
    raise AssertionError("the file opened")


def _enum_values(cls):
    return [e.value for e in cls]


# ======================================================================
class TestTheValidFileOpensTheSame:

    def test_the_json_goes_round_unchanged(self):
        data = _data()
        again = json.loads(json.dumps(_open(copy.deepcopy(data)).to_dict()))
        assert again == data

    def test_the_document_hash_is_the_same(self):
        from ogr_core.api.workspace import default_document_hash
        p = _project()
        data = json.loads(json.dumps(p.to_dict()))
        assert default_document_hash(_open(data)) == default_document_hash(p)


# ======================================================================
class TestPermeability:

    def _hyd(self, data):
        return data["materials"][0]["hydraulic"]

    def test_every_model_of_the_enumeration_opens(self):
        from ogr_core.hydraulic.hydraulic_properties import PermeabilityModel
        for value in _enum_values(PermeabilityModel):
            data = _data()
            self._hyd(data)["model"] = value
            assert _open(data).materials[0].hydraulic.model.value == value

    def test_an_unknown_model_is_refused_by_its_code(self):
        from ogr_core.file_messages import ENUM_UNKNOWN
        from ogr_core.hydraulic.hydraulic_properties import PermeabilityModel
        for value in ("future_model", None, 5):
            data = _data()
            self._hyd(data)["model"] = value
            assert value not in _enum_values(PermeabilityModel)
            exc = _refused(data)
            assert exc.code == ENUM_UNKNOWN
            assert exc.values == {"value": value,
                                  "enum": "PermeabilityModel"}
            # Python's text, which the agent reads
            assert str(exc) == f"{value!r} is not a valid PermeabilityModel"

    def test_an_unknown_legacy_model_is_refused_by_its_code(self):
        from ogr_core.file_messages import ENUM_UNKNOWN
        data = _data()
        hyd = self._hyd(data)
        del hyd["model"]
        hyd["unsaturated_model"] = "future_model"
        exc = _refused(data)
        assert exc.code == ENUM_UNKNOWN
        assert exc.values["enum"] == "PermeabilityModel"

    def test_the_migration_of_an_absent_model_does_not_move(self):
        from ogr_core.hydraulic.hydraulic_properties import PermeabilityModel
        for legacy in (None, "saturated", "van_genuchten", "absent"):
            data = _data()
            hyd = self._hyd(data)
            del hyd["model"]
            if legacy != "absent":
                hyd["unsaturated_model"] = legacy
            want = (PermeabilityModel.VAN_GENUCHTEN
                    if legacy == "van_genuchten"
                    else PermeabilityModel.CONSTANT)
            assert _open(data).materials[0].hydraulic.model is want, legacy


# ======================================================================
class TestTheDrawdownEnvelope:

    def _env(self, data):
        return data["materials"][0]

    def test_both_kinds_open(self):
        from ogr_core.materials.drawdown_envelopes import (Kc1Envelope,
                                                           REnvelope)
        from ogr_core.materials.material import ENVELOPE_KINDS
        assert ENVELOPE_KINDS == ("r", "kc1")
        data = _data()
        assert isinstance(_open(data).materials[0].drawdown_envelope,
                          REnvelope)
        data = _data()
        self._env(data)["drawdown_envelope"] = {"kind": "kc1", "d": 3.0,
                                                "psi_deg": 15.0}
        assert isinstance(_open(data).materials[0].drawdown_envelope,
                          Kc1Envelope)

    def test_an_unknown_kind_is_refused_by_its_code(self):
        from ogr_core.file_messages import VALUE_UNKNOWN
        from ogr_core.materials.material import ENVELOPE_KINDS
        for kind, shown in (("future", "future"), (None, "null")):
            data = _data()
            self._env(data)["drawdown_envelope"]["kind"] = kind
            exc = _refused(data)
            coded = exc.args[0]
            assert coded.code == VALUE_UNKNOWN
            assert coded.args["field"] == "drawdown_envelope.kind"
            assert coded.args["value"] is kind or coded.args["value"] == kind
            assert list(coded.args["known"].items) == list(ENVELOPE_KINDS)
            assert str(exc) == (f"Unknown value of 'drawdown_envelope.kind':"
                                f" '{shown}'. Known: r, kc1")

    def test_an_envelope_without_a_kind_is_refused(self):
        from ogr_core.file_messages import VALUE_UNKNOWN
        data = _data()
        del self._env(data)["drawdown_envelope"]["kind"]
        assert _refused(data).args[0].code == VALUE_UNKNOWN

    def test_absent_empty_and_null_are_no_envelope(self):
        for value in ("absent", {}, None):
            data = _data()
            if value == "absent":
                del self._env(data)["drawdown_envelope"]
            else:
                self._env(data)["drawdown_envelope"] = value
            assert _open(data).materials[0].drawdown_envelope is None


# ======================================================================
class TestTheGridInterpolation:

    def test_both_interpolations_open_and_differ(self):
        from ogr_core.hydraulic.water_pressure_grid import INTERPOLATIONS
        assert INTERPOLATIONS == ("tps", "idw")
        got = {}
        for value in INTERPOLATIONS:
            data = _data()
            data["water_pressure_grid"]["interpolation"] = value
            grid = _open(data).water_pressure_grid
            assert grid.interpolation == value
            got[value] = grid.value_at(3.0, 3.0)
        assert got["tps"] != got["idw"]

    def test_an_unknown_interpolation_is_refused_by_its_code(self):
        from ogr_core.file_messages import VALUE_UNKNOWN
        from ogr_core.hydraulic.water_pressure_grid import INTERPOLATIONS
        for value, shown in (("kriging", "kriging"), (None, "null")):
            data = _data()
            data["water_pressure_grid"]["interpolation"] = value
            exc = _refused(data)
            coded = exc.args[0]
            assert coded.code == VALUE_UNKNOWN
            assert coded.args["field"] == "interpolation"
            assert coded.args["value"] == value
            assert list(coded.args["known"].items) == list(INTERPOLATIONS)
            assert str(exc) == (f"Unknown value of 'interpolation': "
                                f"'{shown}'. Known: tps, idw")

    def test_an_absent_interpolation_is_tps(self):
        data = _data()
        del data["water_pressure_grid"]["interpolation"]
        assert _open(data).water_pressure_grid.interpolation == "tps"


# ======================================================================
class TestTheAccelerationUnit:

    def test_every_unit_of_the_enumeration_opens(self):
        from ogr_core.loads.seismic_record import AccelerationUnit
        for value in _enum_values(AccelerationUnit):
            data = _data()
            data["seismic_records"][0]["source_unit"] = value
            rec = _open(data).seismic_records[0]
            assert rec.source_unit.value == value

    def test_an_unknown_unit_is_refused_by_its_code(self):
        from ogr_core.file_messages import ENUM_UNKNOWN
        from ogr_core.loads.seismic_record import AccelerationUnit
        for value in ("furlongs", None):
            assert value not in _enum_values(AccelerationUnit)
            data = _data()
            data["seismic_records"][0]["source_unit"] = value
            exc = _refused(data)
            assert exc.code == ENUM_UNKNOWN
            assert exc.values == {"value": value, "enum": "AccelerationUnit"}
            assert str(exc) == f"{value!r} is not a valid AccelerationUnit"

    def test_an_absent_unit_is_g(self):
        from ogr_core.loads.seismic_record import AccelerationUnit
        data = _data()
        del data["seismic_records"][0]["source_unit"]
        assert _open(data).seismic_records[0].source_unit is AccelerationUnit.G


# ======================================================================
class TestTheTypesOfAMaterial:

    def _set(self, field, value):
        data = _data()
        data["materials"][0][field] = value
        return data

    def test_numbers_and_text_open(self):
        for field, value in (("unit_weight", 20), ("unit_weight", 20.0),
                             ("sat_unit_weight", 21),
                             ("sat_unit_weight", 21.5), ("name", "Clay")):
            m = _open(self._set(field, value)).materials[0]
            assert getattr(m, field) == value

    def test_a_weight_of_another_type_is_refused_with_its_item(self):
        from ogr_core.file_messages import FIELD_TYPE
        for field in ("unit_weight", "sat_unit_weight"):
            for value, found, word in (("x", "string", "a string"),
                                       (True, "bool", "a boolean"),
                                       (None, "null", "null")):
                exc = _refused(self._set(field, value))
                coded = exc.args[0]
                assert coded.code == FIELD_TYPE
                assert coded.args == {"field": field, "n": 1,
                                      "section": "materials",
                                      "expected": "number", "found": found}
                assert str(exc) == (
                    f"The field '{field}' of item 1 of the section "
                    f"'materials' of the file must be a number, not {word}.")

    def test_a_name_of_another_type_is_refused_with_its_item(self):
        from ogr_core.file_messages import FIELD_TYPE
        for value, found, word in ((5, "number", "a number"),
                                   (None, "null", "null")):
            exc = _refused(self._set("name", value))
            coded = exc.args[0]
            assert coded.code == FIELD_TYPE
            assert coded.args["expected"] == "string"
            assert coded.args["found"] == found
            assert str(exc) == (
                "The field 'name' of item 1 of the section 'materials' of "
                f"the file must be a string, not {word}.")

    def test_the_item_is_counted_from_one(self):
        data = _data()
        second = copy.deepcopy(data["materials"][0])
        second["unit_weight"] = "x"
        data["materials"].append(second)
        assert _refused(data).args[0].args["n"] == 2

    def test_an_absent_weight_keeps_its_default(self):
        data = _data()
        del data["materials"][0]["unit_weight"]
        assert _open(data).materials[0].unit_weight == 20.0


# ======================================================================
class TestTheCodes:

    def test_the_templates_say_what_the_readers_say(self):
        """The template, filled with the values, is the reader's sentence
        (the window says the template, translated)."""
        from ogr_core.file_messages import (FIELD_TYPE, FILE_MESSAGES,
                                            SHAPE_WORDS, VALUE_UNKNOWN)
        t = FILE_MESSAGES[VALUE_UNKNOWN].english
        assert t.format(field="interpolation", value="kriging",
                        known="tps, idw") == (
            "Unknown value of 'interpolation': 'kriging'. Known: tps, idw")
        t = FILE_MESSAGES[FIELD_TYPE].english
        assert t.format(field="name", n=1, section="materials",
                        expected=SHAPE_WORDS["string"],
                        found=SHAPE_WORDS["number"]) == (
            "The field 'name' of item 1 of the section 'materials' of the "
            "file must be a string, not a number.")
