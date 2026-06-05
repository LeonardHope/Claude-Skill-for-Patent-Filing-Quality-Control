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
    check_inventor_names, check_application_title, check_attorney_docket,
    check_correspondence, check_assignee_name, check_filing_date,
    check_inventor_count, check_residency,
)
from .completeness import (  # noqa: F401
    check_required_documents, check_ads_fields,
    check_declaration_signatures, check_assignment_signatures,
)

# id -> callable(qc) -> Issue | list[Issue] ; checks core/checks now owns.
REGISTRY = {
    1: check_inventor_names,
    2: check_application_title,
    3: check_attorney_docket,
    4: check_correspondence,
    5: check_assignee_name,
    6: check_filing_date,
    7: check_inventor_count,
    8: check_residency,
    9: check_required_documents,
    10: check_ads_fields,
    11: check_declaration_signatures,
    12: check_assignment_signatures,
}

# Check IDs owned by core/checks (skipped in the engine when run via core).
MIGRATED_IDS = set(REGISTRY)
