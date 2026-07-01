"""Comprehensive test suite for the QC skill (post PR #6/#9 sync).

Sections:
  1. Baseline (perfect filing → all PASS, no CRITICAL)
  2. Failure-branch scenarios (each check's CRITICAL/WARN path)
  3. Suffix handling (XFA 'last' vs split()[-1])
  4. Missing-document fallbacks emit only real check IDs (no phantoms 26/30/43)
  5. self.documents path-based replacements (verify the right Path is used)
  6. Check 75 (unrecognized files) surfaces in report
  7. Tightened signature checks (11, 12, 44) — labels alone don't pass
  8. Check 8 residency uses XFA structured field
  9. Check 49 .docx fallback emits INFO not false PASS
 10. IDS checks 76-80 (NEW — PR #6)
 11. Compound-surname extraction (NEW — PR #9)
 12. Rotated-drawings FIG handling (NEW — PR #6)
"""
import sys, copy, re, os, tempfile, atexit, shutil
from pathlib import Path

# Resolve the script dir relative to this test file so the suite is portable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
from qc_patent_filing import PatentFilingQC, Severity, LIGHTWEIGHT_SKIP_IDS

# Scratch working dir with placeholder PDFs. Several checks stat the files in
# self.documents (e.g. Check 58 file-size), so the referenced paths must exist.
WORK = Path(tempfile.mkdtemp(prefix="qc_test_"))
atexit.register(lambda: shutil.rmtree(WORK, ignore_errors=True))
for _n in ['Spec.pdf', 'Drawings.pdf', 'ADS.pdf', 'Decl.pdf', 'Asgn.pdf',
           'POA.pdf', 'IDS.pdf', 'WA.pdf']:
    (WORK / _n).write_bytes(b'%PDF-1.4 placeholder')

# ============================================================
# Test fixtures
# ============================================================
BASE_INVENTORS = [
    {"prefix": "", "first": "Sarah", "middle": "J.", "last": "CHEN", "suffix": "",
     "citizenship": "US", "residency": "us-residency",
     "res_city": "Mountain View", "res_state": "CA", "res_country": "US",
     "mail_address1": "1500 Lumina Way", "mail_address2": "",
     "mail_city": "Mountain View", "mail_state": "CA",
     "mail_postcode": "94043", "mail_country": "US"},
    {"prefix": "", "first": "Aditya", "middle": "Vikram", "last": "MEHTA", "suffix": "",
     "citizenship": "IN", "residency": "non-us-residency",
     "res_city": "Bengaluru", "res_state": "", "res_country": "IN",
     "mail_address1": "c/o Lumina AI India",
     "mail_address2": "", "mail_city": "Bengaluru", "mail_state": "KA",
     "mail_postcode": "560103", "mail_country": "IN"},
]
BASE_ADS = {
    "inventors": BASE_INVENTORS,
    "title": "MEMORY-EFFICIENT INFERENCE FOR LARGE LANGUAGE MODELS",
    "docket_number": "LUM-0142US", "customer_number": "142810",
    "attorney_customer_number": "142810", "form_pages": "9",
    "small_entity": False, "application_type": "REGULAR",
    "submission_type": "UTL", "drawing_sheets": "8",
    "representative_figure": "1", "non_publication": False,
    "aia_transition": False, "assignee_org": "LUMINA AI, INC.",
    "assignee_address": {"address1": "1500 Lumina Way", "address2": "",
                         "city": "Mountain View", "state": "CA",
                         "postcode": "94043", "country": "US"},
    "signer": {"first_name": "Robert", "last_name": "Holcomb",
               "registration_number": "62198",
               "signature": "/Robert M. Holcomb/", "date": "2026-05-09"},
    "domestic_continuity_entries": [], "foreign_priority_entries": [],
}
BASE_SPEC = """LUM-0142US
MEMORY-EFFICIENT INFERENCE FOR LARGE LANGUAGE MODELS
BACKGROUND
[0001] Modern LLMs use lots of memory.
SUMMARY
[0010] Embodiments provide a system 100 and a method.
BRIEF DESCRIPTION OF THE DRAWINGS
[0020] FIG. 1 is a block diagram of a system 100.
[0021] FIG. 2 illustrates a controller 102.
DETAILED DESCRIPTION
[0030] FIG. 1 depicts a system 100 with a controller 102.
CLAIMS
What is claimed is:
1. A method comprising: measuring sensitivity; selecting precision; quantizing weights.
2. The method of claim 1, wherein the measuring uses Hessian saliency.
3. The method of claim 1, further comprising offloading cache entries.
ABSTRACT
A system and method for memory-efficient inference dynamically selects per-layer precision and offloads cache tensors.
"""
BASE_DRAWINGS = "Sheet 1/2 FIG. 1 100 102\nSheet 2/2 FIG. 2 102 104\n"
BASE_DECL = """DECLARATION (37 CFR 1.63)
Attorney Docket Number: LUM-0142US
I hereby declare that I am an original inventor.
Inventor 1
Suffix
Sarah J. CHEN
/Sarah J. Chen/  Date: 2026-05-09
I hereby declare that I am an original inventor.
Inventor 2
Suffix
Aditya Vikram MEHTA
/Aditya Vikram Mehta/  Date: 2026-05-09
"""
BASE_ASGN = """ASSIGNMENT
Attorney Docket Number: LUM-0142US
WHEREAS, Assignor(s):
Sarah J. CHEN
Aditya Vikram MEHTA
are the inventors of the invention entitled MEMORY-EFFICIENT INFERENCE
FOR LARGE LANGUAGE MODELS described in U.S. Patent Application bearing
Attorney Docket No. LUM-0142US, hereby sell, assign, and transfer unto
Assignee, LUMINA AI, INC., the entire right, title and interest.
/Sarah J. Chen/  Date: 2026-05-09
/Aditya Vikram Mehta/  Date: 2026-05-09
"""
BASE_POA = """POWER OF ATTORNEY (PTO/AIA/82B)
Attorney Docket Number: LUM-0142US
Applicant: LUMINA AI, INC.
Customer Number: 142810
First Named Inventor Sarah J. CHEN
/Catherine A. Reyes/  Registration Number: 73415  Date: 2025-09-12
"""

DOC_KEYS = ['Specification', 'Drawings', 'ADS', 'Declaration', 'Assignment',
            'Power of Attorney', 'IDS', 'IDS Written Assertion']

def build_qc(**overrides):
    qc = PatentFilingQC(str(WORK))
    default_files = {
        "Specification": "Spec.pdf", "Drawings": "Drawings.pdf",
        "ADS": "ADS.pdf", "Declaration": "Decl.pdf",
        "Assignment": "Asgn.pdf", "Power of Attorney": "POA.pdf",
    }
    qc.report.files_found = overrides.get('files_found', default_files)
    folder = WORK
    # documents dict keeps all 8 canonical keys; absent ones → None
    qc.documents = {k: None for k in DOC_KEYS}
    for k, v in qc.report.files_found.items():
        qc.documents[k] = (folder / v) if v else None
    qc.ads_data = copy.deepcopy(overrides.get('ads_data', BASE_ADS))
    qc.ads_is_xfa = bool(qc.ads_data)
    qc.ads_text = qc._synthesize_ads_text_from_xfa(qc.ads_data) if qc.ads_data else (overrides.get('ads_text') or "")
    qc.spec_text = overrides.get('spec', BASE_SPEC)
    qc.drawings_text = overrides.get('drawings', BASE_DRAWINGS)
    qc.declaration_text = overrides.get('decl', BASE_DECL)
    qc.assignment_text = overrides.get('asgn', BASE_ASGN)
    qc.poa_text = overrides.get('poa', BASE_POA)
    qc.ids_text = overrides.get('ids_text', "")
    qc.ids_assertion_text = overrides.get('ids_assertion_text', "")
    qc.image_only_pages = overrides.get('image_only_pages', {})
    qc.unrecognized_files = overrides.get('unrecognized_files', [])
    return qc

def get_check(qc, cid):
    return next((i for i in qc.report.issues if i.check_id == cid), None)

def get_checks(qc, cid):
    return [i for i in qc.report.issues if i.check_id == cid]

# ============================================================
# Test runner
# ============================================================
TESTS = []

def test(label):
    def deco(fn):
        TESTS.append((label, fn))
        return fn
    return deco

def assert_severity(qc, cid, expected, label):
    qc.run_all_checks()
    issue = get_check(qc, cid)
    if not issue:
        print(f"  ❌ {label}: Check {cid} did not fire")
        return False
    if issue.severity != expected:
        print(f"  ❌ {label}: Check {cid} = {issue.severity.value} (expected {expected.value})")
        print(f"      msg: {issue.message[:90]}")
        return False
    return True

# ============================================================
# 1. Baseline
# ============================================================
@test("BASELINE: perfect filing → 0 CRITICAL")
def t():
    qc = build_qc()
    qc.run_all_checks()
    crit = [i for i in qc.report.issues if i.severity == Severity.CRITICAL]
    if crit:
        print(f"  ❌ Got {len(crit)} CRITICAL findings:")
        for i in crit: print(f"      [{i.check_id}] {i.message[:80]}")
        return False
    return True

# ============================================================
# 2. Failure-branch scenarios
# ============================================================
@test("F2.1: Check 1 → CRITICAL when inventor missing from decl")
def t():
    qc = build_qc(decl=BASE_DECL.replace('Aditya Vikram MEHTA', '').replace('/Aditya Vikram Mehta/', ''))
    return assert_severity(qc, 1, Severity.CRITICAL, "Check 1")

