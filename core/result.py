"""The Result + Evidence schema — the contract between the engine and every
frontend (the HTML report and the interactive app). This is where the
"receipts" live: each Issue carries the evidence that produced its verdict.

Pure data + serialization only; no engine or extraction logic here. See
DESIGN.md §5. The dataclasses are JSON-serializable via `Result.to_dict()`
(which prunes None for a compact payload) and `Result.to_json()`.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---- Locators: where a piece of evidence lives -----------------------------
# A flat dataclass tagged by `type` (rather than a class hierarchy) keeps JSON
# serialization trivial. Interpretation by type:
#   "pdf_region" -> (page, bbox)        : highlight a box on a page
#   "pdf_page"   -> (page)              : scroll to a page (no precise box)
#   "xfa_field"  -> (field_path)        : structured ADS field; no PDF geometry
#   "none"       -> ()                  : engine-level finding, text only
@dataclass
class Locator:
    type: str
    page: Optional[int] = None
    bbox: Optional[List[float]] = None      # [x0, top, x1, bottom] in PDF points
    field_path: Optional[str] = None


@dataclass
class Evidence:
    """One receipt: what the check looked at and what it found."""
    doc_type: Optional[str]                 # which document (None = engine-level)
    locator: Locator
    snippet: str = ""                       # the relevant text
    expected: Optional[str] = None
    actual: Optional[str] = None
    kind: str = "context"                   # match | mismatch | missing | value | context
    label: Optional[str] = None             # human caption


@dataclass
class PageMeta:
    index: int                              # 0-based
    width: float                            # PDF points
    height: float


@dataclass
class DocumentRef:
    doc_type: str
    filename: Optional[str]
    path: Optional[str]                     # relative to the filing folder
    source: str                             # "pdf" | "docx" | "xfa" | "missing"
    page_count: int = 0
    pages: List[PageMeta] = field(default_factory=list)


@dataclass
class Issue:
    check_id: int
    category: str
    check_name: str
    severity: str                           # CRITICAL | WARNING | INFO | PASS
    message: str
    details: str = ""                       # legacy free-text fallback
    evidence: List[Evidence] = field(default_factory=list)


@dataclass
class Result:
    folder: str
    generated_at: str                       # ISO-8601
    documents: List[DocumentRef] = field(default_factory=list)
    ads_data: Optional[Dict[str, Any]] = None
    issues: List[Issue] = field(default_factory=list)

    def to_dict(self, *, prune_none: bool = True) -> Dict[str, Any]:
        d = asdict(self)
        return _prune(d) if prune_none else d

    def to_json(self, *, indent: Optional[int] = None) -> str:
        import json
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def _prune(obj):
    """Recursively drop dict entries whose value is None (keeps payloads
    compact; empty strings and empty lists are preserved)."""
    if isinstance(obj, dict):
        return {k: _prune(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_prune(x) for x in obj]
    return obj
