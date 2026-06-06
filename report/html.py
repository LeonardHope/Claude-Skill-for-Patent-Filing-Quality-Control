"""render(result) -> a self-contained HTML report string.

Consumes a core.result.Result (no engine access). Print-friendly, embedded CSS,
no external assets. Unlike the monolith's report it is evidence-aware: each
finding lists its receipts (which document / where).
"""
import html as _html
from typing import List

from core.result import Result

_SEV_ORDER = ["CRITICAL", "WARNING", "INFO", "PASS"]
_SEV_LABEL = {
    "CRITICAL": "Critical — Must Fix Before Filing",
    "WARNING": "Warnings — Should Review",
    "INFO": "Informational / Manual Review",
    "PASS": "Passed",
}

_CSS = """
:root{--crit:#c0392b;--warn:#b7791f;--info:#2c6fbb;--pass:#1e7a46;--line:#e3e6ea;--muted:#6b7280;}
*{box-sizing:border-box;}
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a1f29;margin:0;background:#fff;}
.wrap{max-width:920px;margin:0 auto;padding:28px 22px 60px;}
h1{font-size:22px;margin:0 0 2px;} .sub{color:var(--muted);font-size:13px;margin-bottom:18px;}
.counts{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 26px;}
.pill{padding:6px 12px;border-radius:18px;font-weight:700;font-size:13px;color:#fff;}
.pill.CRITICAL{background:var(--crit);} .pill.WARNING{background:var(--warn);}
.pill.INFO{background:var(--info);} .pill.PASS{background:var(--pass);}
h2{font-size:16px;margin:26px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--line);}
table{border-collapse:collapse;width:100%;font-size:13px;margin:6px 0 14px;}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top;}
th{color:var(--muted);font-weight:600;}
.issue{border:1px solid var(--line);border-left-width:4px;border-radius:6px;padding:10px 13px;margin:8px 0;}
.issue.CRITICAL{border-left-color:var(--crit);} .issue.WARNING{border-left-color:var(--warn);}
.issue.INFO{border-left-color:var(--info);} .issue.PASS{border-left-color:var(--pass);}
.issue .id{color:var(--muted);font-weight:600;} .issue .name{font-weight:700;}
.issue .msg{margin-top:3px;} .issue .details{color:var(--muted);white-space:pre-wrap;margin-top:5px;font-size:12.5px;}
.receipts{margin-top:7px;padding-top:6px;border-top:1px dashed var(--line);}
.receipt{font-size:12.5px;color:#374151;}
.receipt .loc{color:var(--muted);} .receipt.missing{color:var(--crit);}
.muted{color:var(--muted);}
@media print{.wrap{max-width:none;}}
"""


def _esc(s) -> str:
    return _html.escape("" if s is None else str(s))


def _receipt_line(ev) -> str:
    L = ev.get("locator", {})
    t = L.get("type")
    if t == "pdf_region":
        loc = f"{ev.get('doc_type')} p.{(L.get('page', 0) or 0) + 1}"
    elif t == "pdf_page":
        loc = f"{ev.get('doc_type')} p.{(L.get('page', 0) or 0) + 1}"
    elif t == "xfa_field":
        loc = f"{ev.get('doc_type')} field “{L.get('field_path')}”"
    else:
        loc = ev.get("doc_type") or ""
    label = ev.get("label") or ev.get("snippet") or ""
    cls = "receipt missing" if ev.get("kind") == "missing" else "receipt"
    mark = "✓" if ev.get("kind") == "match" else ("✗" if ev.get("kind") == "missing" else "•")
    return (f'<div class="{cls}">{mark} <span class="loc">{_esc(loc)}</span> — '
            f'{_esc(label)}</div>')


def _issue_html(issue: dict) -> str:
    parts = [f'<div class="issue {issue["severity"]}">',
             f'<div><span class="id">{issue["check_id"]}.</span> '
             f'<span class="name">{_esc(issue["check_name"])}</span> '
             f'<span class="muted">({_esc(issue["category"])})</span></div>',
             f'<div class="msg">{_esc(issue["message"])}</div>']
    if issue.get("details"):
        parts.append(f'<div class="details">{_esc(issue["details"])}</div>')
    evs = issue.get("evidence") or []
    if evs:
        parts.append('<div class="receipts">' + "".join(_receipt_line(e) for e in evs)
                     + "</div>")
    parts.append("</div>")
    return "".join(parts)


def _documents_table(docs: List[dict]) -> str:
    if not docs:
        return '<p class="muted">No documents classified.</p>'
    rows = "".join(
        f"<tr><td>{_esc(d['doc_type'])}</td><td>{_esc(d.get('filename'))}</td>"
        f"<td>{_esc(d.get('source'))}</td><td>{_esc(d.get('page_count'))}</td></tr>"
        for d in docs)
    return ("<table><tr><th>Document</th><th>File</th><th>Source</th><th>Pages</th></tr>"
            + rows + "</table>")


def _ads_summary(ads: dict) -> str:
    if not ads:
        return ""
    fields = [("Title", ads.get("title")), ("Docket", ads.get("docket_number")),
              ("Customer #", ads.get("customer_number")),
              ("Assignee", ads.get("assignee_org")),
              ("Inventors", len(ads.get("inventors", []) or []) or None)]
    rows = "".join(f"<tr><td>{k}</td><td>{_esc(v)}</td></tr>"
                   for k, v in fields if v not in (None, ""))
    if not rows:
        return ""
    return "<h2>ADS Data Summary</h2><table>" + rows + "</table>"


def render(result: Result) -> str:
    d = result.to_dict()
    issues = d.get("issues", [])
    counts = {s: sum(1 for i in issues if i["severity"] == s) for s in _SEV_ORDER}

    pills = "".join(f'<span class="pill {s}">{counts[s]} {s.title()}</span>'
                    for s in _SEV_ORDER if counts[s])

    sections = []
    for s in _SEV_ORDER:
        group = [i for i in issues if i["severity"] == s]
        if not group:
            continue
        sections.append(f"<h2>{_SEV_LABEL[s]} ({len(group)})</h2>"
                        + "".join(_issue_html(i) for i in group))

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Newport IP — Patent Filing QC Report</title><style>{_CSS}</style></head>
<body><div class="wrap">
<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
<span style="width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,#3b82f6,#1e40af);
color:#fff;font-weight:800;display:inline-flex;align-items:center;justify-content:center;font-size:17px;">N</span>
<span style="font-size:17px;font-weight:700;color:#0f1729;">Newport <span style="color:#2563eb;">IP</span></span>
</div>
<h1>Patent Filing QC Report</h1>
<div class="sub">{_esc(d.get('folder'))} · {_esc(d.get('generated_at'))}</div>
<div class="counts">{pills or '<span class="muted">No findings.</span>'}</div>
<h2>Documents Found</h2>{_documents_table(d.get('documents', []))}
{_ads_summary(d.get('ads_data') or {})}
{''.join(sections)}
</div></body></html>"""
