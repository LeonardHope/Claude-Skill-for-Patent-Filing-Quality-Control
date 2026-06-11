"""Priority / related-application checks: 63, 64, 65, and the OFFLINE path of 81
(priority application number verification — the Spec↔ADS consistency comparison
and manual verification links). The engine's optional USPTO ODP *network* branch
(active only when an API key is configured) is intentionally not replicated here;
the standalone skill still performs it. See _priority_app_numbers.
"""
import re
import urllib.parse

from ..result import Issue
from ._ev import region, data

_CAT = "Priority Claims"

_SPEC_PRIORITY = (
    r"(?:claims|claiming)\s+(?:the\s+)?(?:benefit|priority)\s+(?:of|to|under)",
    r"\bcontinuation(?:[-\s]in[-\s]part)?\s+of",
    r"\bdivisional\s+(?:of|application)",
    r"\bprovisional\s+application\s+(?:no\.?|number)",
)
_SPEC_RELATED = (
    r"CROSS[-\s]*REFERENCE", r"RELATED\s+APPLICATION", r"PRIORITY\s+CLAIM",
    r"PRIORITY\s+TO\s+RELATED", r"\bcontinuation\s+of\b",
    r"\bclaims\s+(?:the\s+)?(?:benefit|priority)",
)


def check_priority(qc):
    ads = getattr(qc, "ads_data", None)
    dom = (ads.get("domestic_continuity_entries") if ads else None) or []
    foreign = (ads.get("foreign_priority_entries") if ads else None) or []
    spec = getattr(qc, "spec_text", "") or ""
    spec_priority = next((re.search(p, spec, re.IGNORECASE).group(0)
                          for p in _SPEC_PRIORITY if re.search(p, spec, re.IGNORECASE)), None)
    sp = (getattr(qc, "documents", {}) or {}).get("Specification")
    c63 = _consistency(dom, foreign, spec_priority)
    if spec_priority:
        e = region("Specification", sp, spec_priority, kind="match",
                   label="Priority language in Specification")
        if e:
            c63.evidence = [e]
    return ([c63, _related(qc, dom, foreign, spec_priority, spec, sp), _foreign(foreign)]
            + _priority_app_numbers(qc, dom))


def _consistency(dom, foreign, spec_priority) -> Issue:
    name = "Priority Claim Consistency"
    if dom or foreign:
        if spec_priority:
            return Issue(63, _CAT, name, "PASS",
                         f"Priority claims present in both ADS and specification "
                         f"({len(dom)} domestic, {len(foreign)} foreign in ADS)")
        return Issue(63, _CAT, name, "WARNING",
                     f"ADS lists {len(dom)} domestic and {len(foreign)} foreign priority "
                     f"entries, but no priority language found in specification. Spec "
                     f"should reference the parent/priority application(s).")
    if spec_priority:
        return Issue(63, _CAT, name, "WARNING",
                     "Priority language detected in specification but no priority entries "
                     "in ADS. Verify the ADS continuity/foreign-priority sections are "
                     "filled in correctly.")
    return Issue(63, _CAT, name, "PASS",
                 "No priority claims detected in specification or ADS")


def _related(qc, dom, foreign, spec_priority, spec, sp=None) -> Issue:
    name = "Related Application References"
    if dom or foreign or spec_priority:
        hit = next((re.search(p, spec, re.IGNORECASE) for p in _SPEC_RELATED
                    if spec and re.search(p, spec, re.IGNORECASE)), None)
        if hit:
            issue = Issue(64, _CAT, name, "PASS",
                          "Related-application cross-reference language found in specification")
            e = region("Specification", sp, hit.group(0), kind="match",
                       label="Related-application reference")
            if e:
                issue.evidence = [e]
            return issue
        return Issue(64, _CAT, name, "WARNING",
                     "Priority claims present but no Cross-Reference / Related Applications "
                     "section found in specification. Verify the spec includes proper "
                     "priority/continuation language near the start.")
    return Issue(64, _CAT, name, "PASS", "No related applications detected")


def _foreign(foreign) -> Issue:
    name = "Foreign Priority Documents"
    if foreign:
        countries = sorted({(e.get("country") or "?").upper() for e in foreign})
        issue = Issue(65, _CAT, name, "INFO",
                      f"{len(foreign)} foreign priority claim(s) in ADS "
                      f"({', '.join(countries)}). Verify that certified copies of the "
                      f"foreign priority documents are on file or being filed.")
        issue.evidence = [data("Foreign priority claims (ADS)",
                               actual=f"{len(foreign)} — {', '.join(countries)}", kind="value",
                               doc_type="ADS")]
        return issue
    issue = Issue(65, _CAT, name, "N/A", "No foreign priority claims in ADS")
    issue.evidence = [data("Foreign priority claims (ADS)", actual="none", kind="value")]
    return issue


# ---- Check 81: priority application number verification (offline path) -------
# The engine's Check 81 is ~640 lines, dominated by the optional USPTO ODP
# network branch (only active when an API key is configured). We migrate the
# OFFLINE behaviour that runs by default: the no-continuity PASS, the Spec ↔ ADS
# application-number consistency comparison, and the manual verification links.
# When an ODP key is set, the standalone skill still does the online check; the
# app (core path) does the offline comparison — "leaving the ODP lookup as-is".
def _norm81(s):
    return re.sub(r"[/,.\s\-]", "", (s or "").strip()).upper()


