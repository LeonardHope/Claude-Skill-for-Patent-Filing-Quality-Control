"""Final-quality checks (66-70), migrated to core. Mirrors the engine verbatim."""
import re

from ..result import Issue
from ._ev import region, data

_CAT = "Final Quality"
_MONTHS = (r"(?:January|February|March|April|May|June|July|August|September|October|"
           r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)")


def check_final_quality(qc):
    # Check 69 (claim reference numerals vs spec) was removed — its premise was
    # wrong (US claims carry no reference numerals) and the real claim-element →
    # specification support check is Check 59 (Cross-References).
    return [_typos(qc), _dates(qc), _long_claims(qc), _figure_format(qc)]


def _typos(qc) -> Issue:
    name = "No Obvious Typos in Critical Fields"
    spec = getattr(qc, "spec_text", "") or ""
    ads = getattr(qc, "ads_text", "") or ""
    if not (spec or ads):
        return Issue(66, _CAT, name, "INFO", "Insufficient document text for typo analysis")
    issues = []
    dockets = set()
    for text in (spec, ads, getattr(qc, "declaration_text", "") or ""):
        for m in re.findall(r"[A-Z]\d{2,4}[\s\-]*\d{3,4}[A-Z]{2}", text):
            dockets.add(re.sub(r"\s", "", m))
    if len(dockets) > 1:
        issues.append(f"Multiple docket number variants: {', '.join(dockets)}")
    if ads:
        for nm in re.findall(r"(?:Given|Family)\s*Name[:\s]+([A-Za-z]+)", ads):
            if nm and len(nm) > 1 and not (nm.isupper() or nm.islower() or nm.istitle()):
                issues.append(f"Unusual capitalization in inventor name: '{nm}'")
    tm = re.search(r"(?:Title|TITLE).*?(?:of|:)\s*(?:the\s+)?(?:Invention\s*)?(.*?)"
                   r"(?:\n|$|Attorney)", ads or spec, re.IGNORECASE)
    if tm and len(tm.group(1).strip()) < 5:
        issues.append(f"Title appears too short: '{tm.group(1).strip()}'")
    if issues:
        issue = Issue(66, _CAT, name, "WARNING",
                      f"Potential issues found: {'; '.join(issues[:3])}")
        issue.evidence = [data(s, kind="mismatch", doc_type="Specification") for s in issues[:5]]
        return issue
    issue = Issue(66, _CAT, name, "PASS", "No obvious typos detected in critical fields")
    issue.evidence = [data("Critical fields scanned (docket, names, title)",
                           actual="no obvious typos", kind="match")]
    return issue


def _dates(qc) -> Issue:
    name = "Dates in Proper Format"
    text = ((getattr(qc, "ads_text", "") or "") + (getattr(qc, "declaration_text", "") or "")
            + (getattr(qc, "assignment_text", "") or ""))
    if not text:
        return Issue(67, _CAT, name, "INFO", "Insufficient document text for date analysis")
    patterns = [
        (r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b", "MM/DD/YYYY"),
        (r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})\b", "MM/DD/YY"),
        (r"\b(" + _MONTHS + r")\s+(\d{1,2}),?\s+(\d{4})\b", "Month DD, YYYY"),
        (r"\b(\d{1,2})\s+(" + _MONTHS + r")\s+(\d{4})\b", "DD Month YYYY"),
    ]
    boiler = re.compile(r"(?:approved\s+for\s+use|OMB|Paperwork\s+Reduction|collection\s+of"
                        r"\s+information|CFR\s+\d|U\.S\.\s+Patent\s+and\s+Trademark)", re.IGNORECASE)
    found, issues = [], []
    for pat, fmt in patterns:
        for mo in re.finditer(pat, text, re.IGNORECASE):
            ctx = text[max(0, mo.start() - 100):min(len(text), mo.end() + 100)]
            if boiler.search(ctx):
                continue
            g = mo.groups()
            found.append((g, fmt))
            if fmt == "MM/DD/YY":
                issues.append(f"2-digit year found: {'/'.join(g)}")
            if fmt in ("MM/DD/YYYY", "Month DD, YYYY", "DD Month YYYY"):
                if int(g[2]) < 2000 or int(g[2]) > 2030:
                    issues.append(f"Date with unusual year: {' '.join(g)}")
    if issues:
        issue = Issue(67, _CAT, name, "WARNING", f"Date format issues: {'; '.join(issues[:3])}")
        issue.evidence = [data(s, kind="mismatch") for s in issues[:5]]
        return issue
    if found:
        issue = Issue(67, _CAT, name, "PASS", f"All {len(found)} dates appear properly formatted")
        issue.evidence = [data("Dates examined", actual=f"{len(found)} — all properly formatted",
                               kind="match")]
        return issue
    issue = Issue(67, _CAT, name, "PASS", "No date format issues detected")
    issue.evidence = [data("Dates examined", actual="none in a recognized numeric format", kind="match")]
    return issue


