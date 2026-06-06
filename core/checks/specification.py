"""Specification checks (13-21), migrated to core. Mirrors the engine verbatim.

Check 16 (reference-numeral consistency) is migrated too — copied verbatim,
calling the engine helpers qc._extract_reference_numerals[_from_drawings].
check_specification(qc) returns issues for 13-21.
"""
import re

from ..result import Issue
from ._ev import region, data

_CAT = "Specification"
_SPEC_IDS = (13, 14, 15, 17, 18, 19, 20, 21)


def check_specification(qc):
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        out = [Issue(i, _CAT, f"Check {i}", "CRITICAL", "Specification not found")
               for i in _SPEC_IDS]
        out.append(_reference_numerals(qc))   # 16 emits INFO when spec is absent
        return out
    sp = (getattr(qc, "documents", {}) or {}).get("Specification")
    out = [_claim_numbering(qc, spec), _claim_dependency(qc, spec),
           _figure_refs(qc, spec), _reference_numerals(qc),
           _abstract(spec, sp), _background(spec, sp),
           _brief_description(spec, sp), _detailed_description(spec, sp),
           _claims_section(spec, sp)]
    return out


def _located(issue, spec_path, phrase, label):
    """Attach a pdf_region receipt pointing at `phrase` (a found section header)
    in the specification PDF, when locatable. No-op if the spec is a .docx or the
    header can't be located. Returns the issue for chaining."""
    e = region("Specification", spec_path, phrase, label=label, kind="match")
    if e:
        issue.evidence = [e]
    return issue


# ---- Check 13: claim numbering sequential ----------------------------------
def _claim_numbering(qc, spec) -> Issue:
    name = "Claim Numbering Sequential"
    claims_text = None
    for pat in (r"\bCLAIMS\b\s*\n(.{50,}?)(?:\bABSTRACT\b|\Z)",
                r"CLAIMS\s+What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)",
                r"What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)",
                r"(?:CLAIMS?\s*\n|What is claimed[^\n]*\n)(.*?)(?:ABSTRACT|$)"):
        m = re.search(pat, spec, re.DOTALL | re.IGNORECASE)
        if m:
            claims_text = m.group(1)
            break
    if not claims_text:
        claims_text = spec

    claim_matches = []
    for pat in (r"(?:^|\n)\s*(\d+)\.\s+(?=\D)", r"(?:\.\s+|\;\s+|:\s+)(\d+)\.\s+(?=\D)",
                r"\s{2,}(\d+)\.\s+(?=\D)", r"\s+\d{2,3}\s+(\d+)\.\s+(?=\D)"):
        claim_matches.extend(re.findall(pat, claims_text, re.IGNORECASE))
    claim_matches = list(set(claim_matches))

    temp = sorted({int(n) for n in claim_matches if 1 <= int(n) <= 100})
    if temp:
        for g in set(range(1, max(temp) + 1)) - set(temp):
            if re.search(rf"(?<=\S){g}\.\s+(?=\D)", claims_text):
                claim_matches.append(str(g))
        claim_matches = list(set(claim_matches))

    if claim_matches:
        nums = sorted({int(n) for n in claim_matches if 1 <= int(n) <= 100})
        expected = list(range(1, max(nums) + 1))
        found_ev = data("Claim numbers found", actual=", ".join(map(str, nums)),
                        kind="match", doc_type="Specification")
        if nums == expected:
            issue = Issue(13, _CAT, name, "PASS", f"Claims numbered sequentially (1-{len(nums)})")
            issue.evidence = [found_ev]
            return issue
        missing = set(expected) - set(nums)
        if missing:
            issue = Issue(13, _CAT, name, "CRITICAL",
                          f"Claims not numbered sequentially - missing: {sorted(missing)}",
                          details=f"Found: {nums}")
            found_ev.kind = "mismatch"
            issue.evidence = [found_ev,
                              data("Missing claim numbers",
                                   actual=", ".join(map(str, sorted(missing))), kind="mismatch")]
            return issue
        issue = Issue(13, _CAT, name, "PASS", f"Claims numbered sequentially (1-{max(nums)})")
        issue.evidence = [found_ev]
        return issue

    simple = []
    for pat in (r"(?:^|\n)\s*(\d+)\.\s+", r"(?:\.\s+|\;\s+|:\s+)(\d+)\.\s+",
                r"\s{2,}(\d+)\.\s+", r"^\s*(\d+)\.\s+", r"\s+\d{2,3}\s+(\d+)\.\s+"):
        simple.extend(re.findall(pat, claims_text, re.MULTILINE))
    snums = sorted({int(n) for n in simple if 1 <= int(n) <= 100})
    if snums:
        if snums == list(range(1, max(snums) + 1)):
            return Issue(13, _CAT, name, "PASS",
                         f"Claims appear numbered sequentially (1-{len(snums)})")
        return Issue(13, _CAT, name, "WARNING",
                     f"Claim numbering may have issues. Found numbers: {snums}")
    return Issue(13, _CAT, name, "WARNING",
                 "Unable to detect claim numbers - claims may use non-standard format")


