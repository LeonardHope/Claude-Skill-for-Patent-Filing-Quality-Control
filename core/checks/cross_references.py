"""Cross-reference checks. 61 (drawing figure count) and 62 (claim count) are
migrated. Checks 59 (claims reference spec elements) and 60 (summary matches
claims) are intricate drafting-quality NLP heuristics, left engine-emitted.
"""
import re

from ..result import Issue
from ._ev import region

_CAT = "Cross-References"


def _claims_anchor(qc):
    """A pdf_region receipt at the claims-section header in the spec, if locatable."""
    spec = getattr(qc, "spec_text", "") or ""
    sp = (getattr(qc, "documents", {}) or {}).get("Specification")
    for m in (re.search(r"What is claimed", spec, re.IGNORECASE),
              re.search(r"(?:^|\n)\s*CLAIMS?\b", spec, re.IGNORECASE)):
        if m:
            e = region("Specification", sp, m.group(0).strip(), kind="match",
                       label="Claims section")
            if e:
                return [e]
    return []


def _fig_sort_key(fid):
    m = re.match(r"(\d+)([A-Za-z]*)", fid)
    return (int(m.group(1)), m.group(2)) if m else (0, fid)


def check_cross_references(qc):
    return [_figure_count(qc), _claim_count(qc)]


def _figure_count(qc) -> Issue:
    name = "Drawing Figure Count Matches Specification"
    spec = getattr(qc, "spec_text", "") or ""
    draw = getattr(qc, "drawings_text", "") or ""
    if not qc._drawings_text_extractable():
        spec_figs = qc._extract_figure_identities(spec) if spec else []
        return Issue(61, _CAT, name, "INFO",
                     f"Drawings PDF appears to be image-only — figure count not "
                     f"verifiable by text extraction. Spec references {len(spec_figs)} "
                     f"figure(s)" + (f" (FIG. {', '.join(spec_figs)})" if spec_figs else "")
                     + ". Manually verify drawings contain matching figures.")
    if spec and draw:
        sf = set(qc._extract_figure_identities(spec))
        df = set(qc._extract_figure_identities(draw))
        if sf == df:
            return Issue(61, _CAT, name, "PASS",
                         f"Figure numbers match: {len(sf)} figures "
                         f"(FIG. {', '.join(sorted(sf, key=_fig_sort_key))})")
        if len(sf) == len(df):
            return Issue(61, _CAT, name, "WARNING",
                         f"Same figure count ({len(sf)}) but different numbers. "
                         f"Spec: {sorted(sf, key=_fig_sort_key)}, "
                         f"Drawings: {sorted(df, key=_fig_sort_key)}")
        return Issue(61, _CAT, name, "WARNING",
                     f"Figure count mismatch: Spec references {len(sf)} figures, "
                     f"Drawings has {len(df)} figures")
    return Issue(61, _CAT, name, "INFO", "Unable to compare figure counts")


def _claim_count(qc) -> Issue:
    name = "Claim Count Verification"
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        return Issue(62, _CAT, name, "WARNING", "Specification not found")
    claims_text = qc._extract_claims_section() or spec
    nums = []
    for pat in (r"(?:^|\n)\s*(\d+)\.\s+(?=\D)", r"(?:\.\s+|\;\s+|:\s+)(\d+)\.\s+(?=\D)",
                r"\s{2,}(\d+)\.\s+(?=\D)", r"\s+\d{2,3}\s+(\d+)\.\s+(?=\D)"):
        nums.extend(re.findall(pat, claims_text, re.IGNORECASE))
    if nums:
        uniq = sorted({int(n) for n in nums if 1 <= int(n) <= 100})
        issue = Issue(62, _CAT, name, "PASS",
                      f"Total claims detected: {len(uniq)} (Claims 1-{max(uniq)})")
        issue.evidence = _claims_anchor(qc)
        return issue
    simple = []
    for pat in (r"(?:^|\n)\s*(\d+)\.\s+", r"(?:\.\s+|\;\s+|:\s+)(\d+)\.\s+",
                r"\s{2,}(\d+)\.\s+", r"^\s*(\d+)\.\s+", r"\s+\d{2,3}\s+(\d+)\.\s+"):
        simple.extend(re.findall(pat, claims_text, re.MULTILINE))
    simple = [n for n in simple if 1 <= int(n) <= 100]
    if simple:
        return Issue(62, _CAT, name, "INFO",
                     f"Possible claims detected: {len(set(simple))} "
                     f"(manual verification recommended)")
    return Issue(62, _CAT, name, "WARNING",
                 "Unable to count claims - claims section may use non-standard format")
