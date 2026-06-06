"""USPTO formatting checks: 45 (line numbering) and 49 (page numbering). Both
migrated; 49 reads the spec PDF page-by-page (PyPDF2), read-only.
"""
import re

from ..result import Issue
from ._ev import data

_CAT = "USPTO Formatting"


def check_formatting(qc):
    return [_line_numbering(qc), _page_numbering(qc)]


def _page_numbering(qc) -> Issue:
    name = "Page Numbering Present"
    import PyPDF2
    spec_path = (getattr(qc, "documents", {}) or {}).get("Specification")
    is_pdf = bool(spec_path and spec_path.suffix.lower() == ".pdf")
    if is_pdf:
        try:
            with open(spec_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                total = len(reader.pages)
                with_nums = 0
                for i, page in enumerate(reader.pages):
                    pt = page.extract_text() or ""
                    pn = str(i + 1)
                    pats = [r"(?:Page|page)\s+" + pn + r"\b", r"\b" + pn + r"\s+of\s+\d+\b",
                            r"-\s*" + pn + r"\s*-", r"(?:^|\n)\s*" + pn + r"\s*(?:\n|$)"]
                    if any(re.search(p, pt) for p in pats):
                        with_nums += 1
                if total > 0 and with_nums >= total * 0.8:
                    issue = Issue(49, _CAT, name, "PASS",
                                  f"Page numbering detected ({with_nums}/{total} pages)")
                    issue.evidence = [data("Pages with page numbers",
                                           actual=f"{with_nums} of {total}", kind="match",
                                           doc_type="Specification")]
                    return issue
        except Exception:
            pass
    if not is_pdf:
        issue = Issue(49, _CAT, name, "INFO",
                      "Specification is a .docx — page numbering not verifiable "
                      "by text extraction. Verify manually that the rendered/filed "
                      "PDF has page numbers.")
        issue.evidence = [data("Page numbering", actual=".docx — verify in the filed PDF",
                               kind="value", doc_type="Specification")]
        return issue
    spec = getattr(qc, "spec_text", "") or ""
    page_refs = re.findall(r"(?:^|\s)(\d{1,3})(?:\s|$)", spec)
    sequential = [int(n) for n in page_refs if 1 <= int(n) <= 100]
    if sequential and max(sequential) >= 10:
        expected = set(range(1, max(sequential) + 1))
        coverage = len(expected & set(sequential)) / len(expected)
        if coverage >= 0.7:
            issue = Issue(49, _CAT, name, "PASS",
                          "Page numbering appears present in specification")
            issue.evidence = [data("Page numbering", actual="sequential page numbers in text",
                                   kind="match", doc_type="Specification")]
            return issue
    issue = Issue(49, _CAT, name, "INFO",
                  "Page numbering not clearly detected - verify all pages numbered")
    issue.evidence = [data("Page numbering", actual="not clearly detected — verify",
                           kind="value", doc_type="Specification")]
    return issue


def _line_numbering(qc):
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        issue = Issue(45, _CAT, "Check 45", "CRITICAL", "Specification not found")
        issue.evidence = [data("Specification", actual="not found", kind="missing")]
        return issue
    cands = re.findall(r"(?:^|\s)(\d{1,3})(?:\s|$)", spec)
    fives = {int(n) for n in cands if int(n) % 5 == 0 and 5 <= int(n) <= 50}
    name = "Specification Line Numbering"
    if {5, 10, 15, 20, 25}.issubset(fives):
        issue = Issue(45, _CAT, name, "PASS",
                      "Line numbering detected (multiples of 5 found in text)")
        issue.evidence = [data("Line numbering", actual="multiples of 5 detected",
                               kind="match", doc_type="Specification")]
        return issue
    issue = Issue(45, _CAT, name, "INFO",
                  "Line numbering not clearly detected - verify line numbers every 5 lines")
    issue.evidence = [data("Line numbering", actual="not clearly detected — verify",
                           kind="value", doc_type="Specification")]
    return issue
