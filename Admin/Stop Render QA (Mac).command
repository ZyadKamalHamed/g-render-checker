#!/bin/bash
# Stops Render QA if it's running (restarting the computer does the same).
cd "$(dirname "$0")/.."
[ -x .venv/bin/python ] && .venv/bin/python launcher.py --stop
read -n 1 -s -r -p "Press any key to close this window."
