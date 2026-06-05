"""Cross-document consistency checks, migrated to core (emit native evidence).

Currently: Check 2 (Application Title Consistency). Each check here takes the
finished engine instance `qc` (for its extracted texts, ADS data, and document
paths) and returns a fully-formed Issue with its receipts attached — no
post-hoc enricher needed.
"""
import re

from ..locate import locate_flex
from ..result import Issue, Evidence, Locator

_CAT = "Cross-Document Consistency"
_NAME = "Application Title Consistency"


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.upper()).strip().rstrip(".,;:")


def check_application_title(qc) -> Issue:
    """Check 2: the ADS title appears in the specification.

    Mirrors the engine's logic exactly (verbatim match, else a 60%-prefix
    match), and additionally attaches evidence: a pdf_region highlight of the
    title in the spec PDF plus the ADS title as a structured xfa_field.
    """
    ads_data = getattr(qc, "ads_data", None) or {}
    ads_title = ads_data.get("title") or (
        qc.extract_title(qc.ads_text) if getattr(qc, "ads_text", "") else "")
    spec_text = getattr(qc, "spec_text", "") or ""

    if not ads_title:
        return Issue(2, _CAT, _NAME, "WARNING", "Unable to extract title from ADS")
    if not spec_text:
        return Issue(2, _CAT, _NAME, "WARNING",
                     "Specification not available to compare title")

    ads_norm = _normalize(ads_title)
    spec_norm = _normalize(spec_text)
    if ads_norm in spec_norm:
        severity, message = "PASS", "ADS title appears verbatim in specification"
    else:
        words = ads_norm.split()
        chunk = " ".join(words[:max(4, int(len(words) * 0.6))])
        if chunk in spec_norm:
            severity, message = "PASS", ("Most of ADS title appears in specification "
                                         "(minor wording differences detected)")
        else:
            severity, message = "CRITICAL", ("ADS title does not appear in "
                                             "specification — verify they describe "
                                             "the same application")

    issue = Issue(2, _CAT, _NAME, severity, message,
                  details=("" if severity == "PASS" else f"ADS title: {ads_title}"))

    # ---- native evidence ----
    spec_path = (getattr(qc, "documents", {}) or {}).get("Specification")
    if spec_path:
        hit = locate_flex(spec_path, ads_title)
        if hit:
            issue.evidence.append(Evidence(
                doc_type="Specification",
                locator=Locator(type="pdf_region", page=hit["page"], bbox=hit["bbox"]),
                snippet=hit["matched"], expected=ads_title, actual=hit["matched"],
                kind="match" if severity == "PASS" else "mismatch",
                label="ADS title located in the specification"))
    issue.evidence.append(Evidence(
        doc_type="ADS",
        locator=Locator(type="xfa_field", field_path="title"),
        snippet=ads_title, actual=ads_title, kind="value",
        label="ADS invention title (structured XFA field)"))
    return issue
