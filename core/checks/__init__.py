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
from .cross_document import check_application_title  # noqa: F401

# Check IDs owned by core/checks (skipped in the engine when run via core).
MIGRATED_IDS = {2}

# id -> callable(qc) -> Issue
from .cross_document import check_application_title as _title  # noqa: E402

REGISTRY = {2: _title}
