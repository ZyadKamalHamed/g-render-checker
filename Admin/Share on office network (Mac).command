#!/bin/bash
# Runs Render QA on this Mac so others on the office network can open it with a link.
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo "Render QA isn't set up yet. Double-click \"Set up (Mac)\" first."
  read -n 1 -s -r -p "Press any key to close this window."; exit 1
fi
.venv/bin/python launcher.py --share
echo
echo "Send that link to your colleagues. It's also shown at the bottom of Render QA."
echo "Keep this Mac switched on and awake while people are using it."
echo "If macOS asks whether Python may accept incoming connections, click Allow."
echo
read -n 1 -s -r -p "Press any key to close this window (Render QA keeps running)."
