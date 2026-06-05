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
from core.evidence import enrich                                       # noqa: E402
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


# ---- evidence enrichment (Phase 2) -----------------------------------------
# The sample Declaration.pdf carries "Sarah J. CHEN" (page 1) and
# "Aditya Vikram MEHTA" (page 2). Drive Check 1 from injected ADS data.
_ADS = {"docket_number": "LUM-0142US",
        "inventors": [{"first": "Sarah", "middle": "J.", "last": "CHEN"},
                      {"first": "Aditya", "middle": "Vikram", "last": "MEHTA"}]}

def _result_with_checks_1_and_3(ads=_ADS):
    return Result(folder="/f", generated_at=GEN_AT, ads_data=ads, issues=[
        Issue(1, "Cross-Document Consistency", "Inventor Names Consistency",
              "PASS", "all present"),
        Issue(3, "Cross-Document Consistency", "Attorney Docket Number Consistency",
              "PASS", "docket matches"),
    ])

@test("EVID.1: Check 1 gets a pdf_region per inventor on the right page")
def t():
    res = _result_with_checks_1_and_3()
    enrich(res, {"Declaration": SAMPLE_PDF})
    c1 = next(i for i in res.issues if i.check_id == 1)
    regions = [e for e in c1.evidence if e.locator.type == "pdf_region"]
    by_name = {e.expected: e for e in regions}
    if set(by_name) != {"CHEN", "MEHTA"}:
        print(f"  ❌ surnames located: {set(by_name)}"); return False
    if by_name["CHEN"].locator.page != 0 or by_name["MEHTA"].locator.page != 1:
        print(f"  ❌ wrong pages: CHEN={by_name['CHEN'].locator.page} "
              f"MEHTA={by_name['MEHTA'].locator.page}"); return False
    b = by_name["CHEN"].locator.bbox
    if not (b and len(b) == 4 and b[2] > b[0] and b[3] > b[1]):
        print(f"  ❌ bad bbox: {b}"); return False
    return True

@test("EVID.2: Check 3 gets an xfa_field receipt with the docket value")
def t():
    res = _result_with_checks_1_and_3()
    enrich(res, {"Declaration": SAMPLE_PDF})
    c3 = next(i for i in res.issues if i.check_id == 3)
    xf = [e for e in c3.evidence if e.locator.type == "xfa_field"]
    if not xf or xf[0].locator.field_path != "docket_number" or xf[0].actual != "LUM-0142US":
        print(f"  ❌ xfa_field evidence wrong: {xf}"); return False
    return True

@test("EVID.3: a surname not in the document yields a 'missing' receipt")
def t():
    ads = {"inventors": [{"first": "Nobody", "last": "ZZZNOTHERE"}]}
    res = Result(folder="/f", generated_at=GEN_AT, ads_data=ads, issues=[
        Issue(1, "Cross-Document Consistency", "Inventor Names Consistency",
              "CRITICAL", "missing")])
    enrich(res, {"Declaration": SAMPLE_PDF})
    c1 = res.issues[0]
    miss = [e for e in c1.evidence if e.kind == "missing"]
    if not miss or miss[0].locator.type != "pdf_page":
        print(f"  ❌ expected a missing pdf_page receipt: {c1.evidence}"); return False
    return True

@test("EVID.4: enriched evidence serializes (pdf_region bbox survives to JSON)")
def t():
    res = _result_with_checks_1_and_3()
    enrich(res, {"Declaration": SAMPLE_PDF})
    back = json.loads(res.to_json())
    c1 = next(i for i in back["issues"] if i["check_id"] == 1)
    region = next(e for e in c1["evidence"] if e["locator"]["type"] == "pdf_region")
    if "bbox" not in region["locator"] or len(region["locator"]["bbox"]) != 4:
        print(f"  ❌ bbox missing in JSON: {region['locator']}"); return False
    return True

