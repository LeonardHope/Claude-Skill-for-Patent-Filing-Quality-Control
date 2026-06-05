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
    chars: 'X000-0000US)' -> 'X000-0179us' (internal '-' kept); 'CHEN,' ->
    'chen'. Lets a phrase match even when the PDF token carries a trailing
    paren/comma from its surrounding text."""
    return _norm(s).strip(_EDGE_PUNCT)


def locate(pdf_path, phrase: str, *, pad: float = 1.5) -> Optional[Dict]:
    """First run of consecutive words on a page whose concatenation matches
    `phrase` (case/space/edge-punctuation-insensitive). Returns
    {page, bbox:[x0,top,x1,bottom], page_width, page_height, matched} or None.
    Never raises — returns None on any extraction error."""
    targets = [_tok(t) for t in _norm(phrase).split()]
    targets = [t for t in targets if t]
    if not targets:
        return None
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_index, page in enumerate(pdf.pages):
                words = page.extract_words(use_text_flow=True)
                normed = [_tok(w["text"]) for w in words]
                for i in range(len(words) - len(targets) + 1):
                    if normed[i:i + len(targets)] == targets:
                        span = words[i:i + len(targets)]
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
