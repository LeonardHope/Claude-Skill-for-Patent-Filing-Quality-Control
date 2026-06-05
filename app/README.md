# app/ — interactive evidence-linked QC (v2)

This directory holds the **v2** work planned in [`../DESIGN.md`](../DESIGN.md):
an interactive, evidence-linked review surface where every check links to the
source-document region that produced it. It lives on the `next` branch and does
**not** affect the shipping skill on `main`.

## `spike/` — Phase-0 de-risking spike (mostly throwaway)

The smallest end-to-end slice that proves the riskiest parts of the architecture
before any large refactor. It covers **both** evidence rendering paths:

- **Check 1 (Inventor Names)** → `pdf_region` evidence: locate an inventor
  surname in the real declaration PDF and highlight its bounding box.
- **Check 3 (Attorney Docket)** → `xfa_field` evidence: a structured data card
  (no PDF geometry — the point of that locator type).

### Run it

```bash
python3 app/sample/make_sample.py        # generate the sample declaration PDF (once)
python3 app/spike/serve.py               # serves http://localhost:8000, opens a browser
```

Click a check (or one of its receipts) on the left; the viewer on the right
either highlights the region in the PDF or shows the data card.

### What it proves (status: ✅ validated)

- **Coordinate capture** — `spike/locate.py` maps matched text → page + bbox via
  pdfplumber `extract_words()`. Verified pixel-perfect: the box lands exactly on
  "CHEN" on page 1 and "MEHTA" on page 2 (rendered-and-inspected).
- **The schema** — `spike/result_builder.py` emits the `Result` + `Evidence`
  shape from DESIGN.md §5, including both `pdf_region` and `xfa_field` locators.
- **Delivery** — `spike/serve.py` is a stdlib-only local server (JSON API + PDF
  bytes); the frontend (`static/index.html`) renders with PDF.js and overlays
  the highlight using `point × scale`.

### Pieces

| File | Role | Becomes (real build) |
|---|---|---|
| `spike/locate.py` | text → page + bbox | `core/locate.py` (the single shared locator — DESIGN §4.1) |
| `spike/result_builder.py` | hand-built 2-check Result | output of `core/` running all checks |
| `spike/serve.py` | stdlib JSON+PDF server | `frontends/app/` server |
| `spike/static/index.html` | PDF.js viewer + checks panel | `frontends/app/` frontend |
| `sample/` | generated demo filing | replaced by real filings |

### Known shortcuts (because it's a spike)

- PDF.js is loaded from a CDN; the real build bundles it (offline / firm use).
- The ADS is simulated as structured data (real build extracts XFA).
- Two checks only, hand-built; the real path is the `core/` engine + evidence.
