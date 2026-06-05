"""Attach structured Evidence to a Result (Phase 2, incremental).

In the end state each check emits its own evidence as it runs (DESIGN.md).
While the checks still live in the monolith, this module enriches specific
issues post-hoc from the engine's structured data + the source PDFs — proving
the receipts/click-to-locate pipeline one check at a time without rewriting the
engine. Currently wired:

  - Check 1  (Inventor Names)  -> pdf_region per inventor surname, located in
                                  the Declaration / Assignment PDFs.
  - Check 3  (Attorney Docket) -> xfa_field receipt from the ADS docket value.

Enrichment is additive and never raises: a surname that can't be located yields
a `pdf_page`/missing receipt rather than an error.
"""
from pathlib import Path
from typing import Dict, Optional

from .locate import locate
from .result import Result, Evidence, Locator

# Documents that carry inventor names as locatable text.
_NAME_DOCS = ("Declaration", "Assignment")


def _surnames(ads_data: Optional[dict]):
    if not ads_data:
        return []
    out = []
    for inv in ads_data.get("inventors", []) or []:
        last = (inv.get("last") or "").strip()
        if last:
            full = " ".join(p for p in (inv.get("first"), inv.get("middle"),
                                        inv.get("last")) if p).strip()
            out.append((last, full))
    return out


def _inventor_evidence(surname: str, full: str, doc_paths: Dict[str, Path]):
    """One Evidence per name-bearing document: a pdf_region highlight where the
    surname appears, or a `missing` pdf_page receipt when it doesn't."""
    ev = []
    for doc_type in _NAME_DOCS:
        path = doc_paths.get(doc_type)
        if not path:
            continue
        hit = locate(path, surname) or locate(path, full)
        if hit:
            ev.append(Evidence(
                doc_type=doc_type,
                locator=Locator(type="pdf_region", page=hit["page"], bbox=hit["bbox"]),
                snippet=hit["matched"], expected=surname, actual=hit["matched"],
                kind="match",
                label=f"Inventor surname '{surname}' found in {doc_type}",
            ))
        else:
            ev.append(Evidence(
                doc_type=doc_type,
                locator=Locator(type="pdf_page", page=0),
                snippet="", expected=surname, actual=None, kind="missing",
                label=f"Inventor surname '{surname}' not located in {doc_type}",
            ))
    return ev


def enrich(result: Result, doc_paths: Dict[str, Path]) -> Result:
    """Attach evidence to the issues this module knows how to enrich. Mutates
    and returns `result`. `doc_paths` maps doc_type -> absolute Path."""
    by_id = {}
    for issue in result.issues:
        by_id.setdefault(issue.check_id, issue)

    # Check 1 — inventor names -> pdf_region per surname per name-bearing doc.
    c1 = by_id.get(1)
    if c1 is not None:
        for surname, full in _surnames(result.ads_data):
            c1.evidence.extend(_inventor_evidence(surname, full, doc_paths))

    # Check 3 — attorney docket -> xfa_field receipt from the ADS value.
    c3 = by_id.get(3)
    if c3 is not None and result.ads_data:
        docket = (result.ads_data.get("docket_number") or "").strip()
        if docket:
            c3.evidence.append(Evidence(
                doc_type="ADS",
                locator=Locator(type="xfa_field", field_path="docket_number"),
                snippet=docket, actual=docket, kind="value",
                label="ADS attorney docket number (structured XFA field)",
            ))

    return result
