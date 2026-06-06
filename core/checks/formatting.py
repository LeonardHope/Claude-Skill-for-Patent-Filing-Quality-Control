"""USPTO formatting checks. Check 45 (line numbering) is migrated; Check 49
(page numbering) opens and reads the spec PDF page-by-page (PyPDF2 + .docx
fallback) and is left engine-emitted.
"""
import re

from ..result import Issue
from ._ev import data

_CAT = "USPTO Formatting"


def check_formatting(qc):
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        issue = Issue(45, _CAT, "Check 45", "CRITICAL", "Specification not found")
        issue.evidence = [data("Specification", actual="not found", kind="missing")]
        return [issue]
    cands = re.findall(r"(?:^|\s)(\d{1,3})(?:\s|$)", spec)
    fives = {int(n) for n in cands if int(n) % 5 == 0 and 5 <= int(n) <= 50}
    name = "Specification Line Numbering"
    if {5, 10, 15, 20, 25}.issubset(fives):
        issue = Issue(45, _CAT, name, "PASS",
                      "Line numbering detected (multiples of 5 found in text)")
        issue.evidence = [data("Line numbering", actual="multiples of 5 detected",
                               kind="match", doc_type="Specification")]
        return [issue]
    issue = Issue(45, _CAT, name, "INFO",
                  "Line numbering not clearly detected - verify line numbers every 5 lines")
    issue.evidence = [data("Line numbering", actual="not clearly detected — verify",
                           kind="value", doc_type="Specification")]
    return [issue]
