"""Power of Attorney checks (42, 44), migrated to core. Mirrors the engine.

Check 41 (names all practitioners) is left engine-emitted — filled POA forms are
often mostly form-label text, so the engine OCRs the POA when the extracted text
is short. check_poa(qc) returns issues for 42 and 44, and handles the
POA-missing fallback (42, 44; 41 is the engine's).
"""
import re

from ..result import Issue

_CAT = "Power of Attorney"
_IDS = (42, 44)


def check_poa(qc):
    text = getattr(qc, "poa_text", "") or ""
    if not text:
        return [Issue(i, _CAT, f"Check {i}", "INFO",
                      "Power of Attorney not found (may not be required)") for i in _IDS]
    return [_registration_numbers(text), _signed(qc, text)]


def _registration_numbers(text) -> Issue:
    name = "POA Includes Registration Numbers"
    if re.search(r"registration\s*(?:no|number)|\d{5,6}", text, re.IGNORECASE):
        return Issue(42, _CAT, name, "PASS", "Registration numbers appear to be included")
    return Issue(42, _CAT, name, "WARNING", "Registration numbers not clearly detected")


def _signed(qc, text) -> Issue:
    name = "POA Properly Signed"
    has_sig = ("/s/" in text or "signature" in text.lower()
               or bool(re.search(r"/[A-Z][^/\n]{2,40}/", text)))
    img = (getattr(qc, "image_only_pages", {}) or {}).get("Power of Attorney", 0)
    if has_sig:
        return Issue(44, _CAT, name, "PASS", "Signature indicators detected in POA")
    if img:
        return Issue(44, _CAT, name, "INFO",
                     f"No text-based signature indicators found, but POA has {img} "
                     f"image-only page(s) — signature may be a scanned image. Verify "
                     f"manually.")
    return Issue(44, _CAT, name, "WARNING", "Signatures not clearly detected in POA")
