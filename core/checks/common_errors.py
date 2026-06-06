"""Common-error checks. Checks 50 (placeholder text) and 51 (track changes) are
migrated. Checks 52-54 (claim terminology consistency, antecedent basis,
undefined terms) are intricate drafting-quality heuristics with high replication
risk and low evidence value, so they stay engine-emitted.
"""
import re

from ..result import Issue
from ._ev import region, data

_CAT = "Common Errors"

# (doc_type, qc text attribute) for documents whose page text we can locate a
# placeholder in. ADS text comes from XFA datasets (no page geometry), so it is
# scanned for the message but not for a pdf_region receipt.
_SCAN = (("Specification", "spec_text"), ("Declaration", "declaration_text"),
         ("Assignment", "assignment_text"))

_PLACEHOLDERS = (
    (r"\[INSERT[^\]]{0,80}\]", "[INSERT…]"),
    (r"\[TBD[^\]]{0,80}\]", "[TBD…]"),
    (r"\[FILL[^\]]{0,80}\]", "[FILL…]"),
    (r"\[PLACEHOLDER[^\]]{0,80}\]", "[PLACEHOLDER…]"),
    (r"\[\s*___+\s*\]", "[___]"),
    (r"\bTODO\b", "TODO"),
    (r"\bFIXME\b", "FIXME"),
    (r"\bXXX\b", "XXX"),
    (r"\*\*\*+", "***"),
)
_TRACK = ("Deleted:", "Inserted:", "Comment [", "Formatted:")


def check_common_errors(qc):
    all_text = (getattr(qc, "spec_text", "") or "") + (getattr(qc, "ads_text", "") or "") \
        + (getattr(qc, "declaration_text", "") or "") + (getattr(qc, "assignment_text", "") or "")

    found = [label for pat, label in _PLACEHOLDERS if re.search(pat, all_text)]
    if not found:
        placeholder = Issue(50, _CAT, "No Placeholder Text Remaining", "PASS",
                            "No common placeholder text detected")
    else:
        placeholder = Issue(50, _CAT, "No Placeholder Text Remaining", "CRITICAL",
                           f"Placeholder text found: {', '.join(found)}")
        placeholder.evidence = _placeholder_evidence(qc)

    indicators = [i for i in _TRACK if i in all_text]
    if not indicators:
        track = Issue(51, _CAT, "No Track Changes or Comments Visible", "PASS",
                      "No track change indicators detected")
        track.evidence = [data("Track-change / comment markers", actual="none detected",
                               kind="match")]
    else:
        track = Issue(51, _CAT, "No Track Changes or Comments Visible", "WARNING",
                      f"Possible track change indicators: {', '.join(indicators)}")
        track.evidence = [data(f"Marker: {ind}", actual="present", kind="mismatch")
                          for ind in indicators]
    return [placeholder, track, _claim_terminology(qc), _antecedent_basis(qc),
            _undefined_terms(qc)]


def _placeholder_evidence(qc, cap=12):
    """A pdf_region receipt for each placeholder occurrence we can locate in a
    text-bearing document (capped so a runaway template doesn't flood the panel)."""
    docs = getattr(qc, "documents", {}) or {}
    ev = []
    for doc_type, attr in _SCAN:
        text, path = getattr(qc, attr, "") or "", docs.get(doc_type)
        if not text or not path:
            continue
        for pat, label in _PLACEHOLDERS:
            for m in re.finditer(pat, text):
                e = region(doc_type, path, m.group(0), kind="mismatch",
                           label=f"Placeholder {label} in {doc_type}")
                if e:
                    ev.append(e)
                    if len(ev) >= cap:
                        return ev
    return ev


