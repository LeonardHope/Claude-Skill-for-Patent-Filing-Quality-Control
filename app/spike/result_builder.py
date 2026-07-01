"""Build a Result for the Phase-0 spike.

Produces the Result + Evidence schema from DESIGN.md §5 for exactly two checks,
covering both evidence rendering paths:

  - Check 1 (Inventor Names)  -> pdf_region evidence (highlight in the PDF)
  - Check 3 (Attorney Docket) -> xfa_field evidence (structured data card)

The declaration is a REAL PDF (so the locate/bbox path is genuinely exercised).
The ADS is simulated as structured data — Check 3 is an `xfa_field` receipt with
no PDF geometry, which is exactly the point of that locator type.

In the real build this is replaced by core/ running all checks and emitting
evidence; here it's a hand-built two-check slice to de-risk the architecture.
"""
from pathlib import Path
from typing import Dict, List

import pdfplumber

from locate import locate

SAMPLE = Path(__file__).resolve().parent.parent / "sample"

# Simulated authoritative data (in the real build this comes from the ADS XFA
# extraction + the spec text).
ADS = {
    "docket_number": "X000-0000US",
    "inventors": [
        {"first": "Alice", "middle": "J.", "last": "EXAMPLE"},
        {"first": "Carol", "middle": "Dana", "last": "SAMPLE"},
    ],
}
SPEC_DOCKET = "X000-0000US"  # what the spec carries (matches -> PASS)


def _document_ref(doc_type: str, path: Path) -> Dict:
    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            pages.append({"index": i, "width": float(page.width),
                          "height": float(page.height)})
    return {
        "doc_type": doc_type,
        "filename": path.name,
        "path": path.name,
        "source": "pdf",
        "page_count": len(pages),
        "pages": pages,
    }


def build_result(folder: Path = SAMPLE) -> Dict:
    decl = folder / "Declaration.pdf"
    documents = [_document_ref("Declaration", decl)]

    issues: List[Dict] = []

    # ---- Check 1: Inventor Names Consistency (pdf_region evidence) ----
    evidence = []
    missing = []
    for inv in ADS["inventors"]:
        surname = inv["last"]
        loc = locate(decl, surname)
        if loc:
            evidence.append({
                "doc_type": "Declaration",
                "locator": {"type": "pdf_region", "page": loc["page"],
                            "bbox": loc["bbox"]},
                "snippet": loc["matched"],
                "expected": surname,
                "actual": loc["matched"],
                "kind": "match",
                "label": f"ADS inventor surname '{surname}' found in declaration",
            })
        else:
            missing.append(surname)
            evidence.append({
                "doc_type": "Declaration",
                "locator": {"type": "pdf_page", "page": 0},
                "snippet": "",
                "expected": surname,
                "actual": None,
                "kind": "missing",
                "label": f"ADS inventor surname '{surname}' NOT found in declaration",
            })
    issues.append({
        "check_id": 1,
        "category": "Cross-Document Consistency",
        "check_name": "Inventor Names Consistency",
        "severity": "CRITICAL" if missing else "PASS",
        "message": (f"{len(missing)} ADS inventor(s) not found in declaration: "
                    f"{', '.join(missing)}" if missing
                    else f"All {len(ADS['inventors'])} ADS inventors appear in the declaration"),
        "details": "",
        "evidence": evidence,
    })

    # ---- Check 3: Attorney Docket Number (xfa_field evidence) ----
    match = ADS["docket_number"] == SPEC_DOCKET
    issues.append({
        "check_id": 3,
        "category": "Cross-Document Consistency",
        "check_name": "Attorney Docket Number Consistency",
        "severity": "PASS" if match else "CRITICAL",
        "message": (f"Docket matches: {ADS['docket_number']}" if match
                    else f"Docket mismatch: ADS '{ADS['docket_number']}' vs spec '{SPEC_DOCKET}'"),
        "details": "",
        "evidence": [{
            "doc_type": "ADS",
            "locator": {"type": "xfa_field", "field_path": "docket_number"},
            "snippet": ADS["docket_number"],
            "expected": SPEC_DOCKET,
            "actual": ADS["docket_number"],
            "kind": "match" if match else "mismatch",
            "label": "ADS docket number (structured XFA field) vs specification",
        }],
    })

    return {
        "folder": str(folder),
        "generated_at": "2026-06-06T00:00:00Z",  # spike: fixed (no clock dep)
        "documents": documents,
        "ads_data": ADS,
        "issues": issues,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(build_result(), indent=2))
