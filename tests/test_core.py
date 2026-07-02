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
    qc.ads_data = {"docket_number": "X000-0000US"}
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
    if not res.folder or (res.ads_data or {}).get("docket_number") != "X000-0000US":
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
# The sample Declaration.pdf carries "Alice J. EXAMPLE" (page 1) and
# "Carol Dana SAMPLE" (page 2).
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

_INV2 = [{"first": "Alice", "middle": "J.", "last": "EXAMPLE"},
         {"first": "Carol", "middle": "Dana", "last": "SAMPLE"}]
_DECL_TXT = ("DECLARATION\nAlice J. EXAMPLE and Carol Dana SAMPLE are inventors.\n"
             + "padding.\n" * 10)

@test("MIG1.1: native Check 1 PASS + pdf_region per inventor on the right page")
def t():
    qc = _qc1(_INV2, _DECL_TXT, documents={"Declaration": SAMPLE_PDF})
    issue = check_inventor_names(qc)
    if issue.check_id != 1 or issue.severity != "PASS":
        print(f"  ❌ {issue.check_id}/{issue.severity}: {issue.message[:60]}"); return False
    regions = {e.expected: e for e in issue.evidence if e.locator.type == "pdf_region"}
    if set(regions) != {"EXAMPLE", "SAMPLE"}:
        print(f"  ❌ located surnames: {set(regions)}"); return False
    if regions["EXAMPLE"].locator.page != 0 or regions["SAMPLE"].locator.page != 1:
        print("  ❌ wrong pages"); return False
    return True

@test("MIG1.short: short surname locates full name first; normal surname unchanged")
def t():
    import core.checks.cross_document as cd
    calls = []
    orig = cd.locate
    cd.locate = lambda path, q: (calls.append(q), None)[1]   # record order, find nothing
    try:
        qc = _qc1([], "", documents={"Declaration": SAMPLE_PDF})
        cd._inventor_evidence(qc, [("Alpha Bravo P", "P")])
        if calls[:2] != ["Alpha Bravo P", "P"]:
            print(f"  ❌ short-surname order: {calls}"); return False
        calls.clear()
        cd._inventor_evidence(qc, [("Alice J. EXAMPLE", "EXAMPLE")])
        if calls[:2] != ["EXAMPLE", "Alice J. EXAMPLE"]:
            print(f"  ❌ normal-surname order: {calls}"); return False
        return True
    finally:
        cd.locate = orig

# ---- locate(): hyphenation / whitespace tolerance (title-highlight FP fix) --
from core.locate import locate, _collapse  # noqa: E402

def _hyphen_split_pdf():
    """A tiny 1-page PDF whose title line-breaks mid-word ('… LOW-' /
    'LATENCY …'), with a lowercase prose restatement lower on the page.
    Reproduces the layout that made locate() highlight the Summary
    sentence instead of the title heading. Returns a temp Path (caller unlinks)."""
    from fpdf import FPDF
    import tempfile
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.set_xy(72, 72); pdf.cell(0, 18, "SYSTEMS AND METHODS FOR LOW-")
    pdf.set_xy(72, 92); pdf.cell(0, 18, "LATENCY DISTRIBUTED CACHING")
    pdf.set_font("Helvetica", size=11)
    pdf.set_xy(72, 300)
    pdf.cell(0, 14, "Technologies for systems and methods for "
                    "low-latency distributed caching.")
    path = Path(tempfile.mkstemp(suffix=".pdf")[1])
    pdf.output(str(path))
    return path

