#!/bin/bash
# One-time setup: installs what Render QA needs into a private folder (.venv).
# Safe to run again, for example after updating Render QA.
cd "$(dirname "$0")/.."
echo "Setting up Render QA. The first time takes a few minutes."
echo

PY=""
for c in python3.14 python3.13 python3.12 python3.11 \
         /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
         /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done

if [ -z "$PY" ]; then
  echo "Render QA needs Python 3.11 or newer, which isn't installed on this Mac."
  echo "Opening the Python download page. Install the latest version, then"
  echo "double-click this setup file again."
  open "https://www.python.org/downloads/macos/"
  echo
  read -n 1 -s -r -p "Press any key to close this window."
  exit 1
fi
echo "Using $("$PY" --version)"

[ -x .venv/bin/python ] && .venv/bin/python launcher.py --stop >/dev/null 2>&1

fail() {
  echo
  echo "Setup didn't finish. Check the internet connection and try again."
  read -n 1 -s -r -p "Press any key to close this window."
  exit 1
}
"$PY" -m venv --clear .venv || fail
.venv/bin/python -m pip install --quiet --upgrade pip || fail
.venv/bin/python -m pip install --quiet -r requirements.txt || fail

# Let the double-click files run without macOS security warnings.
xattr -dr com.apple.quarantine . 2>/dev/null
chmod +x ./*.command Admin/*.command

echo
echo "All done. Double-click \"Render QA\" to open it."
read -n 1 -s -r -p "Press any key to close this window."