@test("F2.2: Check 2 → CRITICAL when title not in spec")
def t():
    qc = build_qc(spec=BASE_SPEC.replace('MEMORY-EFFICIENT INFERENCE FOR LARGE LANGUAGE MODELS', 'TOTALLY DIFFERENT'))
    return assert_severity(qc, 2, Severity.CRITICAL, "Check 2")

@test("F2.3: Check 3 → CRITICAL when docket mismatch")
def t():
    ads = copy.deepcopy(BASE_ADS); ads['docket_number'] = 'XXX-9999US'
    qc = build_qc(ads_data=ads)
    return assert_severity(qc, 3, Severity.CRITICAL, "Check 3")

@test("F2.4: Check 4 → CRITICAL when customer number mismatch")
def t():
    qc = build_qc(poa=BASE_POA.replace('142810', '999999'))
    return assert_severity(qc, 4, Severity.CRITICAL, "Check 4")

@test("F2.5: Check 5 → WARN when assignee not in assignment")
def t():
    qc = build_qc(asgn=BASE_ASGN.replace('LUMINA AI, INC.', 'TOTALLY DIFFERENT ENTITY'))
    return assert_severity(qc, 5, Severity.WARNING, "Check 5")

@test("F2.6: Check 7 → CRITICAL when decl count < ADS count")
def t():
    qc = build_qc(decl=BASE_DECL.split('I hereby declare')[0] + 'I hereby declare\n/Sarah J. Chen/\n')
    return assert_severity(qc, 7, Severity.CRITICAL, "Check 7")

@test("F2.7: Check 9 → CRITICAL when spec missing")
def t():
    qc = build_qc(spec='', files_found={
        "Specification": None, "Drawings": "Drawings.pdf", "ADS": "ADS.pdf",
        "Declaration": "Decl.pdf", "Assignment": "Asgn.pdf", "Power of Attorney": "POA.pdf"})
    return assert_severity(qc, 9, Severity.CRITICAL, "Check 9")

@test("F2.8: Check 9 → CRITICAL with confirm-prompt when only decl missing")
def t():
    qc = build_qc(decl='', files_found={
        "Specification": "Spec.pdf", "Drawings": "Drawings.pdf", "ADS": "ADS.pdf",
        "Declaration": None, "Assignment": "Asgn.pdf", "Power of Attorney": "POA.pdf"})
    qc.run_all_checks()
    issue = next((i for i in qc.report.issues if i.check_id == 9 and 'confirm' in i.message.lower()), None)
    if not issue:
        print(f"  ❌ No 'confirm' message in Check 9 findings"); return False
    return True

@test("F2.9: Check 17 → WARN when abstract over 150 words")
def t():
    long_abs = ' '.join(['word'] * 200) + '.'
    qc = build_qc(spec=BASE_SPEC.replace(
        'A system and method for memory-efficient inference dynamically selects per-layer precision and offloads cache tensors.',
        long_abs))
    return assert_severity(qc, 17, Severity.WARNING, "Check 17")

@test("F2.10: Check 13 → CRITICAL when claim missing")
def t():
    qc = build_qc(spec=BASE_SPEC.replace('2. The method of claim 1', '5. The method of claim 1'))
    return assert_severity(qc, 13, Severity.CRITICAL, "Check 13")

@test("F2.11: Check 27 → WARN when inventor missing country")
def t():
    ads = copy.deepcopy(BASE_ADS); ads['inventors'][0]['mail_country'] = ''
    qc = build_qc(ads_data=ads)
    return assert_severity(qc, 27, Severity.WARNING, "Check 27")

@test("F2.12: Check 32 → WARN when inventor not in declaration")
def t():
    qc = build_qc(decl=BASE_DECL.replace('Aditya Vikram MEHTA', '').replace('/Aditya Vikram Mehta/', ''))
    return assert_severity(qc, 32, Severity.WARNING, "Check 32")

@test("F2.13: Check 36 → CRITICAL when assignor missing")
def t():
    qc = build_qc(asgn=BASE_ASGN.replace('Aditya Vikram MEHTA', '').replace('/Aditya Vikram Mehta/', ''))
    return assert_severity(qc, 36, Severity.CRITICAL, "Check 36")

@test("F2.14: Check 50 → CRITICAL when placeholder text in spec")
def t():
    qc = build_qc(spec=BASE_SPEC.replace('A method comprising', '[INSERT CLAIM TEXT HERE]'))
    return assert_severity(qc, 50, Severity.CRITICAL, "Check 50")

@test("F2.15: Check 73 → WARN when attorney/correspondence customer # differ")
def t():
    ads = copy.deepcopy(BASE_ADS); ads['attorney_customer_number'] = '999999'
    qc = build_qc(ads_data=ads)
    return assert_severity(qc, 73, Severity.WARNING, "Check 73")

@test("F2.16: Check 35 → CRITICAL when decl date in future")
def t():
    qc = build_qc(decl=BASE_DECL.replace('Date: 2026-05-09', 'Date: 2099-01-01'))
    return assert_severity(qc, 35, Severity.CRITICAL, "Check 35")

@test("F2.17: Check 39 → CRITICAL when assignment date in future")
def t():
    future = '/Sarah J. Chen/  Date: 2099-01-01\n/Aditya Vikram Mehta/  Date: 2099-01-01'
    qc = build_qc(asgn=BASE_ASGN.replace('/Sarah J. Chen/  Date: 2026-05-09\n/Aditya Vikram Mehta/  Date: 2026-05-09', future))
    return assert_severity(qc, 39, Severity.CRITICAL, "Check 39")

@test("F2.18: Check 65 → INFO when foreign priority claim present")
def t():
    ads = copy.deepcopy(BASE_ADS)
    ads['foreign_priority_entries'] = [{'application_number': 'EP12345', 'country': 'EP', 'priority_date': '2024-01-01', 'access_code': ''}]
    qc = build_qc(ads_data=ads)
    return assert_severity(qc, 65, Severity.INFO, "Check 65")

@test("F2.19: Check 63 → WARN when priority in spec but not ADS")
def t():
    qc = build_qc(spec=BASE_SPEC + "\nThis application claims the benefit of priority to U.S. Provisional Application No. 63/000,000.")
    return assert_severity(qc, 63, Severity.WARNING, "Check 63")

# ============================================================
# 3. Suffix handling
# ============================================================
@test("S3.1: _xfa_surname returns last field (not 'Jr.' suffix)")
def t():
    qc = PatentFilingQC(str(WORK))
    if qc._xfa_surname({"first": "John", "last": "SMITH", "suffix": "Jr."}) != "SMITH":
        print("  ❌ Jr. case"); return False
    if qc._xfa_surname({"first": "Lukas", "last": "SCHMIDT", "suffix": "III"}) != "SCHMIDT":
        print("  ❌ III case"); return False
    return True

@test("S3.2: Check 1 uses surname (not suffix) for cross-doc match")
def t():
    ads = copy.deepcopy(BASE_ADS)
    ads['inventors'].append({
        "prefix": "", "first": "Lukas", "middle": "", "last": "SCHMIDT", "suffix": "III",
        "citizenship": "DE", "residency": "non-us-residency",
        "res_city": "Munich", "res_state": "", "res_country": "DE",
        "mail_address1": "Munich St", "mail_address2": "",
        "mail_city": "Munich", "mail_state": "", "mail_postcode": "80539", "mail_country": "DE"})
    decl = BASE_DECL + "Inventor 3\nLukas SCHMIDT III\n/Lukas Schmidt III/  Date: 2026-05-09\n"
    asgn = BASE_ASGN.replace('Aditya Vikram MEHTA', 'Aditya Vikram MEHTA\nLukas SCHMIDT III')
    qc = build_qc(ads_data=ads, decl=decl, asgn=asgn, drawings="")
    qc.run_all_checks()
    issue = get_check(qc, 1)
    if issue.severity != Severity.PASS:
        print(f"  ❌ Check 1 = {issue.severity.value}, expected PASS; {issue.message[:90]}")
        return False
    return True

# ============================================================
# 4. Missing-document fallbacks
# ============================================================
@test("M4.1: Spec-missing emits only IDs 13-21 (no phantoms 22-27)")
def t():
    qc = build_qc(spec='', files_found={
        "Specification": None, "Drawings": "Drawings.pdf", "ADS": "ADS.pdf",
        "Declaration": "Decl.pdf", "Assignment": "Asgn.pdf", "Power of Attorney": "POA.pdf"})
    qc.run_all_checks()
    ids = sorted({i.check_id for i in qc.report.issues
                  if i.message == "Specification not found" and i.category == "Specification"})
    if ids != list(range(13, 22)):
        print(f"  ❌ got {ids}, expected {list(range(13, 22))}"); return False
    return True

@test("M4.2: ADS-missing emits only (27, 28, 29, 31) — no phantom 30")
def t():
    qc = build_qc(ads_data=None, ads_text='', files_found={
        "Specification": "Spec.pdf", "Drawings": "Drawings.pdf", "ADS": None,
        "Declaration": "Decl.pdf", "Assignment": "Asgn.pdf", "Power of Attorney": "POA.pdf"})
    qc.run_all_checks()
    ids = sorted({i.check_id for i in qc.report.issues
                  if i.message == "ADS not found" and i.category == "ADS"})
    if ids != [27, 28, 29, 31]:
        print(f"  ❌ got {ids}, expected [27, 28, 29, 31]"); return False
    return True

@test("M4.3: POA-missing → no phantom 43")
def t():
    qc = build_qc(poa='', files_found={
        "Specification": "Spec.pdf", "Drawings": "Drawings.pdf", "ADS": "ADS.pdf",
        "Declaration": "Decl.pdf", "Assignment": "Asgn.pdf", "Power of Attorney": None})
    qc.run_all_checks()
    if 43 in {i.check_id for i in qc.report.issues}:
        print(f"  ❌ phantom Check 43 emitted"); return False
    return True

