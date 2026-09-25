"""Start Render QA in the background and open it in the browser.

Used by the double-click launchers; nobody needs to run this by hand.

    python launcher.py            start (or just reopen) on this computer only
    python launcher.py --share    start so others on the office network can open it
    python launcher.py --stop     stop it
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / ".render-qa.json"
LOG_DIR = ROOT / "logs"
FIRST_PORT = 8520
PORT_RANGE = range(FIRST_PORT, FIRST_PORT + 20)


def is_render_qa(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1.5) as r:
            return r.status == 200
    except OSError:
        return False


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if os.name != "nt":  # as the server does, so a just-closed port counts as free
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def lan_address() -> str | None:
    """This computer's address on the office network (nothing is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def read_state() -> dict | None:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return None


def running_state() -> dict | None:
    state = read_state()
    if state and is_render_qa(state.get("port", 0)):
        return state
    return None


def stop(state: dict) -> None:
    pid = state.get("pid")
    if pid:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            else:
                os.killpg(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
    for _ in range(100):  # wait for the port to be released so a restart can reuse it
        if not is_render_qa(state["port"]) and port_free(state["port"]):
            break
        time.sleep(0.1)
    STATE_FILE.unlink(missing_ok=True)


def start(share: bool, prefer: int | None = None) -> dict:
    ports = ([prefer] if prefer else []) + list(PORT_RANGE)
    port = next((p for p in ports if port_free(p)), None)
    if port is None:
        raise SystemExit("Render QA couldn't find a free port to run on. Try restarting the computer.")

    LOG_DIR.mkdir(exist_ok=True)
    log = open(LOG_DIR / "render-qa.log", "a", encoding="utf-8")
    cmd = [
        sys.executable, str(ROOT / "serve.py"), "run", str(ROOT / "app.py"),
        "--server.port", str(port),
        "--server.address", "0.0.0.0" if share else "localhost",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    kwargs: dict = {"cwd": ROOT, "stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        # Use the windowless Python so no console appears.
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            cmd[0] = str(pythonw)
    else:
        kwargs["start_new_session"] = True  # keeps running after the launcher window closes
    proc = subprocess.Popen(cmd, **kwargs)

    for _ in range(600):  # up to a minute; the first start is the slowest
        if is_render_qa(port):
            break
        if proc.poll() is not None:
            raise SystemExit(f"Render QA didn't start. Details are in {LOG_DIR / 'render-qa.log'}")
        time.sleep(0.1)
    else:
        raise SystemExit(f"Render QA is taking too long to start. Details are in {LOG_DIR / 'render-qa.log'}")

    state = {"pid": proc.pid, "port": port, "share": share}
    STATE_FILE.write_text(json.dumps(state))
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Start or stop Render QA.")
    parser.add_argument("--share", action="store_true", help="let others on the office network open it")
    parser.add_argument("--stop", action="store_true", help="stop Render QA")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = parser.parse_args()

    state = running_state()
    if args.stop:
        if state:
            stop(state)
            print("Render QA has been stopped.")
        else:
            STATE_FILE.unlink(missing_ok=True)
            print("Render QA wasn't running.")
        return

    prefer = None
    if state and args.share and not state.get("share"):
        stop(state)  # restart so the office network can reach it
        prefer, state = state["port"], None
    if not state:
        print("Starting Render QA…")
        state = start(args.share, prefer)

    url = f"http://localhost:{state['port']}"
    if not args.no_browser:
        webbrowser.open(url)
    print(f"Render QA is running at {url}")
    if state.get("share"):
        ip = lan_address()
        if ip:
            print(f"Others in the office can open: http://{ip}:{state['port']}")


if __name__ == "__main__":
    main()
