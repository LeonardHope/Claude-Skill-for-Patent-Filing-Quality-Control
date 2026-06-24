"""app server — the real interactive viewer over the core pipeline.

Runs the actual engine via core.build.run() with native evidence, then serves:
  GET  /                     -> the viewer (static/index.html)
  GET  /api/pick             -> open a native OS folder picker, return {path}
  GET  /api/result?folder=…  -> the Result JSON (issues + evidence + documents)
  GET  /api/pdf/<doc>?folder=… -> the bytes of a document PDF in that folder
  GET  /static/<file>        -> static assets

The folder can be chosen interactively in the browser (no CLI arg needed); pass
one on the command line to pre-select it. All processing is local and nothing
leaves the machine — the picker is a native dialog, PDFs are read from disk and
streamed to PDF.js. Results are cached per folder so opening a document doesn't
re-run QC (append ?refresh=1 to re-run after editing files).

Run:  python3 app/server.py [/path/to/filing/folder]
Then open http://localhost:8000 (the script tries to open it).
"""
import json
import os
import platform
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

# ── Windows compatibility ────────────────────────────────────────────────────
# qc_patent_filing.py uses emoji in its progress print statements. Windows
# consoles default to cp1252 which cannot encode them, causing a
# UnicodeEncodeError that crashes the server silently mid-request.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Tesseract is required for OCR of image-only PDFs (executed declarations,
# scanned assignments, filing receipts). On Windows it is not on PATH by
# default even when installed; add the standard install location if present.
_tesseract_dir = r"C:\Program Files\Tesseract-OCR"
if platform.system() == "Windows" and os.path.isdir(_tesseract_dir):
    if _tesseract_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + _tesseract_dir
# ────────────────────────────────────────────────────────────────────────────

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))           # repo root, for `import core`
from core.build import run                       # noqa: E402

STATIC = HERE / "static"
PORT = 8000

PRESELECTED = None
if len(sys.argv) >= 2:
    p = Path(sys.argv[1]).resolve()
    if not p.is_dir():
        print(f"not a folder: {p}")
        sys.exit(2)
    PRESELECTED = str(p)

_CACHE = {}   # folder -> Result


def build_for(folder: str, refresh: bool = False):
    """Run QC for a folder once and cache the Result. Raises on a bad folder."""
    if not folder or not Path(folder).is_dir():
        raise FileNotFoundError(folder)
    key = str(Path(folder).resolve())
    if refresh:
        _CACHE.pop(key, None)
    if key not in _CACHE:
        _CACHE[key] = run(key, generated_at="local-run")
    return _CACHE[key]


# Each platform's native folder chooser is invoked as a SUBPROCESS, never an
# in-process GUI toolkit — the HTTP handler runs in a worker thread, and Tk/Win32
# dialogs must own the main thread, so a subprocess is the only safe way here.

# macOS: `activate` brings the chooser to the front (else it can open *behind*
# the browser). Cancel → osascript exits non-zero with error -128.
_OSA = (
    'activate\n'
    'set theFolder to choose folder with prompt '
    '"Select the patent filing folder to QC"\n'
    'return POSIX path of theFolder'
)

# Windows: a PowerShell FolderBrowserDialog (TopMost so it comes to the front).
# Prints the chosen path, or "__CANCELLED__" so we can tell cancel from failure.
_PS = (
    "Add-Type -AssemblyName System.Windows.Forms;"
    "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
    "$d.Description = 'Select the patent filing folder to QC';"
    "$d.ShowNewFolderButton = $false;"
    "$top = New-Object System.Windows.Forms.Form -Property @{TopMost=$true};"
    "if ($d.ShowDialog($top) -eq [System.Windows.Forms.DialogResult]::OK)"
    " { Write-Output $d.SelectedPath } else { Write-Output '__CANCELLED__' }"
)


def pick_folder():
    """Open a native OS 'choose folder' dialog on the machine running the server.
    Returns {"path": str|None, "error": str|None}. A user cancel is not an error
    (path None, error None); anything else reports a reason the UI can show."""
    system = platform.system()
    try:
        if system == "Windows":
            r = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command", _PS],
                capture_output=True, text=True, timeout=600)
            out = (r.stdout or "").strip()
            if not out or out == "__CANCELLED__":
                return {"path": None, "error": None}        # cancelled — fine
            return {"path": out, "error": None}
        if system == "Darwin":
            r = subprocess.run(["osascript", "-e", _OSA],
                               capture_output=True, text=True, timeout=600)
            if r.returncode == 0:
                return {"path": r.stdout.strip().rstrip("/") or None, "error": None}
            if "-128" in (r.stderr or "") or "User canceled" in (r.stderr or ""):
                return {"path": None, "error": None}        # cancelled — fine
            return {"path": None, "error": (r.stderr or "folder chooser failed").strip()}
    except Exception as e:
        return {"path": None, "error": f"could not launch folder chooser: {e}"}
    # Linux / unknown: no reliable headless-safe native chooser — use path entry.
    return {"path": None, "error": "no native folder chooser on this OS — "
            "paste the folder path below instead"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        q = parse_qs(u.query)
        folder = unquote(q.get("folder", [""])[0]) or PRESELECTED

        if path in ("/", "/index.html"):
            self._send(200, (STATIC / "index.html").read_bytes(),
                       "text/html; charset=utf-8")
            return

        if path == "/api/config":
            self._json(200, {"preselected": PRESELECTED})
            return

        if path == "/api/pick":
            self._json(200, pick_folder())
            return

        if path == "/api/result":
            try:
                result = build_for(folder, refresh=q.get("refresh", ["0"])[0] == "1")
            except FileNotFoundError:
                self._json(400, {"error": f"not a folder: {folder or '(none)'}"})
                return
            except Exception as e:
                self._json(500, {"error": f"{type(e).__name__}: {e}"})
                return
            self._send(200, result.to_json(), "application/json")
            return

        if path.startswith("/api/pdf/"):
            doc_type = unquote(path[len("/api/pdf/"):])
            try:
                result = build_for(folder)
            except Exception:
                self._send(400, b"bad folder", "text/plain"); return
            ref = next((d for d in result.documents if d.doc_type == doc_type), None)
            if not ref or not ref.path:
                self._send(404, b"unknown document", "text/plain"); return
            pdf_path = Path(folder) / ref.path
            if not pdf_path.exists():
                self._send(404, b"file missing", "text/plain"); return
            self._send(200, pdf_path.read_bytes(), "application/pdf")
            return

        if path.startswith("/static/"):
            asset = STATIC / path[len("/static/"):]
            if asset.exists() and asset.is_file():
                ctype = ("application/javascript" if asset.suffix == ".js"
                         else "text/plain")
                self._send(200, asset.read_bytes(), ctype)
                return

        self._send(404, b"not found", "text/plain")

    def log_message(self, *args):  # quiet
        pass


def main():
    # Prefer :8000, but fall back to an OS-assigned free port so a second copy
    # (or anything already on 8000) doesn't fail to launch — important for the
    # double-click launcher where the user can't free the port themselves.
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    url = f"http://localhost:{port}"
    where = PRESELECTED or "(choose a folder in the browser)"
    print(f"Patent Filing QC\n  folder: {where}\n  {url}\n"
          f"  (leave this window open while you work; close it to stop)")
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass
    httpd.serve_forever()


if __name__ == "__main__":
    main()
