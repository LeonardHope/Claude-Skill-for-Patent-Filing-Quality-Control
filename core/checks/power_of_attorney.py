"""Power of Attorney checks (42, 44), migrated to core. Mirrors the engine.

Check 41 (names all practitioners) is left engine-emitted — filled POA forms are
often mostly form-label text, so the engine OCRs the POA when the extracted text
is short. check_poa(qc) returns issues for 42 and 44, and handles the
POA-missing fallback (42, 44; 41 is the engine's).
"""
import re

from ..result import Issue
from ._ev import data

_CAT = "Power of Attorney"
_IDS = (42, 44)


def check_poa(qc):
    text = getattr(qc, "poa_text", "") or ""
    if not text:
        return [Issue(i, _CAT, f"Check {i}", "N/A",
                      "Power of Attorney not found (may not be required)") for i in _IDS]
    return [_registration_numbers(text), _signed(qc, text)]


def _registration_numbers(text) -> Issue:
    name = "POA Includes Registration Numbers"
    m = re.search(r"\d{5,6}", text)
    if re.search(r"registration\s*(?:no|number)", text, re.IGNORECASE) or m:
        issue = Issue(42, _CAT, name, "PASS", "Registration numbers appear to be included")
        issue.evidence = [data("Registration number", actual=(m.group(0) if m else "present"),
                               kind="match", doc_type="Power of Attorney")]
        return issue
    issue = Issue(42, _CAT, name, "WARNING", "Registration numbers not clearly detected")
    issue.evidence = [data("Registration number", actual="not detected", kind="mismatch",
                           doc_type="Power of Attorney")]
    return issue


def _signed(qc, text) -> Issue:
    name = "POA Properly Signed"
    has_sig = ("/s/" in text or "signature" in text.lower()
               or bool(re.search(r"/[A-Z][^/\n]{2,40}/", text)))
    img = (getattr(qc, "image_only_pages", {}) or {}).get("Power of Attorney", 0)
    if has_sig:
        issue = Issue(44, _CAT, name, "PASS", "Signature indicators detected in POA")
        issue.evidence = [data("Signature indicators", actual="present", kind="match",
                               doc_type="Power of Attorney")]
        return issue
    if img:
        issue = Issue(44, _CAT, name, "INFO",
                      f"No text-based signature indicators found, but POA has {img} "
                      f"image-only page(s) — signature may be a scanned image. Verify "
                      f"manually.")
        issue.evidence = [data("Signature", actual=f"{img} image-only page(s) — verify visually",
                               kind="value", doc_type="Power of Attorney")]
        return issue
    issue = Issue(44, _CAT, name, "WARNING", "Signatures not clearly detected in POA")
    issue.evidence = [data("Signature indicators", actual="not detected", kind="mismatch",
                           doc_type="Power of Attorney")]
    return issue
