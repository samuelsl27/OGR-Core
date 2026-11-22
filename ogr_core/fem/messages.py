# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
What the seepage solvers say about a field, with stable codes
(v0.1.352, D335).

``notes["error"]``, ``notes["warning"]``, ``notes["mesh_warning"]`` and the
initial-state notes of a transient: why a field could not be solved, why it
did not converge, what a flat element does to the system. They were English
sentences with their values in them; each is a code here with that English
and its format specs, so the sentence is the one the solver wrote -- the
tests, the API and the bank read it -- and the interface translates it. A
reason that follows another sentence (an initial state that failed BECAUSE
of something) is nested with its own code.

Codes are ``seepage.*``.

Author: Samuel Sáez López (UPCT)
"""
from __future__ import annotations

from ogr_core.messages import Coded, MessageSpec, coded

EMPTY_MESH = "seepage.empty_mesh"
NO_DIRICHLET = "seepage.no_dirichlet"
LINEAR_FAILED = "seepage.linear_failed"
PICARD_LINEAR_FAILED = "seepage.picard_linear_failed"
FINAL_FAILED = "seepage.final_failed"
FACE_UNSETTLED = "seepage.face_unsettled"
PICARD_NO_RESCUE = "seepage.picard_no_rescue"
PICARD_RESCUE_FAILED = "seepage.picard_rescue_failed"
PICARD_RESCUE_PIECEWISE_NA = "seepage.picard_rescue_piecewise_na"
INITIAL_FAILED = "seepage.initial_failed"
INITIAL_FAILED_WHY = "seepage.initial_failed_why"
NO_TIME_STEP = "seepage.no_time_step"
STAGE_STEPS = "seepage.stage_steps"
INITIAL_NOT_CONVERGED = "seepage.initial_not_converged"
INITIAL_NOT_CONVERGED_WHY = "seepage.initial_not_converged_why"
MESH_FLAT = "seepage.mesh_flat"

_PICARD = ("Picard iteration did not converge in {steps} steps (last change "
           "{change:.3e} m), and ")

SEEPAGE_NOTES = {s.code: s for s in (
    MessageSpec(EMPTY_MESH, "empty mesh"),
    MessageSpec(NO_DIRICHLET,
                "no Dirichlet (head) boundary condition: the problem is "
                "singular. Prescribe Total Head, Pressure Head or Zero "
                "Pressure somewhere on the boundary."),
    MessageSpec(LINEAR_FAILED, "linear solve failed"),
    MessageSpec(PICARD_LINEAR_FAILED,
                "linear solve failed at Picard iteration {it}"),
    MessageSpec(FINAL_FAILED, "final solve failed"),
    MessageSpec(FACE_UNSETTLED,
                "the seepage face never settled: {unsettled} boundary "
                "node(s) still want to switch between 'P = 0' and 'no flow' "
                "({frozen} were frozen by the switch budget of {budget}). The "
                "free surface this reports is not the converged one."),
    MessageSpec(PICARD_NO_RESCUE, _PICARD + "the rescue is switched off."),
    MessageSpec(PICARD_RESCUE_FAILED,
                _PICARD + "neither did the rescue (Anderson acceleration, then "
                "continuation with Newton's method; last change "
                "{rescue_change:.3e} m). A permeability function that drops "
                "many decades over a short suction range is the usual cause: "
                "check the curves of the materials near the water table."),
    # v0.1.362 (D367): the continuation stopped where its path turns back,
    # and the road that follows such turns works only with User Defined
    # curves
    MessageSpec(PICARD_RESCUE_PIECEWISE_NA,
                _PICARD + "neither did the rescue (Anderson acceleration, then "
                "continuation with Newton's method; last change "
                "{rescue_change:.3e} m). The continuation stopped where its "
                "path of solutions turns back; the road that follows the "
                "path across such turns works only when every material has "
                "a User Defined permeability curve, and this model has "
                "others."),
    MessageSpec(INITIAL_FAILED, "initial steady state failed"),
    MessageSpec(INITIAL_FAILED_WHY, "initial steady state failed: {why}"),
    MessageSpec(NO_TIME_STEP, "no time step computed"),
    MessageSpec(STAGE_STEPS,
                "stage {k}: some time steps did not converge; try more time "
                "steps or more Picard iterations per step"),
    MessageSpec(INITIAL_NOT_CONVERGED,
                "the initial steady state did not converge"),
    MessageSpec(INITIAL_NOT_CONVERGED_WHY,
                "the initial steady state did not converge: {why}"),
    MessageSpec(MESH_FLAT,
                "the mesh has {n} flat element(s) (three collinear nodes): "
                "nodes under them do not count as boundary and the "
                "conductivity matrix is badly conditioned. Regenerate the "
                "mesh."),
)}


def seepage_note(code: str, **args) -> Coded:
    """The note ``code`` with ``args``: its English sentence, carrying the
    code and the values."""
    return coded(SEEPAGE_NOTES, code, **args)


# ----------------------------------------------------------------------
# v0.2.5 -- what the quality triangulation (``refine``) says about its
# input, and the notes it leaves on the mesh. A table of their own, with
# codes ``refine.*``: the programs import each catalogue by name, so a new
# one leaves their translation tables as they are until they add it.

REFINE_BAD_RATIO = "refine.bad_ratio"
REFINE_BAD_SIZE = "refine.bad_size"
REFINE_EMPTY = "refine.empty"
REFINE_BAD_VERTEX = "refine.bad_vertex"
REFINE_DUPLICATE_VERTEX = "refine.duplicate_vertex"
REFINE_BAD_SEGMENT = "refine.bad_segment"
REFINE_DUPLICATE_SEGMENT = "refine.duplicate_segment"
REFINE_CROSSING_SEGMENTS = "refine.crossing_segments"
REFINE_VERTEX_ON_SEGMENT = "refine.vertex_on_segment"
REFINE_SEED_ON_SEGMENT = "refine.seed_on_segment"
REFINE_VOID_ON_SEGMENT = "refine.void_on_segment"
REFINE_SEED_OUTSIDE = "refine.seed_outside"
REFINE_VOID_OUTSIDE = "refine.void_outside"
REFINE_SEEDS_SHARE_REGION = "refine.seeds_share_region"
REFINE_REGION_WITHOUT_SEED = "refine.region_without_seed"
REFINE_VERTEX_OUTSIDE = "refine.vertex_outside"
REFINE_TOO_MANY_TRIANGLES = "refine.too_many_triangles"
REFINE_LENGTH_UNIT = "refine.length_unit"
REFINE_TOO_FINE = "refine.too_fine"

REFINE_MESSAGES = {s.code: s for s in (
    MessageSpec(REFINE_BAD_RATIO,
                "the quality bound B = {ratio:.6g} is below sqrt(2) = 1.41421: "
                "Delaunay refinement is guaranteed to finish only for "
                "B >= sqrt(2)"),
    MessageSpec(REFINE_BAD_SIZE,
                "the size bound at ({x:.6g}, {y:.6g}) is {h}: it must be a "
                "positive length, or infinity where there is no bound"),
    MessageSpec(REFINE_EMPTY,
                "nothing to mesh: the input needs at least three vertices, "
                "one segment and one seed"),
    MessageSpec(REFINE_BAD_VERTEX,
                "vertex {i} is not a point of two finite coordinates"),
    MessageSpec(REFINE_DUPLICATE_VERTEX,
                "vertices {i} and {j} are the same point ({x:.6g}, {y:.6g})"),
    MessageSpec(REFINE_BAD_SEGMENT,
                "segment {k} does not join two different input vertices "
                "({u} and {v})"),
    MessageSpec(REFINE_DUPLICATE_SEGMENT,
                "segments {k} and {j} join the same two vertices"),
    MessageSpec(REFINE_CROSSING_SEGMENTS,
                "segments {k} and {j} cross or overlap"),
    MessageSpec(REFINE_VERTEX_ON_SEGMENT,
                "vertex {i} lies inside segment {k}"),
    MessageSpec(REFINE_SEED_ON_SEGMENT,
                "the seed of region {region} at ({x:.6g}, {y:.6g}) lies on a "
                "segment or on a vertex"),
    MessageSpec(REFINE_VOID_ON_SEGMENT,
                "the void point ({x:.6g}, {y:.6g}) lies on a segment or on a "
                "vertex"),
    MessageSpec(REFINE_SEED_OUTSIDE,
                "the seed of region {region} at ({x:.6g}, {y:.6g}) is outside "
                "the domain or in a void"),
    MessageSpec(REFINE_VOID_OUTSIDE,
                "the void point ({x:.6g}, {y:.6g}) is outside the domain"),
    MessageSpec(REFINE_SEEDS_SHARE_REGION,
                "the seeds of regions {first} and {second} are in the same "
                "region: no segments separate them"),
    MessageSpec(REFINE_REGION_WITHOUT_SEED,
                "a part of the domain bounded by segments has no seed; one of "
                "its points is ({x:.6g}, {y:.6g})"),
    MessageSpec(REFINE_VERTEX_OUTSIDE,
                "vertex {i} at ({x:.6g}, {y:.6g}) is outside the domain or in "
                "a void"),
    MessageSpec(REFINE_TOO_MANY_TRIANGLES,
                "the mesh reached {limit} triangles before it was finished: "
                "raise the limit, or relax the size bound"),
    MessageSpec(REFINE_TOO_FINE,
                "the refinement made edges too short for the floating-point "
                "coordinates near ({x:.6g}, {y:.6g}) and cannot go on"),
    MessageSpec(REFINE_LENGTH_UNIT,
                "next to a vertex where two segments meet, the mesh splits the "
                "segments at distances that are powers of two of the unit of "
                "length: the same model in other units gives another mesh"),
)}


def refine_note(code: str, **args) -> Coded:
    """The message ``code`` of the quality triangulation with ``args``."""
    return coded(REFINE_MESSAGES, code, **args)
