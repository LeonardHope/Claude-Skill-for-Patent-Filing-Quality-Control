"""Shared evidence helpers for core checks — one place to turn a located phrase
into a `pdf_region` receipt, so checks don't each reimplement the locate→Evidence
dance (DESIGN.md §4.1, kept DRY).
"""
from ..locate import locate, locate_flex
from ..result import Evidence, Locator


def data(label, *, actual=None, expected=None, doc_type=None, kind="value"):
    """A non-located 'data receipt' — the concrete value(s) a check examined,
    optionally tied to a source document (so the UI can still open it). Use this
    for checks that have no single spot to highlight (counts, comparisons,
    presence lists) so every check still shows the evidence behind its verdict."""
    return Evidence(
        doc_type=doc_type, locator=Locator(type="none"), kind=kind, label=label,
        actual=None if actual is None else str(actual),
        expected=None if expected is None else str(expected),
    )


def region(doc_type, path, phrase, *, label, actual=None, kind="match", flex=False):
    """Locate `phrase` in `path` (a PDF) and return a `pdf_region` Evidence, or
    None if there's no path or the phrase can't be located. `flex` falls back to
    shorter prefixes (for long phrases like a title that may not extract as one
    run)."""
    if not path or not phrase:
        return None
    hit = (locate_flex if flex else locate)(path, phrase)
    if not hit:
        return None
    return Evidence(
        doc_type=doc_type,
        locator=Locator(type="pdf_region", page=hit["page"], bbox=hit["bbox"]),
        snippet=hit["matched"],
        actual=actual if actual is not None else phrase,
        kind=kind,
        label=label,
    )
