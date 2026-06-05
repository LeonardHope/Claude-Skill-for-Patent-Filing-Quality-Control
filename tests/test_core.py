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


# ---- native Check 1 (core/checks) + Check 3 enricher -----------------------
# The sample Declaration.pdf carries "Sarah J. CHEN" (page 1) and
# "Aditya Vikram MEHTA" (page 2).
from core.checks.cross_document import check_inventor_names  # noqa: E402

def _qc1(inventors, decl, asgn="", image_only=None, documents=None):
    """A real PatentFilingQC (for its name-matching helpers) with just the
    state Check 1 reads, set directly."""
    qc = PatentFilingQC(str(SAMPLE_PDF.parent))
    qc.ads_data = {"inventors": inventors}
    qc.ads_text = ""
    qc.declaration_text = decl
    qc.assignment_text = asgn
    qc.image_only_pages = image_only or {}
    qc.documents = documents or {}
    return qc

_INV2 = [{"first": "Sarah", "middle": "J.", "last": "CHEN"},
         {"first": "Aditya", "middle": "Vikram", "last": "MEHTA"}]
_DECL_TXT = ("DECLARATION\nSarah J. CHEN and Aditya Vikram MEHTA are inventors.\n"
             + "padding.\n" * 10)

@test("MIG1.1: native Check 1 PASS + pdf_region per inventor on the right page")
def t():
    qc = _qc1(_INV2, _DECL_TXT, documents={"Declaration": SAMPLE_PDF})
    issue = check_inventor_names(qc)
    if issue.check_id != 1 or issue.severity != "PASS":
        print(f"  ❌ {issue.check_id}/{issue.severity}: {issue.message[:60]}"); return False
    regions = {e.expected: e for e in issue.evidence if e.locator.type == "pdf_region"}
    if set(regions) != {"CHEN", "MEHTA"}:
        print(f"  ❌ located surnames: {set(regions)}"); return False
    if regions["CHEN"].locator.page != 0 or regions["MEHTA"].locator.page != 1:
        print("  ❌ wrong pages"); return False
    return True

from core.checks.cross_document import check_attorney_docket, check_correspondence  # noqa: E402

def _qc(**attrs):
    qc = PatentFilingQC(str(SAMPLE_PDF.parent))
    for k, v in attrs.items():
        setattr(qc, k, v)
    return qc

_DOCKET = "MS1-9771USC3"  # a shape the engine's extract_docket_numbers recognizes

@test("MIG3.1: native Check 3 PASS when ADS + Spec share a docket; xfa_field receipt")
def t():
    qc = _qc(ads_data={"docket_number": _DOCKET}, ads_text="", spec_text=f"Spec {_DOCKET} body",
             declaration_text="", assignment_text="", documents={})
    issue = check_attorney_docket(qc)
    if issue.check_id != 3 or issue.severity != "PASS":
        print(f"  ❌ {issue.check_id}/{issue.severity}: {issue.message[:60]}"); return False
    xf = [e for e in issue.evidence if e.locator.type == "xfa_field"]
    if not xf or xf[0].actual != _DOCKET:
        print(f"  ❌ xfa_field wrong: {issue.evidence}"); return False
    return True

@test("MIG3.2: native Check 3 CRITICAL when dockets disagree")
def t():
    qc = _qc(ads_data={"docket_number": _DOCKET}, ads_text="",
             spec_text="Spec XYZ9-8888USA1 body", declaration_text="", assignment_text="",
             documents={})
    issue = check_attorney_docket(qc)
    if issue.severity != "CRITICAL":
        print(f"  ❌ severity = {issue.severity} (expected CRITICAL)"); return False
    return True

@test("MIG4.1: native Check 4 PASS when ADS + POA customer numbers match")
def t():
    qc = _qc(ads_data={"customer_number": "142810"}, ads_text="",
             poa_text="Customer Number: 142810", documents={})
    issue = check_correspondence(qc)
    if issue.check_id != 4 or issue.severity != "PASS":
        print(f"  ❌ {issue.check_id}/{issue.severity}"); return False
    xf = [e for e in issue.evidence if e.locator.type == "xfa_field"]
    if not xf or xf[0].actual != "142810":
        print(f"  ❌ xfa_field wrong: {issue.evidence}"); return False
    return True

