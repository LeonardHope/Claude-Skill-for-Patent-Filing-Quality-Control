"""app server — the real interactive viewer over the core pipeline.

Unlike app/spike/ (which used hand-built data), this runs the actual engine via
core.build.run() with evidence enrichment, then serves:
  GET /                -> the viewer (static/index.html)
  GET /api/result      -> the Result JSON (issues + evidence + documents)
  GET /api/pdf/<doc>   -> the bytes of a document PDF
  GET /static/<file>   -> static assets

All processing is local; nothing leaves the machine. The frontend fetches PDF
bytes and renders with PDF.js, so no HTTP range support is needed.

Run:  python3 app/server.py /path/to/filing/folder
Then open http://localhost:8000 (the script tries to open it).
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))           # repo root, for `import core`
from core.build import run                       # noqa: E402

STATIC = HERE / "static"
PORT = 8000

if len(sys.argv) < 2:
    print("usage: python3 app/server.py /path/to/filing/folder")
    sys.exit(2)
FOLDER = Path(sys.argv[1]).resolve()
if not FOLDER.is_dir():
    print(f"not a folder: {FOLDER}")
    sys.exit(2)


def _build():
    """Run the engine + enrichment fresh (cheap relative to a human reading the
    report; keeps things simple and always current). Fixed timestamp keeps the
    payload stable across refreshes within a session."""
    return run(str(FOLDER), generated_at="local-run")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            return

        if path == "/api/result":
            self._send(200, _build().to_json().encode("utf-8"), "application/json")
            return

        if path.startswith("/api/pdf/"):
            doc_type = path[len("/api/pdf/"):].replace("%20", " ")
            ref = next((d for d in _build().documents if d.doc_type == doc_type), None)
            if not ref or not ref.path:
                self._send(404, b"unknown document", "text/plain"); return
            pdf_path = FOLDER / ref.path
            if not pdf_path.exists():
                self._send(404, b"file missing", "text/plain"); return
            self._send(200, pdf_path.read_bytes(), "application/pdf")
            return

        if path.startswith("/static/"):
            asset = STATIC / path[len("/static/"):]
            if asset.exists() and asset.is_file():
                ctype = "application/javascript" if asset.suffix == ".js" else "text/plain"
                self._send(200, asset.read_bytes(), ctype)
                return

        self._send(404, b"not found", "text/plain")

    def log_message(self, *args):  # quiet
        pass


def main():
    print(f"Patent Filing QC — interactive viewer\n  folder: {FOLDER}\n  http://localhost:{PORT}")
    try:
        import webbrowser
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