@test("M4.4: Decl-missing emits 32-35")
def t():
    qc = build_qc(decl='', files_found={
        "Specification": "Spec.pdf", "Drawings": "Drawings.pdf", "ADS": "ADS.pdf",
        "Declaration": None, "Assignment": "Asgn.pdf", "Power of Attorney": "POA.pdf"})
    qc.run_all_checks()
    ids = sorted({i.check_id for i in qc.report.issues
                  if i.category == "Declaration" and i.message == "Declaration not found"})
    if ids != list(range(32, 36)):
        print(f"  ❌ got {ids}, expected {list(range(32, 36))}"); return False
    return True

# ============================================================
# 5. self.documents path-based replacements
# ============================================================
@test("P5.1: self.documents dict has all 8 canonical keys, all None pre-load")
def t():
    qc = PatentFilingQC(str(WORK))
    if set(qc.documents.keys()) != set(DOC_KEYS):
        print(f"  ❌ keys mismatch: {set(qc.documents.keys())}"); return False
    if any(v is not None for v in qc.documents.values()):
        print(f"  ❌ values should be None pre-load"); return False
    return True

@test("P5.2: Check 58 (file size) reads from self.documents not folder.glob")
def t():
    folder = (WORK / "zerofile"); folder.mkdir(exist_ok=True)
    zero = folder / "zero.pdf"; zero.write_bytes(b'')
    other = folder / "other.pdf"; other.write_bytes(b'%PDF-1.4 ok')
    qc = PatentFilingQC(str(folder))
    qc.documents = {k: other for k in DOC_KEYS}
    qc.documents["Specification"] = zero
    qc.documents["IDS"] = None; qc.documents["IDS Written Assertion"] = None
    qc.report.files_found = {k: (v.name if v else None) for k, v in qc.documents.items()}
    for a in ['spec_text','drawings_text','ads_text','declaration_text','assignment_text','poa_text']:
        setattr(qc, a, "")
    qc.run_all_checks()
    issue = get_check(qc, 58)
    if not issue or issue.severity != Severity.CRITICAL or '0 bytes' not in issue.message:
        print(f"  ❌ Check 58 didn't catch 0-byte file: {issue.severity.value if issue else 'absent'}")
        return False
    return True

# ============================================================
# 6. Check 75 unrecognized files
# ============================================================
@test("U6.1: Check 75 fires WARNING with file names")
def t():
    qc = build_qc(unrecognized_files=[(WORK / "Notes.pdf"), (WORK / "Random.docx")])
    qc.run_all_checks()
    issue = get_check(qc, 75)
    if not issue or issue.severity != Severity.WARNING:
        print(f"  ❌ Check 75 = {issue.severity.value if issue else 'absent'}"); return False
    if 'Notes.pdf' not in (issue.details or '') or 'Random.docx' not in (issue.details or ''):
        print(f"  ❌ Filenames not in details"); return False
    return True

@test("U6.2: Check 75 does NOT fire when no unrecognized files")
def t():
    qc = build_qc(unrecognized_files=[])
    qc.run_all_checks()
    if get_check(qc, 75) is not None:
        print(f"  ❌ Check 75 fired unexpectedly"); return False
    return True

# ============================================================
# 7. Tightened signature checks
# ============================================================
@test("Sig7.1: Check 11 — form labels alone do NOT pass")
def t():
    return assert_severity(build_qc(decl="DECLARATION\nLegal name of inventor: Sarah CHEN\nsignature\n"),
                           11, Severity.WARNING, "Check 11 form-label-only")

@test("Sig7.2: Check 11 — /Name/ marker passes")
def t():
    return assert_severity(build_qc(decl="DECLARATION\n/Sarah J. Chen/  Date: 2026-05-09\n"),
                           11, Severity.PASS, "Check 11 /Name/")

@test("Sig7.3: Check 11 — /s/ Name marker passes")
def t():
    return assert_severity(build_qc(decl="DECLARATION\n/s/ Sarah Chen\n2026-05-09\n"),
                           11, Severity.PASS, "Check 11 /s/ Name")

@test("Sig7.4: Check 11 — image-only pages → INFO hedge")
def t():
    return assert_severity(build_qc(decl="DECLARATION\nForm body text only\n",
                                    image_only_pages={'Declaration': 2}),
                           11, Severity.INFO, "Check 11 image-only hedge")

@test("Sig7.5: Check 12 — /Name/ marker passes (assignment)")
def t():
    return assert_severity(build_qc(asgn="ASSIGNMENT\n/Sarah Chen/  Date: 2026-05-09\n"),
                           12, Severity.PASS, "Check 12 /Name/")

@test("Sig7.6: Check 12 — image-only pages → INFO hedge")
def t():
    return assert_severity(build_qc(asgn="ASSIGNMENT\nForm body text only\n",
                                    image_only_pages={'Assignment': 2}),
                           12, Severity.INFO, "Check 12 image-only hedge")

@test("Sig7.7: Check 44 — /Name/ marker passes")
def t():
    return assert_severity(build_qc(poa="POWER OF ATTORNEY\n/Catherine Reyes/  Date: 2025-09-12\n"),
                           44, Severity.PASS, "Check 44 /Name/")

@test("Sig7.8: Check 44 — image-only pages → INFO hedge")
def t():
    return assert_severity(build_qc(poa="POWER OF ATTORNEY\nForm body only\n",
                                    image_only_pages={'Power of Attorney': 1}),
                           44, Severity.INFO, "Check 44 image-only hedge")

# ============================================================
# 8. Check 8 residency
# ============================================================
@test("R8.1: Check 8 PASS when all inventors have residency in XFA")
def t():
    return assert_severity(build_qc(), 8, Severity.PASS, "Check 8 baseline")

@test("R8.2: Check 8 WARN when one inventor missing residency")
def t():
    ads = copy.deepcopy(BASE_ADS); ads['inventors'][1]['residency'] = ''
    return assert_severity(build_qc(ads_data=ads), 8, Severity.WARNING, "Check 8 missing residency")

@test("R8.3: Check 8 doesn't double-count 'US Residency' inside 'non-US Residency'")
def t():
    qc = PatentFilingQC(str(WORK))
    qc.documents = {k: None for k in DOC_KEYS}
    qc.report.files_found = {k: 'x.pdf' for k in DOC_KEYS}
    qc.ads_data = None
    qc.ads_text = "Inventor 1\nnon-US Residency\nInventor 2\nnon-US Residency\n"
    qc.spec_text = "BACKGROUND\nbody"; qc.drawings_text = ""; qc.declaration_text = ""
    qc.assignment_text = ""; qc.poa_text = ""; qc.ids_text = ""; qc.ids_assertion_text = ""
    qc.image_only_pages = {}; qc.unrecognized_files = []
    qc.run_all_checks()
    issue = get_check(qc, 8)
    if issue.severity != Severity.PASS:
        print(f"  ❌ Check 8 = {issue.severity.value}; {issue.message[:90]}"); return False
    return True

# ============================================================
# 9. Check 49 .docx fallback
# ============================================================
@test("D9.1: Check 49 → INFO when spec is .docx")
def t():
    folder = (WORK / "docx_spec"); folder.mkdir(exist_ok=True)
    docx = folder / "Spec.docx"; docx.write_bytes(b'PK\x03\x04 placeholder docx')
    qc = PatentFilingQC(str(folder))
    qc.documents = {k: None for k in DOC_KEYS}
    qc.documents["Specification"] = docx
    qc.report.files_found = {"Specification": "Spec.docx"}
    qc.spec_text = BASE_SPEC
    for a in ['drawings_text','ads_text','declaration_text','assignment_text','poa_text','ids_text','ids_assertion_text']:
        setattr(qc, a, "")
    qc.ads_data = None; qc.image_only_pages = {}; qc.unrecognized_files = []
    qc.run_all_checks()
    issue = get_check(qc, 49)
    if not issue or issue.severity != Severity.INFO:
        print(f"  ❌ Check 49 = {issue.severity.value if issue else 'absent'}, expected INFO"); return False
    if 'docx' not in issue.message.lower():
        print(f"  ❌ Check 49 message doesn't mention .docx: {issue.message[:80]}"); return False
    return True

# ============================================================
# 10. IDS checks 76-80 (NEW — PR #6)
# ============================================================
def _ids_xfa(sig="/Robert M. Holcomb/", reg="62198", us_docs=("10123456","10222333"),
             pubs=(), foreigns=(), npls=()):
    """Build a minimal XFA-like IDS text blob the check_ids parser understands."""
    parts = ["<ids-form>"]
    if sig is not None or reg is not None:
        parts.append("<electronic-signature><basic-signature><text-string>"
                     + (sig or "") + "</text-string></basic-signature>"
                     + (f"<registered-number>{reg}</registered-number>" if reg else "")
                     + "</electronic-signature>")
    if us_docs:
        parts.append("<us-patent-cite>" +
                     "".join(f"<us-doc-reference><doc-number>{d}</doc-number></us-doc-reference>"
                             for d in us_docs) + "</us-patent-cite>")
    if pubs:
        parts.append("<us-pub-appl-cite>" +
                     "".join(f"<us-doc-reference><doc-number>{d}</doc-number></us-doc-reference>"
                             for d in pubs) + "</us-pub-appl-cite>")
    if foreigns:
        parts.append("<us-foreign-document-cite>" +
                     "".join(f"<us-doc-reference><doc-number>{d}</doc-number></us-doc-reference>"
                             for d in foreigns) + "</us-foreign-document-cite>")
    if npls:
        parts.append("<us-nplcit>" + "".join(f"<text>{n}</text>" for n in npls) + "</us-nplcit>")
    parts.append("</ids-form>")
    return "".join(parts)

