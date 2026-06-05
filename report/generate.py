"""Generate the static HTML report from a filing folder, via core.

  python3 report/generate.py /path/to/folder [output.html]

Runs the engine through core (with evidence), renders, and writes the HTML.
Default output: Patent_Filing_QC_Report.html in the filing folder.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root
from core.build import run          # noqa: E402
from report.html import render      # noqa: E402


def main():
    if len(sys.argv) < 2:
        print("usage: python3 report/generate.py <folder> [output.html]")
        sys.exit(2)
    folder = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else folder / "Patent_Filing_QC_Report.html"
    result = run(str(folder))
    out.write_text(render(result), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
