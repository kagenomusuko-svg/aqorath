"""Aqorath desktop application entrypoint."""

import os
import sys
import threading
import time
import urllib.request
import webbrowser

from aqorath.local_server import DEFAULT_PORT, LOCAL_HOST, run_local_surface

LOCAL_URL = f"http://{LOCAL_HOST}:{DEFAULT_PORT}/"


def _ensure_windowed_streams():
    """Provide writable streams when PyInstaller --windowed omits the console."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _open_browser_when_ready():
    """Open the local UI only after the packaged server is actually responding."""
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(LOCAL_URL, timeout=1.0) as response:
                if response.status == 200:
                    webbrowser.open(LOCAL_URL, new=1)
                    return
        except OSError:
            time.sleep(0.25)


def main():
    _ensure_windowed_streams()

    # CI sets this flag so the Windows smoke test does not launch a browser.
    if os.environ.get("AQORATH_NO_BROWSER") != "1":
        threading.Thread(
            target=_open_browser_when_ready,
            name="aqorath-browser-opener",
            daemon=True,
        ).start()
    run_local_surface()


if __name__ == "__main__":
    main()