@test("IDS10.1: Check 76 N/A when no IDS present (optional)")
def t():
    qc = build_qc()  # no IDS in documents
    return assert_severity(qc, 76, Severity.N_A, "Check 76 no-IDS")

@test("IDS10.2: Check 76 INFO when IDS form present")
def t():
    qc = build_qc(ids_text=_ids_xfa())
    qc.documents['IDS'] = (WORK / "IDS.pdf")
    qc.run_all_checks()
    issue = get_check(qc, 76)
    if not issue or issue.severity != Severity.INFO:
        print(f"  ❌ Check 76 = {issue.severity.value if issue else 'absent'}"); return False
    return True

@test("IDS10.3: Check 77 PASS when signature + reg no present")
def t():
    qc = build_qc(ids_text=_ids_xfa(sig="/Robert M. Holcomb/", reg="62198"))
    qc.documents['IDS'] = (WORK / "IDS.pdf")
    return assert_severity(qc, 77, Severity.PASS, "Check 77 signed")

@test("IDS10.4: Check 77 WARN when signature absent")
def t():
    qc = build_qc(ids_text=_ids_xfa(sig="", reg=""))
    qc.documents['IDS'] = (WORK / "IDS.pdf")
    return assert_severity(qc, 77, Severity.WARNING, "Check 77 unsigned")

@test("IDS10.5: Check 77 WARN when only partial (sig, no reg)")
def t():
    qc = build_qc(ids_text=_ids_xfa(sig="/Robert M. Holcomb/", reg=""))
    qc.documents['IDS'] = (WORK / "IDS.pdf")
    return assert_severity(qc, 77, Severity.WARNING, "Check 77 partial")

@test("IDS10.6: Check 78 INFO with correct reference counts")
def t():
    qc = build_qc(ids_text=_ids_xfa(us_docs=("10123456","10222333","10999000"),
                                    pubs=("20210000001",), npls=("Smith et al. 2020",)))
    qc.documents['IDS'] = (WORK / "IDS.pdf")
    qc.run_all_checks()
    issue = get_check(qc, 78)
    if not issue or issue.severity != Severity.INFO:
        print(f"  ❌ Check 78 = {issue.severity.value if issue else 'absent'}"); return False
    # 3 US patents + 1 pub + 1 NPL = 5 references
    if '5 reference' not in issue.message:
        print(f"  ❌ Check 78 count wrong: {issue.message[:100]}"); return False
    return True

@test("IDS10.7: Check 78 WARN when no references filled")
def t():
    qc = build_qc(ids_text=_ids_xfa(us_docs=()))  # signature only, no cites
    qc.documents['IDS'] = (WORK / "IDS.pdf")
    return assert_severity(qc, 78, Severity.WARNING, "Check 78 empty")

@test("IDS10.8: Check 79 PASS when exactly one §1.17(v) box checked")
def t():
    qc = build_qc()
    qc.documents['IDS Written Assertion'] = (WORK / "WA.pdf")
    qc._extract_acroform_fields = lambda p: {"Check Box1": "/Yes", "Check Box2": "/Off",
                                             "Check Box3": "/Off", "Check Box4": "/Off",
                                             "Signature": "", "Name PrintTyped": ""}
    return assert_severity(qc, 79, Severity.PASS, "Check 79 one box")

@test("IDS10.9: Check 79 CRITICAL when multiple boxes checked")
def t():
    qc = build_qc()
    qc.documents['IDS Written Assertion'] = (WORK / "WA.pdf")
    qc._extract_acroform_fields = lambda p: {"Check Box1": "/Yes", "Check Box2": "/Yes",
                                             "Check Box3": "/Off", "Check Box4": "/Off"}
    return assert_severity(qc, 79, Severity.CRITICAL, "Check 79 multi-box")

@test("IDS10.10: Check 79 CRITICAL when no box checked")
def t():
    qc = build_qc()
    qc.documents['IDS Written Assertion'] = (WORK / "WA.pdf")
    qc._extract_acroform_fields = lambda p: {"Check Box1": "/Off", "Check Box2": "/Off",
                                             "Check Box3": "/Off", "Check Box4": "/Off"}
    return assert_severity(qc, 79, Severity.CRITICAL, "Check 79 no-box")

@test("IDS10.11: Check 80 PASS when WA signed (sig + name)")
def t():
    qc = build_qc()
    qc.documents['IDS Written Assertion'] = (WORK / "WA.pdf")
    qc._extract_acroform_fields = lambda p: {"Check Box1": "/Yes", "Signature": "/Robert Holcomb/",
                                             "Name PrintTyped": "Robert Holcomb",
                                             "Practitioner Registration Number if applicable": "62198",
                                             "Date": "2026-05-09"}
    return assert_severity(qc, 80, Severity.PASS, "Check 80 signed")

@test("IDS10.12: Check 80 WARN when WA unsigned")
def t():
    qc = build_qc()
    qc.documents['IDS Written Assertion'] = (WORK / "WA.pdf")
    qc._extract_acroform_fields = lambda p: {"Check Box1": "/Yes", "Signature": "",
                                             "Name PrintTyped": "", "Date": ""}
    return assert_severity(qc, 80, Severity.WARNING, "Check 80 unsigned")

# ============================================================
# 11. Compound-surname extraction (NEW — PR #9)
# ============================================================
@test("CS11.1: extract_inventors captures multi-word ALL-CAPS surname")
def t():
    qc = PatentFilingQC(str(WORK))
    text = "Suffix\nJohann JINGLEHEIMER SCHMIT\n"
    names = qc.extract_inventors(text)
    if not any('JINGLEHEIMER SCHMIT' in n for n in names):
        print(f"  ❌ compound surname truncated: {names}"); return False
    return True

@test("CS11.2: compound surname + suffix both captured")
def t():
    qc = PatentFilingQC(str(WORK))
    text = "Suffix\nMaria DE LA CRUZ III\n"
    names = qc.extract_inventors(text)
    hit = next((n for n in names if 'DE LA CRUZ' in n), None)
    if not hit:
        print(f"  ❌ compound surname not captured: {names}"); return False
    return True

@test("CS11.3: no-middle and full-middle names still work (no regression)")
def t():
    qc = PatentFilingQC(str(WORK))
    for txt, want in [("Suffix\nSarah CHEN\n", "CHEN"),
                      ("Suffix\nSarah Jane CHEN\n", "CHEN"),
                      ("Suffix\nAditya Vikram MEHTA\n", "MEHTA")]:
        names = qc.extract_inventors(txt)
        if not any(want in n for n in names):
            print(f"  ❌ {txt!r} → {names}"); return False
    return True

@test("CS11.4: middle-INITIAL name captured (e.g. 'Sarah J. CHEN')")
def t():
    qc = PatentFilingQC(str(WORK))
    names = qc.extract_inventors("Suffix\nSarah J. CHEN\n")
    if not any('CHEN' in n for n in names):
        print(f"  ❌ middle-initial name dropped: {names}"); return False
    # two middle initials
    names2 = qc.extract_inventors("Suffix\nSarah J. K. CHEN\n")
    if not any('CHEN' in n for n in names2):
        print(f"  ❌ two-initial name dropped: {names2}"); return False
    return True

@test("CS11.5: partial-extraction false positive fixed (mixed middle styles)")
def t():
    # Decl mixes a middle-initial name with a full-middle name. Before the fix,
    # only the full-middle name was captured → the other was falsely 'missing'.
    qc = PatentFilingQC(str(WORK))
    got = qc.extract_inventors("Suffix\nSarah J. CHEN\nSuffix\nAditya Vikram MEHTA\n")
    if not (any('CHEN' in n for n in got) and any('MEHTA' in n for n in got)):
        print(f"  ❌ both names not captured: {got}"); return False
    return True

# ============================================================
# 12. Rotated-drawings FIG handling (NEW — PR #6)
# ============================================================
@test("RD12.1: _drawings_text_extractable accepts reversed 'N.GIF' rotated labels")
def t():
    qc = PatentFilingQC(str(WORK))
    qc.drawings_text = "1.GIF some content 2.GIF more content"
    if not qc._drawings_text_extractable():
        print(f"  ❌ rotated (reversed) FIG labels not recognized as extractable"); return False
    return True

@test("RD12.2: _drawings_text_extractable accepts normal 'FIG. N' labels")
def t():
    qc = PatentFilingQC(str(WORK))
    qc.drawings_text = "FIG. 1 ... FIG. 2 ..."
    if not qc._drawings_text_extractable():
        print(f"  ❌ normal FIG labels not recognized"); return False
    return True

@test("RD12.3: _drawings_text_extractable False for image-only (no FIG labels)")
def t():
    qc = PatentFilingQC(str(WORK))
    qc.drawings_text = "just some scattered numbers 100 102 no fig markers"
    if qc._drawings_text_extractable():
        print(f"  ❌ image-only wrongly classified as extractable"); return False
    return True

# ============================================================
# 13. Conditional OCR name-recovery for signed forms (Declaration/Assignment)
#     Replaces PR #11's "always OCR" with: OCR only when the ADS inventor
#     names are missing from the extracted text, and REPLACE (not union).
# ============================================================
import qc_patent_filing as _qcmod

