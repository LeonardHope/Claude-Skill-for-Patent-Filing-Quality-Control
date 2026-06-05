"""IDS checks (76-80), migrated to core. Mirrors the engine verbatim.

IDS is optional under MPEP 609: when no IDS document is present, emit a single
PASS (76) and stop. check_ids(qc) returns the list of IDS issues.
"""
import re

from ..result import Issue

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
        return [Issue(76, _CAT, "IDS Documents Present", "PASS",
                      "No IDS documents present — IDS is optional under MPEP 609. "
                      "Skipping IDS-specific checks.")]

    out = []
    found = []
    if ids_path:
        found.append(f"IDS form: {ids_path.name}")
    if wa_path:
        found.append(f"Written Assertion (SB/08c): {wa_path.name}")
    out.append(Issue(76, _CAT, "IDS Documents Present", "INFO",
                     f"{len(found)} IDS-related document(s) found.",
                     details="\n".join(f"  • {s}" for s in found)))

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
        return Issue(77, _CAT, name, "PASS", f"IDS appears signed: '{sig}' (Reg. No. {reg}).")
    if sig or reg:
        return Issue(77, _CAT, name, "WARNING",
                     f"Partial signature data on IDS — signature='{sig or '(empty)'}', "
                     f"reg no='{reg or '(empty)'}'. Confirm the form is properly signed.")
    return Issue(77, _CAT, name, "WARNING",
                 "IDS form has no filled signature or practitioner registration number. "
                 "Sign before filing.")


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
        return Issue(78, _CAT, name, "INFO",
                     f"IDS lists {total} reference(s): {us_pat} US patent(s), {us_pub} US "
                     f"publication(s), {fp} foreign document(s), {npl} NPL item(s). Verify "
                     f"each cited reference is accompanied by a copy or covered by a "
                     f"§1.98(a)(2) exception.",
                     details=("Cited US patent doc numbers (first 20): "
                              + ", ".join(doc_nums[:20])) if doc_nums else "")
    return Issue(78, _CAT, name, "WARNING",
                 "IDS form has no filled reference citations. Either the form is empty or "
                 "the extractor missed them — verify manually before filing.")


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
        return Issue(79, _CAT, name, "PASS",
                     f"Written Assertion has one selection: {checked[0]} (asserts: {meaning}).")
    if len(checked) > 1:
        return Issue(79, _CAT, name, "CRITICAL",
                     f"Written Assertion has {len(checked)} boxes checked, but only one is "
                     f"allowed per §1.17(v). Checked: {', '.join(checked)}.")
    if cb:
        return Issue(79, _CAT, name, "CRITICAL",
                     "Written Assertion has NO §1.17(v) box checked. The form will be "
                     "treated as no assertion made. Check exactly one of the four options "
                     "before filing.")
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
        return Issue(80, _CAT, name, "PASS",
                     f"Written Assertion signed: '{sig}' (name: {nm or 'n/a'}, "
                     f"reg no: {reg or 'n/a'}, date: {date or 'n/a'}).")
    if sig:
        return Issue(80, _CAT, name, "WARNING",
                     f"Written Assertion has a signature ('{sig}') but name/reg no fields "
                     f"are empty. Confirm signature is valid.")
    return Issue(80, _CAT, name, "WARNING",
                 "Written Assertion has no filled signature field. Sign before filing.")
