@echo off
rem Double-click to open Render QA in your browser.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Render QA isn't set up on this computer yet.
  echo Ask whoever looks after the office computers to open the Admin folder
  echo and double-click "Set up (Windows)" once.
  echo.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 (
  echo.
  echo Render QA couldn't start. Try again, or ask whoever looks after the
  echo office computers to run "Set up (Windows)" in the Admin folder.
  pause
)
