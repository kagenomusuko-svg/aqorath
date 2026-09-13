"""Android runtime adapter for the canonical Aqorath local product.

This module owns only Android process lifecycle and containment. It does not
implement accounting, fiscal, persistence or presentation rules.
"""

from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import socket
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

_ANDROID_HOST = "127.0.0.1"
_ANDROID_PORT = 8765
_ANDROID_URL = f"http://{_ANDROID_HOST}:{_ANDROID_PORT}/"
_ANDROID_CAPABILITIES_URL = f"{_ANDROID_URL}api/capabilities"
_SERVER = None
_SERVER_THREAD = None
_GUARD_INSTALLED = False

_ORIGINAL_SOCKET_CLASS = socket.socket
_ORIGINAL_CREATE_CONNECTION = socket.create_connection
_ORIGINAL_GETADDRINFO = socket.getaddrinfo


def _host_is_loopback(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="strict")
    text = str(host).strip().lower()
    if text == "localhost":
        return True
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _require_loopback_address(address) -> None:
    if isinstance(address, tuple) and address:
        host = address[0]
        if _host_is_loopback(host):
            return
    raise OSError("Aqorath Android blocks all non-loopback network destinations")


class _LoopbackOnlySocket(_ORIGINAL_SOCKET_CLASS):
    def connect(self, address):
        _require_loopback_address(address)
        return super().connect(address)

    def connect_ex(self, address):
        _require_loopback_address(address)
        return super().connect_ex(address)


def install_loopback_only_network_guard() -> None:
    """Fail closed on every Python outbound destination except loopback."""
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return

    def guarded_create_connection(address, *args, **kwargs):
        _require_loopback_address(address)
        return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if not _host_is_loopback(host):
            raise socket.gaierror(
                socket.EAI_NONAME,
                "Aqorath Android blocks external DNS resolution",
            )
        return _ORIGINAL_GETADDRINFO(host, *args, **kwargs)

    socket.socket = _LoopbackOnlySocket
    socket.create_connection = guarded_create_connection
    socket.getaddrinfo = guarded_getaddrinfo
    _GUARD_INSTALLED = True


def _configure_private_storage(files_dir: str) -> Path:
    root = Path(files_dir).resolve() / "aqorath"
    root.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(root)
    os.environ["AQORATH_DB"] = str(root / "aqorath.db")
    return root


def _assert_external_network_is_blocked() -> None:
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=0.05)
    except OSError as exc:
        if "blocks all non-loopback" not in str(exc):
            raise RuntimeError("Android network guard did not fail closed") from exc
    else:  # pragma: no cover - catastrophic guard regression
        raise RuntimeError("Android network guard allowed an external connection")


def _wait_until_ready(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urlopen(_ANDROID_URL, timeout=0.5) as response:  # noqa: S310 - fixed loopback URL
                if 200 <= response.status < 500:
                    return
        except (OSError, URLError) as exc:
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError("Aqorath Android local surface did not become ready") from last_error


def _assert_capabilities_surface() -> None:
    """Prove the canonical local API is reachable from inside Android itself."""
    try:
        with urlopen(_ANDROID_CAPABILITIES_URL, timeout=2.0) as response:  # noqa: S310 - fixed loopback URL
            if response.status != 200:
                raise RuntimeError(
                    f"Aqorath Android capabilities returned HTTP {response.status}"
                )
            payload = json.load(response)
    except (OSError, URLError, ValueError) as exc:
        raise RuntimeError(
            "Aqorath Android local capabilities surface is unavailable"
        ) from exc

    if not isinstance(payload, (dict, list)):
        raise RuntimeError("Aqorath Android capabilities payload has an unexpected shape")


def _self_test_canonical_modules() -> None:
    """Import authorities whose dependency closure must survive Android packaging."""
    from . import cfdi_source as _cfdi_source  # noqa: F401
    from . import fixed_asset_acquisition as _fixed_asset_acquisition  # noqa: F401
    from . import inventory_operations as _inventory_operations  # noqa: F401
    from . import recovery_infrastructure as _recovery_infrastructure  # noqa: F401
    from . import report_product_catalog as _report_product_catalog  # noqa: F401


def start(files_dir: str) -> str:
    """Start the one canonical Aqorath app inside Android private storage."""
    global _SERVER, _SERVER_THREAD
    if _SERVER_THREAD is not None and _SERVER_THREAD.is_alive():
        return _ANDROID_URL

    _configure_private_storage(files_dir)
    install_loopback_only_network_guard()
    _assert_external_network_is_blocked()

    from .local_server import load_local_app
    from .product_bootstrap import bootstrap_local_product
    import uvicorn

    bootstrap_local_product()
    _self_test_canonical_modules()

    config = uvicorn.Config(
        load_local_app(),
        host=_ANDROID_HOST,
        port=_ANDROID_PORT,
        log_level="warning",
        access_log=False,
    )
    _SERVER = uvicorn.Server(config)
    _SERVER_THREAD = threading.Thread(
        target=_SERVER.run,
        name="aqorath-android-local-server",
        daemon=True,
    )
    _SERVER_THREAD.start()
    _wait_until_ready()
    _assert_capabilities_surface()
    return _ANDROID_URL


def stop() -> None:
    global _SERVER, _SERVER_THREAD
    if _SERVER is not None:
        _SERVER.should_exit = True
    if _SERVER_THREAD is not None:
        _SERVER_THREAD.join(timeout=10.0)
    _SERVER = None
    _SERVER_THREAD = None


def diagnostics(files_dir: str) -> dict:
    root = _configure_private_storage(files_dir)
    return {
        "storage_root": str(root),
        "database": os.environ["AQORATH_DB"],
        "url": _ANDROID_URL,
        "network_policy": "loopback-only",
    }


__all__ = [
    "diagnostics",
    "install_loopback_only_network_guard",
    "start",
    "stop",
]