# ---- Check 14: claim dependency validity -----------------------------------
_DEP = (r"of|according to|as (?:recited|claimed|set forth) in|as in")


def _claim_dependency(qc, spec) -> Issue:
    name = "Claim Dependency Validity"
    deps = []
    for pat in (rf"(?:^|\n|\.\s{{1,3}})(\d+)\.\s+(?:The|A|An)\s+[\w\-]+(?:\s+[\w\-]+)*\s+(?:{_DEP})\s+claim\s+(\d+)",
                rf"\s{{2,}}(\d+)\.\s+(?:The|A|An)\s+[\w\-]+(?:\s+[\w\-]+)*\s+(?:{_DEP})\s+claim\s+(\d+)",
                rf"\s+\d{{2,3}}\s+(\d+)\.\s+(?:The|A|An)\s+[\w\-]+(?:\s+[\w\-]+)*\s+(?:{_DEP})\s+claim\s+(\d+)"):
        deps.extend(re.findall(pat, spec, re.IGNORECASE | re.MULTILINE))
    deps = list(set(deps))

    if deps:
        valid = [(c, d) for c, d in deps
                 if int(c) != int(d) and 1 <= int(c) <= 100 and 1 <= int(d) <= 100]
        invalid = [(c, d) for c, d in valid if int(c) <= int(d)]
        if not invalid and valid:
            issue = Issue(14, _CAT, name, "PASS",
                          f"Dependent claims reference lower-numbered claims "
                          f"({len(valid)} dependencies found)")
            issue.evidence = [data("Dependencies found",
                                   actual=", ".join(f"claim {c}→{d}" for c, d in valid[:10]),
                                   kind="match", doc_type="Specification")]
            return issue
        if invalid:
            issue = Issue(14, _CAT, name, "CRITICAL",
                          "Invalid claim dependencies found - claims reference same or "
                          "higher numbered claims", details=str(invalid))
            issue.evidence = [data(f"Claim {c} depends on claim {d}",
                                   actual="references a same/higher-numbered claim",
                                   kind="mismatch", doc_type="Specification")
                              for c, d in invalid[:5]]
            return issue
        return Issue(14, _CAT, name, "INFO",
                     "No valid dependent claims detected after filtering")

    fb = re.findall(r"(\d+)\.\s+(?:The|A|An)\s+.{0,150}?\s+(?:of\s+)?claim\s+(\d+)",
                    spec, re.IGNORECASE)
    fb = list({(c, d) for c, d in fb
               if int(c) != int(d) and 1 <= int(c) <= 100 and 1 <= int(d) <= 100})
    if fb:
        invalid = [(c, d) for c, d in fb if int(c) <= int(d)]
        if not invalid:
            return Issue(14, _CAT, name, "PASS",
                         f"Dependent claims appear valid ({len(fb)} dependencies found)")
        return Issue(14, _CAT, name, "CRITICAL", "Invalid claim dependencies found",
                     details=str(invalid))
    return Issue(14, _CAT, name, "INFO",
                 "No dependent claims detected (all claims may be independent)")


# ---- Check 15: figure reference validity -----------------------------------
def _figure_refs(qc, spec) -> Issue:
    name = "Figure Reference Validity"
    spec_figs = set(qc._extract_figure_numbers(spec))
    draw_figs = set(qc._extract_figure_numbers(qc.drawings_text)) if getattr(qc, "drawings_text", "") else set()

    def fl(s):
        return ", ".join(str(n) for n in sorted(s))

    if not qc._drawings_text_extractable() and spec_figs:
        issue = Issue(15, _CAT, name, "INFO",
                      f"Drawings PDF appears to be image-only — cannot verify FIG. labels "
                      f"by text extraction. Spec references: FIG. {fl(spec_figs)}. "
                      f"Manually verify each is present in the drawings.")
        issue.evidence = [data("Figures referenced in specification",
                               actual=f"FIG. {fl(spec_figs)}", kind="value", doc_type="Specification")]
        return issue
    if spec_figs and draw_figs:
        missing = spec_figs - draw_figs
        if not missing:
            issue = Issue(15, _CAT, name, "PASS",
                          f"All referenced figures exist in drawings (FIG. {fl(spec_figs)})")
            issue.evidence = [data("Figures in spec & drawings", actual=f"FIG. {fl(spec_figs)}",
                                   kind="match", doc_type="Specification")]
            return issue
        return Issue(15, _CAT, name, "CRITICAL",
                     f"Specification references figures not in drawings: FIG. {fl(missing)}")
    if spec_figs:
        return Issue(15, _CAT, name, "INFO",
                     f"Drawings text extraction was minimal — cannot verify. "
                     f"Spec references: FIG. {fl(spec_figs)}")
    return Issue(15, _CAT, name, "WARNING",
                 "Unable to detect figure references in specification")


