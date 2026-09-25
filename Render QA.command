#!/bin/bash
# Double-click to open Render QA in your browser.
cd "$(dirname "$0")"

close_window() {
  # Close this Terminal window once we're done, so nobody has to look at it.
  (sleep 0.5; osascript -e 'tell application "Terminal" to close (every window whose name contains "Render QA.command")') >/dev/null 2>&1 &
}

if [ ! -x .venv/bin/python ]; then
  osascript -e 'display dialog "Render QA isn’t set up on this Mac yet.\n\nAsk whoever looks after the office computers to open the Admin folder and double-click “Set up (Mac)” once." buttons {"OK"} default button 1 with title "Render QA" with icon caution' >/dev/null 2>&1
  close_window
  exit 0
fi

if ! .venv/bin/python launcher.py; then
  osascript -e 'display dialog "Render QA couldn’t start. Try again, or ask whoever looks after the office computers to run “Set up (Mac)” in the Admin folder." buttons {"OK"} default button 1 with title "Render QA" with icon caution' >/dev/null 2>&1
fi
close_window
exit 0
