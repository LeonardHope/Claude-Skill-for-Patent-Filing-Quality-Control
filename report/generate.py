"""Generate the static HTML report from a filing folder, via core.

  python3 report/generate.py /path/to/folder [output.html]

Runs the engine through core (read-only on the filing folder) and writes the
HTML report. The report is NEVER written inside the filing folder — QC must not
modify the user's work. Default output: Patent_Filing_QC_Report.html in the
current working directory; pass an explicit path to write elsewhere (but not
inside the filing folder).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root
from core.build import run          # noqa: E402
from report.html import render      # noqa: E402


def _inside(path: Path, folder: Path) -> bool:
    """True if `path` resolves to `folder` itself or anything beneath it."""
    path, folder = path.resolve(), folder.resolve()
    return path == folder or folder in path.parents


def main():
    if len(sys.argv) < 2:
        print("usage: python3 report/generate.py <folder> [output.html]")
        sys.exit(2)
    folder = Path(sys.argv[1]).resolve()
    out = (Path(sys.argv[2]) if len(sys.argv) > 2
           else Path.cwd() / "Patent_Filing_QC_Report.html")
    if _inside(out, folder):
        print(f"refusing to write inside the filing folder (QC never modifies it):\n"
              f"  {out.resolve()}\nChoose an output path outside {folder}.")
        sys.exit(2)
    result = run(str(folder))
    out.write_text(render(result), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
