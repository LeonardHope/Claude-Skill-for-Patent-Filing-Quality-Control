"""ADS checks (27, 29, 31, 73), migrated to core. Mirrors the engine verbatim.

Check 28 (first-named inventor) is left engine-emitted — it OCRs the POA to read
the filled-in name. check_ads(qc) returns issues for 27, 29, 31, and 73 (when
applicable), and handles the ADS-missing fallback (27, 29, 31; 28 is the
engine's).
"""
import re

from ..result import Issue
from ._ev import data

_CAT = "ADS"


def check_ads(qc):
    ads_text = getattr(qc, "ads_text", "") or ""
    if not ads_text:
        return [Issue(i, _CAT, f"Check {i}", "CRITICAL", "ADS not found")
                for i in (27, 29, 31)]
    out = [_inventor_addresses(qc, ads_text), _entity_status(ads_text),
           _attorney_info(ads_text)]
    c73 = _customer_numbers(qc)
    if c73 is not None:
        out.append(c73)
    return out


def _inventor_addresses(qc, ads_text) -> Issue:
    name = "Inventor Addresses Complete"
    ads = getattr(qc, "ads_data", None)
    if ads and ads.get("inventors"):
        incomplete, complete = [], 0
        for idx, inv in enumerate(ads["inventors"], start=1):
            miss = []
            if not (inv.get("mail_address1") or "").strip():
                miss.append("Address 1")
            if not (inv.get("mail_city") or "").strip():
                miss.append("City")
            if not (inv.get("mail_state") or "").strip() and \
                    (inv.get("mail_country") or "").upper() == "US":
                miss.append("State")
            if not (inv.get("mail_postcode") or "").strip():
                miss.append("Postal Code")
            if not (inv.get("mail_country") or "").strip():
                miss.append("Country")
            if miss:
                nm = qc._format_xfa_inventor(inv) or f"Inventor {idx}"
                incomplete.append(f"{nm}: missing {', '.join(miss)}")
            else:
                complete += 1
        if incomplete:
            issue = Issue(27, _CAT, name, "WARNING",
                          f"{len(incomplete)} of {len(ads['inventors'])} inventor mailing "
                          f"addresses are incomplete in the ADS",
                          details="\n".join(f"  • {ln}" for ln in incomplete))
            issue.evidence = [data(ln.split(":")[0], actual=ln.split(":", 1)[1].strip(),
                                   kind="mismatch", doc_type="ADS") for ln in incomplete[:6]]
            return issue
        issue = Issue(27, _CAT, name, "PASS",
                      f"All {complete} inventor mailing addresses are complete in the ADS")
        issue.evidence = [data("Inventor addresses complete (ADS)",
                               actual=f"{complete} of {complete}", kind="match", doc_type="ADS")]
        return issue

    sections = [s for s in re.split(r"(?=Inventor\s+\d+)", ads_text, flags=re.IGNORECASE)
                if re.match(r"Inventor\s+\d+", s, re.IGNORECASE)]
    if sections:
        incomplete, complete = [], 0
        for section in sections:
            m = re.match(r"Inventor\s+(\d+)", section, re.IGNORECASE)
            num = m.group(1) if m else "?"
            miss = []
            if not re.search(r"Address\s*1\s+[A-Za-z0-9c/o]", section, re.IGNORECASE):
                miss.append("Address 1")
            if not re.search(r"City\s+[A-Za-z]{2,}", section, re.IGNORECASE):
                miss.append("City")
            if not re.search(r"State\s*/?\s*Province\s+[A-Z]{2}", section, re.IGNORECASE):
                miss.append("State/Province")
            if not re.search(r"Postal\s*Code\s+\d{5}", section, re.IGNORECASE):
                miss.append("Postal Code")
            if not re.search(r"Country\s*[:\s]*[A-Z]{2}", section, re.IGNORECASE):
                miss.append("Country")
            if miss:
                incomplete.append(f"Inventor {num}: missing {', '.join(miss)}")
            else:
                complete += 1
        if incomplete:
            return Issue(27, _CAT, name, "WARNING",
                         f"Incomplete inventor addresses: {'; '.join(incomplete[:3])}")
        return Issue(27, _CAT, name, "PASS",
                     f"All {complete} inventor addresses appear complete")

    has = (re.search(r"Address\s*1\s+[A-Za-z0-9]", ads_text, re.IGNORECASE) and
           re.search(r"Postal\s*Code\s+\d{5}", ads_text, re.IGNORECASE))
    if has:
        return Issue(27, _CAT, name, "PASS", "Address information detected in ADS")
    return Issue(27, _CAT, name, "WARNING", "Could not verify inventor addresses in ADS")


def _entity_status(ads_text) -> Issue:
    name = "Entity Status Specified"
    m = re.search(r"(small entity|micro entity|large entity|entity status)", ads_text, re.IGNORECASE)
    if m:
        issue = Issue(29, _CAT, name, "PASS", "Entity status appears to be specified")
        issue.evidence = [data("Entity status", actual=m.group(1), kind="match", doc_type="ADS")]
        return issue
    issue = Issue(29, _CAT, name, "WARNING", "Entity status not clearly specified")
    issue.evidence = [data("Entity status", actual="not found in ADS", kind="mismatch", doc_type="ADS")]
    return issue


def _attorney_info(ads_text) -> Issue:
    name = "Attorney/Agent Information"
    if re.search(r"registration\s*(?:no|number)", ads_text, re.IGNORECASE):
        issue = Issue(31, _CAT, name, "PASS",
                      "Attorney/agent registration information appears present")
        issue.evidence = [data("Attorney/agent registration", actual="present", kind="match",
                               doc_type="ADS")]
        return issue
    issue = Issue(31, _CAT, name, "INFO",
                  "Manual review recommended for attorney/agent registration number")
    issue.evidence = [data("Attorney/agent registration", actual="not detected — manual review",
                           kind="value", doc_type="ADS")]
    return issue


def _customer_numbers(qc):
    """Check 73 — only fires when ADS XFA data is present and at least one
    customer number is populated."""
    ads = getattr(qc, "ads_data", None)
    if not ads:
        return None
    name = "Attorney vs Correspondence Customer Number"
    corr = (ads.get("customer_number") or "").strip()
    atty = (ads.get("attorney_customer_number") or "").strip()
    if corr and atty:
        if corr == atty:
            issue = Issue(73, _CAT, name, "PASS",
                          f"Attorney and correspondence customer numbers match: {corr}")
            issue.evidence = [data("Customer number (both)", actual=corr, kind="match", doc_type="ADS")]
            return issue
        issue = Issue(73, _CAT, name, "WARNING",
                      f"Attorney customer number ({atty}) differs from correspondence "
                      f"customer number ({corr})",
                      details="These are often the same firm. Confirm the difference is "
                              "intentional.")
        issue.evidence = [data("Correspondence customer number", actual=corr, kind="mismatch", doc_type="ADS"),
                          data("Attorney customer number", actual=atty, kind="mismatch", doc_type="ADS")]
        return issue
    if corr or atty:
        return Issue(73, _CAT, name, "INFO",
                     f"Only one customer number populated (correspondence="
                     f"{corr or '—'}, attorney={atty or '—'}); manual review recommended")
    return None
