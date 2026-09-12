from pathlib import Path

import pytest


def test_android_runtime_accepts_only_loopback_destinations():
    import aqorath.android_runtime as android_runtime

    assert android_runtime._host_is_loopback("127.0.0.1") is True
    assert android_runtime._host_is_loopback("::1") is True
    assert android_runtime._host_is_loopback("localhost") is True
    assert android_runtime._host_is_loopback("8.8.8.8") is False
    assert android_runtime._host_is_loopback("example.com") is False

    android_runtime._require_loopback_address(("127.0.0.1", 8765))
    with pytest.raises(OSError, match="blocks all non-loopback"):
        android_runtime._require_loopback_address(("1.1.1.1", 443))


def test_android_runtime_places_database_under_private_files_root(tmp_path, monkeypatch):
    import aqorath.android_runtime as android_runtime

    monkeypatch.delenv("AQORATH_DB", raising=False)
    root = android_runtime._configure_private_storage(str(tmp_path))

    assert root == tmp_path.resolve() / "aqorath"
    assert Path(android_runtime.os.environ["AQORATH_DB"]) == root / "aqorath.db"
    assert Path(android_runtime.os.environ["HOME"]) == root


def test_android_shell_contains_no_remote_product_endpoint():
    root = Path(__file__).resolve().parents[1]
    activity = (
        root
        / "packaging/android/app/src/main/java/org/meriadock/aqorath/MainActivity.kt"
    ).read_text(encoding="utf-8")
    manifest = (
        root / "packaging/android/app/src/main/AndroidManifest.xml"
    ).read_text(encoding="utf-8")

    assert "127.0.0.1" in activity
    assert "localhost" in activity
    assert "AQORATH_ANDROID_NETWORK_GUARD=loopback-only" in activity
    assert "https://" not in activity
    assert "http://" not in activity
    assert "android.permission.INTERNET" in manifest
    assert "allowBackup=\"false\"" in manifest


def test_android_runtime_dependency_smoke_uses_canonical_modules():
    import inspect
    import aqorath.android_runtime as android_runtime

    source = inspect.getsource(android_runtime._self_test_canonical_modules)
    assert "cfdi_source" in source
    assert "fixed_asset_acquisition" in source
    assert "inventory_operations" in source
    assert "recovery_infrastructure" in source
    assert "report_product_catalog" in source
