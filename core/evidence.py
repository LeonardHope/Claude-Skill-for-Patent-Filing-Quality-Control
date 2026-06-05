"""Attach structured Evidence to a Result (Phase 2, incremental bridge).

In the end state each check emits its own evidence as it runs (DESIGN.md) — and
checks that have migrated to core/checks/ already do (Checks 1-4). This module
is the transitional bridge for checks that still live in the monolith: it
enriches their issues post-hoc from the engine's structured data + the source
PDFs. Currently wired:

  - Check 23  (Drawings margin)      -> pdf_region of the docket in the drawings.

Enrichment is additive and never raises.
"""
from pathlib import Path
from typing import Dict

from .locate import locate
from .result import Result, Evidence, Locator


def enrich(result: Result, doc_paths: Dict[str, Path]) -> Result:
    """Attach evidence to the issues this module knows how to enrich. Mutates
    and returns `result`. `doc_paths` maps doc_type -> absolute Path."""
    by_id = {}
    for issue in result.issues:
        by_id.setdefault(issue.check_id, issue)

    # (Checks 1-4 are native core checks now — core/checks/ — not enriched.)

    # Check 23 — drawings margin labels -> highlight the docket number where it
    # appears in the drawings margin (the strongest "wrong file" identity mark).
    c23 = by_id.get(23)
    if c23 is not None and result.ads_data:
        docket = (result.ads_data.get("docket_number") or "").strip()
        drawings = doc_paths.get("Drawings")
        hit = locate(drawings, docket) if (docket and drawings) else None
        if hit:
            c23.evidence.append(Evidence(
                doc_type="Drawings",
                locator=Locator(type="pdf_region", page=hit["page"], bbox=hit["bbox"]),
                snippet=hit["matched"], expected=docket, actual=hit["matched"],
                kind="match", label="Docket number found in the drawings margin",
            ))

    return result
