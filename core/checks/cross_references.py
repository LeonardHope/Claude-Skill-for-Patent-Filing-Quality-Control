"""Cross-reference checks. 61 (drawing figure count) and 62 (claim count) are
migrated. Checks 59 (claims reference spec elements) and 60 (summary matches
claims) are intricate drafting-quality NLP heuristics, left engine-emitted.
"""
import re

from ..result import Issue
from ._ev import region, data

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
    return [_claims_reference_spec(qc), _summary_matches_claims(qc),
            _figure_count(qc), _claim_count(qc)]


def _figure_count(qc) -> Issue:
    name = "Drawing Figure Count Matches Specification"
    spec = getattr(qc, "spec_text", "") or ""
    draw = getattr(qc, "drawings_text", "") or ""
    if not qc._drawings_text_extractable():
        spec_figs = qc._extract_figure_identities(spec) if spec else []
        issue = Issue(61, _CAT, name, "INFO",
                      f"Drawings PDF appears to be image-only — figure count not "
                      f"verifiable by text extraction. Spec references {len(spec_figs)} "
                      f"figure(s)" + (f" (FIG. {', '.join(spec_figs)})" if spec_figs else "")
                      + ". Manually verify drawings contain matching figures.")
        issue.evidence = [data("Figures referenced in specification",
                               actual=(f"FIG. {', '.join(spec_figs)}" if spec_figs else "none"),
                               kind="value", doc_type="Specification")]
        return issue
    if spec and draw:
        sf = set(qc._extract_figure_identities(spec))
        df = set(qc._extract_figure_identities(draw))
        sl = ", ".join(sorted(sf, key=_fig_sort_key))
        dl = ", ".join(sorted(df, key=_fig_sort_key))
        if sf == df:
            issue = Issue(61, _CAT, name, "PASS",
                          f"Figure numbers match: {len(sf)} figures (FIG. {sl})")
            issue.evidence = [data("Figures in spec & drawings", actual=f"{len(sf)}: FIG. {sl}",
                                   kind="match", doc_type="Specification")]
            return issue
        issue = (Issue(61, _CAT, name, "WARNING",
                       f"Same figure count ({len(sf)}) but different numbers. "
                       f"Spec: {sorted(sf, key=_fig_sort_key)}, Drawings: {sorted(df, key=_fig_sort_key)}")
                 if len(sf) == len(df) else
                 Issue(61, _CAT, name, "WARNING",
                       f"Figure count mismatch: Spec references {len(sf)} figures, "
                       f"Drawings has {len(df)} figures"))
        issue.evidence = [data("Figures in specification", actual=f"FIG. {sl}",
                               kind="mismatch", doc_type="Specification"),
                          data("Figures in drawings", actual=f"FIG. {dl}",
                               kind="mismatch", doc_type="Drawings")]
        return issue
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


# ---- Check 59: claims reference specification elements (migrated verbatim) ---
_STOPWORDS = {'method', 'system', 'apparatus', 'device', 'medium', 'product', 'invention',
              'embodiment', 'present', 'following', 'above', 'said', 'wherein', 'thereof',
              'therein', 'further', 'least', 'one', 'more', 'each', 'plurality', 'time',
              'use', 'set', 'first', 'second', 'third', 'fourth', 'fifth', 'at'}
_TAIL_TRIM = {'and', 'or', 'but', 'nor', 'yet', 'to', 'for', 'with', 'by', 'from', 'in',
              'on', 'at', 'of', 'through', 'into', 'onto', 'further', 'thereby', 'whereby', 'wherein'}
_CLAIM_ONLY = {'non-transitory'}
_NP = r"\b(?:a|an|the|said)\s+([a-z][\w\-]*\s+[\w\-]+(?:\s+[\w\-]+)?)\b"


