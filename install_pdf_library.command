#!/bin/bash
cd "$(dirname "$0")"
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import tkinter' >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
done
if [ -z "$PYTHON" ]; then echo "Python 3 with Tkinter not found."; read -r -p "Press Return to close..."; exit 1; fi
echo "Installing ReportLab for: $($PYTHON -c 'import sys; print(sys.executable)')"
"$PYTHON" -m ensurepip --upgrade || true
"$PYTHON" -m pip install --upgrade --user 'reportlab>=4.2,<5' || "$PYTHON" -m pip install --upgrade 'reportlab>=4.2,<5' || { echo "Installation failed. Check internet access and permissions."; read -r -p "Press Return to close..."; exit 1; }
"$PYTHON" -c 'import reportlab; print("ReportLab installed:", reportlab.Version)'
read -r -p "Press Return to close..."
