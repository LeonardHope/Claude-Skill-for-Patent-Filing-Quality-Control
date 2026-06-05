"""Cross-document consistency checks, migrated to core (emit native evidence).

Currently: Checks 1 (Inventor Names), 2 (Title), 3 (Attorney Docket), 4
(Correspondence / Customer Number). Each check here takes the finished engine
instance `qc` (for its extracted texts, ADS data, and document paths) and
returns a fully-formed Issue with its receipts attached — no post-hoc enricher
needed.
"""
import re

from ..locate import locate, locate_flex
from ..result import Issue, Evidence, Locator

_CUST_RE = re.compile(r"Customer\s*(?:Number|No\.?)[:\s]*(\d{5,6})", re.IGNORECASE)

_CAT = "Cross-Document Consistency"
_NAME = "Application Title Consistency"
_INV_NAME = "Inventor Names Consistency"
_NAME_DOCS = ("Declaration", "Assignment")


def _ads_inventor_pairs(qc):
    """(formatted_name, surname) pairs from the ADS — mirrors the engine."""
    pairs = []
    ads = getattr(qc, "ads_data", None)
    if ads and ads.get("inventors"):
        for inv in ads["inventors"]:
            pairs.append((qc._format_xfa_inventor(inv), qc._xfa_surname(inv)))
    elif getattr(qc, "ads_text", ""):
        for name in qc.extract_inventors(qc.ads_text):
            surname = name.split()[-1] if name.split() else ""
            pairs.append((name, surname))
    return pairs


def _inventor_evidence(qc, pairs):
    """One receipt per inventor per name-bearing doc: a pdf_region where the
    surname (or full name) appears, else a 'missing' pdf_page receipt."""
    docs = getattr(qc, "documents", {}) or {}
    ev = []
    for inv_name, surname in pairs:
        for doc_type in _NAME_DOCS:
            path = docs.get(doc_type)
            if not path:
                continue
            hit = locate(path, surname) or locate(path, inv_name)
            if hit:
                ev.append(Evidence(
                    doc_type=doc_type,
                    locator=Locator(type="pdf_region", page=hit["page"], bbox=hit["bbox"]),
                    snippet=hit["matched"], expected=surname, actual=hit["matched"],
                    kind="match",
                    label=f"Inventor surname '{surname}' found in {doc_type}"))
            else:
                ev.append(Evidence(
                    doc_type=doc_type,
                    locator=Locator(type="pdf_page", page=0),
                    snippet="", expected=surname, actual=None, kind="missing",
                    label=f"Inventor surname '{surname}' not located in {doc_type}"))
    return ev


def check_inventor_names(qc) -> Issue:
    """Check 1: every ADS inventor's name appears in the Declaration/Assignment.
    Mirrors the engine's verdict (SKIPPED / PASS / CRITICAL, with image-only
    hedging to WARNING) and attaches a pdf_region receipt per inventor."""
    pairs = _ads_inventor_pairs(qc)
    ads_inventors = [n for n, _ in pairs]

    if not ads_inventors:
        return Issue(1, _CAT, _INV_NAME, "WARNING",
                     "SKIPPED — could not extract inventor names from ADS to use "
                     "as reference")

    other = [("Declaration", getattr(qc, "declaration_text", "") or ""),
             ("Assignment", getattr(qc, "assignment_text", "") or "")]
    present = [(n, t) for n, t in other if t and len(t.strip()) > 100]
    if not present:
        return Issue(1, _CAT, _INV_NAME, "WARNING",
                     "SKIPPED — no other documents available to cross-check ADS "
                     "inventor names against",
                     details=f"ADS inventors: {ads_inventors}")

    per_doc_missing = {}
    for doc_name, doc_text in present:
        norm_doc = qc._normalize_for_compare(doc_text)
        missing = []
        for inv_name, surname in pairs:
            last_norm = qc._normalize_for_compare(surname)
            full_norm = qc._normalize_for_compare(inv_name)
            if qc._surname_present(last_norm, norm_doc) or \
               (full_norm and full_norm in norm_doc):
                continue
            missing.append(inv_name)
        if missing:
            per_doc_missing[doc_name] = missing

    img = getattr(qc, "image_only_pages", {}) or {}
    if not per_doc_missing:
        issue = Issue(1, _CAT, _INV_NAME, "PASS",
                      f"All {len(ads_inventors)} ADS inventors appear in: "
                      f"{', '.join(n for n, _ in present)}")
    else:
        details_lines = []
        for doc_name, missing in per_doc_missing.items():
            line = (f"{doc_name}: missing {len(missing)} of {len(ads_inventors)} — "
                    + ", ".join(missing))
            if img.get(doc_name):
                line += (f"  [Note: {doc_name} has {img.get(doc_name)} image-only "
                         f"page(s) — name(s) may be there but not extractable.]")
            details_lines.append(line)
        all_hedged = all(img.get(n) for n in per_doc_missing)
        severity = "WARNING" if all_hedged else "CRITICAL"
        msg = ("Some ADS inventors not found in cross-checked document text — "
               "may be on image-only pages") if all_hedged else \
              "Some ADS inventors do not appear in all cross-checked documents"
        issue = Issue(1, _CAT, _INV_NAME, severity, msg, details="\n".join(details_lines))

    issue.evidence = _inventor_evidence(qc, pairs)
    return issue


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.upper()).strip().rstrip(".,;:")


