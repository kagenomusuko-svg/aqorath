"""Native desktop shell for the already-canonical Aqorath localhost product.

This module owns only desktop lifecycle: bootstrap, local HTTP server lifetime and
one native webview window. It deliberately imports no accounting authorities.
"""

from __future__ import annotations

import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

from .local_server import DEFAULT_PORT, LOCAL_HOST, load_local_app
from .product_bootstrap import bootstrap_local_product
from .version import __version__

APP_TITLE = "Aqorath"
WINDOW_URL = f"http://{LOCAL_HOST}:{DEFAULT_PORT}/"
_STARTUP_TIMEOUT_SECONDS = 30.0


def _emit(message: str) -> None:
    """Write diagnostics only when the process owns a console stream."""
    if sys.stdout is not None:
        print(message)


def _wait_for_local_surface(*, timeout: float = _STARTUP_TIMEOUT_SECONDS) -> None:
    """Wait until the canonical loopback surface is accepting HTTP requests."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(WINDOW_URL, timeout=0.5) as response:  # noqa: S310 - fixed loopback URL
                if 200 <= response.status < 500:
                    return
        except (OSError, URLError) as exc:
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(
        "Aqorath no pudo iniciar su superficie local dentro del tiempo esperado."
    ) from last_error


def _self_test() -> int:
    """Non-GUI smoke used by native packaging CI."""
    bootstrap_local_product()
    app = load_local_app()
    if getattr(app, "title", None) != "Aqorath Local Surface":
        raise RuntimeError("canonical FastAPI surface was not materialized")
    _emit(f"Aqorath desktop shell {__version__}: OK")
    return 0


def _gui_import_test() -> int:
    """Verify the optional GUI dependency can be imported from the packaged app."""
    import webview  # noqa: F401

    _emit("Aqorath native GUI dependency: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Launch Aqorath as a desktop application without a terminal window."""
    args = list(sys.argv[1:] if argv is None else argv)
    if "--version" in args:
        _emit(__version__)
        return 0
    if "--self-test" in args:
        return _self_test()
    if "--gui-import-test" in args:
        return _gui_import_test()

    bootstrap_local_product()

    # GUI-only dependencies are intentionally lazy: the normal wheel/CLI remains
    # independent of the optional native installer toolchain.
    import uvicorn
    import webview

    config = uvicorn.Config(
        load_local_app(),
        host=LOCAL_HOST,
        port=DEFAULT_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(
        target=server.run,
        name="aqorath-local-server",
        daemon=True,
    )
    server_thread.start()

    try:
        _wait_for_local_surface()
        webview.create_window(
            APP_TITLE,
            WINDOW_URL,
            width=1280,
            height=820,
            min_size=(960, 640),
        )
        webview.start()
    finally:
        server.should_exit = True
        server_thread.join(timeout=10.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["APP_TITLE", "WINDOW_URL", "main"]
