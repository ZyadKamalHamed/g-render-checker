@echo off
rem Runs Render QA on this computer so others on the office network can open it with a link.
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  echo Render QA isn't set up yet. Double-click "Set up (Windows)" first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" launcher.py --share
echo.
echo Send that link to your colleagues. It's also shown at the bottom of Render QA.
echo Keep this computer switched on and awake while people are using it.
echo If Windows asks whether to allow Python through the firewall, allow it on
echo private networks.
echo.
pause
