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


# ---- Claim-context helpers: turn a flagged term into "Claim N + the clause" --
# So 52/53/54 receipts carry the actual offending claim language and its claim
# number — the reader sees the problem without opening the specification.

def _claim_spans(claims_text):
    """[(claim_no, start, end)] for each numbered claim in the claims section."""
    marks = [(int(m.group(1)), m.start())
             for m in re.finditer(r"(?m)^\s*(\d{1,3})\.\s", claims_text)]
    return [(no, s, (marks[i + 1][1] if i + 1 < len(marks) else len(claims_text)))
            for i, (no, s) in enumerate(marks)]


def _claim_no_at(spans, pos):
    return next((no for no, s, e in spans if s <= pos < e), None)


def _clause_at(text, start, end):
    """Trim to the surrounding claim clause around [start, end] — claim clauses
    break on ';', newlines, and ':'. Whitespace-normalized and length-capped."""
    left = max([text.rfind(c, 0, start) for c in ";\n:"] + [-1]) + 1
    rights = [r for r in (text.find(c, end) for c in ";\n") if r != -1]
    right = min(rights) if rights else min(end + 140, len(text))
    snip = re.sub(r"\s+", " ", text[left:right]).strip(" .;:")
    return (snip[:220].rstrip() + "…") if len(snip) > 220 else snip


def _context_receipt(claims_text, spans, regex, *, label, kind="mismatch"):
    """Locate `regex` in the claims and return a data receipt carrying the claim
    number (in the label) and the verbatim clause (as the snippet). Falls back to
    a plain receipt if the phrase can't be pinpointed."""
    m = re.search(regex, claims_text, re.IGNORECASE)
    if not m:
        return data(label, actual="see claims", kind=kind, doc_type="Specification")
    no = _claim_no_at(spans, m.start())
    clause = _clause_at(claims_text, m.start(), m.end())
    lbl = (f"Claim {no} · " if no else "") + label
    return data(lbl, kind=kind, doc_type="Specification", snippet=clause)


_ANTE_FUNC_WORDS = {
    "a", "an", "the", "and", "or", "nor", "but", "of", "to", "for", "in", "on",
    "at", "by", "with", "said", "is", "are", "was", "were", "as", "from", "that",
    "which", "wherein", "thereby", "whereby", "further",
}


def _has_bare_introduction(claims_text, term):
    """True if some significant word of `term` first appears in the claims in a
    NON-referential position — i.e. introduced as a bare noun ("by firmware") or
    with "a/an", rather than first appearing as "the/said X". Such an element has
    proper antecedent basis even without an explicit "a/an" introduction (mass
    nouns like "firmware"/"software", elements introduced via a preposition, or
    acronyms like "(BMC)"). Function words are skipped (checking whether "and"
    has a bare mention is meaningless) but short acronyms are not. Used to
    suppress false antecedent-basis warnings."""
    for w in term.split():
        if len(w) < 2 or w in _ANTE_FUNC_WORDS:
            continue
        m = re.search(r"\b" + re.escape(w) + r"\b", claims_text, re.IGNORECASE)
        if not m:
            continue
        prev = re.search(r"([A-Za-z]+)\W*$", claims_text[:m.start()])
        if not (prev and prev.group(1).lower() in ("the", "said")):
            return True
    return False


_CLAIM_VERB_WORDS = {
    "is", "are", "was", "were", "be", "been", "being", "has", "have", "had",
    "comprises", "comprise", "comprising", "includes", "include", "including",
    "consists", "consist", "consisting", "having", "responsive", "wherein",
}


def _is_claim_term_phrase(words, stop_words):
    """A real claim term is a contiguous noun phrase. Reject n-grams that span a
    preposition/conjunction ("license application for installation"), contain a
    verb/copula ("… comprises …", "… is outside"), or contain a gerund
    ("comprises transmitting"). Those are clause fragments, not element names —
    they'd never be "defined" in the spec, so flagging them is just noise."""
    for w in words:
        if w in stop_words or w in _CLAIM_VERB_WORDS or w.endswith("ing"):
            return False
    return True


def _is_modifier_extension(v1, v2):
    """True if one phrase is the other with leading modifier word(s) prepended
    ("computing device" vs "target computing device"; "challenge token" vs
    "echoed challenge token"). Such genus/species pairs are deliberate narrower
    terms, not a terminology inconsistency — don't flag them."""
    a, b = sorted((v1.split(), v2.split()), key=len)
    return len(b) > len(a) and b[-len(a):] == a


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
                            if (w1 and w2 and len(w1.symmetric_difference(w2)) == 1
                                    and not _is_modifier_extension(v1, v2)):
                                inconsistencies.append((v1, v2))
    if inconsistencies:
        examples = [f"'{a}' vs '{b}'" for a, b in inconsistencies[:3]]
        issue = Issue(52, _CAT, name, "WARNING",
                      f"Potential terminology inconsistencies: {'; '.join(examples)}")
        spans = _claim_spans(claims_text)
        ev = []
        for a, b in inconsistencies[:5]:
            ev.append(_context_receipt(claims_text, spans, re.escape(a),
                                       label=f"“{a}” — inconsistent with “{b}”"))
            ev.append(_context_receipt(claims_text, spans, re.escape(b),
                                       label=f"“{b}” — inconsistent with “{a}”"))
        issue.evidence = ev
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
        # An element can be introduced without "a/an" — as a bare mass noun
        # ("by firmware…") or via a preposition; if its first mention in the
        # claims is non-referential it has antecedent basis, so don't flag it.
        if not found and _has_bare_introduction(claims_text, ref):
            found = True
        if not found:
            antecedent_issues.append(ref)
    if antecedent_issues:
        issue = Issue(53, _CAT, name, "WARNING",
                      f"Potential antecedent basis issues - 'the/said' without prior "
                      f"'a/an': {antecedent_issues[:5]}")
        spans = _claim_spans(claims_text)
        ev = []
        for t in antecedent_issues[:5]:
            first = t.split()[0]
            rx = (rf"(?:the|said)\s+{re.escape(t)}"
                  rf"|(?:the|said)\s+{re.escape(first)}")
            ev.append(_context_receipt(
                claims_text, spans, rx,
                label=f"“the/said {t}” — no earlier introduction of “{t}”"))
        issue.evidence = ev
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
        if (len(words) >= 2 and len(term) > 10 and not any(s in term for s in skip_phrases)
                and _is_claim_term_phrase(words, conj_prep)):
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
        spans = _claim_spans(claims_text)
        ev = []
        for t in undefined_terms[:5]:
            ev.append(_context_receipt(
                claims_text, spans, re.escape(t),
                label=f"“{t}” — not found in the detailed description"))
        issue.evidence = ev
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