# A pdfplumber-style boilerplate decl that captured the form template but NOT
# the filled-in inventor names. Contains a token unique to this source so the
# anti-union test can prove the result isn't a concatenation.
_PDFPLUMBER_NONAMES = (
    "DECLARATION (37 CFR 1.63)  UNIQUE_PDFPLUMBER_TOKEN\n"
    "I hereby declare that I am an original inventor.\n"
    "Legal name of inventor: ____________________\n"
    "I hereby declare that I am an original inventor.\n"
    "Legal name of inventor: ____________________\n"
)
# An OCR-style text that recovered both inventor names (CHEN, MEHTA from BASE_ADS).
_OCR_WITHNAMES = (
    "DECLARATION (37 CFR 1.63)\n"
    "I hereby declare that I am an original inventor.\n"
    "Sarah J. CHEN   /Sarah J. Chen/  2026-05-09\n"
    "I hereby declare that I am an original inventor.\n"
    "Aditya Vikram MEHTA   /Aditya Vikram Mehta/  2026-05-09\n"
)

def _with_ocr(qc, ocr_return, calls=None):
    """Patch the module OCR flag on and stub _ocr_pdf_text to return a fixed
    string (recording calls). Returns a restore() callable."""
    prev = _qcmod.OCR_AVAILABLE
    _qcmod.OCR_AVAILABLE = True
    def stub(pdf_path, doc_type):
        if calls is not None:
            calls.append(doc_type)
        return ocr_return
    qc._ocr_pdf_text = stub
    return lambda: setattr(_qcmod, 'OCR_AVAILABLE', prev)

@test("CR13.1: native PDF with all names present → no OCR, text unchanged")
def t():
    qc = build_qc()
    calls = []
    restore = _with_ocr(qc, _OCR_WITHNAMES, calls)
    try:
        text_in = "Decl body Sarah J. CHEN ... Aditya Vikram MEHTA ... signed"
        out = qc._maybe_ocr_for_names(WORK / "Decl.pdf", "Declaration", text_in)
    finally:
        restore()
    if calls:
        print(f"  ❌ OCR was called despite names present: {calls}"); return False
    if out != text_in:
        print(f"  ❌ text changed unexpectedly"); return False
    return True

@test("CR13.2: scanned, names missing, OCR recovers them → returns OCR text")
def t():
    qc = build_qc()
    restore = _with_ocr(qc, _OCR_WITHNAMES)
    try:
        out = qc._maybe_ocr_for_names(WORK / "Decl.pdf", "Declaration", _PDFPLUMBER_NONAMES)
    finally:
        restore()
    if out != _OCR_WITHNAMES:
        print(f"  ❌ expected OCR text to replace boilerplate; got len={len(out)}"); return False
    return True

@test("CR13.3: names missing but OCR also misses → keep cleaner original")
def t():
    qc = build_qc()
    restore = _with_ocr(qc, "OCR garbage with no inventor names at all\n")
    try:
        out = qc._maybe_ocr_for_names(WORK / "Decl.pdf", "Declaration", _PDFPLUMBER_NONAMES)
    finally:
        restore()
    if out != _PDFPLUMBER_NONAMES:
        print(f"  ❌ should have kept original when OCR didn't help"); return False
    return True

@test("CR13.4: non-signed doc type (Specification) never triggers OCR")
def t():
    qc = build_qc()
    calls = []
    restore = _with_ocr(qc, _OCR_WITHNAMES, calls)
    try:
        out = qc._maybe_ocr_for_names(WORK / "Spec.pdf", "Specification", _PDFPLUMBER_NONAMES)
    finally:
        restore()
    if calls or out != _PDFPLUMBER_NONAMES:
        print(f"  ❌ Specification should not OCR (calls={calls})"); return False
    return True

@test("CR13.5: no ADS data → no trigger, text unchanged")
def t():
    qc = build_qc(ads_data=None, ads_text="")
    calls = []
    restore = _with_ocr(qc, _OCR_WITHNAMES, calls)
    try:
        out = qc._maybe_ocr_for_names(WORK / "Decl.pdf", "Declaration", _PDFPLUMBER_NONAMES)
    finally:
        restore()
    if calls or out != _PDFPLUMBER_NONAMES:
        print(f"  ❌ no-ADS should not OCR (calls={calls})"); return False
    return True

@test("CR13.6: OCR unavailable → text unchanged even if names missing")
def t():
    qc = build_qc()
    prev = _qcmod.OCR_AVAILABLE
    _qcmod.OCR_AVAILABLE = False
    try:
        out = qc._maybe_ocr_for_names(WORK / "Decl.pdf", "Declaration", _PDFPLUMBER_NONAMES)
    finally:
        _qcmod.OCR_AVAILABLE = prev
    if out != _PDFPLUMBER_NONAMES:
        print(f"  ❌ should be unchanged when OCR unavailable"); return False
    return True

@test("CR13.7: ANTI-UNION — result is a single source, not a concatenation")
def t():
    qc = build_qc()
    restore = _with_ocr(qc, _OCR_WITHNAMES)
    try:
        out = qc._maybe_ocr_for_names(WORK / "Decl.pdf", "Declaration", _PDFPLUMBER_NONAMES)
    finally:
        restore()
    # The pdfplumber-only token must be ABSENT (proves it's a replace, not union)
    if "UNIQUE_PDFPLUMBER_TOKEN" in out:
        print(f"  ❌ result contains both sources (union!)"); return False
    # Count-based checks must not double: "I hereby declare" appears 2x (OCR),
    # never 4x (would happen under union).
    n = len(re.findall(r'I hereby declare', out))
    if n != 2:
        print(f"  ❌ 'I hereby declare' count = {n}, expected 2 (union would give 4)"); return False
    return True

@test("CR13.8: partial — text has 1/2 names, OCR has 2/2 → OCR wins")
def t():
    qc = build_qc()
    text_1of2 = "Decl body Sarah J. CHEN present but co-inventor missing\n"
    restore = _with_ocr(qc, _OCR_WITHNAMES)
    try:
        out = qc._maybe_ocr_for_names(WORK / "Decl.pdf", "Declaration", text_1of2)
    finally:
        restore()
    if out != _OCR_WITHNAMES:
        print(f"  ❌ OCR (2/2) should replace text (1/2)"); return False
    return True

@test("CR13.9: _count_ads_inventors_present counts surnames correctly")
def t():
    qc = build_qc()
    if qc._count_ads_inventors_present(_OCR_WITHNAMES) != 2:
        print(f"  ❌ expected 2 in OCR text"); return False
    if qc._count_ads_inventors_present(_PDFPLUMBER_NONAMES) != 0:
        print(f"  ❌ expected 0 in boilerplate"); return False
    if qc._count_ads_inventors_present("only Sarah CHEN here") != 1:
        print(f"  ❌ expected 1 partial"); return False
    return True

@test("CR13.10: full pipeline still PASSES Check 1/7 on a clean baseline (no regression)")
def t():
    # Sanity: conditional-replace must not disturb the all-good baseline.
    qc = build_qc()
    qc.run_all_checks()
    c1 = get_check(qc, 1); c7 = get_check(qc, 7)
    if c1.severity not in (Severity.PASS, Severity.INFO):
        print(f"  ❌ Check 1 = {c1.severity.value}"); return False
    if c7.severity == Severity.CRITICAL:
        print(f"  ❌ Check 7 unexpectedly CRITICAL: {c7.message[:80]}"); return False
    return True

# ============================================================
# 14. PR #14 fixes: Check 13 footer-merge lookbehind, Check 28 POA regex
# ============================================================
# Spec with claims 1-4 where claim 3 is footer-merged against a docket that
# ENDS IN A LETTER ("...US3."). The "3" is preceded by 'S', not a digit, so the
# old (?<=\d) gap-fill missed it; (?<=\S) recovers it. Claim 3 must be interior
# (claim 4 present) because gap-fill only fills gaps below max(detected).
_SPEC_LETTER_MERGE = """LUM-0142US
MEMORY-EFFICIENT INFERENCE FOR LARGE LANGUAGE MODELS
BACKGROUND
[0001] Body.
BRIEF DESCRIPTION OF THE DRAWINGS
[0020] FIG. 1 is a diagram of a system 100.
[0021] FIG. 2 shows a controller 102.
DETAILED DESCRIPTION
[0030] FIG. 1 depicts a system 100 with controller 102.
CLAIMS
What is claimed is:
1. A method comprising measuring sensitivity and selecting precision.
2. The method of claim 1, wherein the measuring uses Hessian saliency.
LUM-0142US3. The method of claim 2, further comprising offloading cache entries.
4. The method of claim 3, wherein the offloading is dynamic.
ABSTRACT
A system and method for memory-efficient inference.
"""

@test("PR14.1: Check 13 recovers a claim footer-merged after a LETTER-ending docket")
def t():
    qc = build_qc(spec=_SPEC_LETTER_MERGE)
    qc.run_all_checks()
    issue = get_check(qc, 13)
    if not issue or issue.severity != Severity.PASS:
        print(f"  ❌ Check 13 = {issue.severity.value if issue else 'absent'} (expected PASS); "
              f"{issue.message[:90] if issue else ''}")
        return False
    return True

@test("PR14.2: Check 13 still CRITICAL when an interior claim is genuinely missing")
def t():
    # Claims 1, 2, 4 — no '3' anywhere. Widened lookbehind must not over-recover.
    spec = _SPEC_LETTER_MERGE.replace(
        "LUM-0142US3. The method of claim 2, further comprising offloading cache entries.\n", "")
    qc = build_qc(spec=spec)
    qc.run_all_checks()
    issue = get_check(qc, 13)
    if not issue or issue.severity != Severity.CRITICAL:
        print(f"  ❌ Check 13 = {issue.severity.value if issue else 'absent'} (expected CRITICAL)")
        return False
    return True

