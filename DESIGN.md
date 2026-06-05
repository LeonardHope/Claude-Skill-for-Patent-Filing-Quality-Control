# Design: Interactive, Evidence-Linked Patent Filing QC

Status: **Draft / planning** · Last updated: 2026-06-06

This document describes the planned evolution of the Patent Filing QC tool from
a static, single-file HTML report into an **interactive, evidence-linked
document review surface** — without abandoning the existing skill.

---

## 1. Vision

Turn the report from a *list of verdicts* into something where every verdict is
traceable to the exact data that produced it, with the source documents right
there. Four user-facing capabilities:

1. **Receipts** — for every check (PASS *and* FAIL), the user can see the
   underlying data the check used to reach its verdict.
2. **In-report document review** — read the filing documents inside the report;
   no jumping back and forth to a separate PDF viewer.
3. **Integrated PDF viewer** — the actual filing PDFs render in the report.
4. **Click-to-locate** — clicking a check highlights the relevant region(s) of
   the relevant document(s) in the viewer.

## 2. Constraints (these drive the architecture)

- **Confidentiality is paramount.** Filings are often unpublished and under
  attorney–client privilege / pre-filing secrecy. **Documents must never leave
  firm control** — no third-party SaaS, no uploading to servers we operate.
  Processing stays local or on firm-controlled infrastructure. (The only
  outbound call in the whole tool is the *optional* USPTO ODP lookup in Check
  81; everything else is offline.)
- **Users are non-technical.** Lawyers and paralegals will not run a script from
  a terminal. The end-user experience must be click-to-open.
- **Multi-user within a firm.** Several people need to use it; deployment must
  scale beyond one technical operator.
- **Don't fork the engine.** The check engine is the crown jewels and must have
  a single source of truth. (See §6 — a second repo or a copied engine would
  recreate the stale-divergence problem this project already lived through.)

## 3. Delivery model

**A local web app**: a Python core that exposes a JSON API + serves the filing
PDFs, and a browser frontend that renders them with [PDF.js] and links checks to
document regions.

This is chosen because it is the only option that is **deployment-flexible from
a single codebase**:

| Deploy shape | How it runs | Good for |
|---|---|---|
| **Per-desktop** | A one-click launcher (e.g. PyInstaller) bundles Python, starts the local server, opens the browser. All processing stays on the user's machine. | Strongest privacy; no firm server needed. |
| **Internal-hosted** | Deployed once on a firm-controlled box; users hit an internal URL. Central updates, zero per-user install. | Lowest per-user friction; docs transit firm-owned infra only. |

The deploy shape can be **decided later** (at packaging time) without changing
application code. Rejected alternatives:

