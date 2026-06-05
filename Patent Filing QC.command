#!/bin/bash
# Patent Filing QC — double-click launcher (macOS).
#
# First run: creates a private Python environment (.venv) next to this file and
# installs the dependencies (needs internet that one time). Every run after that
# starts instantly and works offline. Closing the Terminal window stops the tool.
#
# If macOS says it "cannot verify the developer", right-click this file → Open
# the first time (only needed once).

cd "$(dirname "$0")" || exit 1

PYTHON="${PYTHON:-python3}"
VENV=".venv"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install it from https://www.python.org/downloads/ and try again."
  echo "Press Return to close."; read -r _; exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
  echo "First-time setup — creating a local environment and installing dependencies…"
  "$PYTHON" -m venv "$VENV" || { echo "Could not create the environment."; read -r _; exit 1; }
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet -r requirements.txt || {
    echo "Dependency install failed. Check your internet connection and try again."
    echo "Press Return to close."; read -r _; exit 1; }
  echo "Setup complete."
fi

echo "Starting Patent Filing QC… your browser will open shortly."
exec "$VENV/bin/python" app/server.py
