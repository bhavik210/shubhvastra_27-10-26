@echo off
cd /d "%~dp0"
py -3 -c "import tkinter" >nul 2>&1
if errorlevel 1 (
  echo Python 3 with Tkinter was not found. Install Python from https://www.python.org/downloads/windows/
  pause
  exit /b 1
)
py -3 -c "import reportlab" >nul 2>&1
if errorlevel 1 (
  echo Installing PDF library ReportLab into the Python 3 interpreter...
  py -3 -m pip install --user "reportlab>=4.2,<5"
  if errorlevel 1 (
    echo Install failed. Check internet access and run: py -3 -m pip install --user reportlab
    pause
    exit /b 1
  )
)
py -3 app.py
if errorlevel 1 pause