@test("PR14.3: Check 28 — two-column POA (title on next row) captures name only")
def t():
    # OCR-style stacked layout: label, then name, then the title of invention
    # on the immediately following line. The old \s+ tail swallowed the title.
    poa = ("POWER OF ATTORNEY (PTO/AIA/82B)\n"
           "First Named Inventor\n"
           "Sarah J. CHEN\n"
           "MEMORY-EFFICIENT INFERENCE FOR LARGE LANGUAGE MODELS\n"
           "Customer Number: 142810\n")
    qc = build_qc(poa=poa)
    qc.documents['Power of Attorney'] = None  # force poa_text path (skip OCR branch)
    qc.run_all_checks()
    issue = get_check(qc, 28)
    if not issue or issue.severity != Severity.PASS:
        print(f"  ❌ Check 28 = {issue.severity.value if issue else 'absent'} (expected PASS); "
              f"{issue.message[:120] if issue else ''}")
        return False
    if 'MEMORY' in (issue.message or '') or 'INFERENCE' in (issue.message or ''):
        print(f"  ❌ title words leaked into captured name: {issue.message[:120]}")
        return False
    return True

@test("PR14.4: Check 28 — single-line POA layout still works (no regression)")
def t():
    qc = build_qc()  # BASE_POA is single-line "First Named Inventor Sarah J. CHEN"
    qc.documents['Power of Attorney'] = None
    qc.run_all_checks()
    issue = get_check(qc, 28)
    if not issue or issue.severity != Severity.PASS:
        print(f"  ❌ Check 28 = {issue.severity.value if issue else 'absent'} (expected PASS)")
        return False
    return True

# ============================================================
# 15. Sequence-listing checks 82-85 (reapplied from PR #13, renumbered)
# ============================================================
def _seq_file(name, content):
    p = WORK / name
    p.write_text(content, encoding='utf-8')
    return p

_ST26_OK = ('<ST26SequenceListing>'
            '<SequenceTotalQuantity>1</SequenceTotalQuantity>'
            '<SequenceData sequenceIDNumber="1">ACGTACGTACGT</SequenceData>'
            '</ST26SequenceListing>')
_ST26_COUNT_MISMATCH = ('<ST26SequenceListing>'
            '<SequenceTotalQuantity>3</SequenceTotalQuantity>'
            '<SequenceData sequenceIDNumber="1">ACGT</SequenceData>'
            '</ST26SequenceListing>')

@test("SL15.1: non-biological filing → single Check 82 N/A, no 83/84/85")
def t():
    qc = build_qc()  # LLM patent — no biological terms
    qc.run_all_checks()
    c82 = get_check(qc, 82)
    if not c82 or c82.severity != Severity.N_A:
        print(f"  ❌ Check 82 = {c82.severity.value if c82 else 'absent'} (expected N/A gate)")
        return False
    if get_check(qc, 83) or get_check(qc, 84) or get_check(qc, 85):
        print(f"  ❌ downstream seq checks fired on a non-biological filing")
        return False
    return True

@test("SL15.2: SEQ ID NO in spec but no listing file → Check 82 CRITICAL")
def t():
    qc = build_qc(spec=BASE_SPEC + "\nThe polypeptide of SEQ ID NO: 1 is disclosed.\n")
    qc.sequence_listing_files = []
    qc.run_all_checks()
    c82 = get_check(qc, 82)
    if not c82 or c82.severity != Severity.CRITICAL:
        print(f"  ❌ Check 82 = {c82.severity.value if c82 else 'absent'} (expected CRITICAL)")
        return False
    return True

@test("SL15.3: .txt sequence listing only → Check 83 CRITICAL (ST.25 not accepted)")
def t():
    txt = _seq_file("seqlist.txt", "ST.25 plain text sequence listing\nSEQ ID NO 1\n")
    qc = build_qc(spec=BASE_SPEC + "\nThe polypeptide of SEQ ID NO: 1.\n")
    qc.sequence_listing_files = [txt]
    qc.run_all_checks()
    c83 = get_check(qc, 83)
    if not c83 or c83.severity != Severity.CRITICAL:
        print(f"  ❌ Check 83 = {c83.severity.value if c83 else 'absent'} (expected CRITICAL)")
        return False
    return True

@test("SL15.4: valid ST.26 XML → Check 82 PASS (present) + Check 83 PASS (format)")
def t():
    xml = _seq_file("seqlist.xml", _ST26_OK)
    qc = build_qc(spec=BASE_SPEC + "\nThe polypeptide of SEQ ID NO: 1.\n")
    qc.sequence_listing_files = [xml]
    qc.run_all_checks()
    c82, c83 = get_check(qc, 82), get_check(qc, 83)
    if not c82 or c82.severity != Severity.PASS:
        print(f"  ❌ Check 82 = {c82.severity.value if c82 else 'absent'} (expected PASS)")
        return False
    if not c83 or c83.severity != Severity.PASS:
        print(f"  ❌ Check 83 = {c83.severity.value if c83 else 'absent'} (expected PASS)")
        return False
    return True

@test("SL15.5: above-threshold sequence, no SEQ ID NO → Check 85 WARNING")
def t():
    spec = (BASE_SPEC + "\nThe polynucleotide construct comprises the sequence "
            "ACGTACGTACGTACGTACGT used in the assay.\n")  # 20 bases, no 'SEQ ID NO'
    qc = build_qc(spec=spec)
    qc.sequence_listing_files = []
    qc.run_all_checks()
    c85 = get_check(qc, 85)
    if not c85 or c85.severity != Severity.WARNING:
        print(f"  ❌ Check 85 = {c85.severity.value if c85 else 'absent'} (expected WARNING); "
              f"{c85.message[:80] if c85 else ''}")
        return False
    return True

@test("SL15.6: ST.26 XML count mismatch → Check 84 WARNING")
def t():
    xml = _seq_file("seqmismatch.xml", _ST26_COUNT_MISMATCH)
    qc = build_qc(spec=BASE_SPEC + "\nThe polypeptide of SEQ ID NO: 1.\n")
    qc.sequence_listing_files = [xml]
    qc.run_all_checks()
    c84 = get_check(qc, 84)
    if not c84 or c84.severity != Severity.WARNING:
        print(f"  ❌ Check 84 = {c84.severity.value if c84 else 'absent'} (expected WARNING); "
              f"{c84.message[:80] if c84 else ''}")
        return False
    return True

# ============================================================
# 16. Check 81 — priority application number verification (offline Branch B)
# ============================================================
# Force the offline branch (no ODP key) so these tests never hit the network.
os.environ.pop('USPTO_ODP_API_KEY', None)

def _ads_with_continuity(app_num='12/407,367'):
    ads = copy.deepcopy(BASE_ADS)
    ads['domestic_continuity_entries'] = [{
        'application_number': app_num, 'continuation_type': 'CON',
        'prior_application_number': '', 'date': '2009-03-19',
        'patent_number': '', 'issue_date': '',
    }]
    return ads

_SPEC_PRIORITY = (BASE_SPEC + "\nCROSS-REFERENCE TO RELATED APPLICATIONS\n"
                  "This application claims the benefit of U.S. Application No. 12/407,367.\n")

@test("PRI16.1: Check 81 PASS when spec priority app number matches ADS")
def t():
    qc = build_qc(ads_data=_ads_with_continuity('12/407,367'), spec=_SPEC_PRIORITY)
    qc.run_all_checks()
    c81 = [i for i in get_checks(qc, 81)]
    consistency = next((i for i in c81 if 'Consistency' in (i.check_name or '')), None)
    if not consistency or consistency.severity != Severity.PASS:
        print(f"  ❌ Check 81 consistency = "
              f"{consistency.severity.value if consistency else 'absent'} (expected PASS)")
        return False
    return True

@test("PRI16.2: Check 81 CRITICAL on a digit error (spec vs ADS mismatch)")
def t():
    # ADS says 12/407,367; spec says 12/407,368 (transposed/changed digit)
    spec_bad = _SPEC_PRIORITY.replace('12/407,367', '12/407,368')
    qc = build_qc(ads_data=_ads_with_continuity('12/407,367'), spec=spec_bad)
    qc.run_all_checks()
    consistency = next((i for i in get_checks(qc, 81)
                        if 'Consistency' in (i.check_name or '')), None)
    if not consistency or consistency.severity != Severity.CRITICAL:
        print(f"  ❌ Check 81 consistency = "
              f"{consistency.severity.value if consistency else 'absent'} (expected CRITICAL)")
        return False
    return True

@test("PRI16.3: Check 81 PASS/NA when no domestic continuity entries")
def t():
    qc = build_qc()  # BASE_ADS has empty domestic_continuity_entries
    qc.run_all_checks()
    c81 = get_checks(qc, 81)
    if not c81:
        print(f"  ❌ Check 81 did not fire at all"); return False
    if any(i.severity == Severity.CRITICAL for i in c81):
        print(f"  ❌ Check 81 unexpectedly CRITICAL with no continuity entries")
        return False
    return True

@test("PRI16.4: Check 81 emits manual verification links (Branch B, no key)")
def t():
    qc = build_qc(ads_data=_ads_with_continuity('12/407,367'), spec=_SPEC_PRIORITY)
    qc.run_all_checks()
    links = next((i for i in get_checks(qc, 81)
                  if 'Link' in (i.check_name or '')), None)
    if not links:
        print(f"  ❌ no verification-links issue emitted"); return False
    if 'patentcenter.uspto.gov' not in (links.details or ''):
        print(f"  ❌ Patent Center link missing from details"); return False
    return True

