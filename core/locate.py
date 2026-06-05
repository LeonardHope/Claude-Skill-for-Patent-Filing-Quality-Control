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


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def locate(pdf_path, phrase: str, *, pad: float = 1.5) -> Optional[Dict]:
    """First run of consecutive words on a page whose concatenation matches
    `phrase` (case/space-insensitive). Returns
    {page, bbox:[x0,top,x1,bottom], page_width, page_height, matched} or None.
    Never raises — returns None on any extraction error."""
    targets = _norm(phrase).split()
    if not targets:
        return None
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_index, page in enumerate(pdf.pages):
                words = page.extract_words(use_text_flow=True)
                normed = [_norm(w["text"]) for w in words]
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
