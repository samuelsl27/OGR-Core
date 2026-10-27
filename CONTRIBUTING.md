# Contributing to OGR Core

Thanks for wanting to help. *OpenGeoRock* (or *OGR Suite*) is the umbrella over the suite's
programs; **OGR Core** is the library they share, and it is what this repository contains.

Licence: **AGPL-3.0-or-later**. Contributions are accepted under the terms in [`CLA.md`](CLA.md),
the same agreement as the rest of the suite. Read it before your first pull request.

---

## Getting set up

```bash
git clone https://github.com/samuelsl27/OGR-Core.git
cd OGR-Core
python -m venv .venv && source .venv/bin/activate
pip install -e .
python tests/_runner.py
```

The runner exits non-zero if anything fails, which is what CI checks. While working on one area,
run only that part (`python tests/_runner.py geometry`, `-k erfc`, `--list`). A pattern that matches
nothing **exits 2**, and a filtered run prints a `FILTERED RUN` warning around its totals: before
opening a pull request, run the suite with no arguments.

**A change here is tested in the programs too.** Before a release is tagged, the full suite of every
program that will pin it must pass against it (rule 8 of [`AGENTS.md`](AGENTS.md)).

## What a change must satisfy

The rules are in [`AGENTS.md`](AGENTS.md), which is the single source and applies equally to people
and to AI agents. In short: numerical work is validated against something external; the core never
translates (user-facing messages are codes, and each program's interface translates them); every
source file carries the licence header; tests leak no state; anomalies are reported before they are
corrected; and no setting may do nothing.

## Commits and branches

- Branch from `main` as `dev/short-description`.
- Sign off your commits: `git commit -s -m "..."` (Developer Certificate of Origin).
- Write commit subjects that say what changed and why.
- Keep unrelated changes in separate commits.

## Versioning

`0.MINOR.PATCH` while pre-1.0, in its own series since the extraction. Each release bumps the
version in `pyproject.toml` and `ogr_core/__init__.py` (a test fails if they disagree), is tagged
`vX.Y.Z`, and adds a changelog entry recording **what was found**, including what a program has to
change to use it.

---

© 2026 Samuel Sáez López — UPCT — AGPL-3.0-or-later
