#!/bin/bash
# SHUBHVASTRA 2026 - macOS launcher
cd "$(dirname "$0")"
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import tkinter' >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
done
if [ -z "$PYTHON" ]; then echo "Python 3 with Tkinter not found. Install Python from https://www.python.org/downloads/macos/"; read -r -p "Press Return to close..."; exit 1; fi
if ! "$PYTHON" -c 'import reportlab' >/dev/null 2>&1; then
  echo "Installing PDF library ReportLab..."
  "$PYTHON" -m pip install --user 'reportlab>=4.2,<5' || { echo "Install failed. Check internet access and run: $PYTHON -m pip install --user reportlab"; read -r -p "Press Return to close..."; exit 1; }
fi
"$PYTHON" app.py
