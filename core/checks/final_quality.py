"""Final-quality checks (66-70), migrated to core. Mirrors the engine verbatim."""
import re

from ..result import Issue

_CAT = "Final Quality"
_MONTHS = (r"(?:January|February|March|April|May|June|July|August|September|October|"
           r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)")


def check_final_quality(qc):
    return [_typos(qc), _dates(qc), _long_claims(qc), _refs_all_claims(qc),
            _figure_format(qc)]


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
        return Issue(66, _CAT, name, "WARNING",
                     f"Potential issues found: {'; '.join(issues[:3])}")
    return Issue(66, _CAT, name, "PASS", "No obvious typos detected in critical fields")


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
        return Issue(67, _CAT, name, "WARNING", f"Date format issues: {'; '.join(issues[:3])}")
    if found:
        return Issue(67, _CAT, name, "PASS", f"All {len(found)} dates appear properly formatted")
    return Issue(67, _CAT, name, "PASS", "No date format issues detected")


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
            return Issue(68, _CAT, name, "WARNING", f"Unusually long claims detected: {d}")
        return Issue(68, _CAT, name, "PASS",
                     f"No excessively long claims detected ({len(claims)} claims checked)")
    return Issue(68, _CAT, name, "INFO", "Unable to parse individual claims for length check")


def _refs_all_claims(qc) -> Issue:
    name = "Specification References All Claims"
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        return Issue(69, _CAT, name, "WARNING", "Specification not found")
    claims_text = None
    for pat in (r"CLAIMS\s+What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)",
                r"What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)",
                r"(?:CLAIMS?\s*\n|What is claimed[^\n]*\n)(.*?)(?:ABSTRACT|$)"):
        m = re.search(pat, spec, re.DOTALL | re.IGNORECASE)
        if m:
            claims_text = m.group(1)
            break
    dm = re.search(r"(?:DETAILED\s+DESCRIPTION|DESCRIPTION\s+OF.*?EMBODIMENTS?)(.*?)"
                   r"(?:CLAIMS|What is claimed)", spec, re.DOTALL | re.IGNORECASE)
    desc = dm.group(1) if dm else ""
    if claims_text and desc:
        valid = {n for n in set(re.findall(r"\b(\d{2,3})\b", claims_text))
                 if re.search(r"(?:a|an|the|said)\s+[\w\-]+(?:\s+[\w\-]+){0,2}\s+" + n + r"\b",
                              claims_text, re.IGNORECASE)}
        if valid:
            missing = [n for n in valid if n not in desc]
            if not missing:
                return Issue(69, _CAT, name, "PASS",
                             f"All {len(valid)} claim reference numerals found in specification")
            if len(missing) <= 2:
                return Issue(69, _CAT, name, "PASS",
                             f"Most claim elements referenced in specification "
                             f"({len(valid) - len(missing)}/{len(valid)})")
            return Issue(69, _CAT, name, "WARNING",
                         f"{len(missing)} claim reference numerals not found in "
                         f"specification: {', '.join(sorted(missing)[:5])}")
        return Issue(69, _CAT, name, "INFO",
                     "No reference numerals detected in claims — cannot verify "
                     "claim-to-specification element references. Manual review recommended.")
    return Issue(69, _CAT, name, "INFO",
                 "Could not isolate claims and description for cross-reference")


def _figure_format(qc) -> Issue:
    name = "Consistent Figure Reference Format"
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        return Issue(70, _CAT, name, "WARNING", "Specification not found")
    refs = re.findall(r"(FIG(?:URE)?\.?\s*\d+)", spec, re.IGNORECASE)
    if refs:
        formats = {r.split()[0].upper() for r in refs}
        if len(formats) == 1:
            return Issue(70, _CAT, name, "PASS",
                         f"Figure references use consistent format: {list(formats)[0]}")
        return Issue(70, _CAT, name, "WARNING",
                     f"Mixed figure reference formats detected: {formats}")
    return Issue(70, _CAT, name, "INFO", "No figure references detected")