# ============================================================
# 17. --lightweight (filing-identity-only) mode
# ============================================================
def _run_lightweight(**overrides):
    qc = build_qc(**overrides)
    qc.report.skip_check_ids = set(LIGHTWEIGHT_SKIP_IDS)
    qc.run_all_checks()
    return qc

@test("LW17.1: lightweight mode drops ALL drafting-quality check IDs")
def t():
    qc = _run_lightweight()
    present = {i.check_id for i in qc.report.issues}
    leaked = present & LIGHTWEIGHT_SKIP_IDS
    if leaked:
        print(f"  ❌ skipped IDs leaked into report: {sorted(leaked)}"); return False
    return True

@test("LW17.2: full (default) mode DOES emit some of those drafting checks")
def t():
    qc = build_qc()
    qc.run_all_checks()
    present = {i.check_id for i in qc.report.issues}
    drafting_in_full = present & LIGHTWEIGHT_SKIP_IDS
    if not drafting_in_full:
        print(f"  ❌ no drafting checks fired in full mode — test fixture can't "
              f"distinguish the modes"); return False
    return True

@test("LW17.3: lightweight keeps file-identity checks (1, 13, 15)")
def t():
    qc = _run_lightweight()
    present = {i.check_id for i in qc.report.issues}
    for cid in (1, 13, 15):
        if cid not in present:
            print(f"  ❌ identity Check {cid} missing in lightweight mode"); return False
    return True

@test("LW17.4: lightweight still catches a file-identity CRITICAL")
def t():
    # Inventor missing from declaration → Check 1 CRITICAL (a kept identity check)
    qc = _run_lightweight(decl=BASE_DECL.replace('Aditya Vikram MEHTA', '')
                          .replace('/Aditya Vikram Mehta/', ''))
    c1 = get_check(qc, 1)
    if not c1 or c1.severity != Severity.CRITICAL:
        print(f"  ❌ Check 1 = {c1.severity.value if c1 else 'absent'} (expected CRITICAL)")
        return False
    # ...and the drafting checks are still suppressed
    if {i.check_id for i in qc.report.issues} & LIGHTWEIGHT_SKIP_IDS:
        print(f"  ❌ drafting checks leaked"); return False
    return True

@test("LW17.5: lightweight report has fewer issues than full mode")
def t():
    full = build_qc(); full.run_all_checks()
    lite = _run_lightweight()
    if len(lite.report.issues) >= len(full.report.issues):
        print(f"  ❌ lightweight={len(lite.report.issues)} not < full={len(full.report.issues)}")
        return False
    return True

@test("LW17.6: skip set is exactly the documented 17 IDs")
def t():
    if len(LIGHTWEIGHT_SKIP_IDS) != 17:
        print(f"  ❌ expected 17 skip IDs, got {len(LIGHTWEIGHT_SKIP_IDS)}: "
              f"{sorted(LIGHTWEIGHT_SKIP_IDS)}"); return False
    expected = {16,17,18,19,20,24,25,45,49,52,53,54,59,60,66,68,70}
    if set(LIGHTWEIGHT_SKIP_IDS) != expected:
        print(f"  ❌ skip set mismatch: {sorted(LIGHTWEIGHT_SKIP_IDS)}"); return False
    return True

# ============================================================
# 17. Image-only drawings classification fallback
#     (an image-only drawings PDF with no extractable text must not be dropped
#      to Unknown — that cascaded into 5 false "Drawings not found" CRITICALs)
# ============================================================
_qc_bare = PatentFilingQC(str(WORK))

@test("DR18.1: image-only file (no text), generic name → Drawings (low conf)")
def t():
    r = _qc_bare._maybe_unreadable_drawings("X000-0000US-001", "")
    if r != [("Drawings", 3.0)]:
        print(f"  ❌ got {r}"); return False
    return True

@test("DR18.2: filename '...-Drawings.pdf' → Drawings (the reported case)")
def t():
    r = _qc_bare._maybe_unreadable_drawings("X000-0000US-Drawings", "")
    if not r or r[0][0] != "Drawings":
        print(f"  ❌ got {r}"); return False
    return True

@test("DR18.3: 'Figures'/'Sheets' filename hints → Drawings even with some text")
def t():
    longish = "x" * 80  # >50 chars, so only the name hint can fire
    for stem in ("Figures", "FormalSheets", "drawing-set"):
        r = _qc_bare._maybe_unreadable_drawings(stem, longish)
        if not r or r[0][0] != "Drawings":
            print(f"  ❌ {stem!r} → {r}"); return False
    return True

@test("DR18.4: no hint + substantial readable text → None (don't grab it)")
def t():
    r = _qc_bare._maybe_unreadable_drawings(
        "CoverLetter", "Dear Sir, enclosed are the documents for this filing.")
    if r is not None:
        print(f"  ❌ should not classify a readable non-drawings file: {r}"); return False
    return True

@test("DR18.5: fallback only applies on Unknown — readable docs classify normally")
def t():
    # _classify_text on declaration text must NOT be Unknown, so the fallback
    # branch in _classify_file never runs for a readable document.
    res = _qc_bare._classify_text(
        "DECLARATION I hereby declare that I am an original inventor 37 CFR 1.63")
    if not res or res[0][0] == "Unknown":
        print(f"  ❌ declaration text classified Unknown: {res}"); return False
    return True