@test("MIG4.2: native Check 4 CRITICAL on customer number mismatch")
def t():
    qc = _qc(ads_data={"customer_number": "142810"}, ads_text="",
             poa_text="Customer Number: 999999", documents={})
    issue = check_correspondence(qc)
    if issue.severity != "CRITICAL":
        print(f"  ❌ severity = {issue.severity} (expected CRITICAL)"); return False
    return True

from core.checks.cross_document import (check_assignee_name, check_filing_date,  # noqa: E402
                                        check_inventor_count, check_residency)

@test("MIG5.1: native Check 5 PASS when assignee appears in assignment; xfa_field")
def t():
    qc = _qc(ads_data={"assignee_org": "LUMINA AI, INC."}, ads_text="",
             assignment_text="assigns to LUMINA AI, INC. the entire right title "
                             "and interest", documents={})
    issue = check_assignee_name(qc)
    if issue.check_id != 5 or issue.severity != "PASS":
        print(f"  ❌ {issue.check_id}/{issue.severity}"); return False
    if not any(e.locator.type == "xfa_field" for e in issue.evidence):
        print(f"  ❌ no xfa_field receipt"); return False
    return True

@test("MIG5.2: native Check 5 WARNING when assignee not found in assignment")
def t():
    qc = _qc(ads_data={"assignee_org": "LUMINA AI, INC."}, ads_text="",
             assignment_text="assigns to SOME OTHER ENTITY the entire right", documents={})
    issue = check_assignee_name(qc)
    if issue.severity != "WARNING":
        print(f"  ❌ severity = {issue.severity}"); return False
    return True

@test("MIG6.1: native Check 6 PASS with no conflicting filing dates")
def t():
    qc = _qc(ads_text="", poa_text="Filing Date Herewith")
    issue = check_filing_date(qc)
    if issue.check_id != 6 or issue.severity != "PASS":
        print(f"  ❌ {issue.check_id}/{issue.severity}"); return False
    return True

_INV2D = [{"first": "Sarah", "last": "CHEN"}, {"first": "Aditya", "last": "MEHTA"}]

@test("MIG7.1: native Check 7 PASS when ADS count == declaration count")
def t():
    qc = _qc(ads_data={"inventors": _INV2D}, ads_text="", image_only_pages={},
             declaration_text="I hereby declare ... I hereby declare ...")
    issue = check_inventor_count(qc)
    if issue.check_id != 7 or issue.severity != "PASS":
        print(f"  ❌ {issue.check_id}/{issue.severity}: {issue.message[:60]}"); return False
    return True

@test("MIG7.2: native Check 7 CRITICAL when declaration has fewer inventors")
def t():
    qc = _qc(ads_data={"inventors": _INV2D}, ads_text="", image_only_pages={},
             declaration_text="I hereby declare that I am an inventor.")
    issue = check_inventor_count(qc)
    if issue.severity != "CRITICAL":
        print(f"  ❌ severity = {issue.severity}"); return False
    return True

@test("MIG8.1: native Check 8 PASS when all inventors have residency")
def t():
    qc = _qc(ads_data={"inventors": [{"residency": "us-residency"},
                                     {"residency": "non-us-residency"}]}, ads_text="")
    issue = check_residency(qc)
    if issue.check_id != 8 or issue.severity != "PASS":
        print(f"  ❌ {issue.check_id}/{issue.severity}"); return False
    return True

@test("MIG8.2: native Check 8 WARNING when an inventor lacks residency")
def t():
    qc = _qc(ads_data={"inventors": [{"residency": "us-residency"}, {"residency": ""}]},
             ads_text="")
    issue = check_residency(qc)
    if issue.severity != "WARNING":
        print(f"  ❌ severity = {issue.severity}"); return False
    return True

# ---- Document Completeness (Checks 9-12) -----------------------------------
import tempfile  # noqa: E402
from core.checks.completeness import (check_required_documents, check_ads_fields,  # noqa: E402
                                      check_declaration_signatures,
                                      check_assignment_signatures)

def _qc_files(files_found, folder=None, **attrs):
    qc = _qc(**attrs)
    qc.report.files_found = files_found
    if folder:
        from pathlib import Path
        qc.folder_path = Path(folder)
    return qc

_ALL = {"Specification": "s.pdf", "Drawings": "d.pdf", "ADS": "a.pdf",
        "Declaration": "dec.pdf"}