@test("EVID.5: run(folder, enrich=False) attaches no evidence")
def t():
    from core.build import run
    res = run(str(SAMPLE_PDF.parent), generated_at=GEN_AT, enrich=False)
    if any(i.evidence for i in res.issues):
        print(f"  ❌ evidence present despite enrich=False"); return False
    return True

SPEC_PDF = SAMPLE_PDF.parent / "Specification.pdf"
DRAW_PDF = SAMPLE_PDF.parent / "Drawings.pdf"
_TITLE = "MEMORY-EFFICIENT INFERENCE FOR LARGE LANGUAGE MODELS"

@test("LOC.1: locate strips surrounding punctuation from tokens")
def t():
    from core.locate import _tok, locate
    if (_tok("A088-0179US)"), _tok("CHEN,"), _tok("(Docket")) != ("a088-0179us", "chen", "docket"):
        print("  ❌ _tok punctuation strip wrong"); return False
    if not locate(DRAW_PDF, "LUM-0142US"):   # 'LUM-0142US)' in the PDF
        print("  ❌ docket not located against trailing-paren token"); return False
    return True

class _FakeQC:
    """Minimal stand-in for a finished engine run, for the native core check."""
    def __init__(self, ads_data, spec_text, documents):
        self.ads_data = ads_data; self.spec_text = spec_text
        self.ads_text = ""; self.documents = documents
    def extract_title(self, _): return ""

@test("MIG.1: native Check 2 (core/checks) — PASS + pdf_region + xfa_field")
def t():
    from core.checks.cross_document import check_application_title
    qc = _FakeQC({"title": _TITLE}, f"BACKGROUND\n{_TITLE}\nbody",
                 {"Specification": SPEC_PDF})
    issue = check_application_title(qc)
    if issue.check_id != 2 or issue.severity != "PASS":
        print(f"  ❌ check_id/severity = {issue.check_id}/{issue.severity}"); return False
    types = {e.locator.type for e in issue.evidence}
    if types != {"pdf_region", "xfa_field"}:
        print(f"  ❌ evidence types = {types}"); return False
    return True

@test("MIG.2: native Check 2 — CRITICAL when the title is absent from the spec")
def t():
    from core.checks.cross_document import check_application_title
    qc = _FakeQC({"title": _TITLE}, "BACKGROUND\nsomething unrelated entirely",
                 {"Specification": SPEC_PDF})
    issue = check_application_title(qc)
    if issue.severity != "CRITICAL":
        print(f"  ❌ severity = {issue.severity} (expected CRITICAL)"); return False
    return True

@test("MIG.3: core.run emits Check 2 exactly once (engine copy skipped)")
def t():
    from core.build import run
    res = run(str(SAMPLE_PDF.parent), generated_at=GEN_AT)
    c2 = [i for i in res.issues if i.check_id == 2]
    if len(c2) != 1:
        print(f"  ❌ Check 2 appears {len(c2)} times (duplicate or missing)"); return False
    return True

@test("MIG.4: issues stay ordered by check_id after core checks are appended")
def t():
    from core.build import run
    res = run(str(SAMPLE_PDF.parent), generated_at=GEN_AT)
    ids = [i.check_id for i in res.issues]
    if ids != sorted(ids):
        print(f"  ❌ issues not ordered by check_id"); return False
    return True

@test("EVID.7: Check 23 gets a pdf_region for the docket in the drawings margin")
def t():
    res = Result(folder="/f", generated_at=GEN_AT,
                 ads_data={"docket_number": "LUM-0142US"},
                 issues=[Issue(23, "Drawings", "All Figures Have Labels", "PASS", "ok")])
    enrich(res, {"Drawings": DRAW_PDF})
    regions = [e for e in res.issues[0].evidence if e.locator.type == "pdf_region"]
    if not regions or regions[0].doc_type != "Drawings":
        print(f"  ❌ no drawings pdf_region: {res.issues[0].evidence}"); return False
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