# ============================================================
# 18. Drawings scoring — figure-rich drawings with lots of callout text
#     (synthetic; reproduces a real filing where a 9-figure, 60+ reference-
#      numeral drawings PDF extracted 4k+ chars and was wrongly dropped to
#      Unknown because of a prose-length ceiling)
# ============================================================
def _figure_rich_drawings_text(figs=9, n_callouts=360):
    """Build drawings-style text: figure labels + a 'Page N of M' margin header
    + many reference numerals + dense uppercase part-label callouts, with NO
    specification structure. Comfortably exceeds the old 4000-char ceiling."""
    parts = []
    labels = ["AUTOMATED TEST FAILURES", "FIRMWARE SOURCE CODE REPOSITORY",
              "INTEGRATED DEVELOPMENT ENVIRONMENT", "SYSTEM UNDER TEST",
              "MACHINE LEARNING MODEL", "TEST FAILURE ANALYZER",
              "RENDERED TEST EXECUTION LOG", "VECTOR DATABASE",
              "DIAGNOSTIC ROUTING MODULE", "ERROR ORIGIN CLASSIFIER"]
    for fig in range(1, figs + 1):
        parts.append(f"Page {fig} of {figs}    (Docket No.: X000-0000US)")
        for i in range(n_callouts // figs):
            parts.append(labels[i % len(labels)])
            parts.append(str(100 + (i * 2) % 900))   # reference numeral on its own line
        parts.append(f"FIG. {fig}")
    return "\n".join(parts)

@test("DR19.1: figure-rich drawings with 4k+ chars of callouts → Drawings")
def t():
    text = _figure_rich_drawings_text()
    assert len(re.sub(r"\s+", " ", text)) > 4000, "fixture should exceed old ceiling"
    bt, bs, scores = _qc_bare._score_text(text)
    if bt != "Drawings":
        print(f"  ❌ classified {bt} (score {bs}); Drawings={scores.get('Drawings')}")
        return False
    return True

@test("DR19.2: 'Page N of M' margin header recognized as a sheet signal")
def t():
    # Sparse text, only the margin header + a couple numerals (no FIG label).
    text = "Page 1 of 7\n(Docket No.: X000-0000US)\n102\n104\n"
    bt, bs, scores = _qc_bare._score_text(text)
    if scores.get("Drawings", 0) < 3:
        print(f"  ❌ Drawings score too low: {scores.get('Drawings')}"); return False
    return True

@test("DR19.3: a real spec that references figures is NOT misclassified as Drawings")
def t():
    # Spec has FIG. mentions but also claim/abstract/background structure.
    bt, bs, scores = _qc_bare._score_text(BASE_SPEC)
    if bt == "Drawings":
        print(f"  ❌ spec misclassified as Drawings; scores={scores}"); return False
    if scores.get("Specification", 0) < 5:
        print(f"  ❌ spec didn't score as Specification: {scores}"); return False
    return True

@test("DR19.4: figure-label regex accepts 'FIG 1' / 'FIGURE 1' (no period)")
def t():
    for variant in ("FIG 1", "FIGURE 1", "Figs. 2"):
        text = f"Page 1 of 3\n{variant}\nWIDGET ASSEMBLY\n102\nFRAME\n104\n{variant}\n"
        # add a second figure label so fig_count >= 2 path is exercised
        text += "FIG 2\nGEAR\n106\n"
        _, _, scores = _qc_bare._score_text(text)
        if scores.get("Drawings", 0) < 3:
            print(f"  ❌ {variant!r} not recognized: Drawings={scores.get('Drawings')}")
            return False
    return True

# ============================================================
# 19. Figure counting — sub-figures + plural "FIGS." (Check 61)
# ============================================================
_FC_SPEC = (
    "Title of invention\nBRIEF DESCRIPTION OF THE DRAWINGS\n"
    "FIG. 1 is a system diagram. FIG. 2 is a flow chart. FIG. 3 shows a module. "
    "FIGS. 4A and 4B are flow diagrams. FIG. 5 is a timeline. FIG. 6 is a graph. "
    "FIG. 7 is a circuit. FIG. 8 is a layout.\nDETAILED DESCRIPTION\nbody text.\n"
)
_FC_DRAW = "FIG. 1\nFIG. 2\nFIG. 3\nFIG. 4A\nFIG. 4B\nFIG. 5\nFIG. 6\nFIG. 7\nFIG. 8\n"

@test("FC20.1: sub-figures counted distinctly — 4A and 4B are two figures")
def t():
    ids = _qc_bare._extract_figure_identities(_FC_DRAW)
    if ids != ["1", "2", "3", "4A", "4B", "5", "6", "7", "8"]:
        print(f"  ❌ identities = {ids}"); return False
    if len(ids) != 9:
        print(f"  ❌ count = {len(ids)} (expected 9)"); return False
    return True

@test("FC20.2: plural 'FIGS. 4A and 4B' enumeration captures both 4A and 4B")
def t():
    subs = _qc_bare._extract_subfigures("FIGS. 4A and 4B are flow diagrams")
    if subs != {(4, "A"), (4, "B")}:
        print(f"  ❌ subfigures = {subs}"); return False
    return True

@test("FC20.3: adjacent 'FIG. 1\\nFIG. 2\\n...' — no alternating figures dropped")
def t():
    nums = _qc_bare._extract_figure_numbers(_FC_DRAW)
    if nums != [1, 2, 3, 4, 5, 6, 7, 8]:
        print(f"  ❌ base nums = {nums} (adjacency bug?)"); return False
    return True

@test("FC20.4: Check 61 PASS — spec 9 figs == drawings 9 figs (the reported case)")
def t():
    qc = build_qc(spec=_FC_SPEC, drawings=_FC_DRAW)
    qc.run_all_checks()
    issue = get_check(qc, 61)
    if not issue or issue.severity != Severity.PASS:
        print(f"  ❌ Check 61 = {issue.severity.value if issue else 'absent'} "
              f"(expected PASS); {issue.message[:100] if issue else ''}")
        return False
    if "9 figures" not in issue.message:
        print(f"  ❌ message should report 9 figures: {issue.message[:100]}"); return False
    return True

@test("FC20.5: 'CONFIGURATION' is not mistaken for a figure")
def t():
    if _qc_bare._extract_figure_numbers("the CONFIGURATION 3 settings"):
        print("  ❌ CONFIG matched as a figure"); return False
    return True

# ============================================================
# 20. Short-surname matching — single-letter family initials (e.g. "Manoj
#     Kumar P") must not match every stray letter (Check 1 false negative)
# ============================================================
@test("SS21.1: _surname_present — single-letter surname needs a standalone token")
def t():
    qc = _qc_bare
    if not qc._surname_present("P", "MANOJ KUMAR P SIGNED HERE"):
        print("  ❌ standalone 'P' not matched"); return False
    if qc._surname_present("P", "SPECIFICATION DEPLOYMENT PROCESS"):
        print("  ❌ 'P' inside words matched (spurious)"); return False
    return True

@test("SS21.2: _surname_present — normal surnames keep substring behavior")
def t():
    qc = _qc_bare
    if not qc._surname_present("CHEN", "SARAH J CHEN"):
        print("  ❌ CHEN not matched"); return False
    if qc._surname_present("MEHTA", "ONLY CHEN HERE"):
        print("  ❌ absent MEHTA matched"); return False
    return True

def _ads_single_letter_surname():
    ads = copy.deepcopy(BASE_ADS)
    ads["inventors"] = [{"prefix": "", "first": "Manoj", "middle": "Kumar",
                         "last": "P", "suffix": "", "citizenship": "IN",
                         "residency": "non-us-residency", "res_city": "Chennai",
                         "res_state": "", "res_country": "IN",
                         "mail_address1": "1 St", "mail_address2": "",
                         "mail_city": "Chennai", "mail_state": "TN",
                         "mail_postcode": "600001", "mail_country": "IN"}]
    return ads

@test("SS21.3: Check 1 PASS when 'Manoj Kumar P' appears (standalone P)")
def t():
    decl = ("DECLARATION (37 CFR 1.63)\nI hereby declare that I am an original "
            "inventor.\nInventor 1\nManoj Kumar P\n/Manoj Kumar P/  Date: 2026-05-09\n"
            + "padding line.\n" * 10)
    qc = build_qc(ads_data=_ads_single_letter_surname(), decl=decl, asgn=decl)
    qc.run_all_checks()
    issue = get_check(qc, 1)
    if not issue or issue.severity != Severity.PASS:
        print(f"  ❌ Check 1 = {issue.severity.value if issue else 'absent'} (expected PASS); "
              f"{issue.message[:80] if issue else ''}")
        return False
    return True

@test("SS21.4: Check 1 CRITICAL when the 'P' inventor is genuinely missing")
def t():
    # Declaration has 'p' inside many words but never the inventor's name nor a
    # standalone 'P'. Old substring match would falsely PASS; the fix flags it.
    decl = ("DECLARATION (37 CFR 1.63)\nThe specification describes a deployment "
            "pipeline supporting application processing.\n" + "padding text.\n" * 12)
    qc = build_qc(ads_data=_ads_single_letter_surname(), decl=decl, asgn=decl)
    qc.run_all_checks()
    issue = get_check(qc, 1)
    if not issue or issue.severity != Severity.CRITICAL:
        print(f"  ❌ Check 1 = {issue.severity.value if issue else 'absent'} (expected CRITICAL)")
        return False
    return True

# ============================================================
# 13. Biological gate & sequence-listing false positives
#     (reversed drawing text "AND"→"DNA"; common words as nucleotides)
# ============================================================
@test("BIO.gate-reversed: reversed 'AND' ('DNA') in drawings does NOT gate biological")
def _():
    # Rotated landscape drawing pages extract in reverse order, so
    # "…STORAGE AND INDEXING…" comes out "…GNIXEDNI DNA EGAROTS…".
    qc = build_qc(spec="A software method for routing queries among agents.",
                  drawings="GNIXEDNI DNA EGAROTS 104 GROUND GENERATOR ENGINE",
                  ads_data=None, ads_text="")
    qc.sequence_listing_files = []
    if qc._is_biological_application():
        print("  ❌ bare/reversed DNA triggered the biological gate"); return False
    return True

@test("BIO.gate-real: genuine biological phrases still gate biological")
def _():
    for txt in ("The DNA sequence encodes a protein.",
                "an isolated nucleic acid molecule",
                "SEQ ID NO: 1",
                "an mRNA transcript was measured",
                "genomic DNA was extracted"):
        qc = build_qc(spec=txt, drawings="", ads_data=None, ads_text="")
        qc.sequence_listing_files = []
        if not qc._is_biological_application():
            print(f"  ❌ failed to gate real bio text: {txt!r}"); return False
    return True

@test("BIO.82: non-bio filing → Check 82 N/A and Check 85 does not run")
def _():
    qc = build_qc(spec="LOW-LATENCY MULTI-CORE systems for language models.",
                  drawings="STRUCTURED TEXT LANGUAGE MODEL ATTACH VERSION TAG",
                  ads_data=None, ads_text="")
    qc.sequence_listing_files = []
    qc.check_sequence_listing()
    ids = {i.check_id: i for i in qc.report.issues}
    if 82 not in ids or ids[82].severity != Severity.N_A:
        print(f"  ❌ Check 82 = {ids[82].severity if 82 in ids else 'absent'}"); return False
    if 85 in ids:
        print("  ❌ Check 85 ran on a non-biological filing"); return False
    return True

@test("BIO.85-nuc: lowercase words (language/structure) are not nucleotide hits")
def _():
    # Force the gate open with a real phrase, then confirm the nucleotide
    # scanner ignores ordinary lowercase English words in the context window.
    bio = ("An isolated nucleic acid is described. The language model "
           "processes the structured representation accurately.")
    qc = build_qc(spec=bio, drawings="", ads_data=None, ads_text="")
    qc.sequence_listing_files = []
    qc.check_sequence_listing()
    c85 = next((i for i in qc.report.issues if i.check_id == 85), None)
    if not c85:
        print("  ❌ Check 85 absent (gate should be open)"); return False
    blob = (c85.message + " " + (c85.details or "")).lower()
    if "nucleotide" in blob:
        print(f"  ❌ false nucleotide hit from prose: {blob[:120]}"); return False
    return True

@test("BIO.85-real: a genuine uppercase inline sequence IS detected")
def _():
    bio = "The nucleic acid comprises the sequence ATGGCATGCATGCAAT as shown."
    qc = build_qc(spec=bio, drawings="", ads_data=None, ads_text="")
    qc.sequence_listing_files = []
    qc.check_sequence_listing()
    c85 = next((i for i in qc.report.issues if i.check_id == 85), None)
    blob = (c85.message + " " + (c85.details or "")).lower() if c85 else ""
    if "nucleotide" not in blob:
        print(f"  ❌ real 16-base sequence missed: {blob[:120]}"); return False
    return True

# ============================================================
# Run
# ============================================================
print("="*80); print(f"COMPREHENSIVE TEST SUITE — {len(TESTS)} tests"); print("="*80)
passed = 0; failed = 0; fail_labels = []
for label, fn in TESTS:
    try:
        ok = fn()
    except Exception as e:
        import traceback
        print(f"  💥 {label}: EXCEPTION {type(e).__name__}: {e}")
        traceback.print_exc()
        ok = False
    if ok:
        print(f"  ✓ {label}"); passed += 1
    else:
        failed += 1; fail_labels.append(label)
print()
print("="*80)
print(f"RESULTS: {passed} passed, {failed} failed (out of {len(TESTS)})")
print("="*80)
if fail_labels:
    print("Failures:")
    for f in fail_labels: print(f"  - {f}")

# Exit non-zero on any failure so CI (and `python tests/...` locally) fails.
sys.exit(1 if failed else 0)
