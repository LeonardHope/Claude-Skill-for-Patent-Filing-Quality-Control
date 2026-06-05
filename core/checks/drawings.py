"""Drawings checks (22-24), migrated to core. Mirrors the engine verbatim.

Check 25 (no color drawings) is left engine-emitted — it rasterizes the PDF and
samples pixels (OCR/Pillow dependency, image processing), high cost to replicate
for little evidence value. check_drawings(qc) returns issues for 22, 23, 24 and
handles the drawings-missing fallback.
"""
import re

from ..locate import locate
from ..result import Issue, Evidence, Locator

_CAT = "Drawings"
_IDS = (22, 23, 24)


def check_drawings(qc):
    text = getattr(qc, "drawings_text", "") or ""
    if not text:
        found = bool(qc.report.files_found.get("Drawings"))
        msg = ("Drawings PDF is image-only — cannot verify by text extraction. "
               "Manually verify figure numbering and margin labels.") if found else \
              "Drawings not found"
        sev = "INFO" if found else "CRITICAL"
        return [Issue(i, _CAT, f"Check {i}", sev, msg) for i in _IDS]
    return [_figure_numbering(qc, text), _margin_labels(qc, text), _sheet_numbering(text)]


def _figure_numbering(qc, text) -> Issue:
    name = "Figure Numbering Sequential"
    if not qc._drawings_text_extractable():
        return Issue(22, _CAT, name, "INFO",
                     "Drawings PDF appears to be image-only — figure labels not "
                     "extractable as text. Manually verify FIG. numbering is sequential.")
    fig = sorted(set(qc._extract_figure_numbers(text)))
    if fig:
        missing = set(range(1, max(fig) + 1)) - set(fig)
        if not missing:
            return Issue(22, _CAT, name, "PASS",
                         f"Figures numbered sequentially (1-{max(fig)})")
        return Issue(22, _CAT, name, "WARNING",
                     f"Figure numbers may have gaps. Found: {fig}, Missing: {sorted(missing)}")
    return Issue(22, _CAT, name, "INFO", "No extractable figure numbers — manually verify")


def _margin_labels(qc, text) -> Issue:
    name = "All Figures Have Labels"
    issues = []
    ads = getattr(qc, "ads_data", None)

    title_words = []
    if ads and ads.get("title"):
        title_words = [w for w in ads["title"].split() if len(w) > 3]
    elif getattr(qc, "spec_text", ""):
        m = re.search(r"(?:TITLE|Title).*?(?:of.*?Invention)?[:\s]*([\w\s\-]+?)"
                      r"(?:\n|CROSS|BACKGROUND|FIELD)", qc.spec_text, re.IGNORECASE)
        if m:
            title_words = [w for w in m.group(1).strip().split() if len(w) > 3]

    has_title = False
    if title_words and len(title_words) >= 2:
        found = sum(1 for w in title_words if w.upper() in text.upper())
        if found >= len(title_words) * 0.5:
            has_title = True
    elif re.search(r"Title:", text, re.IGNORECASE):
        has_title = True
    if not has_title:
        issues.append("Application title not detected in drawings margin")

    docket_candidates = []
    if ads and ads.get("docket_number"):
        docket_candidates.append(ads["docket_number"])
    for m in re.finditer(r"\b([A-Z]{2,4}\d?[-_]\d{3,5}[A-Z]{0,5}\d?)\b",
                         getattr(qc, "ads_text", "") or getattr(qc, "spec_text", "") or "",
                         re.IGNORECASE):
        docket_candidates.append(m.group(1))
    norm = re.sub(r"[\s\-_]", "", text).upper()
    has_docket = any(re.sub(r"[\s\-_]", "", c).upper() in norm
                     for c in docket_candidates if c)
    if not has_docket and re.search(r"Docket\s*(?:No\.?|Number)", text, re.IGNORECASE):
        has_docket = True
    if not has_docket:
        issues.append("Docket number not detected in drawings margin")

    issue = (Issue(23, _CAT, name, "PASS",
                   "Drawings margin labels present (title and docket number)")
             if not issues else
             Issue(23, _CAT, name, "WARNING", "; ".join(issues)))

    # Native evidence: highlight the docket in the drawings margin.
    docket = (ads or {}).get("docket_number")
    draw_path = (getattr(qc, "documents", {}) or {}).get("Drawings")
    if docket and draw_path:
        hit = locate(draw_path, docket)
        if hit:
            issue.evidence.append(Evidence(
                doc_type="Drawings",
                locator=Locator(type="pdf_region", page=hit["page"], bbox=hit["bbox"]),
                snippet=hit["matched"], expected=docket, actual=hit["matched"],
                kind="match", label="Docket number found in the drawings margin"))
    return issue


def _sheet_numbering(text) -> Issue:
    name = "Sheet Numbering Present"
    found = any(re.search(p, text, re.IGNORECASE) for p in
                (r"Sheet\s+\d+\s+of\s+\d+", r"Page\s+\d+\s+of\s+\d+", r"\d+\s*/\s*\d+"))
    if found:
        return Issue(24, _CAT, name, "PASS", "Sheet/page numbering detected")
    return Issue(24, _CAT, name, "WARNING", "Sheet numbering not detected")
