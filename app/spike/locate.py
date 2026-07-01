"""locate(pdf_path, phrase) -> Locator   [Phase-0 spike]

The riskiest primitive in the whole plan: map a piece of matched text back to a
page + bounding box in the source PDF, so the frontend can highlight it.

In the real build this lives in core/locate.py and is the SINGLE shared helper
every `pdf_region` evidence uses (see DESIGN.md §4.1) — never reimplemented per
check. Here it's just enough to prove the approach.

Coordinates are pdfplumber's: origin top-left, units = PDF points, y measured
from the top (x0, top, x1, bottom). Page width/height are returned so the
frontend can map onto the PDF.js viewport at any scale.
"""
import re
from pathlib import Path
from typing import Optional, Dict

import pdfplumber


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def locate(pdf_path, phrase: str) -> Optional[Dict]:
    """Find the first run of consecutive words on a page whose concatenation
    matches `phrase` (case/space-insensitive). Returns:

        {page, bbox: [x0, top, x1, bottom], page_width, page_height, matched}

    or None if not found. bbox is the union of the matched words' boxes.
    """
    targets = _norm(phrase).split()
    if not targets:
        return None

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_index, page in enumerate(pdf.pages):
            words = page.extract_words(use_text_flow=True)
            normed = [_norm(w["text"]) for w in words]
            for i in range(len(words) - len(targets) + 1):
                if normed[i:i + len(targets)] == targets:
                    span = words[i:i + len(targets)]
                    x0 = min(w["x0"] for w in span)
                    x1 = max(w["x1"] for w in span)
                    top = min(w["top"] for w in span)
                    bottom = max(w["bottom"] for w in span)
                    # small padding so the highlight breathes
                    pad = 1.5
                    return {
                        "page": page_index,
                        "bbox": [x0 - pad, top - pad, x1 + pad, bottom + pad],
                        "page_width": float(page.width),
                        "page_height": float(page.height),
                        "matched": " ".join(w["text"] for w in span),
                    }
    return None


if __name__ == "__main__":
    pdf = Path(__file__).resolve().parent.parent / "sample" / "Declaration.pdf"
    for phrase in ("EXAMPLE", "Carol Dana SAMPLE", "NOTFOUND"):
        print(f"{phrase!r:25} -> {locate(pdf, phrase)}")