# ---- Check 52: consistent claim terminology (migrated verbatim) -------------
def _claim_terminology(qc):
    name = "Consistent Use of Claim Terminology"
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        return _info52("Specification not available for terminology check", None)
    m = re.search(r"(?:CLAIMS|What is claimed)(.*?)(?:ABSTRACT|$)", spec, re.DOTALL | re.IGNORECASE)
    claims_text = m.group(1) if m else ""
    if not claims_text:
        return _info52("Could not extract claims for terminology check", "Specification")
    elements = []
    skip_terms = ['method', 'system', 'step', 'claim', 'invention', 'present', 'first',
                  'second', 'third', 'plurality', 'least one', 'one or more', 'following',
                  'above', 'same', 'other']
    for match in re.finditer(r"\b(?:a|an|the)\s+([\w\-]+(?:\s+[\w\-]+){1,2})\b",
                             claims_text, re.IGNORECASE):
        element = match.group(1).lower().strip()
        if not any(s in element for s in skip_terms) and len(element) > 5:
            elements.append(element)
    element_by_noun = {}
    for elem in elements:
        words = elem.split()
        if len(words) >= 2 and len(words[-1]) > 4:
            element_by_noun.setdefault(words[-1], set()).add(elem)
    inconsistencies = []
    for noun, variants in element_by_noun.items():
        if len(variants) > 1:
            norm_variants = {re.sub(r"^(the|a|an)\s+", "", v).strip() for v in variants}
            if len(norm_variants) > 1:
                vl = list(norm_variants)
                for i, v1 in enumerate(vl):
                    for v2 in vl[i + 1:]:
                        if v1 != v2 and v1.endswith(v2.split()[-1]) and v2.endswith(v1.split()[-1]):
                            w1, w2 = set(v1.split()[:-1]), set(v2.split()[:-1])
                            if w1 and w2 and len(w1.symmetric_difference(w2)) == 1:
                                inconsistencies.append((v1, v2))
    if inconsistencies:
        examples = [f"'{a}' vs '{b}'" for a, b in inconsistencies[:3]]
        issue = Issue(52, _CAT, name, "WARNING",
                      f"Potential terminology inconsistencies: {'; '.join(examples)}")
        issue.evidence = [data(f"'{a}' vs '{b}'", actual="inconsistent terminology",
                               kind="mismatch", doc_type="Specification")
                          for a, b in inconsistencies[:5]]
        return issue
    issue = Issue(52, _CAT, name, "PASS",
                  f"No obvious terminology inconsistencies detected "
                  f"({len(set(elements))} unique element terms)")
    issue.evidence = [data("Claim element terms", actual=f"{len(set(elements))} unique — consistent",
                           kind="match", doc_type="Specification")]
    return issue


def _info52(msg, doc):
    issue = Issue(52, _CAT, "Consistent Use of Claim Terminology", "INFO", msg)
    issue.evidence = [data("Claim terminology", actual="not checked", kind="value", doc_type=doc)]
    return issue


# ---- Check 53: antecedent basis in claims (migrated verbatim) ---------------
def _antecedent_basis(qc):
    name = "Antecedent Basis in Claims"
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        return _info53("Specification not available for antecedent basis check", None)
    claims_text = qc._extract_claims_section()
    if not claims_text:
        return _info53("Could not extract claims for antecedent basis check", "Specification")
    introduced = set()
    for match in re.finditer(r"\b(?:a|an)\s+(?=([\w\-]+(?:\s+[\w\-]+){0,2})\b)",
                             claims_text, re.IGNORECASE):
        element = match.group(1).lower().strip()
        if element not in ['method', 'system', 'device', 'apparatus', 'medium', 'product']:
            introduced.add(element)
    referenced = []
    quantifier_phrases = {'at least one', 'one or more', 'two or more', 'three or more',
                          'at least two', 'at least three'}
    continuation_tokens = {'further', 'thereby', 'whereby', 'wherein'}
    skip_terms = ['method', 'system', 'device', 'apparatus', 'medium', 'product', 'claim',
                  'claims', 'invention', 'present', 'following', 'above', 'instructions', 'operations']
    for match in re.finditer(r"\b(?:the|said)\s+(?=([\w\-]+(?:\s+[\w\-]+){0,2})\b)",
                             claims_text, re.IGNORECASE):
        element = match.group(1).lower().strip()
        words = element.split()
        for i, w in enumerate(words):
            if w in continuation_tokens:
                words = words[:i]
                break
        element = ' '.join(words)
        if not element or element in quantifier_phrases:
            continue
        if element not in skip_terms and not any(s in element for s in skip_terms):
            referenced.append(element)
    antecedent_issues = []
    for ref in set(referenced):
        found = False
        ref_words = set(ref.split())
        for intro in introduced:
            if ref == intro or ref_words & set(intro.split()) or ref.split()[-1] == intro.split()[-1]:
                found = True
                break
        if not found:
            antecedent_issues.append(ref)
    if antecedent_issues:
        issue = Issue(53, _CAT, name, "WARNING",
                      f"Potential antecedent basis issues - 'the/said' without prior "
                      f"'a/an': {antecedent_issues[:5]}")
        issue.evidence = [data(f"'the/said {t}' without prior 'a/an'", actual="no antecedent",
                               kind="mismatch", doc_type="Specification")
                          for t in antecedent_issues[:5]]
        return issue
    issue = Issue(53, _CAT, name, "PASS",
                  f"Antecedent basis appears proper ({len(introduced)} elements introduced, "
                  f"{len(set(referenced))} referenced)")
    issue.evidence = [data("Antecedent basis",
                           actual=f"{len(introduced)} introduced, {len(set(referenced))} referenced",
                           kind="match", doc_type="Specification")]
    return issue