def _extract_spec_app_nums(text):
    found = {}
    if not text:
        return found
    for pat in (r"PCT/[A-Z]{2}\s?\d{2,4}/\d+", r"\b\d{2}/\d{3},?\s?\d{3}\b",
                r"\b6[0-2]/\d{3},?\s?\d{3}\b", r"\b\d{8}\b"):
        for m in re.finditer(pat, text, re.IGNORECASE):
            raw = re.sub(r"\s", "", m.group(0).strip())
            n = _norm81(raw)
            if n and n not in found:
                found[n] = raw
    return found


def _verification_urls(raw_app):
    clean = re.sub(r"[/,.\s\-]", "", raw_app)
    if raw_app.upper().startswith("PCT"):
        google = f"https://patents.google.com/?q={urllib.parse.quote(raw_app, safe='')}"
        return f"https://patentcenter.uspto.gov/applications/{clean}", google
    return f"https://patentcenter.uspto.gov/applications/{clean}", None


def _priority_app_numbers(qc, dom):
    name = "Priority Application Number Verification"
    if not dom:
        issue = Issue(81, _CAT, name, "N/A",
                      "No domestic continuity entries — check not applicable")
        issue.evidence = [data("Domestic continuity entries (ADS)", actual="none", kind="value")]
        return [issue]

    ads_num_map = {}
    for idx, entry in enumerate(dom):
        date = (entry.get("date") or "").strip()
        for field in ("application_number", "prior_application_number"):
            raw = (entry.get(field) or "").strip()
            if raw:
                n = _norm81(raw)
                if n and n not in ads_num_map:
                    ads_num_map[n] = (raw, date, idx + 1)

    spec = getattr(qc, "spec_text", "") or ""
    spec_para = None
    if spec:
        m = re.search(r"(?:CROSS[-\s]*REFERENCE\s+(?:TO\s+)?RELATED\s+APPLICATIONS?"
                      r"|RELATED\s+APPLICATIONS?|PRIORITY\s+CLAIMS?|PRIORITY\s+TO\s+RELATED)",
                      spec, re.IGNORECASE)
        if m:
            spec_para = spec[m.start():m.start() + 1500]
        else:
            m2 = re.search(r"(?:claims?\s+(?:the\s+)?(?:benefit|priority)|"
                           r"continuation(?:-in-part)?\s+of)", spec, re.IGNORECASE)
            if m2:
                spec_para = spec[m2.start():m2.start() + 1200]
    spec_num_map = _extract_spec_app_nums(spec_para)

    out = []
    cname = "Priority Application Number Consistency (Spec ↔ ADS)"
    if not spec_para:
        i = Issue(81, _CAT, cname, "INFO",
                  "No priority paragraph found in specification — "
                  "spec/ADS consistency check skipped")
        i.evidence = [data("Spec priority paragraph", actual="not found", kind="value",
                           doc_type="Specification")]
        out.append(i)
    elif not spec_num_map:
        i = Issue(81, _CAT, cname, "WARNING",
                  "Priority paragraph found but no application numbers extracted — "
                  "manual review recommended")
        i.evidence = [data("Spec priority application numbers", actual="none extracted",
                           kind="mismatch", doc_type="Specification")]
        out.append(i)
    else:
        b_issues = []
        for n, raw in spec_num_map.items():
            if n not in ads_num_map:
                b_issues.append(f"Spec has '{raw}' — no matching entry in ADS continuity table")
        for n, (raw, _, _eidx) in ads_num_map.items():
            if n not in spec_num_map:
                b_issues.append(f"'{raw}' in ADS not found in spec priority paragraph")
        if b_issues:
            i = Issue(81, _CAT, cname, "CRITICAL",
                      f"{len(b_issues)} inconsistency/inconsistencies between spec priority "
                      f"paragraph and ADS — possible digit error (e.g. dropped leading zero "
                      f"or transposed digits)", details="\n".join(b_issues))
            i.evidence = [data(b, actual="inconsistent", kind="mismatch") for b in b_issues[:6]]
            out.append(i)
        else:
            i = Issue(81, _CAT, cname, "PASS",
                      f"All {len(spec_num_map)} application number(s) in the spec priority "
                      f"paragraph match ADS entries (and vice versa)")
            i.evidence = [data("Priority application numbers (Spec ↔ ADS)",
                               actual=", ".join(r for r, _, _ in ads_num_map.values()),
                               kind="match", doc_type="ADS")]
            out.append(i)

    url_lines = []
    for n, (raw, date, eidx) in sorted(ads_num_map.items(), key=lambda x: x[1][2]):
        pc, alt = _verification_urls(raw)
        line = f"Entry {eidx}: {raw}"
        if date:
            line += f"  (ADS filing date: {date})"
        line += f"\n  Patent Center: {pc}"
        if alt:
            line += f"\n  Google Patents: {alt}"
        url_lines.append(line)
    links = Issue(81, _CAT, "USPTO Verification Links", "INFO",
                  "Automated verification not active — set USPTO_ODP_API_KEY to enable.\n"
                  "To obtain a free key: https://developer.uspto.gov/ "
                  "(Create Account → API Keys, no approval required).\n"
                  "Manual verification links:",
                  details="\n\n".join(url_lines) if url_lines else "")
    links.evidence = [data(f"Entry {eidx}: {raw}", actual="verify in Patent Center",
                           kind="value", doc_type="ADS")
                      for n, (raw, date, eidx) in sorted(ads_num_map.items(), key=lambda x: x[1][2])][:6]
    out.append(links)
    return out
