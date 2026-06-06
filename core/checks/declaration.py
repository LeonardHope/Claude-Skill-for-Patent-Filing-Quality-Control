"""Declaration checks (32-34), migrated to core. Mirrors the engine verbatim.

Check 35 (declaration date logical) is left engine-emitted — it OCRs the
declaration's signature pages to find dates. check_declaration(qc) returns
issues for 32, 33, 34 and handles the declaration-missing fallback (32-34; 35 is
the engine's).
"""
import re
from pathlib import Path

from ..result import Issue
from ._ev import data

_CAT = "Declaration"
_IDS = (32, 33, 34)


def _scan_hint_msg(qc):
    try:
        hint = any("declar" in p.stem.lower()
                   for p in Path(qc.folder_path).iterdir()
                   if p.suffix.lower() == ".pdf"
                   and p.name != qc.report.files_found.get("ADS", ""))
    except Exception:
        hint = False
    return ("Declaration found by filename but content unreadable (likely "
            "low-quality scan) — verify manually") if hint else "Declaration not found"


def check_declaration(qc):
    decl = getattr(qc, "declaration_text", "") or ""
    if not decl:
        msg = _scan_hint_msg(qc)
        return [Issue(i, _CAT, f"Check {i}", "WARNING", msg) for i in _IDS]
    return [_inventors_named(qc, decl), _oath_format(decl), _references_app(qc, decl)]


def _inventors_named(qc, decl) -> Issue:
    name = "All Inventors Named in Declaration"
    pairs = []
    ads = getattr(qc, "ads_data", None)
    if ads and ads.get("inventors"):
        for inv in ads["inventors"]:
            pairs.append((qc._format_xfa_inventor(inv), qc._xfa_surname(inv)))
    elif getattr(qc, "ads_text", ""):
        for nm in qc.extract_inventors(qc.ads_text):
            pairs.append((nm, nm.split()[-1] if nm.split() else ""))
    names = [n for n, _ in pairs]
    if not names:
        return Issue(32, _CAT, name, "INFO",
                     "Could not extract ADS inventors for cross-reference")

    decl_norm = qc._normalize_for_compare(decl)
    missing = []
    for inv_name, surname in pairs:
        last_norm = qc._normalize_for_compare(surname)
        full_norm = qc._normalize_for_compare(inv_name)
        if (last_norm and last_norm in decl_norm) or (full_norm and full_norm in decl_norm):
            continue
        missing.append(inv_name)
    if not missing:
        issue = Issue(32, _CAT, name, "PASS",
                      f"All {len(names)} ADS inventors appear in the declaration")
        issue.evidence = [data("ADS inventors found in declaration",
                               actual=f"{len(names)} of {len(names)}", kind="match",
                               doc_type="Declaration")]
        return issue
    cont_note = ""
    if qc._is_continuation_filing():
        cont_note = (" Note: this is a continuation filing — if inventorship changed, "
                     "a new declaration is required.")
    img = (getattr(qc, "image_only_pages", {}) or {}).get("Declaration", 0)
    img_note = ""
    if img and len(missing) <= img:
        img_note = (f" The declaration has {img} image-only page(s) — missing "
                    f"inventor(s) may be on those pages but could not be verified by text "
                    f"extraction. Open the declaration and confirm those pages cover the "
                    f"missing inventor(s).")
    issue = Issue(32, _CAT, name, "WARNING",
                  f"{len(missing)} of {len(names)} ADS inventor(s) not found in "
                  f"declaration text." + img_note + cont_note,
                  details="Not found in extracted declaration text:\n" +
                          "\n".join(f"  • {n}" for n in missing))
    issue.evidence = [data(f"Not found in declaration: {n}", actual="missing", kind="missing",
                           doc_type="Declaration") for n in missing[:6]]
    return issue


def _oath_format(decl) -> Issue:
    name = "Oath vs Declaration Format"
    pats = (r"\bswear", r"\boaths?\b", r"declare", r"declara",
            r"under penalty of perjury", r"37\s*CFR\s*1\.63")
    hit = next((re.search(p, decl, re.IGNORECASE) for p in pats
                if re.search(p, decl, re.IGNORECASE)), None)
    if hit:
        issue = Issue(33, _CAT, name, "PASS", "Declaration/oath language detected")
        issue.evidence = [data("Oath/declaration language", actual=f"“{hit.group(0)}”",
                               kind="match", doc_type="Declaration")]
        return issue
    issue = Issue(33, _CAT, name, "WARNING",
                  "Standard oath/declaration language not clearly detected")
    issue.evidence = [data("Oath/declaration language", actual="not clearly detected",
                           kind="mismatch", doc_type="Declaration")]
    return issue


def _references_app(qc, decl) -> Issue:
    name = "Declaration References Correct Application"
    dockets = set()
    ads = getattr(qc, "ads_data", None)
    if ads and ads.get("docket_number"):
        dockets.add(ads["docket_number"])
    elif getattr(qc, "ads_text", ""):
        dockets |= qc.extract_docket_numbers(qc.ads_text)
    if getattr(qc, "spec_text", ""):
        dockets |= qc.extract_docket_numbers(qc.spec_text)

    matched = None
    if dockets:
        decl_strip = re.sub(r"[\s\-_]", "", decl.upper())
        for d in dockets:
            if re.sub(r"[\s\-_]", "", d.upper()) in decl_strip:
                matched = d
                break

    title_in = False
    if ads and ads.get("title"):
        tw = ads["title"].split()
        chunk = " ".join(tw[:max(4, int(len(tw) * 0.6))])
        if qc._normalize_for_compare(chunk) in qc._normalize_for_compare(decl):
            title_in = True

    if matched:
        issue = Issue(34, _CAT, name, "PASS", f"Declaration contains expected docket: {matched}")
        issue.evidence = [data("Docket in declaration", actual=matched, kind="match",
                               doc_type="Declaration")]
        return issue
    if title_in:
        issue = Issue(34, _CAT, name, "PASS",
                      "Declaration references the application title from the ADS")
        issue.evidence = [data("Application title in declaration", actual="matches ADS title",
                               kind="match", doc_type="Declaration")]
        return issue
    if qc._is_continuation_filing():
        return Issue(34, _CAT, name, "INFO",
                     "Could not match this child application's docket/title in the "
                     "declaration. For continuations, the parent's executed declaration "
                     "carried forward typically references the parent's docket and "
                     "original title — manual verification recommended.")
    return Issue(34, _CAT, name, "INFO",
                 "Could not verify declaration references correct application")