# ---- Check 17: abstract present and length ---------------------------------
def _abstract(spec, spec_path=None) -> Issue:
    name = "Abstract Present and Length Compliant"
    m = re.search(
        r"\bABSTRACT\b\s*(?:OF\s+THE\s+(?:DISCLOSURE|INVENTION))?\s*[:\n]+"
        r"(.{20,2500}?)"
        r"(?=\n\s*(?:BACKGROUND|FIELD|BRIEF|DETAILED|CLAIMS|WHAT\s+IS\s+CLAIMED|"
        r"I\s+HEREBY\s+DECLARE|FIG\.|Sheet\s+\d+\s*(?:of|/)\s*\d+)|\Z)",
        spec, re.IGNORECASE | re.DOTALL)
    if not m:
        return Issue(17, _CAT, name, "CRITICAL", "Abstract section not found")
    cleaned = m.group(1)
    cleaned = re.sub(r"\bPage\s+\d+(?:\s+of\s+\d+)?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?m)^\s*\d{1,3}\s*$", " ", cleaned)
    cleaned = re.sub(r"(?m)^\s*\d+\s*/\s*\d+\s*$", " ", cleaned)
    cleaned = re.sub(r"\bPatent\s+Application\s+Publication\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:US|U\.S\.)\s*\d{4}/\d+\s*A\d?\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    wc = len(cleaned.split())
    tag = lambda issue: _located(issue, spec_path, "ABSTRACT", "Abstract section")
    if wc == 0:
        return tag(Issue(17, _CAT, name, "WARNING",
                         "Abstract heading found but body could not be extracted"))
    if wc <= 150:
        return tag(Issue(17, _CAT, name, "PASS", f"Abstract found ({wc} words, limit is 150)"))
    preview = (cleaned[:240] + "…") if len(cleaned) > 240 else cleaned
    return tag(Issue(17, _CAT, name, "WARNING",
                     f"Abstract may be too long ({wc} words, limit is 150)",
                     details=(f"Extracted text used for the count (verify against the source "
                              f".docx, as PDF text extraction can splice in page-header/footer "
                              f"artifacts):\n\n{preview}")))


def _background(spec, spec_path=None) -> Issue:
    name = "Background Section Present"
    m = re.search(r"BACKGROUND|FIELD OF (?:THE )?INVENTION", spec, re.IGNORECASE)
    if m:
        return _located(Issue(18, _CAT, name, "PASS", "Background/Field section found"),
                        spec_path, m.group(0), "Background/Field section")
    return Issue(18, _CAT, name, "WARNING", "Background/Field section not clearly identified")


def _brief_description(spec, spec_path=None) -> Issue:
    name = "Brief Description of Drawings Present"
    m = re.search(r"BRIEF DESCRIPTION OF (?:THE )?DRAWINGS", spec, re.IGNORECASE)
    if m:
        return _located(Issue(19, _CAT, name, "PASS", "Brief Description of Drawings section found"),
                        spec_path, m.group(0), "Brief Description of Drawings section")
    return Issue(19, _CAT, name, "WARNING",
                 "Brief Description of Drawings section not clearly identified")


def _detailed_description(spec, spec_path=None) -> Issue:
    name = "Detailed Description Present"
    m = re.search(r"DETAILED DESCRIPTION", spec, re.IGNORECASE)
    if m:
        return _located(Issue(20, _CAT, name, "PASS", "Detailed Description section found"),
                        spec_path, m.group(0), "Detailed Description section")
    return Issue(20, _CAT, name, "CRITICAL", "Detailed Description section not clearly identified")


def _claims_section(spec, spec_path=None) -> Issue:
    name = "Claims Section Present"
    pats = (r"(?:^|\n)\s*CLAIMS?\s*(?:\n|$)", r"(?:^|\n)\s*What is claimed",
            r"(?:^|\n)\s*I\s+claim", r"(?:^|\n)\s*We\s+claim",
            r"(?:^|\n)\s*1\.\s+A\s+", r"(?:^|\n)\s*1\.\s+An\s+",
            r"(?:^|[^A-Z])CLAIMS(?:[^A-Z]|$)", r"What\s+is\s+claimed",
            r"What\s*is\s*claimed", r"1\.\s*A\s+computer-implemented",
            r"1\.\s*A\s+method", r"1\.\s*A\s+system", r"1\.\s*An?\s+apparatus")
    for p in pats:
        m = re.search(p, spec, re.IGNORECASE | re.MULTILINE)
        if m:
            return _located(Issue(21, _CAT, name, "PASS", "Claims section found"),
                            spec_path, m.group(0).strip(), "Claims section")
    return Issue(21, _CAT, name, "CRITICAL", "Claims section not clearly identified")


# ---- Check 16: reference numeral consistency (migrated verbatim) -------------
def _reference_numerals(qc):
    name = "Reference Numeral Consistency"
    spec = getattr(qc, "spec_text", "") or ""
    spec_refs = qc._extract_reference_numerals(spec) if spec else {}
    draw = getattr(qc, "drawings_text", "") or ""
    drawings_refs = qc._extract_reference_numerals_from_drawings(draw) if draw else set()
    if not spec_refs:
        issue = Issue(16, _CAT, name, "INFO",
                      "Unable to extract reference numerals - manual review recommended")
        issue.evidence = [data("Reference numerals", actual="none extracted", kind="value",
                               doc_type="Specification")]
        return issue

    modifiers = ['target', 'source', 'primary', 'secondary', 'main', 'new', 'old', 'current',
                 'next', 'previous', 'updated', 'original', 'modified', 'first', 'second',
                 'third', 'specific', 'particular', 'given', 'respective', 'corresponding',
                 'associated', 'related']

    def get_core_name(desc):
        words = desc.lower().split()
        core = [w for w in words if w not in modifiers]
        if not core and words:
            core = [words[-1]]
        return ' '.join(core)

    def is_acronym_of(short, lng):
        short = short.replace(' ', '').lower()
        words = lng.split()
        if len(short) == len(words) and len(words) >= 2:
            return ''.join(w[0].lower() for w in words if w) == short
        return False

    def is_same_element(d1, d2):
        c1, c2 = get_core_name(d1), get_core_name(d2)
        if c1 == c2 or c1 in c2 or c2 in c1:
            return True
        if c1.split()[-1] == c2.split()[-1]:
            return True
        if is_acronym_of(c1, c2) or is_acronym_of(c2, c1):
            return True
        return re.sub(r"\s", "", c1.lower()) == re.sub(r"\s", "", c2.lower())

    warnings = []
    for num, rd in spec_refs.items():
        descs = rd['descriptions']
        if len(descs) > 1:
            desc_list = list(descs)
            groups, used = [], set()
            for i, d1 in enumerate(desc_list):
                if i in used:
                    continue
                group = [d1]; used.add(i)
                for j, d2 in enumerate(desc_list):
                    if j not in used and is_same_element(d1, d2):
                        group.append(d2); used.add(j)
                groups.append(group)
            if len(groups) > 1:
                reps = [g[0] for g in groups]
                warnings.append(f"Ref {num} may have inconsistent descriptions: {reps[:3]}")

    if drawings_refs:
        spec_ref_nums = set(spec_refs.keys())
        truly_missing = [n for n in sorted(drawings_refs - spec_ref_nums)
                         if not re.search(rf"\b{re.escape(n)}\b", spec)]
        if truly_missing:
            warnings.append(f"Reference numerals in drawings may need verification: {truly_missing}")

    total_refs = len(spec_refs)
    total_occ = sum(rd['count'] for rd in spec_refs.values())
    if warnings:
        ws = "; ".join(warnings[:3])
        if len(warnings) > 3:
            ws += f" (and {len(warnings) - 3} more)"
        issue = Issue(16, _CAT, name, "WARNING", f"Potential inconsistencies: {ws}",
                      details=f"Total reference numerals: {total_refs}. Manual review recommended.")
        issue.evidence = [data(w.split(":")[0], actual="inconsistent", kind="mismatch",
                               doc_type="Specification") for w in warnings[:5]]
        return issue
    issue = Issue(16, _CAT, name, "PASS",
                  f"Reference numerals appear consistent ({total_refs} unique numerals, "
                  f"{total_occ} total occurrences)")
    issue.evidence = [data("Reference numerals",
                           actual=f"{total_refs} unique, {total_occ} occurrences — consistent",
                           kind="match", doc_type="Specification")]
    return issue