def _long_claims(qc) -> Issue:
    name = "No Excessively Long Claims"
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        return Issue(68, _CAT, name, "WARNING", "Specification not found")
    claims_text = qc._extract_claims_section() or spec
    positions = []
    for pat in (r"(?:^|\n)\s*(\d+)\.\s+(?=\D)", r"(?:\.\s{1,3})(\d+)\.\s+(?=\D)",
                r"\s{2,}(\d+)\.\s+(?=\D)", r"\s+\d{2,3}\s+(\d+)\.\s+(?=\D)"):
        for m in re.finditer(pat, claims_text, re.IGNORECASE | re.MULTILINE):
            n = int(m.group(1))
            if 1 <= n <= 100:
                positions.append((m.start(), n, m.end()))
    seen = {}
    for start, num, end in sorted(positions):
        if num not in seen:
            seen[num] = (start, end)
    claims = []
    sc = sorted(seen.items())
    for i, (num, (start, tstart)) in enumerate(sc):
        end = sc[i + 1][1][0] if i + 1 < len(sc) else len(claims_text)
        claims.append((num, len(claims_text[tstart:end].strip().split())))
    if claims:
        long = [(n, w) for n, w in claims if w > 200]
        if long:
            d = ", ".join(f"Claim {n} ({w} words)" for n, w in long[:5])
            issue = Issue(68, _CAT, name, "WARNING", f"Unusually long claims detected: {d}")
            issue.evidence = [data(f"Claim {n}", actual=f"{w} words", kind="mismatch",
                                   doc_type="Specification") for n, w in long[:5]]
            return issue
        longest = max(claims, key=lambda c: c[1])
        issue = Issue(68, _CAT, name, "PASS",
                      f"No excessively long claims detected ({len(claims)} claims checked)")
        issue.evidence = [data(f"{len(claims)} claims checked",
                               actual=f"longest is claim {longest[0]} ({longest[1]} words, limit 200)",
                               kind="match", doc_type="Specification")]
        return issue
    return Issue(68, _CAT, name, "INFO", "Unable to parse individual claims for length check")


def _figure_format(qc) -> Issue:
    name = "Consistent Figure Reference Format"
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        return Issue(70, _CAT, name, "WARNING", "Specification not found")
    refs = re.findall(r"(FIG(?:URE)?\.?\s*\d+)", spec, re.IGNORECASE)
    if refs:
        formats = {r.split()[0].upper() for r in refs}
        if len(formats) == 1:
            issue = Issue(70, _CAT, name, "PASS",
                          f"Figure references use consistent format: {list(formats)[0]}")
        else:
            issue = Issue(70, _CAT, name, "WARNING",
                          f"Mixed figure reference formats detected: {formats}")
        sp = (getattr(qc, "documents", {}) or {}).get("Specification")
        e = region("Specification", sp, refs[0], kind="match",
                   label=f"Figure reference '{refs[0]}' in Specification")
        if e:
            issue.evidence = [e]
        return issue
    return Issue(70, _CAT, name, "INFO", "No figure references detected")
