"""Adapt the existing engine into the Result schema (Phase 1 bridge).

`build_result(qc)` reads a finished PatentFilingQC run and produces a `Result`
— the data contract every frontend consumes. It does NOT change any check
behavior; it only restructures the engine's output. Evidence starts empty here
(checks still emit free-text `details`); Phase 2 populates structured evidence
as checks move into core/checks/.

`run(folder)` is a convenience that loads + runs the engine and adapts the
result, for the app server and CLI.
"""
from pathlib import Path
from typing import Optional

from .result import Result, DocumentRef, PageMeta, Issue, Evidence, Locator


def _page_metas(path: Path):
    """Best-effort per-page dimensions (PDF points). Returns [] on any failure
    (e.g. a non-PDF, an unreadable file) so adapting never raises."""
    if path is None or path.suffix.lower() != ".pdf" or not path.exists():
        return []
    try:
        import pdfplumber
        out = []
        with pdfplumber.open(str(path)) as pdf:
            for i, pg in enumerate(pdf.pages):
                out.append(PageMeta(index=i, width=float(pg.width),
                                    height=float(pg.height)))
        return out
    except Exception:
        return []


def _source_for(path: Optional[Path]) -> str:
    if path is None:
        return "missing"
    return {".pdf": "pdf", ".docx": "docx"}.get(path.suffix.lower(), "pdf")


def _document_refs(qc):
    """One DocumentRef per classified (present) document. Missing slots are
    omitted — the report's completeness checks already convey absence, and a
    frontend can't render a file that isn't there."""
    refs = []
    documents = getattr(qc, "documents", {}) or {}
    for doc_type, filename in qc.report.files_found.items():
        if not filename:
            continue
        path = documents.get(doc_type)
        pages = _page_metas(path) if path else []
        refs.append(DocumentRef(
            doc_type=doc_type,
            filename=filename,
            path=(path.name if path else filename),
            source=_source_for(path),
            page_count=len(pages),
            pages=pages,
        ))
    return refs


def _severity_str(sev) -> str:
    # Engine uses a Severity enum (sev.value == "CRITICAL"/...); be tolerant.
    return getattr(sev, "value", str(sev))


def _issue_from_qc(qc_issue) -> Issue:
    # Phase 1: no structured evidence yet — carry the legacy free-text details.
    # Phase 2 will attach Evidence (pdf_region / xfa_field / ...) per check.
    return Issue(
        check_id=qc_issue.check_id,
        category=qc_issue.category,
        check_name=qc_issue.check_name,
        severity=_severity_str(qc_issue.severity),
        message=qc_issue.message,
        details=getattr(qc_issue, "details", "") or "",
        evidence=[],
    )


def build_result(qc, *, generated_at: str) -> Result:
    """Adapt a PatentFilingQC instance that has already run load_documents() +
    run_all_checks() into a Result. `generated_at` is supplied by the caller so
    this stays deterministic and testable."""
    return Result(
        folder=str(getattr(qc, "folder_path", "")),
        generated_at=generated_at,
        documents=_document_refs(qc),
        ads_data=getattr(qc, "ads_data", None),
        issues=[_issue_from_qc(i) for i in qc.report.issues],
    )


def run(folder: str, *, generated_at: Optional[str] = None,
        enrich: bool = True) -> Result:
    """Load the folder, run all checks, and return a Result. Imports the engine
    lazily so `core.result`/`build_result` stay decoupled from the legacy
    script. When `enrich` is set, attaches structured evidence (receipts) for
    the checks core knows how to enrich."""
    import sys
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts))
    from qc_patent_filing import PatentFilingQC  # noqa: E402

    if generated_at is None:
        from datetime import datetime, timezone
        generated_at = datetime.now(timezone.utc).isoformat()

    from .checks import MIGRATED_IDS, CHECKS

    qc = PatentFilingQC(folder)
    qc.load_documents()
    # Tell the engine to skip checks core now owns — set ONLY here, so the
    # standalone CLI (which doesn't go through core.run) is unaffected.
    qc.report.skip_check_ids = set(qc.report.skip_check_ids) | set(MIGRATED_IDS)
    qc.run_all_checks()

    result = build_result(qc, generated_at=generated_at)

    # Run the migrated core checks natively (they emit their own evidence). A
    # check returns an Issue, a list of Issues (a check or a whole category may
    # emit several), or None.
    for fn in CHECKS:
        out = fn(qc)
        if out is None:
            continue
        if isinstance(out, list):
            result.issues.extend(i for i in out if i is not None)
        else:
            result.issues.append(out)
    result.issues.sort(key=lambda i: i.check_id)

    if enrich:
        from .evidence import enrich as _enrich
        doc_paths = {k: v for k, v in (getattr(qc, "documents", {}) or {}).items() if v}
        _enrich(result, doc_paths)
    _reclassify_na(result)
    _backfill_doc_links(result)
    return result


# Engine-emitted checks that report a skipped / inapplicable state as PASS are
# re-tagged "N/A" so they don't inflate the Pass count (migrated core checks emit
# "N/A" directly). Kept to a tight set of unambiguous "didn't apply" phrasings.
_NA_PHRASES = ("sequence listing checks skipped", "checks skipped",
               "check not applicable", "— not applicable", "not applicable")


def _reclassify_na(result: Result) -> None:
    for issue in result.issues:
        if issue.severity == "PASS" and any(p in (issue.message or "").lower()
                                            for p in _NA_PHRASES):
            issue.severity = "N/A"


# A check's category names the single document it is about, used to give any
# still-receipt-less check an "Open <doc>" affordance. Per-document categories
# map to their document; "Sequence Listing" maps to the Specification (the gate
# check examines the spec for SEQ ID NO references). Genuinely cross-cutting
# categories (consistency / completeness / cross-references / final quality /
# file quality / formatting / priority) are absent — their checks carry their
# own data receipts instead.
_CATEGORY_DOC = {
    "Specification": "Specification",
    "Drawings": "Drawings",
    "Declaration": "Declaration",
    "Assignment": "Assignment",
    "Power of Attorney": "Power of Attorney",
    "ADS": "ADS",
    "IDS": "IDS",
    "Sequence Listing": "Specification",
}


def _backfill_doc_links(result: Result) -> None:
    """Give every check that lacks a precise receipt a 'view document' affordance
    — a `pdf_page` locator to the single document its category is about, when
    that document is present as a PDF. Checks that already carry a located
    receipt (pdf_region / xfa_field), and cross-cutting categories, are left
    untouched. This is a navigation aid, not located evidence, so it uses
    kind='document' and the frontend keeps it distinct from real receipts."""
    pdf_docs = {d.doc_type for d in result.documents if d.source == "pdf"}
    for issue in result.issues:
        if issue.evidence:                       # already carries its own receipt(s)
            continue
        doc = _CATEGORY_DOC.get(issue.category)
        if doc and doc in pdf_docs:
            issue.evidence.append(Evidence(
                doc_type=doc, locator=Locator(type="pdf_page", page=0),
                snippet="", kind="document", label=f"Open {doc}"))