@test("LOC.hyphen: locate() anchors on a title split across a line-break hyphen")
def t():
    try:
        import fpdf  # noqa: F401  (dev-only; used to synthesize the fixture)
    except ImportError:
        print("  ⏭  skipped (fpdf not installed — `pip install fpdf2`)"); return True
    path = _hyphen_split_pdf()
    try:
        hit = locate(path, "SYSTEMS AND METHODS FOR LOW-LATENCY "
                           "DISTRIBUTED CACHING")
        if not hit:
            print("  ❌ no match (hyphen-split title not found)"); return False
        # Heading is at top (top≈72); the lowercase restatement is at y≈300.
        # Must land on the heading, not the restatement.
        if hit["bbox"][1] > 150:
            print(f"  ❌ matched restatement, not heading: top={hit['bbox'][1]:.0f}")
            return False
        return True
    finally:
        path.unlink()

@test("LOC.collapse: _collapse strips case, whitespace, hyphens, edge punct")
def t():
    cases = {"LOW-": "low", "MULTI-CORE": "multicore",
             "systems.": "systems", "  X000-0000US ": "x0000000us"}
    for src, want in cases.items():
        if _collapse(src) != want:
            print(f"  ❌ _collapse({src!r})={_collapse(src)!r} want {want!r}")
            return False
    return True

from core.checks.cross_document import check_attorney_docket, check_correspondence  # noqa: E402

def _qc(**attrs):
    qc = PatentFilingQC(str(SAMPLE_PDF.parent))
    for k, v in attrs.items():
        setattr(qc, k, v)
    return qc

_DOCKET = "X000-0000USC3"  # a shape the engine's extract_docket_numbers recognizes

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
             spec_text="Spec X999-9999USA1 body", declaration_text="", assignment_text="",
             documents={})
    issue = check_attorney_docket(qc)
    if issue.severity != "CRITICAL":
        print(f"  ❌ severity = {issue.severity} (expected CRITICAL)"); return False
    return True

@test("MIG4.1: native Check 4 PASS when ADS + POA customer numbers match")
def t():
    qc = _qc(ads_data={"customer_number": "100000"}, ads_text="",
             poa_text="Customer Number: 100000", documents={})
    issue = check_correspondence(qc)
    if issue.check_id != 4 or issue.severity != "PASS":
        print(f"  ❌ {issue.check_id}/{issue.severity}"); return False
    xf = [e for e in issue.evidence if e.locator.type == "xfa_field"]
    if not xf or xf[0].actual != "100000":
        print(f"  ❌ xfa_field wrong: {issue.evidence}"); return False
    return True

@test("MIG4.2: native Check 4 CRITICAL on customer number mismatch")
def t():
    qc = _qc(ads_data={"customer_number": "100000"}, ads_text="",
             poa_text="Customer Number: 999999", documents={})
    issue = check_correspondence(qc)
    if issue.severity != "CRITICAL":
        print(f"  ❌ severity = {issue.severity} (expected CRITICAL)"); return False
    return True

from core.checks.cross_document import (check_assignee_name, check_filing_date,  # noqa: E402
                                        check_inventor_count, check_residency)

@test("MIG5.1: native Check 5 PASS when assignee appears in assignment; xfa_field")
def t():
    qc = _qc(ads_data={"assignee_org": "ACME CORP."}, ads_text="",
             assignment_text="assigns to ACME CORP. the entire right title "
                             "and interest", documents={})
    issue = check_assignee_name(qc)
    if issue.check_id != 5 or issue.severity != "PASS":
        print(f"  ❌ {issue.check_id}/{issue.severity}"); return False
    if not any(e.locator.type == "xfa_field" for e in issue.evidence):
        print(f"  ❌ no xfa_field receipt"); return False
    return True

