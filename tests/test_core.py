"""Tests for core/ — the Result schema and the engine->Result adapter (Phase 1).

Self-contained runner (like test_qc_patent_filing.py): exits non-zero on any
failure. Validates the contract without changing or re-testing check behavior.

Run:  python3 tests/test_core.py
"""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))                       # for `import core`
sys.path.insert(0, str(_ROOT / "scripts"))           # for the engine

from core.result import Result, DocumentRef, Issue, Evidence, Locator  # noqa: E402
from core.build import build_result                                    # noqa: E402
from qc_patent_filing import PatentFilingQC, Severity                  # noqa: E402

SAMPLE_PDF = _ROOT / "app" / "sample" / "Declaration.pdf"
GEN_AT = "2026-06-06T00:00:00+00:00"

TESTS = []
def test(label):
    def deco(fn): TESTS.append((label, fn)); return fn
    return deco


def _make_qc():
    """A PatentFilingQC with a hand-populated report + one real document, so we
    can adapt it without running the whole engine."""
    qc = PatentFilingQC(str(SAMPLE_PDF.parent))
    qc.report.files_found = {
        "Specification": None,
        "Declaration": SAMPLE_PDF.name,           # present, real PDF
        "ADS": None,
    }
    qc.documents = {"Declaration": SAMPLE_PDF}
    qc.ads_data = {"docket_number": "LUM-0142US"}
    qc.report.add_issue(1, "Cross-Document Consistency", "Inventor Names Consistency",
                        Severity.PASS, "All inventors present", "detail text")
    qc.report.add_issue(9, "Document Completeness", "All Required Documents Present",
                        Severity.CRITICAL, "Specification not found")
    return qc


# ---- schema-level ----------------------------------------------------------
@test("CORE.1: Result.to_dict prunes None, keeps empty strings/lists")
def t():
    r = Result(folder="/f", generated_at=GEN_AT, issues=[
        Issue(1, "C", "N", "PASS", "msg", details="", evidence=[
            Evidence(doc_type=None, locator=Locator(type="none"))])])
    d = r.to_dict()
    ev = d["issues"][0]["evidence"][0]
    if "page" in ev["locator"] or "bbox" in ev["locator"]:
        print(f"  ❌ None locator fields not pruned: {ev['locator']}"); return False
    if ev["locator"].get("type") != "none":
        print(f"  ❌ type missing: {ev['locator']}"); return False
    if d["issues"][0]["details"] != "":   # empty string preserved
        print(f"  ❌ empty details dropped"); return False
    return True

@test("CORE.2: Result.to_json round-trips")
def t():
    r = Result(folder="/f", generated_at=GEN_AT,
               documents=[DocumentRef("Declaration", "D.pdf", "D.pdf", "pdf")])
    back = json.loads(r.to_json())
    if back["folder"] != "/f" or back["documents"][0]["doc_type"] != "Declaration":
        print(f"  ❌ round-trip mismatch: {back}"); return False
    return True


# ---- adapter ---------------------------------------------------------------
@test("CORE.3: build_result maps issues (severity -> string, ids preserved)")
def t():
    res = build_result(_make_qc(), generated_at=GEN_AT)
    by_id = {i.check_id: i for i in res.issues}
    if set(by_id) != {1, 9}:
        print(f"  ❌ issue ids = {set(by_id)}"); return False
    if by_id[1].severity != "PASS" or by_id[9].severity != "CRITICAL":
        print(f"  ❌ severity not mapped to string"); return False
    if not all(isinstance(i.severity, str) for i in res.issues):
        print(f"  ❌ severity not a plain string"); return False
    return True

@test("CORE.4: present document gets real page metadata; missing omitted")
def t():
    res = build_result(_make_qc(), generated_at=GEN_AT)
    types = {d.doc_type for d in res.documents}
    if types != {"Declaration"}:            # Specification/ADS were None -> omitted
        print(f"  ❌ documents = {types}"); return False
    decl = res.documents[0]
    if decl.source != "pdf" or decl.page_count != 2:
        print(f"  ❌ page_count={decl.page_count} source={decl.source} (expected 2/pdf)")
        return False
    if not decl.pages or decl.pages[0].width <= 0 or decl.pages[0].height <= 0:
        print(f"  ❌ bad page dims: {decl.pages[:1]}"); return False
    return True

@test("CORE.5: build_result carries folder, generated_at, ads_data")
def t():
    res = build_result(_make_qc(), generated_at=GEN_AT)
    if res.generated_at != GEN_AT:
        print(f"  ❌ generated_at = {res.generated_at}"); return False
    if not res.folder or (res.ads_data or {}).get("docket_number") != "LUM-0142US":
        print(f"  ❌ folder/ads_data wrong: {res.folder} {res.ads_data}"); return False
    return True

@test("CORE.6: full Result is JSON-serializable end-to-end")
def t():
    res = build_result(_make_qc(), generated_at=GEN_AT)
    s = res.to_json(indent=2)
    back = json.loads(s)
    if back["issues"][0]["check_id"] != 1:
        print(f"  ❌ serialized issue wrong"); return False
    return True


# ---- run -------------------------------------------------------------------
print("=" * 70)
print(f"CORE SCHEMA + ADAPTER TESTS — {len(TESTS)} tests")
print("=" * 70)
passed = failed = 0
for label, fn in TESTS:
    try:
        ok = fn()
    except Exception as e:
        import traceback
        print(f"  💥 {label}: {type(e).__name__}: {e}"); traceback.print_exc(); ok = False
    if ok:
        print(f"  ✓ {label}"); passed += 1
    else:
        failed += 1
print("=" * 70)
print(f"RESULTS: {passed} passed, {failed} failed (out of {len(TESTS)})")
print("=" * 70)
sys.exit(1 if failed else 0)
