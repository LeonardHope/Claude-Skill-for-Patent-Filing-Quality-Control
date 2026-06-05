# app/ — interactive evidence-linked QC (v2)

This directory holds the **v2** work planned in [`../DESIGN.md`](../DESIGN.md):
an interactive, evidence-linked review surface where every check links to the
source-document region that produced it. It lives on the `next` branch and does
**not** affect the shipping skill on `main`.

## The real viewer (`server.py`) — Phase 2

Runs the actual engine through `core` (checks emit their own evidence) and serves
an interactive viewer. All processing is local — nothing is uploaded.

Intended workflow (attorneys / paralegals, at filing time): launch the tool,
**open the filing folder**, and the QC runs and shows its results.

### For firm users — double-click launcher (per-desktop)

From the project folder:

- **Windows:** double-click **`Patent Filing QC.bat`**
- **macOS:** double-click **`Patent Filing QC.command`**

The first launch sets up a private Python environment and installs dependencies
(needs internet that one time, ~1 min); every launch after is instant and works
offline. The browser opens automatically. Closing the window stops the tool.
Requires Python 3 installed (python.org). OCR-based checks additionally need the
system `tesseract` + `poppler` binaries — without them the tool still runs and
all other checks work; only the OCR-dependent checks are skipped.

### For developers

```bash
python3 app/server.py                       # then open the printed URL
python3 app/server.py /path/to/filing/folder  # pre-select a folder, skip landing
```

On the landing screen, **Open filing folder…** launches a native OS folder
chooser on the machine running the server (PowerShell dialog on Windows,
`osascript` on macOS — both run as a subprocess, never an in-process GUI
toolkit). A paste-a-path field is also there for shared / hosted setups. The
server prefers port 8000 and falls back to a free port if it's taken.

> Restart the server after editing `server.py` — a running instance keeps the
> old routes (a stale process is why `/api/pick` would 404).

- Left: every check, grouped by severity, with a **Receipts** filter.
- Click a receipt → the source region highlights in the PDF (`pdf_region`), or a
  structured data card appears for ADS fields (`xfa_field`).
- Migrated checks emit native receipts wherever they can locate the source —
  inventor names (highlighted per inventor in the Declaration), attorney docket,
  assignee, drawing docket label, etc. Checks still in the engine (OCR / image /
  network — see `core/checks/__init__.py`) appear without a locator for now.
- **Re-run** (header) re-runs the checks after you edit files; **Open another
  folder** returns to the landing screen. Results are cached per folder, so
  opening a document never re-runs QC.

Engine + schema live in [`../core/`](../core); tests in
[`../tests/test_core.py`](../tests/test_core.py).

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
