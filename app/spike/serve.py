"""Phase-0 spike server.

Dependency-light (Python stdlib http.server). Serves:
  GET /                 -> the viewer (static/index.html)
  GET /api/result       -> the Result JSON (result_builder)
  GET /api/pdf/<doc>    -> the full bytes of a document PDF
  GET /static/<file>    -> static assets

The frontend fetches the PDF bytes and hands them to PDF.js directly, so we
don't need HTTP range support for this spike.

Run:  python3 app/spike/serve.py [folder]   (folder defaults to app/sample)
Then open http://localhost:8000  (the script tries to open it for you).
"""
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from result_builder import build_result  # noqa: E402

STATIC = HERE / "static"
PORT = 8000

_folder = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (HERE.parent / "sample")


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
            result = build_result(_folder)
            self._send(200, json.dumps(result).encode("utf-8"), "application/json")
            return

        if path.startswith("/api/pdf/"):
            doc_type = path[len("/api/pdf/"):]
            result = build_result(_folder)
            ref = next((d for d in result["documents"] if d["doc_type"] == doc_type), None)
            if not ref:
                self._send(404, b"unknown document", "text/plain")
                return
            pdf_path = _folder / ref["path"]
            if not pdf_path.exists():
                self._send(404, b"file missing", "text/plain")
                return
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
    print(f"Phase-0 spike serving {_folder}")
    print(f"  http://localhost:{PORT}")
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
