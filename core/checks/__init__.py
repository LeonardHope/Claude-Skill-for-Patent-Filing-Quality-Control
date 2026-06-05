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
from .drawings import check_drawings  # noqa: F401
from .ads import check_ads  # noqa: F401
from .declaration import check_declaration  # noqa: F401
from .assignment import check_assignment  # noqa: F401
from .power_of_attorney import check_poa  # noqa: F401
from .formatting import check_formatting  # noqa: F401
from .common_errors import check_common_errors  # noqa: F401
from .file_quality import check_file_quality  # noqa: F401
from .cross_references import check_cross_references  # noqa: F401
from .priority import check_priority  # noqa: F401
from .final_quality import check_final_quality  # noqa: F401
from .ids import check_ids  # noqa: F401

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
    # Drawings (22-24; 25 no-color stays engine-emitted)
    check_drawings,
    # ADS (27, 29, 31, 73; 28 first-named-inventor uses POA OCR -> engine)
    check_ads,
    # Declaration (32-34; 35 date check OCRs signature pages -> engine)
    check_declaration,
    # Assignment (36-38, 40; 39 execution date OCRs signature pages -> engine)
    check_assignment,
    # Power of Attorney (42, 44; 41 OCRs short POA forms -> engine)
    check_poa,
    # USPTO Formatting (45; 49 page-numbering reads the PDF -> engine)
    check_formatting,
    # Common Errors (50, 51; 52-54 drafting-quality heuristics -> engine)
    check_common_errors,
    # File Quality (55, 56, 58; 57 password check reads PDFs -> engine)
    check_file_quality,
    # Cross-References (61, 62; 59-60 drafting-quality NLP -> engine)
    check_cross_references,
    # Priority Claims (63-65; 81 ODP network lookup -> engine)
    check_priority,
    # Final Quality (66-70)
    check_final_quality,
    # IDS (76-80; 74-75 load-time emissions, 71 authoritative-source -> engine)
    check_ids,
]

MIGRATED_IDS = {
    1, 2, 3, 4, 5, 6, 7, 8,
    9, 10, 11, 12,
    13, 14, 15, 17, 18, 19, 20, 21,   # 16 (reference-numeral consistency) left in engine
    22, 23, 24,                       # 25 (no-color, image analysis) left in engine
    27, 29, 31, 73,                   # 28 (first-named inventor, POA OCR) left in engine
    32, 33, 34,                       # 35 (declaration date, OCR) left in engine
    36, 37, 38, 40,                   # 39 (assignment date, OCR) left in engine
    42, 44,                           # 41 (POA practitioners, OCR) left in engine
    45,                               # 49 (page numbering, reads PDF) left in engine
    50, 51,                           # 52-54 (drafting-quality heuristics) left in engine
    55, 56, 58,                       # 57 (password protection, reads PDFs) left in engine
    61, 62,                           # 59, 60 (drafting-quality NLP) left in engine
    63, 64, 65,                       # 81 (priority app number, ODP network) left in engine
    66, 67, 68, 69, 70,
    76, 77, 78, 79, 80,               # 71 (authoritative-source x-check), 74-75 (dup/unknown
                                      # file load-time emissions), 82-85 (ST.26 seq listing)
                                      # left in engine
}
