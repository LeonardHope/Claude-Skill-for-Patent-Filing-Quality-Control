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
import platform
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

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


# AppleScript: `activate` brings the chooser to the front (otherwise it can open
# *behind* the browser and look like nothing happened). Cancel → error -128.
_OSA = (
    'activate\n'
    'set theFolder to choose folder with prompt '
    '"Select the patent filing folder to QC"\n'
    'return POSIX path of theFolder'
)


def pick_folder():
    """Open a native OS 'choose folder' dialog on the machine running the server.
    Returns {"path": str|None, "error": str|None}. A user cancel is not an error
    (path None, error None); anything else reports a reason the UI can show."""
    if platform.system() == "Darwin":
        try:
            r = subprocess.run(["osascript", "-e", _OSA],
                               capture_output=True, text=True, timeout=600)
        except Exception as e:
            return {"path": None, "error": f"could not launch folder chooser: {e}"}
        if r.returncode == 0:
            return {"path": r.stdout.strip().rstrip("/") or None, "error": None}
        if "-128" in (r.stderr or "") or "User canceled" in (r.stderr or ""):
            return {"path": None, "error": None}            # cancelled — fine
        return {"path": None, "error": (r.stderr or "folder chooser failed").strip()}
    try:                                              # Windows / Linux fallback
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Select the patent filing folder to QC")
        root.destroy()
        return {"path": path or None, "error": None}
    except Exception as e:
        return {"path": None, "error": f"no folder chooser available: {e}"}


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
    where = PRESELECTED or "(choose a folder in the browser)"
    print(f"Patent Filing QC — interactive viewer\n  folder: {where}\n"
          f"  http://localhost:{PORT}")
    try:
        import webbrowser
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
