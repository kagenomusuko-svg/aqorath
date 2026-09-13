"""Aqorath Windows desktop application entrypoint."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser


def _ensure_windowed_streams() -> None:
    """Provide writable streams when PyInstaller --windowed omits the console."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _runtime_data_root() -> Path:
    """Return a writable, platform-appropriate local application data directory."""
    override = os.environ.get("AQORATH_DATA_DIR")
    if override:
        root = Path(override).expanduser().resolve()
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = (Path(base) if base else Path.home() / "AppData" / "Local") / "Aqorath"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "Aqorath"
    else:
        base = os.environ.get("XDG_DATA_HOME")
        root = (Path(base) if base else Path.home() / ".local" / "share") / "aqorath"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _configure_runtime_paths() -> Path:
    """Set writable runtime authorities before importing persistence modules."""
    root = _runtime_data_root()
    os.environ.setdefault("AQORATH_DATA_DIR", str(root))
    os.environ.setdefault("AQORATH_DB", str(root / "aqorath.db"))
    Path(os.environ["AQORATH_DB"]).parent.mkdir(parents=True, exist_ok=True)
    return root


def _decorate_web_surfaces() -> None:
    """Apply the desktop layout without changing application/accounting contracts."""
    from aqorath import inventory_web_assets, web_assets
    from aqorath.desktop_shell import desktopize_inventory, desktopize_main

    web_assets.APP_HTML = desktopize_main(web_assets.APP_HTML)
    inventory_web_assets.INVENTORY_HTML = desktopize_inventory(
        inventory_web_assets.INVENTORY_HTML
    )


def _find_edge() -> Path | None:
    if sys.platform != "win32":
        return None
    candidates = []
    for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env_name)
        if not base:
            continue
        base_path = Path(base)
        if env_name == "LOCALAPPDATA":
            candidates.append(base_path / "Microsoft" / "Edge" / "Application" / "msedge.exe")
        else:
            candidates.append(base_path / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    return next((path for path in candidates if path.exists()), None)


_ensure_windowed_streams()
_DATA_ROOT = _configure_runtime_paths()
_decorate_web_surfaces()

# Import only after the runtime path and desktop presentation have been established.
from aqorath.local_server import DEFAULT_PORT, LOCAL_HOST, run_local_surface  # noqa: E402

LOCAL_URL = f"http://{LOCAL_HOST}:{DEFAULT_PORT}/?module=operations"


def _wait_until_ready(timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(LOCAL_URL, timeout=1.0) as response:
                if response.status == 200:
                    return True
        except OSError:
            time.sleep(0.25)
    return False


def _open_desktop_window_when_ready() -> None:
    """Open Aqorath as a dedicated app window after the local server is ready."""
    if not _wait_until_ready():
        return

    edge = _find_edge()
    if edge is None:
        webbrowser.open(LOCAL_URL, new=1)
        return

    profile = _DATA_ROOT / "desktop-profile"
    profile.mkdir(parents=True, exist_ok=True)
    command = [
        str(edge),
        f"--app={LOCAL_URL}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
    ]
    try:
        process = subprocess.Popen(command)
        process.wait()
        os._exit(0)
    except OSError:
        webbrowser.open(LOCAL_URL, new=1)


def main() -> None:
    # CI and diagnostics suppress the graphical window but exercise the same packaged server.
    if os.environ.get("AQORATH_NO_BROWSER") != "1":
        threading.Thread(
            target=_open_desktop_window_when_ready,
            name="aqorath-desktop-window",
            daemon=True,
        ).start()
    run_local_surface()


if __name__ == "__main__":
    main()
