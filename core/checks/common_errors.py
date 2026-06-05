"""Common-error checks. Checks 50 (placeholder text) and 51 (track changes) are
migrated. Checks 52-54 (claim terminology consistency, antecedent basis,
undefined terms) are intricate drafting-quality heuristics with high replication
risk and low evidence value, so they stay engine-emitted.
"""
import re

from ..result import Issue

_CAT = "Common Errors"

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
    placeholder = (Issue(50, _CAT, "No Placeholder Text Remaining", "PASS",
                         "No common placeholder text detected")
                   if not found else
                   Issue(50, _CAT, "No Placeholder Text Remaining", "CRITICAL",
                         f"Placeholder text found: {', '.join(found)}"))

    indicators = [i for i in _TRACK if i in all_text]
    track = (Issue(51, _CAT, "No Track Changes or Comments Visible", "PASS",
                   "No track change indicators detected")
             if not indicators else
             Issue(51, _CAT, "No Track Changes or Comments Visible", "WARNING",
                   f"Possible track change indicators: {', '.join(indicators)}"))
    return [placeholder, track]