def _info53(msg, doc):
    issue = Issue(53, _CAT, "Antecedent Basis in Claims", "INFO", msg)
    issue.evidence = [data("Antecedent basis", actual="not checked", kind="value", doc_type=doc)]
    return issue


# ---- Check 54: no undefined claim terms (migrated verbatim) -----------------
def _undefined_terms(qc):
    name = "No Undefined Claim Terms"
    spec = getattr(qc, "spec_text", "") or ""
    if not spec:
        return _info54("Specification not available for claim term check", None)
    claims_text = qc._extract_claims_section()
    dm = re.search(r"DETAILED DESCRIPTION(.*?)(?:CLAIMS|What is claimed)", spec,
                   re.DOTALL | re.IGNORECASE)
    description_text = dm.group(1) if dm else spec
    if not (claims_text and description_text):
        return _info54("Could not extract claims or description for term check", "Specification")
    conj_prep = {'and', 'or', 'but', 'nor', 'yet', 'to', 'for', 'with', 'by', 'from', 'in',
                 'on', 'at', 'of', 'further', 'thereby', 'whereby', 'wherein'}
    skip_phrases = ['the method', 'the system', 'the device', 'claim 1', 'wherein the',
                    'comprising', 'configured to', 'adapted to', 'based on', 'according to',
                    'at least one', 'one or more', 'or more', 'or fewer']
    claim_terms = set()
    for match in re.finditer(r"\b([\w\-]+(?:\s+[\w\-]+){1,3})\b", claims_text, re.IGNORECASE):
        term = re.sub(r"\s+", " ", match.group(1).lower().strip())
        words = term.split()
        if words and words[0] in conj_prep:
            continue
        while words and words[-1] in conj_prep:
            words.pop()
        term = ' '.join(words)
        if len(words) >= 2 and len(term) > 10 and not any(s in term for s in skip_phrases):
            claim_terms.add(term)
    description_lower = re.sub(r"\s+", " ", description_text.lower())
    undefined_terms = []
    for term in claim_terms:
        if term not in description_lower:
            main_noun = term.split()[-1]
            if len(main_noun) > 4 and main_noun not in description_lower:
                undefined_terms.append(term)
    if undefined_terms:
        issue = Issue(54, _CAT, name, "WARNING",
                      f"Claim terms possibly not in detailed description: {undefined_terms[:5]}")
        issue.evidence = [data(f"'{t}'", actual="not found in detailed description",
                               kind="mismatch", doc_type="Specification")
                          for t in undefined_terms[:5]]
        return issue
    issue = Issue(54, _CAT, name, "PASS",
                  f"Claim terms appear to be supported in specification "
                  f"({len(claim_terms)} terms checked)")
    issue.evidence = [data("Claim terms supported in spec", actual=f"{len(claim_terms)} checked",
                           kind="match", doc_type="Specification")]
    return issue


def _info54(msg, doc):
    issue = Issue(54, _CAT, "No Undefined Claim Terms", "INFO", msg)
    issue.evidence = [data("Claim terms", actual="not checked", kind="value", doc_type=doc)]
    return issue
