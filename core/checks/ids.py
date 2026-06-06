"""IDS checks (76-80), migrated to core. Mirrors the engine verbatim.

IDS is optional under MPEP 609: when no IDS document is present, emit a single
PASS (76) and stop. check_ids(qc) returns the list of IDS issues.
"""
import re

from ..result import Issue
from ._ev import data

_CAT = "IDS"


def _count_filled(outer, leaf, ids_text):
    total = 0
    for blk in re.finditer(rf"<{outer}\b[^>]*>(.*?)</{outer}\s*>", ids_text,
                           re.IGNORECASE | re.DOTALL):
        total += len(re.findall(rf"<{leaf}\b[^>]*>\s*[^<\s][^<]*?\s*</\s*{leaf}\s*>",
                                blk.group(1), re.IGNORECASE | re.DOTALL))
    return total


def check_ids(qc):
    docs = getattr(qc, "documents", {}) or {}
    ids_path = docs.get("IDS")
    wa_path = docs.get("IDS Written Assertion")
    ids_text = getattr(qc, "ids_text", "") or ""

    if not ids_path and not wa_path:
        issue = Issue(76, _CAT, "IDS Documents Present", "PASS",
                      "No IDS documents present — IDS is optional under MPEP 609. "
                      "Skipping IDS-specific checks.")
        issue.evidence = [data("IDS documents", actual="none (optional under MPEP 609)",
                               kind="match")]
        return [issue]

    out = []
    found = []
    if ids_path:
        found.append(f"IDS form: {ids_path.name}")
    if wa_path:
        found.append(f"Written Assertion (SB/08c): {wa_path.name}")
    i76 = Issue(76, _CAT, "IDS Documents Present", "INFO",
                f"{len(found)} IDS-related document(s) found.",
                details="\n".join(f"  • {s}" for s in found))
    i76.evidence = [data("IDS documents found", actual="; ".join(found), kind="value")]
    out.append(i76)

    if ids_path:
        out.append(_ids_signed(ids_text))
        out.append(_ids_reference_counts(ids_text))
    if wa_path:
        out.append(_wa_selection(qc, wa_path))
        out.append(_wa_signed(qc, wa_path))
    return out


def _ids_signed(ids_text) -> Issue:
    name = "IDS Form Signed"
    sm = re.search(r"<\s*basic-signature\b[^>]*>\s*<\s*text-string\b[^>]*>([^<]+)"
                   r"</\s*text-string", ids_text, re.IGNORECASE)
    rm = re.search(r"<\s*registered-number\b[^>]*>\s*(\d{4,6})\s*</", ids_text, re.IGNORECASE)
    sig = sm.group(1).strip() if sm else ""
    reg = rm.group(1).strip() if rm else ""
    if sig and reg:
        issue = Issue(77, _CAT, name, "PASS", f"IDS appears signed: '{sig}' (Reg. No. {reg}).")
        issue.evidence = [data("IDS signature", actual=f"{sig} · Reg. {reg}", kind="match",
                               doc_type="IDS")]
        return issue
    if sig or reg:
        issue = Issue(77, _CAT, name, "WARNING",
                      f"Partial signature data on IDS — signature='{sig or '(empty)'}', "
                      f"reg no='{reg or '(empty)'}'. Confirm the form is properly signed.")
        issue.evidence = [data("IDS signature", actual=f"signature={sig or '—'}, reg={reg or '—'}",
                               kind="mismatch", doc_type="IDS")]
        return issue
    issue = Issue(77, _CAT, name, "WARNING",
                  "IDS form has no filled signature or practitioner registration number. "
                  "Sign before filing.")
    issue.evidence = [data("IDS signature", actual="not signed", kind="mismatch", doc_type="IDS")]
    return issue


