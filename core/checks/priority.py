"""Priority / related-application checks. 63, 64, 65 are migrated. Check 81
(priority application number verification) is left engine-emitted — it optionally
calls the USPTO ODP network API and builds verification links.
"""
import re

from ..result import Issue

_CAT = "Priority Claims"

_SPEC_PRIORITY = (
    r"(?:claims|claiming)\s+(?:the\s+)?(?:benefit|priority)\s+(?:of|to|under)",
    r"\bcontinuation(?:[-\s]in[-\s]part)?\s+of",
    r"\bdivisional\s+(?:of|application)",
    r"\bprovisional\s+application\s+(?:no\.?|number)",
)
_SPEC_RELATED = (
    r"CROSS[-\s]*REFERENCE", r"RELATED\s+APPLICATION", r"PRIORITY\s+CLAIM",
    r"PRIORITY\s+TO\s+RELATED", r"\bcontinuation\s+of\b",
    r"\bclaims\s+(?:the\s+)?(?:benefit|priority)",
)


def check_priority(qc):
    ads = getattr(qc, "ads_data", None)
    dom = (ads.get("domestic_continuity_entries") if ads else None) or []
    foreign = (ads.get("foreign_priority_entries") if ads else None) or []
    spec = getattr(qc, "spec_text", "") or ""
    spec_priority = next((re.search(p, spec, re.IGNORECASE).group(0)
                          for p in _SPEC_PRIORITY if re.search(p, spec, re.IGNORECASE)), None)
    return [_consistency(dom, foreign, spec_priority),
            _related(qc, dom, foreign, spec_priority, spec),
            _foreign(foreign)]


def _consistency(dom, foreign, spec_priority) -> Issue:
    name = "Priority Claim Consistency"
    if dom or foreign:
        if spec_priority:
            return Issue(63, _CAT, name, "PASS",
                         f"Priority claims present in both ADS and specification "
                         f"({len(dom)} domestic, {len(foreign)} foreign in ADS)")
        return Issue(63, _CAT, name, "WARNING",
                     f"ADS lists {len(dom)} domestic and {len(foreign)} foreign priority "
                     f"entries, but no priority language found in specification. Spec "
                     f"should reference the parent/priority application(s).")
    if spec_priority:
        return Issue(63, _CAT, name, "WARNING",
                     "Priority language detected in specification but no priority entries "
                     "in ADS. Verify the ADS continuity/foreign-priority sections are "
                     "filled in correctly.")
    return Issue(63, _CAT, name, "PASS",
                 "No priority claims detected in specification or ADS")


def _related(qc, dom, foreign, spec_priority, spec) -> Issue:
    name = "Related Application References"
    if dom or foreign or spec_priority:
        related = any(re.search(p, spec, re.IGNORECASE) for p in _SPEC_RELATED) if spec else False
        if related:
            return Issue(64, _CAT, name, "PASS",
                         "Related-application cross-reference language found in specification")
        return Issue(64, _CAT, name, "WARNING",
                     "Priority claims present but no Cross-Reference / Related Applications "
                     "section found in specification. Verify the spec includes proper "
                     "priority/continuation language near the start.")
    return Issue(64, _CAT, name, "PASS", "No related applications detected")


def _foreign(foreign) -> Issue:
    name = "Foreign Priority Documents"
    if foreign:
        countries = sorted({(e.get("country") or "?").upper() for e in foreign})
        return Issue(65, _CAT, name, "INFO",
                     f"{len(foreign)} foreign priority claim(s) in ADS "
                     f"({', '.join(countries)}). Verify that certified copies of the "
                     f"foreign priority documents are on file or being filed.")
    return Issue(65, _CAT, name, "PASS", "No foreign priority claims in ADS")