@test("MIG9.1: Check 9 PASS when all required documents present")
def t():
    out = check_required_documents(_qc_files(_ALL))
    if [i.severity for i in out] != ["PASS"]:
        print(f"  ❌ {[(i.severity) for i in out]}"); return False
    return True

@test("MIG9.2: Check 9 CRITICAL (blocking) when the spec is missing")
def t():
    ff = dict(_ALL); ff["Specification"] = None
    out = check_required_documents(_qc_files(ff))
    if not any(i.severity == "CRITICAL" and "Specification" in i.message for i in out):
        print(f"  ❌ {[(i.severity, i.message[:40]) for i in out]}"); return False
    return True

@test("MIG9.3: Check 9 missing-parts CRITICAL when only declaration missing, no scan")
def t():
    ff = dict(_ALL); ff["Declaration"] = None
    with tempfile.TemporaryDirectory() as d:        # empty folder -> no declar file
        out = check_required_documents(_qc_files(ff, folder=d))
    if not any(i.severity == "CRITICAL" and "intentional" in i.message for i in out):
        print(f"  ❌ {[(i.severity, i.message[:40]) for i in out]}"); return False
    return True

@test("MIG9.4: Check 9 WARNING when a 'declar'-named scan is present")
def t():
    ff = dict(_ALL); ff["Declaration"] = None
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path
        (Path(d) / "A088-Declaration.pdf").write_bytes(b"%PDF-1.4 x")
        out = check_required_documents(_qc_files(ff, folder=d))
        sev = [i.severity for i in out]
    if "WARNING" not in sev:
        print(f"  ❌ {sev}"); return False
    return True

@test("MIG10.1: Check 10 CRITICAL when ADS text absent; PASS with fields")
def t():
    if check_ads_fields(_qc(ads_text="")).severity != "CRITICAL":
        print("  ❌ empty ADS not CRITICAL"); return False
    ok = check_ads_fields(_qc(ads_text="Title ... inventor ... correspondence ..."))
    if ok.severity != "PASS":
        print(f"  ❌ {ok.severity}"); return False
    return True

@test("MIG11.1: Check 11 — /Name/ PASS, none WARNING, image-only INFO")
def t():
    if check_declaration_signatures(_qc(declaration_text="/Sarah Chen/ Date")).severity != "PASS":
        print("  ❌ /Name/ not PASS"); return False
    if check_declaration_signatures(_qc(declaration_text="signature line", image_only_pages={})).severity != "WARNING":
        print("  ❌ no-sig not WARNING"); return False
    if check_declaration_signatures(_qc(declaration_text="form body",
                                        image_only_pages={"Declaration": 2})).severity != "INFO":
        print("  ❌ image-only not INFO"); return False
    return True

@test("MIG12.1: Check 12 — assignment /Name/ PASS, missing INFO (optional)")
def t():
    if check_assignment_signatures(_qc(assignment_text="/Sarah Chen/")).severity != "PASS":
        print("  ❌ /Name/ not PASS"); return False
    if check_assignment_signatures(_qc(assignment_text="")).severity != "INFO":
        print("  ❌ missing assignment not INFO"); return False
    return True

@test("MIG1.2: native Check 1 CRITICAL when an inventor is missing")
def t():
    # Second inventor is absent from both the text AND the sample PDF.
    inv = [{"first": "Sarah", "last": "CHEN"},
           {"first": "Nobody", "last": "ZZZNOTHERE"}]
    qc = _qc1(inv, "DECLARATION\nOnly Sarah CHEN is named here.\n" + "padding.\n" * 10,
              documents={"Declaration": SAMPLE_PDF})
    issue = check_inventor_names(qc)
    if issue.severity != "CRITICAL":
        print(f"  ❌ severity = {issue.severity} (expected CRITICAL)"); return False
    miss = [e for e in issue.evidence
            if e.kind == "missing" and e.expected == "ZZZNOTHERE"]
    if not miss or miss[0].locator.type != "pdf_page":
        print(f"  ❌ expected a missing pdf_page receipt for ZZZNOTHERE"); return False
    return True

@test("MIG1.3: native Check 1 hedges to WARNING when missing on an image-only doc")
def t():
    qc = _qc1(_INV2, "DECLARATION\nOnly Sarah J. CHEN is named.\n" + "padding.\n" * 10,
              image_only={"Declaration": 2}, documents={"Declaration": SAMPLE_PDF})
    issue = check_inventor_names(qc)
    if issue.severity != "WARNING":
        print(f"  ❌ severity = {issue.severity} (expected WARNING)"); return False
    return True

