"""core/checks — checks migrated out of the monolith, emitting their own
structured evidence as they run (the Phase-2 end state; DESIGN.md §4, §7).

`MIGRATED_IDS` lists the check IDs core now owns. core.build.run() tells the
engine to skip these (via QCReport.skip_check_ids, set only within the core
path — the standalone CLI is unaffected and keeps the engine's copy) and runs
the core versions instead, so there is exactly one emission per check and it
carries native evidence.

Migration is incremental: one check moves here per step; until the HTML report
also consumes Result, the engine retains its (skipped-in-core) copy.
"""
from .cross_document import (  # noqa: F401
    check_inventor_names, check_application_title,
    check_attorney_docket, check_correspondence,
)

# id -> callable(qc) -> Issue ; checks core/checks now owns.
REGISTRY = {
    1: check_inventor_names,
    2: check_application_title,
    3: check_attorney_docket,
    4: check_correspondence,
}

# Check IDs owned by core/checks (skipped in the engine when run via core).
MIGRATED_IDS = set(REGISTRY)
