"""Common-error checks. Checks 50 (placeholder text) and 51 (track changes) are
migrated. Checks 52-54 (claim terminology consistency, antecedent basis,
undefined terms) are intricate drafting-quality heuristics with high replication
risk and low evidence value, so they stay engine-emitted.
"""
import re

from ..result import Issue
from ._ev import region

_CAT = "Common Errors"

# (doc_type, qc text attribute) for documents whose page text we can locate a
# placeholder in. ADS text comes from XFA datasets (no page geometry), so it is
# scanned for the message but not for a pdf_region receipt.
_SCAN = (("Specification", "spec_text"), ("Declaration", "declaration_text"),
         ("Assignment", "assignment_text"))

_PLACEHOLDERS = (
    (r"\[INSERT[^\]]{0,80}\]", "[INSERT…]"),
    (r"\[TBD[^\]]{0,80}\]", "[TBD…]"),
    (r"\[FILL[^\]]{0,80}\]", "[FILL…]"),
    (r"\[PLACEHOLDER[^\]]{0,80}\]", "[PLACEHOLDER…]"),
    (r"\[\s*___+\s*\]", "[___]"),
    (r"\bTODO\b", "TODO"),
    (r"\bFIXME\b", "FIXME"),
    (r"\bXXX\b", "XXX"),
    (r"\*\*\*+", "***"),
)
_TRACK = ("Deleted:", "Inserted:", "Comment [", "Formatted:")


def check_common_errors(qc):
    all_text = (getattr(qc, "spec_text", "") or "") + (getattr(qc, "ads_text", "") or "") \
        + (getattr(qc, "declaration_text", "") or "") + (getattr(qc, "assignment_text", "") or "")

    found = [label for pat, label in _PLACEHOLDERS if re.search(pat, all_text)]
    if not found:
        placeholder = Issue(50, _CAT, "No Placeholder Text Remaining", "PASS",
                            "No common placeholder text detected")
    else:
        placeholder = Issue(50, _CAT, "No Placeholder Text Remaining", "CRITICAL",
                           f"Placeholder text found: {', '.join(found)}")
        placeholder.evidence = _placeholder_evidence(qc)

    indicators = [i for i in _TRACK if i in all_text]
    track = (Issue(51, _CAT, "No Track Changes or Comments Visible", "PASS",
                   "No track change indicators detected")
             if not indicators else
             Issue(51, _CAT, "No Track Changes or Comments Visible", "WARNING",
                   f"Possible track change indicators: {', '.join(indicators)}"))
    return [placeholder, track]


def _placeholder_evidence(qc, cap=12):
    """A pdf_region receipt for each placeholder occurrence we can locate in a
    text-bearing document (capped so a runaway template doesn't flood the panel)."""
    docs = getattr(qc, "documents", {}) or {}
    ev = []
    for doc_type, attr in _SCAN:
        text, path = getattr(qc, attr, "") or "", docs.get(doc_type)
        if not text or not path:
            continue
        for pat, label in _PLACEHOLDERS:
            for m in re.finditer(pat, text):
                e = region(doc_type, path, m.group(0), kind="mismatch",
                           label=f"Placeholder {label} in {doc_type}")
                if e:
                    ev.append(e)
                    if len(ev) >= cap:
                        return ev
    return ev
