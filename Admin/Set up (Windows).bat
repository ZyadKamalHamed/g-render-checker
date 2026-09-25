@echo off
rem One-time setup: installs what Render QA needs into a private folder (.venv).
rem Safe to run again, for example after updating Render QA.
cd /d "%~dp0\.."
echo Setting up Render QA. The first time takes a few minutes.
echo.

set "PY="
for %%V in (3.14 3.13 3.12 3.11) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Render QA needs Python 3.11 or newer, which isn't installed on this computer.
  echo Opening the Python download page. Install the latest version, ticking
  echo "Add python.exe to PATH", then double-click this setup file again.
  start "" "https://www.python.org/downloads/windows/"
  echo.
  pause
  exit /b 1
)

if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" launcher.py --stop >nul 2>&1

%PY% -m venv --clear .venv || goto failed
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip || goto failed
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto failed

echo.
echo All done. Double-click "Render QA" to open it.
pause
exit /b 0

:failed
echo.
echo Setup didn't finish. Check the internet connection and try again.
pause
exit /b 1
