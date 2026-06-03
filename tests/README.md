# Tests

## `test_qc_patent_filing.py`

A self-contained regression suite for `scripts/qc_patent_filing.py`. It drives
the checks directly against in-memory fixtures (synthetic ADS/spec/declaration/
assignment/POA/IDS text) rather than real PDFs, so it runs in well under a
second with no external dependencies beyond the script's own imports.

Run it:

```bash
python3 tests/test_qc_patent_filing.py
```

It is location-independent (resolves `scripts/` relative to its own path) and
creates/cleans up its own temp working directory, so it can be run from any cwd.

### Coverage

- Baseline: a complete, correct filing produces zero CRITICAL findings.
- Failure branches: each major check's CRITICAL/WARN path.
- Suffix handling: surname comes from the XFA `last` field, not `split()[-1]`.
- Missing-document fallbacks emit only real check IDs (no phantom 26/30/43).
- `self.documents` path lookups (not filename globs).
- Unrecognized-files surfacing (Check 75).
- Tightened signature heuristics (Checks 11/12/44).
- Residency check (Check 8) — no `US`/`non-US` substring double-count.
- `.docx` spec fallback (Check 49) → INFO, not a false PASS.
- IDS checks 76–80 (form recognition, signature, reference counts, written
  assertion checkbox selection and signature).
- Compound-surname and middle-initial inventor extraction.
- Rotated-drawings (`N.GIF`) FIG-label handling.

Add a new test by writing a `@test("label")` function that returns `True` on
pass; it is auto-registered and run.
