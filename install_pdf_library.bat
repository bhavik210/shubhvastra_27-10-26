@echo off
cd /d "%~dp0"
echo Installing ReportLab for the Python used by SHUBHVASTRA...
py -3 -m ensurepip --upgrade
py -3 -m pip install --upgrade --user "reportlab>=4.2,<5"
if errorlevel 1 py -3 -m pip install --upgrade "reportlab>=4.2,<5"
if errorlevel 1 (
  echo.
  echo Installation failed. Check internet/proxy/permissions and read pdf_install_error.log if present.
  echo You can also try: py -3 -m pip install --user reportlab
  pause
  exit /b 1
)
py -3 -c "import reportlab; print('ReportLab installed:', reportlab.Version)"
if errorlevel 1 pause
pause