def check_application_title(qc) -> Issue:
    """Check 2: the ADS title appears in the specification.

    Mirrors the engine's logic exactly (verbatim match, else a 60%-prefix
    match), and additionally attaches evidence: a pdf_region highlight of the
    title in the spec PDF plus the ADS title as a structured xfa_field.
    """
    ads_data = getattr(qc, "ads_data", None) or {}
    ads_title = ads_data.get("title") or (
        qc.extract_title(qc.ads_text) if getattr(qc, "ads_text", "") else "")
    spec_text = getattr(qc, "spec_text", "") or ""

    if not ads_title:
        return Issue(2, _CAT, _NAME, "WARNING", "Unable to extract title from ADS")
    if not spec_text:
        return Issue(2, _CAT, _NAME, "WARNING",
                     "Specification not available to compare title")

    ads_norm = _normalize(ads_title)
    spec_norm = _normalize(spec_text)
    if ads_norm in spec_norm:
        severity, message = "PASS", "ADS title appears verbatim in specification"
    else:
        words = ads_norm.split()
        chunk = " ".join(words[:max(4, int(len(words) * 0.6))])
        if chunk in spec_norm:
            severity, message = "PASS", ("Most of ADS title appears in specification "
                                         "(minor wording differences detected)")
        else:
            severity, message = "CRITICAL", ("ADS title does not appear in "
                                             "specification — verify they describe "
                                             "the same application")

    issue = Issue(2, _CAT, _NAME, severity, message,
                  details=("" if severity == "PASS" else f"ADS title: {ads_title}"))

    # ---- native evidence ----
    spec_path = (getattr(qc, "documents", {}) or {}).get("Specification")
    if spec_path:
        hit = locate_flex(spec_path, ads_title)
        if hit:
            issue.evidence.append(Evidence(
                doc_type="Specification",
                locator=Locator(type="pdf_region", page=hit["page"], bbox=hit["bbox"]),
                snippet=hit["matched"], expected=ads_title, actual=hit["matched"],
                kind="match" if severity == "PASS" else "mismatch",
                label="ADS title located in the specification"))
    issue.evidence.append(Evidence(
        doc_type="ADS",
        locator=Locator(type="xfa_field", field_path="title"),
        snippet=ads_title, actual=ads_title, kind="value",
        label="ADS invention title (structured XFA field)"))
    return issue


