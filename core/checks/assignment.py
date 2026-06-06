"""Assignment checks (36, 37, 38, 40), migrated to core. Mirrors the engine.

Check 39 (execution date logical) is left engine-emitted — it OCRs signature
pages to find the date. check_assignment(qc) returns issues for 36, 37, 38, 40
and handles the assignment-missing fallback (36-38, 40; 39 is the engine's).
"""
import re

from ..result import Issue
from ._ev import data

_CAT = "Assignment"
_IDS = (36, 37, 38, 40)


def check_assignment(qc):
    text = getattr(qc, "assignment_text", "") or ""
    if not text:
        return [Issue(i, _CAT, f"Check {i}", "INFO",
                      "Assignment not found (optional document)") for i in _IDS]
    return [_assignors(qc, text), _assignee(text), _references_app(qc, text),
            _rights(text)]


def _assignors(qc, text) -> Issue:
    name = "Assignment Identifies All Assignors"
    pairs = []
    ads = getattr(qc, "ads_data", None)
    if ads and ads.get("inventors"):
        for inv in ads["inventors"]:
            pairs.append((qc._format_xfa_inventor(inv), qc._xfa_surname(inv)))
    elif getattr(qc, "ads_text", ""):
        for n in qc.extract_inventors(qc.ads_text):
            pairs.append((n, n.split()[-1] if n.split() else ""))
    names = [n for n, _ in pairs]
    if not names:
        return Issue(36, _CAT, name, "INFO",
                     "Unable to extract inventor names from ADS for comparison")

    asgn_norm = qc._normalize_for_compare(text)
    missing = []
    for nm, last in pairs:
        last_n = qc._normalize_for_compare(last)
        full_n = qc._normalize_for_compare(nm)
        if (last_n and last_n in asgn_norm) or (full_n and full_n in asgn_norm):
            continue
        missing.append(nm)
    if not missing:
        issue = Issue(36, _CAT, name, "PASS",
                      f"All {len(names)} inventors from ADS appear in the assignment")
        issue.evidence = [data("ADS inventors found in assignment",
                               actual=f"{len(names)} of {len(names)}", kind="match",
                               doc_type="Assignment")]
        return issue
    img = (getattr(qc, "image_only_pages", {}) or {}).get("Assignment", 0)
    img_note, sev = "", "CRITICAL"
    if img and len(missing) <= img:
        img_note = (f" The assignment has {img} image-only page(s) — missing inventor(s) "
                    f"may be on those pages but could not be verified by text extraction. "
                    f"Open the assignment and confirm those pages cover the missing "
                    f"inventor(s).")
        sev = "WARNING"
    issue = Issue(36, _CAT, name, sev,
                  f"{len(missing)} of {len(names)} ADS inventor(s) not found in "
                  f"assignment text." + img_note,
                  details="Not found in extracted assignment text:\n" +
                          "\n".join(f"  • {n}" for n in missing))
    issue.evidence = [data(f"Not found in assignment: {n}", actual="missing", kind="missing",
                           doc_type="Assignment") for n in missing[:6]]
    return issue


def _assignee(text) -> Issue:
    name = "Assignment Identifies Assignee"
    if re.search(r"assignee", text, re.IGNORECASE):
        issue = Issue(37, _CAT, name, "PASS", "Assignee appears to be identified")
        issue.evidence = [data("Assignee", actual="identified in assignment", kind="match",
                               doc_type="Assignment")]
        return issue
    issue = Issue(37, _CAT, name, "WARNING", "Assignee not clearly identified")
    issue.evidence = [data("Assignee", actual="not clearly identified", kind="mismatch",
                           doc_type="Assignment")]
    return issue


def _references_app(qc, text) -> Issue:
    name = "Assignment References Correct Application"
    ads = getattr(qc, "ads_data", None)
    dockets = set()
    if ads and ads.get("docket_number"):
        dockets.add(ads["docket_number"])
    elif getattr(qc, "ads_text", ""):
        dockets |= qc.extract_docket_numbers(qc.ads_text)
    if getattr(qc, "spec_text", ""):
        dockets |= qc.extract_docket_numbers(qc.spec_text)
    title = (ads or {}).get("title", "") if ads else ""

    matched = None
    asgn_norm = re.sub(r"[\s\-_]", "", text.upper())
    for d in dockets:
        if re.sub(r"[\s\-_]", "", d.upper()) in asgn_norm:
            matched = d
            break
    title_in = False
    if title:
        tw = title.split()
        chunk = " ".join(tw[:max(4, int(len(tw) * 0.6))])
        if qc._normalize_for_compare(chunk) in qc._normalize_for_compare(text):
            title_in = True

    if matched:
        issue = Issue(38, _CAT, name, "PASS", f"Assignment contains expected docket: {matched}")
        issue.evidence = [data("Docket in assignment", actual=matched, kind="match",
                               doc_type="Assignment")]
        return issue
    if title_in:
        issue = Issue(38, _CAT, name, "PASS",
                      "Assignment references the application title from the ADS")
        issue.evidence = [data("Application title in assignment", actual="matches ADS title",
                               kind="match", doc_type="Assignment")]
        return issue
    if qc._is_continuation_filing():
        return Issue(38, _CAT, name, "INFO",
                     "Could not match this child application's docket/title in the "
                     "assignment. For continuations, the assignment carried forward from "
                     "the parent typically references the parent's docket and original "
                     "title — manual verification recommended.")
    return Issue(38, _CAT, name, "WARNING",
                 "Could not verify assignment references correct docket/title")


def _rights(text) -> Issue:
    name = "Assignment Covers Correct Rights"
    pats = (r"entire right", r"(?:title|7tle).*interest", r"sell.*assign.*transfer",
            r"assign.*transfer.*convey", r"right.*(?:title|7tle).*interest",
            r"ASSIGNOR.*ASSIGNEE")
    if any(re.search(p, text, re.IGNORECASE | re.DOTALL) for p in pats):
        issue = Issue(40, _CAT, name, "PASS", "Assignment language appears to transfer rights")
        issue.evidence = [data("Rights-transfer language", actual="present", kind="match",
                               doc_type="Assignment")]
        return issue
    issue = Issue(40, _CAT, name, "WARNING", "Standard assignment language not clearly detected")
    issue.evidence = [data("Rights-transfer language", actual="not clearly detected",
                           kind="mismatch", doc_type="Assignment")]
    return issue