- **Self-contained HTML** (today's model, extended): can't do true multi-user
  interactivity, and embedding PDFs as base64 balloons files to 30–50 MB (past
  email limits). Kept as the *skill's* lightweight output, not the app.
- **Desktop app (Electron/Tauri)**: locks into per-desktop install and adds
  code-signing / auto-update burden. Remains a *later* option layered over the
  same web frontend.

[PDF.js]: https://mozilla.github.io/pdf.js/

## 4. Architecture

One repository, restructured into a shared **core engine** plus **frontends**
that consume it.

```
patent-filing-qc/
├── core/
│   ├── extract.py        # pdfplumber / PyPDF2 / OCR / XFA → text + word bboxes
│   ├── classify.py       # content-based file classification
│   ├── result.py         # the Result + Evidence schema (THE CONTRACT)
│   └── checks/
│       ├── cross_document.py   ├── common_errors.py
│       ├── specification.py     ├── file_quality.py
│       ├── drawings.py          ├── cross_references.py
│       ├── ads.py               ├── priority.py
│       ├── declaration.py       ├── final_quality.py
│       ├── assignment.py        ├── ids.py
│       ├── power_of_attorney.py └── sequence_listing.py
│       └── formatting.py
├── frontends/
│   ├── report/           # CLI → self-contained HTML report (today's product)
│   └── app/              # the --serve web app: JSON API + PDF.js frontend
├── tests/
└── .github/workflows/
```

Three principles:

1. **Engine produces data, not HTML.** `core` returns a JSON-serializable
   `Result` (§5). The HTML report is just one consumer; the app's API is
   another. One engine, two faces.
2. **One module per check category.** Splitting the ~78 checks out of the
   6,000-line monolith both enables the app and permanently removes the
   "every change collides in one giant file" problem.
3. **DRY — shared primitives, not copy-paste.** Cross-cutting logic lives in
   one place and is imported, never duplicated. See §4.1.

### 4.1 Shared primitives (DRY)

The monolith currently repeats logic that should be single-sourced; the
refactor is the moment to extract it. Concrete targets, grounded in real
duplication in `qc_patent_filing.py` today:

| Primitive | Why (current duplication) |
|---|---|
| `core/patterns.py` — inventor-name regex, signature markers (`/s/`, `/Name/`), date formats, docket shapes | The inventor-name pattern is **copy-pasted in 5 places** today; signature-marker logic repeats across Checks 11/12/44. One constant each. |
| `core/locate.py` — `locate(doc, phrase) -> Locator` | **The single biggest new DRY risk.** Mapping matched text → page + bbox must be ONE helper used by every `pdf_region` evidence, never reimplemented per check. |
| `core/names.py` — normalize, surname extraction, "is inventor present in text?" | The presence predicate is mirrored between Check 1 and `_count_ads_inventors_present`; `_normalize_for_compare` is used widely. |
| `core/extract.py` — one OCR path | Already partly done (`_ocr_pdf_text` was factored out during the conditional-OCR work); keep it single-sourced. |
| Date-logic helper | Declaration-date (35) and assignment-date (39) checks are parallel implementations. |
| Missing-document fallback helper | Each missing-doc case emits a range of IDs with near-identical `add_issue` loops. |
| Evidence emission + rendering | Checks emit structured `Evidence` through **one** path; **one** renderer formats it per frontend — replacing today's per-check hand-formatted `details` strings. The evidence model is itself a DRY win: presentation logic stops being copy-pasted into every check. |

Guardrail: when a check needs logic a sibling already has, extract a shared
helper rather than copying it. The regression suite makes that safe.

## 5. The contract: Result + Evidence schema

This schema is the seam between the engine and every frontend, and it is where
the **receipts** live. Sketch (subject to refinement during the spike):

```jsonc
// Result — one per run
{
  "folder": "/path/to/filing",
  "generated_at": "2026-06-06T12:00:00Z",
  "documents": [ DocumentRef, ... ],
  "ads_data": { /* structured XFA extraction */ },
  "issues": [ Issue, ... ]
}

// DocumentRef — one per classified file
{
  "doc_type": "Declaration",
  "filename": "Formals.pdf",
  "path": "Formals.pdf",          // relative to folder
  "source": "pdf",                // "pdf" | "docx" | "xfa"
  "page_count": 4,
  "pages": [ { "index": 0, "width": 612.0, "height": 792.0 }, ... ]  // PDF points
}

// Issue — one per check result (PASS included)
{
  "check_id": 1,
  "category": "Cross-Document Consistency",
  "check_name": "Inventor Names Consistency",
  "severity": "PASS",             // CRITICAL | WARNING | INFO | PASS
  "message": "All 2 ADS inventors appear in: Declaration, Assignment",
  "details": "",                  // legacy free-text, kept as fallback
  "evidence": [ Evidence, ... ]
}

// Evidence — a single receipt
{
  "doc_type": "Declaration",      // which document (null for engine-level)
  "locator": Locator,             // where (tagged union below)
  "snippet": "Sarah J. CHEN",     // the relevant text
  "expected": "CHEN",             // optional
  "actual": "CHEN",               // optional
  "kind": "match",                // match | mismatch | missing | value | context
  "label": "ADS inventor 1 surname found in declaration"  // optional caption
}

// Locator — tagged by "type"
{ "type": "pdf_region", "page": 2, "bbox": [x0, y0, x1, y1] }  // PDF points
{ "type": "pdf_page",   "page": 2 }                            // page-level only
{ "type": "xfa_field",  "field_path": "inventors[0].last" }    // ADS, no geometry
{ "type": "none" }                                             // engine-level
```

The frontend renders each locator type differently:
`pdf_region` → scroll to page + draw highlight box; `pdf_page` → scroll to page;
`xfa_field` → show a structured data card; `none` → text only.

## 6. Coordinate capture (the hard part)

Highlighting needs a page + bounding box, and how attainable that is depends on
where the evidence came from:

| Evidence source | Locator we can produce |
|---|---|
| **pdfplumber text** (spec, declaration, assignment, POA) | `pdf_region` — `page.extract_words()` gives a bbox per word; union the words of the matched phrase. Store page width/height so the viewer can scale to its canvas. |
| **XFA structured data** (the ADS) | `xfa_field` — no page geometry exists in XFA; the receipt is the field value, shown as a data card. |
| **Scanned / image-only pages** | `pdf_page` (page-level highlight) or, if OCR is enabled, `pdf_region` from pytesseract word boxes. |

This mixed model is acceptable: most text checks get a true highlight; ADS
checks get a structured-data receipt; scans degrade to page-level. It is still a
large UX leap over jumping back and forth.

## 7. Refactor strategy — safe because the tests exist now

The monolith refactor is worth doing and **now is the right time, because the
92-test regression suite + CI make it safe**: we can move code and confirm
behavior is byte-for-byte identical at each step. Rules:

- **No big-bang.** Extract the engine/presentation seam + `Result` schema
  first (tests green), then peel one check category into `core/checks/` per PR
  (tests green each time).
- **Evidence rolls out per module.** When a check category moves into its
  module, upgrade those checks to emit structured evidence at the same time.
- **The HTML report is re-pointed at `Result`** early, so both frontends share
  the contract from the start.

### 7.1 The migration mechanism (in use)

A check is migrated by giving `core/checks/` ownership of its ID:

1. The check's logic + native evidence move to a `core/checks/*` module
   (`core.checks.REGISTRY` maps `id -> fn(qc) -> Issue`, `MIGRATED_IDS` is the
   owned set).
2. `core.build.run()` sets `QCReport.skip_check_ids |= MIGRATED_IDS` **only
   within the core path**, so the engine doesn't emit those IDs there, then runs
   the core versions and merges. Exactly one emission per check, with evidence.
3. The **standalone CLI is unaffected** — it doesn't call `core.run`, so the
   engine still emits its copy (this is why the engine keeps a transitional,
   duplicated copy of a migrated check).

The duplicate engine copy is removed only once the **HTML report also consumes
`Result`** (the deferred Phase-1 step) — at that point both frontends go through
`core` and the engine's copy is dead. So: re-point the report at `Result`, then
delete migrated checks from the engine. Until then, `skip_check_ids` keeps the
two paths consistent with no double-emission.

*Status: Check 2 (Application Title) is the first migrated check — native
evidence, engine-skipped in the core path, CLI unchanged.*

*Both frontends now consume `Result`: the interactive viewer (`app/`) and the
static HTML report (`report/`, evidence-aware). Next enabler for clean
move-and-delete: retire the monolith's own `generate_html_report` + `main()` on
`next` (superseded by `report/`), after which migrated checks can be deleted
from the engine rather than skipped.*

## 8. Roadmap

- **Phase 0 — De-risking spike** (mostly throwaway). One vertical slice through
  the whole new architecture, covering **two** evidence types:
  - Check 1 (inventor names) → `pdf_region` highlight in the declaration PDF.
  - Check 3 (docket number) → `xfa_field` data card from the ADS.
  - Minimal `--serve` returns the `Result` JSON + serves the PDFs; a bare
    PDF.js page renders a doc and, on clicking a check, scrolls + highlights.
  - **Proves:** the schema, coordinate capture, the viewer link, and the
    delivery architecture — before any large refactor.
- **Phase 1 — Core extraction.** Engine/presentation split; `Result` schema;
  HTML report re-pointed at it. No check-behavior change. Tests green.
- **Phase 2 — Modularize + evidence rollout.** Move check categories into
  `core/checks/*` one PR at a time; upgrade each to emit evidence as it moves.
- **Phase 3 — App frontend.** Full viewer UX over the `--serve` API: all docs,
  receipts panel, click-to-highlight, severity filtering, navigation.
- **Phase 4 — Packaging / deployment.** Per-desktop launcher and/or internal
  host; optional desktop wrap. Decide deploy shape based on firm IT posture.

## 9. Deferred / open decisions

- **Deploy shape** (per-desktop vs internal-hosted) — deferred to Phase 4; the
  architecture supports both.
- **Frontend stack** — start minimal (vanilla JS + PDF.js, no heavy build
  tooling); revisit a framework only if the UI grows enough to need it.
- **Repo rename** — optional; the GitHub repo can be renamed to a product-level
  name (GitHub redirects the old URL). The skill is registered by its directory
  name and `SKILL.md` `name:` field, so a rename does not break it.
- **`Result` persistence / re-run** — whether the app caches results or always
  re-runs the engine; decide during Phase 3.