def check_attorney_docket(qc) -> Issue:
    """Check 3: a single attorney docket number appears across the documents
    (Spec ↔ ADS only for continuations). Evidence: the ADS docket as an
    xfa_field, plus a pdf_region where it appears in the specification."""
    name = "Attorney Docket Number Consistency"
    ads = getattr(qc, "ads_data", None)
    docket_sets = {}
    if ads and ads.get("docket_number"):
        docket_sets["ADS"] = {ads["docket_number"]}
    elif getattr(qc, "ads_text", ""):
        docket_sets["ADS"] = qc.extract_docket_numbers(qc.ads_text)
    for label, text in [("Spec", getattr(qc, "spec_text", "")),
                        ("Declaration", getattr(qc, "declaration_text", "")),
                        ("Assignment", getattr(qc, "assignment_text", ""))]:
        if text:
            ds = qc.extract_docket_numbers(text)
            if ds:
                docket_sets[label] = ds

    if len(docket_sets) >= 2:
        is_cont = qc._is_continuation_filing()
        sources = [s for s in docket_sets if (s in ("ADS", "Spec") or not is_cont)]
        if len(sources) >= 2:
            normalized = {s: {d.upper() for d in docket_sets[s]} for s in sources}
            shared = set.intersection(*normalized.values()) if normalized else set()
            if shared:
                suffix = (" (Spec↔ADS only — parent's Dec/Asgn dockets carried "
                          "forward)") if is_cont else ""
                issue = Issue(3, _CAT, name, "PASS",
                              f"Attorney docket number consistent across documents"
                              f"{suffix}: {sorted(shared)[0]}")
            else:
                issue = Issue(3, _CAT, name, "CRITICAL",
                              "Attorney docket number mismatch — no docket appears "
                              "in all compared documents",
                              details="\n".join(f"{n}: {sorted(docket_sets[n])}"
                                                 for n in docket_sets))
        else:
            issue = Issue(3, _CAT, name, "WARNING",
                          "Unable to compare dockets — only one source has "
                          "extractable docket numbers")
    else:
        issue = Issue(3, _CAT, name, "WARNING",
                      "Unable to extract docket numbers from multiple documents")

    docket = (ads or {}).get("docket_number")
    if docket:
        issue.evidence.append(Evidence(
            doc_type="ADS", locator=Locator(type="xfa_field", field_path="docket_number"),
            snippet=docket, actual=docket, kind="value",
            label="ADS attorney docket number (structured XFA field)"))
        spec_path = (getattr(qc, "documents", {}) or {}).get("Specification")
        if spec_path:
            hit = locate(spec_path, docket)
            if hit:
                issue.evidence.append(Evidence(
                    doc_type="Specification",
                    locator=Locator(type="pdf_region", page=hit["page"], bbox=hit["bbox"]),
                    snippet=hit["matched"], expected=docket, actual=hit["matched"],
                    kind="match", label="Docket number located in the specification"))
    return issue


def check_correspondence(qc) -> Issue:
    """Check 4: the customer number matches between ADS and POA. Evidence: the
    ADS customer number as an xfa_field."""
    name = "Correspondence Address Consistency"
    ads = getattr(qc, "ads_data", None)
    ads_cust = (ads or {}).get("customer_number")
    if not ads_cust and getattr(qc, "ads_text", ""):
        m = _CUST_RE.search(qc.ads_text)
        ads_cust = m.group(1) if m else None
    poa_cust = None
    if getattr(qc, "poa_text", ""):
        m = _CUST_RE.search(qc.poa_text)
        poa_cust = m.group(1) if m else None

    if ads_cust and poa_cust:
        if ads_cust == poa_cust:
            issue = Issue(4, _CAT, name, "PASS",
                          f"Customer number consistent: {ads_cust}")
        else:
            issue = Issue(4, _CAT, name, "CRITICAL",
                          f"Customer number mismatch: ADS={ads_cust}, POA={poa_cust}")
    elif ads_cust or poa_cust:
        issue = Issue(4, _CAT, name, "PASS",
                      f"Customer number found: {ads_cust or poa_cust}")
    else:
        issue = Issue(4, _CAT, name, "INFO",
                      "No customer number found - manual review of correspondence "
                      "address recommended")

    if ads_cust:
        issue.evidence.append(Evidence(
            doc_type="ADS", locator=Locator(type="xfa_field", field_path="customer_number"),
            snippet=ads_cust, actual=ads_cust, kind="value",
            label="ADS customer number (structured XFA field)"))
    return issue