@test("MIG1.4: native Check 1 evidence serializes (bbox survives to JSON)")
def t():
    qc = _qc1(_INV2, _DECL_TXT, documents={"Declaration": SAMPLE_PDF})
    res = Result(folder="/f", generated_at=GEN_AT, issues=[check_inventor_names(qc)])
    back = json.loads(res.to_json())
    region = next(e for e in back["issues"][0]["evidence"]
                  if e["locator"]["type"] == "pdf_region")
    if len(region["locator"]["bbox"]) != 4:
        print(f"  ❌ bbox missing in JSON"); return False
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


# ---- report frontend (consumes Result) -------------------------------------
from report.html import render  # noqa: E402

def _report_result():
    return Result(
        folder="/f", generated_at=GEN_AT,
        ads_data={"title": "WIDGET", "docket_number": "LUM-0142US",
                  "inventors": [{"last": "CHEN"}]},
        documents=[DocumentRef("Declaration", "D.pdf", "D.pdf", "pdf", 2)],
        issues=[
            Issue(1, "Cross-Document Consistency", "Inventor Names Consistency",
                  "PASS", "all present", evidence=[Evidence(
                      "Declaration", Locator("pdf_region", page=0, bbox=[1, 2, 3, 4]),
                      snippet="CHEN", kind="match", label="surname CHEN found")]),
            Issue(9, "Document Completeness", "All Required Documents Present",
                  "CRITICAL", "Spec missing"),
        ])

@test("REP.1: render produces HTML with severity counts")
def t():
    h = render(_report_result())
    if "<html" not in h or "Patent Filing QC Report" not in h:
        print("  ❌ not an HTML report"); return False
    if "1 Pass" not in h or "1 Critical" not in h:
        print("  ❌ counts pills missing/incorrect"); return False
    return True

@test("REP.2: report is evidence-aware (receipts rendered)")
def t():
    h = render(_report_result())
    if "receipt" not in h or "surname CHEN found" not in h:
        print("  ❌ evidence receipt not rendered"); return False
    if "Declaration p.1" not in h:
        print("  ❌ receipt location not rendered"); return False
    return True

@test("REP.3: ADS summary + documents table appear")
def t():
    h = render(_report_result())
    if "ADS Data Summary" not in h or "LUM-0142US" not in h:
        print("  ❌ ADS summary missing"); return False
    if "Documents Found" not in h or "D.pdf" not in h:
        print("  ❌ documents table missing"); return False
    return True

@test("REP.4: content is HTML-escaped (no injection)")
def t():
    res = Result(folder="/f", generated_at=GEN_AT, issues=[
        Issue(1, "C", "N", "INFO", "<script>alert(1)</script>")])
    h = render(res)
    if "<script>alert(1)</script>" in h:
        print("  ❌ message not escaped"); return False
    if "&lt;script&gt;" not in h:
        print("  ❌ expected escaped form not found"); return False
    return True


# ---- migration parity: core == engine for every migrated check -------------
@test("PARITY: core matches the engine for every migrated check (sample folder)")
def t():
    from collections import defaultdict
    from core.checks import CHECKS, MIGRATED_IDS
    qc = PatentFilingQC(str(SAMPLE_PDF.parent))
    qc.load_documents()
    qc.run_all_checks()                       # engine emits everything (no skip)
    eng = defaultdict(list)
    for i in qc.report.issues:
        if i.check_id in MIGRATED_IDS:
            eng[i.check_id].append((i.severity.value, i.message))
    core = defaultdict(list)
    for fn in CHECKS:
        out = fn(qc)
        for i in (out if isinstance(out, list) else [out]):
            if i is not None:
                core[i.check_id].append((i.severity, i.message))
    bad = [cid for cid in MIGRATED_IDS if sorted(eng[cid]) != sorted(core[cid])]
    if bad:
        print(f"  ❌ parity mismatch (engine vs core) for checks: {sorted(bad)}")
        for cid in sorted(bad)[:3]:
            print(f"      {cid} engine={eng[cid]}")
            print(f"      {cid} core  ={core[cid]}")
        return False
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
