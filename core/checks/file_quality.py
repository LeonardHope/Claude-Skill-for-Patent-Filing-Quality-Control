"""File-quality checks. 55 (text-searchable), 56 (file naming), 58 (file size)
are migrated. Check 57 (password protection) opens each PDF with PyPDF2 to test
encryption and is left engine-emitted.
"""
import re

from ..result import Issue

_CAT = "File Quality"


def check_file_quality(qc):
    return [_searchable(qc), _naming(qc), _file_size(qc)]


def _searchable(qc) -> Issue:
    name = "PDF Text-Searchable"
    texts = {
        "Specification": getattr(qc, "spec_text", ""),
        "Drawings": getattr(qc, "drawings_text", ""),
        "ADS": getattr(qc, "ads_text", ""),
        "Declaration": getattr(qc, "declaration_text", ""),
        "Assignment": getattr(qc, "assignment_text", ""),
        "Power of Attorney": getattr(qc, "poa_text", ""),
    }
    searchable, non = [], []
    for dt, text in texts.items():
        if qc.report.files_found.get(dt):
            (searchable if text and len(text.strip()) > 100 else non).append(dt)
    if non:
        return Issue(55, _CAT, name, "WARNING",
                     f"Limited text extraction from: {', '.join(non)}")
    return Issue(55, _CAT, name, "PASS",
                 f"All {len(searchable)} PDFs are text-searchable")


def _naming(qc) -> Issue:
    name = "File Naming Conventions"
    dockets = set()
    ads = getattr(qc, "ads_data", None)
    if ads and ads.get("docket_number"):
        dockets.add(ads["docket_number"])
    if getattr(qc, "spec_text", ""):
        dockets |= qc.extract_docket_numbers(qc.spec_text)

    issues = []
    for dt, filename in qc.report.files_found.items():
        if filename and dt != "Drawings":
            fnorm = re.sub(r"[\s\-_]", "", filename.upper())
            has = any(re.sub(r"[\s\-_]", "", d.upper()) in fnorm for d in dockets if d)
            if not has and dockets:
                issues.append(f"{dt}: missing docket number")
    if issues:
        return Issue(56, _CAT, name, "INFO",
                     f"Naming suggestions: {'; '.join(issues[:3])}")
    return Issue(56, _CAT, name, "PASS",
                 "File names follow good conventions (contain docket number)")


def _file_size(qc) -> Issue:
    name = "File Size Reasonable"
    for path in (getattr(qc, "documents", {}) or {}).values():
        if path:
            try:
                if path.stat().st_size == 0:
                    return Issue(58, _CAT, name, "CRITICAL", f"{path.name} has 0 bytes")
            except Exception:
                pass
    return Issue(58, _CAT, name, "PASS", "All files have reasonable sizes")