@test("MIG5.2: native Check 5 WARNING when assignee not found in assignment")
def t():
    qc = _qc(ads_data={"assignee_org": "ACME CORP."}, ads_text="",
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

_INV2D = [{"first": "Alice", "last": "EXAMPLE"}, {"first": "Carol", "last": "SAMPLE"}]

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
        (Path(d) / "X000-0000US-Declaration.pdf").write_bytes(b"%PDF-1.4 x")
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
    if check_declaration_signatures(_qc(declaration_text="/Alice Example/ Date")).severity != "PASS":
        print("  ❌ /Name/ not PASS"); return False
    if check_declaration_signatures(_qc(declaration_text="signature line", image_only_pages={})).severity != "WARNING":
        print("  ❌ no-sig not WARNING"); return False
    if check_declaration_signatures(_qc(declaration_text="form body",
                                        image_only_pages={"Declaration": 2})).severity != "INFO":
        print("  ❌ image-only not INFO"); return False
    return True

@test("MIG12.1: Check 12 — assignment /Name/ PASS, missing N/A (optional)")
def t():
    if check_assignment_signatures(_qc(assignment_text="/Alice Example/")).severity != "PASS":
        print("  ❌ /Name/ not PASS"); return False
    if check_assignment_signatures(_qc(assignment_text="")).severity != "N/A":
        print("  ❌ missing assignment not N/A"); return False
    return True

@test("MIG1.2: native Check 1 CRITICAL when an inventor is missing")
def t():
    # Second inventor is absent from both the text AND the sample PDF.
    inv = [{"first": "Alice", "last": "EXAMPLE"},
           {"first": "Nobody", "last": "ZZZNOTHERE"}]
    qc = _qc1(inv, "DECLARATION\nOnly Alice EXAMPLE is named here.\n" + "padding.\n" * 10,
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
    qc = _qc1(_INV2, "DECLARATION\nOnly Alice J. EXAMPLE is named.\n" + "padding.\n" * 10,
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

@test("EVID.5: native receipts are emitted regardless of the (no-op) enrich flag")
def t():
    # Evidence is now emitted natively by core/checks, not by the (stub) enricher,
    # so it must be present even with enrich=False (e.g. the sample spec's
    # leftover placeholder yields a Check 50 receipt).
    from core.build import run
    res = run(str(SAMPLE_PDF.parent), generated_at=GEN_AT, enrich=False)
    if not any(i.evidence for i in res.issues):
        print("  ❌ expected native evidence even with enrich=False"); return False
    return True

SPEC_PDF = SAMPLE_PDF.parent / "Specification.pdf"
DRAW_PDF = SAMPLE_PDF.parent / "Drawings.pdf"
_TITLE = "WIDGET ASSEMBLY DEVICE"

@test("LOC.1: locate strips surrounding punctuation from tokens")
def t():
    from core.locate import _tok, locate
    if (_tok("X000-0000US)"), _tok("EXAMPLE,"), _tok("(Docket")) != ("x000-0000us", "example", "docket"):
        print("  ❌ _tok punctuation strip wrong"); return False
    if not locate(DRAW_PDF, "X000-0000US"):   # 'X000-0000US)' in the PDF
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

@test("MIG23.1: native Check 23 emits a pdf_region docket receipt in the drawings")
def t():
    from core.checks.drawings import check_drawings
    qc = _qc(ads_data={"docket_number": "X000-0000US", "title": "WIDGET ASSEMBLY DEVICE"},
             ads_text="", spec_text="",
             drawings_text="(Docket No.: X000-0000US) Title: WIDGET ASSEMBLY DEVICE "
                          "FIG. 1 FIG. 2 Sheet 1 of 1",
             documents={"Drawings": DRAW_PDF})
    out = check_drawings(qc)
    c23 = next(i for i in out if i.check_id == 23)
    if not any(e.locator.type == "pdf_region" and e.doc_type == "Drawings"
               for e in c23.evidence):
        print(f"  ❌ no drawings pdf_region: {c23.evidence}"); return False
    return True

@test("MIG22.1: native Check 24 detects sheet numbering; missing -> WARNING")
def t():
    from core.checks.drawings import check_drawings
    qc = _qc(drawings_text="FIG. 1 FIG. 2 Sheet 1 of 2", documents={})
    c24 = next(i for i in check_drawings(qc) if i.check_id == 24)
    if c24.severity != "PASS":
        print(f"  ❌ {c24.severity}"); return False
    qc2 = _qc(drawings_text="FIG. 1 FIG. 2 no sheets here", documents={})
    c24b = next(i for i in check_drawings(qc2) if i.check_id == 24)
    if c24b.severity != "WARNING":
        print(f"  ❌ {c24b.severity}"); return False
    return True


# ---- report frontend (consumes Result) -------------------------------------
from report.html import render  # noqa: E402

def _report_result():
    return Result(
        folder="/f", generated_at=GEN_AT,
        ads_data={"title": "WIDGET", "docket_number": "X000-0000US",
                  "inventors": [{"last": "EXAMPLE"}]},
        documents=[DocumentRef("Declaration", "D.pdf", "D.pdf", "pdf", 2)],
        issues=[
            Issue(1, "Cross-Document Consistency", "Inventor Names Consistency",
                  "PASS", "all present", evidence=[Evidence(
                      "Declaration", Locator("pdf_region", page=0, bbox=[1, 2, 3, 4]),
                      snippet="EXAMPLE", kind="match", label="surname EXAMPLE found")]),
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
    if "receipt" not in h or "surname EXAMPLE found" not in h:
        print("  ❌ evidence receipt not rendered"); return False
    if "Declaration p.1" not in h:
        print("  ❌ receipt location not rendered"); return False
    return True

@test("REP.3: ADS summary + documents table appear")
def t():
    h = render(_report_result())
    if "ADS Data Summary" not in h or "X000-0000US" not in h:
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


# ---- IDS (76-80): exercised directly (sample/real folders have no IDS) -----
from core.checks.ids import check_ids  # noqa: E402


def _ids_xfa(sig="/Dana X. TESTER/", reg="00000", us_docs=("10123456", "10222333"),
             pubs=(), npls=()):
    parts = ["<ids-form>", "<electronic-signature><basic-signature><text-string>"
             + (sig or "") + "</text-string></basic-signature>"
             + (f"<registered-number>{reg}</registered-number>" if reg else "")
             + "</electronic-signature>"]
    if us_docs:
        parts.append("<us-patent-cite>" + "".join(
            f"<us-doc-reference><doc-number>{d}</doc-number></us-doc-reference>"
            for d in us_docs) + "</us-patent-cite>")
    if pubs:
        parts.append("<us-pub-appl-cite>" + "".join(
            f"<us-doc-reference><doc-number>{d}</doc-number></us-doc-reference>"
            for d in pubs) + "</us-pub-appl-cite>")
    if npls:
        parts.append("<us-nplcit>" + "".join(f"<text>{n}</text>" for n in npls) + "</us-nplcit>")
    parts.append("</ids-form>")
    return "".join(parts)


def _by_id(issues, cid):
    return next((i for i in issues if i.check_id == cid), None)


@test("MIG76.1: Check 76 N/A (single) when no IDS documents present (optional)")
def t():
    out = check_ids(_qc(documents={}, ids_text=""))
    if len(out) != 1 or out[0].check_id != 76 or out[0].severity != "N/A":
        print(f"  ❌ {[ (i.check_id, i.severity) for i in out]}"); return False
    return True


@test("MIG77.1: Check 77 PASS (sig+reg), WARN (none), WARN (partial)")
def t():
    p = SAMPLE_PDF
    for kw, want in (({"sig": "/R. TESTER/", "reg": "00000"}, "PASS"),
                     ({"sig": "", "reg": ""}, "WARNING"),
                     ({"sig": "/R. TESTER/", "reg": ""}, "WARNING")):
        qc = _qc(documents={"IDS": p}, ids_text=_ids_xfa(**kw))
        i = _by_id(check_ids(qc), 77)
        if not i or i.severity != want:
            print(f"  ❌ {kw} -> {i.severity if i else None} (want {want})"); return False
    return True


@test("MIG78.1: Check 78 INFO counts references; WARN when none")
def t():
    qc = _qc(documents={"IDS": SAMPLE_PDF},
             ids_text=_ids_xfa(us_docs=("10123456", "10222333", "10999000"),
                               pubs=("20210000001",), npls=("Smith et al. 2020",)))
    i = _by_id(check_ids(qc), 78)
    if not i or i.severity != "INFO" or "5 reference" not in i.message:
        print(f"  ❌ {i.severity if i else None}: {i.message[:80] if i else ''}"); return False
    qc2 = _qc(documents={"IDS": SAMPLE_PDF}, ids_text=_ids_xfa(us_docs=()))
    i2 = _by_id(check_ids(qc2), 78)
    if not i2 or i2.severity != "WARNING":
        print(f"  ❌ empty -> {i2.severity if i2 else None}"); return False
    return True


@test("MIG79.1: Check 79 PASS (one box), CRITICAL (multi), CRITICAL (none)")
def t():
    p = SAMPLE_PDF
    cases = (({"Check Box1": "/Yes", "Check Box2": "/Off"}, "PASS"),
             ({"Check Box1": "/Yes", "Check Box2": "/Yes"}, "CRITICAL"),
             ({"Check Box1": "/Off", "Check Box2": "/Off"}, "CRITICAL"))
    for fields, want in cases:
        qc = _qc(documents={"IDS Written Assertion": p})
        qc._extract_acroform_fields = lambda _p, f=fields: f
        i = _by_id(check_ids(qc), 79)
        if not i or i.severity != want:
            print(f"  ❌ {fields} -> {i.severity if i else None} (want {want})"); return False
    return True


@test("MIG80.1: Check 80 PASS (sig+name), WARN (unsigned)")
def t():
    p = SAMPLE_PDF
    qc = _qc(documents={"IDS Written Assertion": p})
    qc._extract_acroform_fields = lambda _p: {"Signature": "/R. TESTER/",
                                              "Name PrintTyped": "Dana TESTER",
                                              "Date": "2026-05-09"}
    i = _by_id(check_ids(qc), 80)
    if not i or i.severity != "PASS":
        print("  ❌ signed != PASS"); return False
    qc2 = _qc(documents={"IDS Written Assertion": p})
    qc2._extract_acroform_fields = lambda _p: {"Signature": "", "Name PrintTyped": ""}
    if _by_id(check_ids(qc2), 80).severity != "WARNING":
        print("  ❌ unsigned != WARNING"); return False
    return True


# ---- receipts: placeholder text highlights where it sits --------------------
@test("MIG50.1: Check 50 CRITICAL + pdf_region receipt on the placeholder")
def t():
    from core.checks.common_errors import check_common_errors
    qc = _qc(spec_text="Some Title\n[INSERT DESCRIPTION OF PRIOR ART]\nbody text",
             ads_text="", declaration_text="", assignment_text="",
             documents={"Specification": SPEC_PDF})
    c50 = next(i for i in check_common_errors(qc) if i.check_id == 50)
    if c50.severity != "CRITICAL":
        print(f"  ❌ severity {c50.severity}"); return False
    regions = [e for e in c50.evidence if e.locator.type == "pdf_region"]
    if not regions or "INSERT" not in (regions[0].snippet or ""):
        print(f"  ❌ no placeholder receipt: {[(e.locator.type, e.snippet) for e in c50.evidence]}")
        return False
    return True


@test("MIG18.1: Check 18 Background PASS carries a pdf_region receipt on the header")
def t():
    from core.checks.specification import check_specification
    qc = _qc(spec_text="A TITLE\nBACKGROUND\nModern systems require efficient inference.\n",
             documents={"Specification": SPEC_PDF})
    c18 = next(i for i in check_specification(qc) if i.check_id == 18)
    if c18.severity != "PASS":
        print(f"  ❌ severity {c18.severity}"); return False
    reg = [e for e in c18.evidence if e.locator.type == "pdf_region"]
    if not reg or "BACKGROUND" not in (reg[0].snippet or "").upper():
        print(f"  ❌ no header receipt: {[(e.locator.type, e.snippet) for e in c18.evidence]}")
        return False
    return True


@test("DOCLINK.1: receiptless per-doc checks get a 'view document' link; others don't")
def t():
    from core.build import run
    r = run(str(SAMPLE_PDF.parent), generated_at=GEN_AT)
    is_doclink = lambda cid, dt: any(
        e.kind == "document" and e.doc_type == dt
        for i in r.issues if i.check_id == cid for e in i.evidence)
    has_doclink = lambda cid: any(
        e.kind == "document" for i in r.issues if i.check_id == cid for e in i.evidence)
    # a Drawings check (present doc, no precise receipt) -> Drawings doc link
    if not is_doclink(22, "Drawings"):
        print("  ❌ check 22 missing Drawings doc link"); return False
    # check 50 already has a precise receipt -> no redundant doc link
    if has_doclink(50):
        print("  ❌ check 50 should not get a doc link"); return False
    # check 9 is cross-cutting (Document Completeness) -> no doc link
    if has_doclink(9):
        print("  ❌ check 9 (cross-cutting) should not get a doc link"); return False
    return True


@test("RCPT.1: claim-count (62) and figure-format (70) carry pdf_region receipts")
def t():
    from core.build import run
    r = run(str(SAMPLE_PDF.parent), generated_at=GEN_AT)
    def snip(cid):
        return next((e.snippet for i in r.issues if i.check_id == cid
                     for e in i.evidence if e.locator.type == "pdf_region"), None)
    s62, s70 = snip(62), snip(70)
    if not s62 or "claimed" not in s62.lower():
        print(f"  ❌ check 62 receipt: {s62!r}"); return False
    if not s70 or "FIG" not in (s70 or "").upper():
        print(f"  ❌ check 70 receipt: {s70!r}"); return False
    return True


# ---- read-only guarantee: the QC run must never touch the filing folder -----
@test("READONLY: core.run() creates, modifies, or deletes nothing in the folder")
def t():
    from core.build import run as _run
    folder = SAMPLE_PDF.parent

    def snap():
        s = {}
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                st = p.stat()
                s[str(p.relative_to(folder))] = (st.st_size, st.st_mtime_ns)
        return s

    before = snap()
    _run(str(folder), generated_at="t")        # full QC incl. OCR on the sample
    after = snap()
    if before != after:
        added = set(after) - set(before)
        removed = set(before) - set(after)
        changed = {k for k in before if k in after and before[k] != after[k]}
        print(f"  ❌ folder changed — added={added} removed={removed} changed={changed}")
        return False
    return True


# ---- migration parity: core == engine for every migrated check -------------
@test("PARITY: core matches the engine for every migrated check (sample folder)")
def t():
    from collections import defaultdict
    from core.checks import CHECKS, MIGRATED_IDS
    qc = PatentFilingQC(str(SAMPLE_PDF.parent))
    qc.load_documents()
    qc.run_all_checks()                       # engine emits everything (no skip)
    # Core may re-tag an inapplicable PASS/INFO as "N/A" (a presentational
    # refinement, not a verdict change). Collapse the three non-blocking
    # severities so PARITY still strictly guards CRITICAL/WARNING + message.
    norm = lambda s: "OK" if s in ("PASS", "INFO", "N/A") else s
    eng = defaultdict(list)
    for i in qc.report.issues:
        if i.check_id in MIGRATED_IDS:
            eng[i.check_id].append((norm(i.severity.value), i.message))
    core = defaultdict(list)
    for fn in CHECKS:
        out = fn(qc)
        for i in (out if isinstance(out, list) else [out]):
            if i is not None:
                core[i.check_id].append((norm(i.severity), i.message))
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