def _claims_reference_spec(qc):
    name = "Claims Reference Specification Elements"
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        issue = Issue(59, _CAT, name, "WARNING", "Specification not found")
        issue.evidence = [data("Specification", actual="not found", kind="missing")]
        return issue
    claims_text = qc._extract_claims_section()
    corpus = spec.replace(claims_text, "") if (claims_text and claims_text in spec) else spec
    if not claims_text:
        issue = Issue(59, _CAT, name, "INFO",
                      "Could not isolate claims section for cross-reference check")
        issue.evidence = [data("Claim elements", actual="claims not isolated", kind="value",
                               doc_type="Specification")]
        return issue
    terms = set()
    for m in re.finditer(_NP, claims_text, re.IGNORECASE):
        words = re.sub(r"\s+", " ", m.group(1).strip().lower()).split()
        if not words or words[0] in _STOPWORDS:
            continue
        changed = True
        while changed and words:
            changed = False
            if words[-1] in _TAIL_TRIM:
                words.pop(); changed = True; continue
            if len(words) > 1 and words[-1].endswith(("ing", "ed")):
                words.pop(); changed = True
        if len(words) >= 2:
            terms.add(" ".join(words))
    if not terms:
        issue = Issue(59, _CAT, name, "PASS", "Claim elements cross-referenced with specification")
        issue.evidence = [data("Claim elements", actual="cross-referenced", kind="match",
                               doc_type="Specification")]
        return issue
    desc_lower = re.sub(r"\s+", " ", corpus.lower())

    def supported(t):
        if t in desc_lower:
            return True
        stripped = " ".join(w for w in t.split() if w not in _CLAIM_ONLY)
        if stripped and stripped != t and stripped in desc_lower:
            return True
        cw = [w for w in t.split() if w not in _STOPWORDS and w not in _CLAIM_ONLY]
        return len(cw) >= 2 and all(re.search(rf"\b{re.escape(w)}\b", desc_lower) for w in cw)

    missing = [t for t in terms if not supported(t)]
    if not missing:
        issue = Issue(59, _CAT, name, "PASS",
                      f"All {len(terms)} claim elements found in specification")
        issue.evidence = [data("Claim elements supported in spec",
                               actual=f"{len(terms)} of {len(terms)}", kind="match",
                               doc_type="Specification")]
        return issue
    if len(missing) <= 3:
        issue = Issue(59, _CAT, name, "PASS",
                      f"Most claim elements found in specification "
                      f"({len(terms) - len(missing)}/{len(terms)})")
        issue.evidence = [data(f"'{t}'", actual="not clearly found in spec", kind="mismatch",
                               doc_type="Specification") for t in list(missing)[:5]]
        return issue
    issue = Issue(59, _CAT, name, "WARNING",
                  f"{len(missing)} claim elements not clearly found in specification",
                  details=f"Missing: {', '.join(list(missing)[:5])}")
    issue.evidence = [data(f"'{t}'", actual="not found in specification", kind="mismatch",
                           doc_type="Specification") for t in list(missing)[:5]]
    return issue


# ---- Check 60: specification summary matches claims (migrated verbatim) ------
_SUM_STOP = {'comprising', 'including', 'wherein', 'thereof', 'therein', 'configured',
             'coupled', 'connected', 'having', 'being', 'first', 'second', 'third', 'method',
             'system', 'apparatus', 'each', 'said', 'claim', 'further', 'least', 'with',
             'from', 'that', 'which', 'where', 'when', 'into', 'upon', 'between'}


def _summary_matches_claims(qc):
    name = "Specification Summary Matches Claims"
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        issue = Issue(60, _CAT, name, "WARNING", "Specification not found")
        issue.evidence = [data("Specification", actual="not found", kind="missing")]
        return issue
    sm = re.search(r"(?:SUMMARY|BRIEF\s+SUMMARY)(.*?)"
                   r"(?:BRIEF\s+DESCRIPTION\s+OF|DETAILED\s+DESCRIPTION|DRAWINGS)",
                   spec, re.DOTALL | re.IGNORECASE)
    cm = re.search(r"(?:What is claimed[^:]*:\s*|CLAIMS\s+).*?1\.\s+(A.*?)"
                   r"(?:\s{2,}\d+\.\s+|\.\s+\d+\.\s+)", spec, re.DOTALL | re.IGNORECASE)
    if not (sm and cm):
        issue = Issue(60, _CAT, name, "INFO",
                      "Could not isolate both summary and claims for comparison")
        issue.evidence = [data("Summary vs claims", actual="could not isolate both",
                               kind="value", doc_type="Specification")]
        return issue
    summary_text = sm.group(1).lower()
    key_terms = set(re.findall(r"\b([a-z]{4,})\b", cm.group(1).lower())) - _SUM_STOP
    if not key_terms:
        issue = Issue(60, _CAT, name, "PASS", "Summary and claims present")
        issue.evidence = [data("Summary & claims", actual="present", kind="match",
                               doc_type="Specification")]
        return issue
    found = sum(1 for t in key_terms if t in summary_text)
    coverage = found / len(key_terms)
    if coverage >= 0.5:
        issue = Issue(60, _CAT, name, "PASS",
                      f"Summary covers {found}/{len(key_terms)} key claim terms "
                      f"({coverage:.0%} coverage)")
        issue.evidence = [data("Summary covers claim 1 terms",
                               actual=f"{found}/{len(key_terms)} ({coverage:.0%})",
                               kind="match", doc_type="Specification")]
        return issue
    issue = Issue(60, _CAT, name, "INFO",
                  f"Heuristic: summary covers only {coverage:.0%} of claim 1 word tokens "
                  f"({found}/{len(key_terms)}). Drafters often use different vocabulary "
                  f"in the summary; this is best verified manually rather than "
                  f"flagged as a finding.")
    issue.evidence = [data("Summary covers claim 1 terms",
                           actual=f"{found}/{len(key_terms)} ({coverage:.0%}) — verify manually",
                           kind="value", doc_type="Specification")]
    return issue
