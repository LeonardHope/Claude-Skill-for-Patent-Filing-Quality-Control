"""Document-completeness checks, migrated to core.

Checks 9 (required documents present, incl. the 37 CFR §1.53(f) missing-parts
handling), 10 (ADS required fields), 11 (declaration signatures), 12 (assignment
signatures). Verdicts mirror the engine exactly. (Checks 74/75 — duplicate /
unrecognized files — are emitted by the engine at load time and are not
migrated here.)
"""
import re
from pathlib import Path

from ..result import Issue
from ._ev import region, data

_CAT = "Document Completeness"
_SIG_PATTERNS = (r"/s/\s*[A-Z]", r"/[A-Z][^/\n]{2,40}/")


def _declar_candidates(qc):
    """PDF files whose name suggests a declaration (used as a last-resort signal
    when the content classifier missed a low-quality scan)."""
    try:
        ads_name = qc.report.files_found.get("ADS", "")
        return [p.name for p in Path(qc.folder_path).iterdir()
                if p.suffix.lower() == ".pdf" and "declar" in p.stem.lower()
                and p.name != ads_name]
    except Exception:
        return []


def check_required_documents(qc):
    """Check 9 — required documents present (may emit two issues: a blocking
    CRITICAL and a missing-parts WARNING/CRITICAL)."""
    name = "All Required Documents Present"
    files_found = qc.report.files_found
    required = ("Specification", "Drawings", "ADS", "Declaration")
    missing = [d for d in required if not files_found.get(d)]
    if not missing:
        issue = Issue(9, _CAT, name, "PASS", "All required documents found")
        issue.evidence = [data("Required documents present",
                               actual=", ".join(required), kind="match")]
        return [issue]

    eligible = {"Declaration"}
    blocking = [d for d in missing if d not in eligible]
    optional = [d for d in missing if d in eligible]
    issues = []
    if blocking:
        iss = Issue(
            9, _CAT, name, "CRITICAL",
            f"Missing required documents: {', '.join(blocking)}",
            details="These documents must be in the filing folder. They are not "
                    "eligible for the missing-parts procedure under 37 CFR §1.53(f).")
        iss.evidence = [data(f"{d}", actual="not found", kind="missing") for d in blocking]
        issues.append(iss)
    if optional:
        declar = _declar_candidates(qc)
        if declar:
            issues.append(Issue(
                9, _CAT, name, "WARNING",
                f"Potential declaration found ({', '.join(declar)}) but content could "
                f"not be verified — likely a low-quality scan that defeated OCR "
                f"classification",
                details=("The file name suggests this is the signed declaration, but "
                         "text could not be extracted to confirm signatures, inventor "
                         "names, or AIA compliance.\n"
                         "  • Manually confirm the document is a signed AIA §1.63 "
                         "declaration\n      (or oath) covering all listed inventors "
                         "before filing.\n"
                         "  • If it is NOT a declaration, add the correct declaration to "
                         "the folder and re-run QC.")))
        else:
            issues.append(Issue(
                9, _CAT, name, "CRITICAL",
                f"{', '.join(optional)} not found — confirm whether this is intentional",
                details=("ACTION REQUIRED: Ask the filer whether this is an intentional "
                         "missing-parts filing under 37 CFR §1.53(f).\n"
                         "  • If YES (intentional): downgrade this to a WARNING and remind "
                         "the filer that:\n"
                         "      – A §1.16(f) surcharge fee is due at or after filing\n"
                         "      – The missing parts (e.g., declaration) must be filed "
                         "within 2 months\n        of the USPTO's Notice to File Missing "
                         "Parts to avoid abandonment\n"
                         "  • If NO (oversight): the missing document(s) must be added "
                         "before filing")))
    return issues


def check_ads_fields(qc) -> Issue:
    """Check 10 — ADS required fields present."""
    name = "ADS Required Fields Complete"
    ads = getattr(qc, "ads_text", "") or ""
    if not ads:
        issue = Issue(10, _CAT, name, "CRITICAL", "ADS not found")
        issue.evidence = [data("ADS", actual="not found", kind="missing")]
        return issue
    tl = ads.lower()
    fields = ("title", "inventor", "correspondence")
    missing = [f for f in fields if f not in tl]
    if not missing:
        issue = Issue(10, _CAT, name, "PASS", "ADS appears to have required fields")
        issue.evidence = [data("Required ADS fields present",
                               actual=", ".join(fields), kind="match", doc_type="ADS")]
        return issue
    issue = Issue(10, _CAT, name, "WARNING", f"ADS may be missing fields: {', '.join(missing)}")
    issue.evidence = [data("Possibly missing ADS field", actual=f, kind="mismatch",
                           doc_type="ADS") for f in missing]
    return issue


def _signature_check(qc, check_id, doc_type, text, img_key, missing_msg, missing_fn):
    if text:
        sig_m = next((m for p in _SIG_PATTERNS for m in (re.search(p, text),) if m), None)
        img = (getattr(qc, "image_only_pages", {}) or {}).get(img_key, 0)
        name = f"{doc_type} Signatures Present"
        if sig_m:
            issue = Issue(check_id, _CAT, name, "PASS",
                          f"{doc_type} has signature markers (/s/ or /Name/)")
            sp = (getattr(qc, "documents", {}) or {}).get(doc_type)
            e = region(doc_type, sp, sig_m.group(0).strip(), kind="match",
                       label=f"Signature marker in {doc_type.lower()}")
            if e:
                issue.evidence = [e]
            return issue
        if img:
            return Issue(check_id, _CAT, name, "INFO",
                         f"No text-based signatures detected, but the "
                         f"{doc_type.lower()} has {img} image-only page(s) — signatures "
                         f"may be scanned. Verify visually.")
        return Issue(check_id, _CAT, name, "WARNING",
                     f"No signature markers (/s/ or /Name/) detected in "
                     f"{doc_type.lower()}. Form labels alone don't confirm a signed "
                     f"{doc_type.lower()}.")
    return missing_fn()


def check_declaration_signatures(qc) -> Issue:
    """Check 11 — declaration signatures present."""
    def _missing():
        hint = any("declar" in p.stem.lower()
                   for p in Path(qc.folder_path).iterdir()
                   if p.suffix.lower() == ".pdf"
                   and p.name != qc.report.files_found.get("ADS", "")) \
            if _safe_iterdir(qc) else False
        msg = ("Declaration found by filename but content unreadable (likely "
               "low-quality scan) — verify manually") if hint else \
              "Declaration not found - cannot check signatures"
        return Issue(11, _CAT, "Declaration Signatures Present", "WARNING", msg)
    return _signature_check(qc, 11, "Declaration",
                            getattr(qc, "declaration_text", ""), "Declaration",
                            None, _missing)


def check_assignment_signatures(qc) -> Issue:
    """Check 12 — assignment signatures present (optional document)."""
    def _missing():
        return Issue(12, _CAT, "Assignment Signatures Present", "INFO",
                     "Assignment not found (optional document)")
    return _signature_check(qc, 12, "Assignment",
                            getattr(qc, "assignment_text", ""), "Assignment",
                            None, _missing)


def _safe_iterdir(qc):
    try:
        list(Path(qc.folder_path).iterdir())
        return True
    except Exception:
        return False
