"""Specification checks (13-21), migrated to core. Mirrors the engine verbatim.

Check 16 (reference-numeral consistency) is intentionally NOT migrated — its
~130 lines of inline element-grouping / acronym-matching logic carry high
replication risk for little evidence value, so it stays engine-emitted and
still appears in the Result. check_specification(qc) returns the list of issues
for 13, 14, 15, 17, 18, 19, 20, 21.
"""
import re

from ..result import Issue

_CAT = "Specification"
_SPEC_IDS = (13, 14, 15, 17, 18, 19, 20, 21)


def check_specification(qc):
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        return [Issue(i, _CAT, f"Check {i}", "CRITICAL", "Specification not found")
                for i in _SPEC_IDS]
    out = [_claim_numbering(qc, spec), _claim_dependency(qc, spec),
           _figure_refs(qc, spec), _abstract(spec), _background(spec),
           _brief_description(spec), _detailed_description(spec),
           _claims_section(spec)]
    return out


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
        if nums == expected:
            return Issue(13, _CAT, name, "PASS", f"Claims numbered sequentially (1-{len(nums)})")
        missing = set(expected) - set(nums)
        if missing:
            return Issue(13, _CAT, name, "CRITICAL",
                         f"Claims not numbered sequentially - missing: {sorted(missing)}",
                         details=f"Found: {nums}")
        return Issue(13, _CAT, name, "PASS", f"Claims numbered sequentially (1-{max(nums)})")

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
            return Issue(14, _CAT, name, "PASS",
                         f"Dependent claims reference lower-numbered claims "
                         f"({len(valid)} dependencies found)")
        if invalid:
            return Issue(14, _CAT, name, "CRITICAL",
                         "Invalid claim dependencies found - claims reference same or "
                         "higher numbered claims", details=str(invalid))
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
        return Issue(15, _CAT, name, "INFO",
                     f"Drawings PDF appears to be image-only — cannot verify FIG. labels "
                     f"by text extraction. Spec references: FIG. {fl(spec_figs)}. "
                     f"Manually verify each is present in the drawings.")
    if spec_figs and draw_figs:
        missing = spec_figs - draw_figs
        if not missing:
            return Issue(15, _CAT, name, "PASS",
                         f"All referenced figures exist in drawings (FIG. {fl(spec_figs)})")
        return Issue(15, _CAT, name, "CRITICAL",
                     f"Specification references figures not in drawings: FIG. {fl(missing)}")
    if spec_figs:
        return Issue(15, _CAT, name, "INFO",
                     f"Drawings text extraction was minimal — cannot verify. "
                     f"Spec references: FIG. {fl(spec_figs)}")
    return Issue(15, _CAT, name, "WARNING",
                 "Unable to detect figure references in specification")


# ---- Check 17: abstract present and length ---------------------------------
def _abstract(spec) -> Issue:
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
    if wc == 0:
        return Issue(17, _CAT, name, "WARNING",
                     "Abstract heading found but body could not be extracted")
    if wc <= 150:
        return Issue(17, _CAT, name, "PASS", f"Abstract found ({wc} words, limit is 150)")
    preview = (cleaned[:240] + "…") if len(cleaned) > 240 else cleaned
    return Issue(17, _CAT, name, "WARNING",
                 f"Abstract may be too long ({wc} words, limit is 150)",
                 details=(f"Extracted text used for the count (verify against the source "
                          f".docx, as PDF text extraction can splice in page-header/footer "
                          f"artifacts):\n\n{preview}"))


def _background(spec) -> Issue:
    name = "Background Section Present"
    if re.search(r"BACKGROUND|FIELD OF (?:THE )?INVENTION", spec, re.IGNORECASE):
        return Issue(18, _CAT, name, "PASS", "Background/Field section found")
    return Issue(18, _CAT, name, "WARNING", "Background/Field section not clearly identified")


def _brief_description(spec) -> Issue:
    name = "Brief Description of Drawings Present"
    if re.search(r"BRIEF DESCRIPTION OF (?:THE )?DRAWINGS", spec, re.IGNORECASE):
        return Issue(19, _CAT, name, "PASS", "Brief Description of Drawings section found")
    return Issue(19, _CAT, name, "WARNING",
                 "Brief Description of Drawings section not clearly identified")


def _detailed_description(spec) -> Issue:
    name = "Detailed Description Present"
    if re.search(r"DETAILED DESCRIPTION", spec, re.IGNORECASE):
        return Issue(20, _CAT, name, "PASS", "Detailed Description section found")
    return Issue(20, _CAT, name, "CRITICAL", "Detailed Description section not clearly identified")


def _claims_section(spec) -> Issue:
    name = "Claims Section Present"
    pats = (r"(?:^|\n)\s*CLAIMS?\s*(?:\n|$)", r"(?:^|\n)\s*What is claimed",
            r"(?:^|\n)\s*I\s+claim", r"(?:^|\n)\s*We\s+claim",
            r"(?:^|\n)\s*1\.\s+A\s+", r"(?:^|\n)\s*1\.\s+An\s+",
            r"(?:^|[^A-Z])CLAIMS(?:[^A-Z]|$)", r"What\s+is\s+claimed",
            r"What\s*is\s*claimed", r"1\.\s*A\s+computer-implemented",
            r"1\.\s*A\s+method", r"1\.\s*A\s+system", r"1\.\s*An?\s+apparatus")
    if any(re.search(p, spec, re.IGNORECASE | re.MULTILINE) for p in pats):
        return Issue(21, _CAT, name, "PASS", "Claims section found")
    return Issue(21, _CAT, name, "CRITICAL", "Claims section not clearly identified")
