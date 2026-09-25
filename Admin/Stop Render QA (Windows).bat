@echo off
rem Stops Render QA if it's running (restarting the computer does the same).
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" launcher.py --stop
pause
