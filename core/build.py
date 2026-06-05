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


def run(folder: str, *, generated_at: Optional[str] = None) -> Result:
    """Load the folder, run all checks, and return a Result. Imports the engine
    lazily so `core.result`/`build_result` stay decoupled from the legacy
    script."""
    import sys
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts))
    from qc_patent_filing import PatentFilingQC  # noqa: E402

    if generated_at is None:
        from datetime import datetime, timezone
        generated_at = datetime.now(timezone.utc).isoformat()

    qc = PatentFilingQC(folder)
    qc.load_documents()
    qc.run_all_checks()
    return build_result(qc, generated_at=generated_at)