def _ids_reference_counts(ids_text) -> Issue:
    name = "IDS Reference Counts"
    us_pat = _count_filled("us-patent-cite", "doc-number", ids_text)
    us_pub = _count_filled("us-pub-appl-cite", "doc-number", ids_text)
    fp = _count_filled("us-foreign-document-cite", "doc-number", ids_text)
    npl = _count_filled("us-nplcit", "text", ids_text)
    doc_nums = re.findall(r"<\s*doc-number\b[^>]*>\s*([^<\s][^<]*?)\s*</\s*doc-number\s*>",
                          ids_text, re.IGNORECASE)
    total = us_pat + us_pub + fp + npl
    if total > 0:
        issue = Issue(78, _CAT, name, "INFO",
                      f"IDS lists {total} reference(s): {us_pat} US patent(s), {us_pub} US "
                      f"publication(s), {fp} foreign document(s), {npl} NPL item(s). Verify "
                      f"each cited reference is accompanied by a copy or covered by a "
                      f"§1.98(a)(2) exception.",
                      details=("Cited US patent doc numbers (first 20): "
                               + ", ".join(doc_nums[:20])) if doc_nums else "")
        issue.evidence = [data("References cited in IDS",
                               actual=f"{total} ({us_pat} US pat, {us_pub} US pub, {fp} foreign, {npl} NPL)",
                               kind="value", doc_type="IDS")]
        return issue
    issue = Issue(78, _CAT, name, "WARNING",
                  "IDS form has no filled reference citations. Either the form is empty or "
                  "the extractor missed them — verify manually before filing.")
    issue.evidence = [data("References cited in IDS", actual="none found", kind="mismatch",
                           doc_type="IDS")]
    return issue


def _wa_selection(qc, wa_path) -> Issue:
    name = "Written Assertion Selection Made"
    fields = qc._extract_acroform_fields(wa_path)
    cb = {n: v for n, v in fields.items() if re.match(r"check\s*box\s*\d", n, re.IGNORECASE)}
    checked = [n for n, v in cb.items() if v.lower() in ("/yes", "yes", "on", "1", "true")]
    meanings = {"1": "§1.17(v): no IDS size fee required", "2": "§1.17(v)(1): fee tier 1",
                "3": "§1.17(v)(2): fee tier 2", "4": "§1.17(v)(3): fee tier 3"}
    if len(checked) == 1:
        m = re.search(r"(\d)", checked[0])
        meaning = meanings.get(m.group(1), "?") if m else "?"
        issue = Issue(79, _CAT, name, "PASS",
                      f"Written Assertion has one selection: {checked[0]} (asserts: {meaning}).")
        issue.evidence = [data("§1.17(v) selection", actual=f"{checked[0]} — {meaning}",
                               kind="match", doc_type="IDS Written Assertion")]
        return issue
    if len(checked) > 1:
        issue = Issue(79, _CAT, name, "CRITICAL",
                      f"Written Assertion has {len(checked)} boxes checked, but only one is "
                      f"allowed per §1.17(v). Checked: {', '.join(checked)}.")
        issue.evidence = [data("§1.17(v) selection", actual=f"{len(checked)} boxes checked",
                               kind="mismatch", doc_type="IDS Written Assertion")]
        return issue
    if cb:
        issue = Issue(79, _CAT, name, "CRITICAL",
                      "Written Assertion has NO §1.17(v) box checked. The form will be "
                      "treated as no assertion made. Check exactly one of the four options "
                      "before filing.")
        issue.evidence = [data("§1.17(v) selection", actual="no box checked", kind="mismatch",
                               doc_type="IDS Written Assertion")]
        return issue
    return Issue(79, _CAT, name, "INFO",
                 "Could not read AcroForm checkbox fields. Manually verify exactly one "
                 "§1.17(v) option is selected.")


def _wa_signed(qc, wa_path) -> Issue:
    name = "Written Assertion Signed"
    fields = qc._extract_acroform_fields(wa_path)
    sig = fields.get("Signature", "").strip()
    nm = fields.get("Name PrintTyped", "").strip()
    reg = fields.get("Practitioner Registration Number if applicable", "").strip()
    date = fields.get("Date", "").strip()
    if sig and (nm or reg):
        issue = Issue(80, _CAT, name, "PASS",
                      f"Written Assertion signed: '{sig}' (name: {nm or 'n/a'}, "
                      f"reg no: {reg or 'n/a'}, date: {date or 'n/a'}).")
        issue.evidence = [data("Written Assertion signature",
                               actual=f"{sig} (name: {nm or 'n/a'}, reg: {reg or 'n/a'})",
                               kind="match", doc_type="IDS Written Assertion")]
        return issue
    if sig:
        issue = Issue(80, _CAT, name, "WARNING",
                      f"Written Assertion has a signature ('{sig}') but name/reg no fields "
                      f"are empty. Confirm signature is valid.")
        issue.evidence = [data("Written Assertion signature", actual=f"{sig} (name/reg empty)",
                               kind="mismatch", doc_type="IDS Written Assertion")]
        return issue
    issue = Issue(80, _CAT, name, "WARNING",
                  "Written Assertion has no filled signature field. Sign before filing.")
    issue.evidence = [data("Written Assertion signature", actual="not signed", kind="mismatch",
                           doc_type="IDS Written Assertion")]
    return issue
