#!/usr/bin/env python3
"""Guard against committing real client / firm material to this PUBLIC repo.

Blocks firm docket / file numbers (a letter, three digits, a dash, then a
serial — the shape of a real matter number) — the recurring way real matter
data has leaked into the repo. Obviously-synthetic placeholders used by the
test fixtures are allowlisted.

Usage:
    check_no_client_material.py                 # scan the whole git-tracked tree
    check_no_client_material.py FILE [FILE...]  # scan specific files (pre-commit)

Exits non-zero (and prints offenders) if anything forbidden is found, so it can
gate a pre-commit hook and CI. See CONTRIBUTING.md.
"""
import re
import subprocess
import sys
from pathlib import Path

# All synthetic dockets in the test fixtures use an obviously-fake family:
# they begin X000- or X999-. Anything else matching the docket shape below is
# treated as a potential real number. Matched case-insensitively.
ALLOW_PREFIXES = ("X000-", "X999-")

# Docket-shaped token: a letter, three digits, a dash, 3-4 digits, optional
# alphanumeric suffix (e.g. the X000-0000US placeholder shape).
DOCKET = re.compile(r"\b[A-Za-z][0-9]{3}-[0-9]{3,4}[A-Za-z0-9]*\b")

# Files that legitimately contain the placeholders / the detector itself.
SKIP = {
    "scripts/check_no_client_material.py",
    ".github/workflows/no-client-material.yml",
    ".githooks/pre-commit",
    "CONTRIBUTING.md",
}


def _tracked_files():
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    return [l for l in out.stdout.splitlines() if l]


def scan(paths):
    hits = []
    for p in paths:
        if p in SKIP:
            continue
        fp = Path(p)
        if not fp.is_file():
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in DOCKET.finditer(line):
                if not m.group(0).upper().startswith(ALLOW_PREFIXES):
                    hits.append((p, n, m.group(0), line.strip()[:100]))
    return hits


def main():
    paths = sys.argv[1:] or _tracked_files()
    hits = scan(paths)
    if not hits:
        return 0
    sys.stderr.write(
        "\n✋  Possible client/firm material — this repo is PUBLIC, do not commit it:\n\n")
    for p, n, tok, ln in hits:
        sys.stderr.write(f"  {p}:{n}: {tok!r}  ->  {ln}\n")
    sys.stderr.write(
        "\nReplace real docket/file numbers with an obviously-fake placeholder "
        "(e.g. X000-0000US).\nIf this is a genuine false positive, add the token "
        "to ALLOW in scripts/check_no_client_material.py.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
