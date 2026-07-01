"""locate(pdf_path, phrase) -> page + bbox   [the single shared locator]

Promoted out of the Phase-0 spike. This is the ONE place that maps matched text
back to a page + bounding box; every `pdf_region` evidence uses it, never a
per-check reimplementation (DESIGN.md §4.1).

Coordinates are pdfplumber's: origin top-left, units = PDF points, y from the
top (x0, top, x1, bottom). Page width/height are returned so a viewer can map
onto the PDF.js viewport at any scale.
"""
import re
from typing import Dict, Optional

_WS = re.compile(r"\s+")
_EDGE_PUNCT = ".,;:()[]{}\"'"


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def _tok(s: str) -> str:
    """Normalize a token and strip surrounding punctuation, keeping internal
    chars: 'X000-0000US)' -> 'x000-0000us' (internal '-' kept); 'CHEN,' ->
    'chen'. Lets a phrase match even when the PDF token carries a trailing
    paren/comma from its surrounding text."""
    return _norm(s).strip(_EDGE_PUNCT)


def _collapse(s: str) -> str:
    """Reduce a token to its bare alphanumerics (lowercased): drop surrounding
    punctuation, internal hyphens, and whitespace. 'RETRIEVAL-' -> 'retrieval',
    'MULTI-CORE' -> 'multiagent', 'systems.' -> 'systems'. This is what lets a
    title that line-breaks mid-word ('RETRIEVAL-\\nAUGMENTED') still match the
    ADS title token 'LOW-LATENCY' — both collapse to the same run of
    characters."""
    return re.sub(r"[^a-z0-9]", "", _norm(s))


def locate(pdf_path, phrase: str, *, pad: float = 1.5) -> Optional[Dict]:
    """First run of consecutive words on a page whose *concatenated characters*
    equal `phrase` (case/space/hyphen/edge-punctuation-insensitive). Matching on
    the collapsed character stream rather than token-by-token means a phrase
    survives line-break hyphenation ('RETRIEVAL-\\nAUGMENTED') and internal
    hyphens ('MULTI-CORE' vs 'MULTI-CORE') that split or join words
    differently between the source phrase and the PDF's extracted words.
    Returns {page, bbox:[x0,top,x1,bottom], page_width, page_height, matched}
    or None. Never raises — returns None on any extraction error."""
    target = _collapse(phrase)
    if not target:
        return None
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_index, page in enumerate(pdf.pages):
                words = page.extract_words(use_text_flow=True)
                normed = [_collapse(w["text"]) for w in words]
                for i in range(len(words)):
                    if not normed[i] or not target.startswith(normed[i]):
                        continue
                    acc = ""
                    for j in range(i, len(words)):
                        acc += normed[j]
                        if not target.startswith(acc):
                            break
                        if acc == target:
                            span = words[i:j + 1]
                            return {
                                "page": page_index,
                                "bbox": [min(w["x0"] for w in span) - pad,
                                         min(w["top"] for w in span) - pad,
                                         max(w["x1"] for w in span) + pad,
                                         max(w["bottom"] for w in span) + pad],
                                "page_width": float(page.width),
                                "page_height": float(page.height),
                                "matched": " ".join(w["text"] for w in span),
                            }
    except Exception:
        return None
    return None


def locate_flex(pdf_path, phrase: str, *, min_words: int = 4) -> Optional[Dict]:
    """locate(), falling back to progressively shorter prefixes. Useful for long
    phrases (e.g. an invention title) that may not extract as one contiguous run
    — a leading chunk still anchors the highlight."""
    hit = locate(pdf_path, phrase)
    if hit:
        return hit
    words = phrase.split()
    while len(words) > min_words:
        words = words[:-1]
        hit = locate(pdf_path, " ".join(words))
        if hit:
            return hit
    return None
