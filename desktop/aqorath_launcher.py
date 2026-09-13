"""Aqorath desktop application launcher.

Starts the local Aqorath browser surface without requiring the user to know the
Python module entrypoint. This is the first layer used by Windows packaging.
"""

import threading
import time
import webbrowser

from aqorath.local_server import DEFAULT_PORT, run_local_surface



def open_browser():
    time.sleep(2)
    webbrowser.open(f"http://127.0.0.1:{DEFAULT_PORT}")



def main():
    threading.Thread(target=open_browser, daemon=True).start()
    run_local_surface()


if __name__ == "__main__":
    main()
