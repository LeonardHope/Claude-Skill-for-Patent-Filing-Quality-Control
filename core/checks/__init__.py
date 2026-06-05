"""core/checks — checks migrated out of the monolith, emitting their own
structured evidence as they run (the Phase-2 end state; DESIGN.md §4, §7).

`CHECKS` is the flat list of migrated check functions; each takes the finished
engine `qc` and returns an Issue, a list of Issues (a check or whole category
may emit several), or None. `MIGRATED_IDS` is the set of check IDs core owns.

core.build.run() sets `QCReport.skip_check_ids |= MIGRATED_IDS` **only within
the core path**, so the engine doesn't emit those IDs there, runs the core
versions, and merges — exactly one emission per check, with native evidence.
The standalone CLI is unaffected (it doesn't call core.run). A few high-
complexity / low-evidence-value checks are intentionally left engine-emitted
(not in MIGRATED_IDS); they still appear in the Result, just from the engine.
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
from .specification import check_specification  # noqa: F401

CHECKS = [
    # Cross-Document Consistency (1-8)
    check_inventor_names, check_application_title, check_attorney_docket,
    check_correspondence, check_assignee_name, check_filing_date,
    check_inventor_count, check_residency,
    # Document Completeness (9-12)
    check_required_documents, check_ads_fields,
    check_declaration_signatures, check_assignment_signatures,
    # Specification (13-21, except 16 which stays engine-emitted)
    check_specification,
]

MIGRATED_IDS = {
    1, 2, 3, 4, 5, 6, 7, 8,
    9, 10, 11, 12,
    13, 14, 15, 17, 18, 19, 20, 21,   # 16 (reference-numeral consistency) left in engine
}
