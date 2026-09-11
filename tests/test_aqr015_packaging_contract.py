"""AQR-015 — source-tree contracts for the installable product package."""

from configparser import ConfigParser
from pathlib import Path
import sqlite3


REPO_ROOT = Path(__file__).resolve().parents[1]


def _setup_config():
    parser = ConfigParser()
    parser.read(REPO_ROOT / "setup.cfg", encoding="utf-8")
    return parser


def test_packaging_declares_runtime_dependencies_entry_point_and_package_data():
    cfg = _setup_config()

    assert cfg["metadata"]["version"].strip() == "attr: aqorath.version.__version__"
    install_requires = cfg["options"]["install_requires"].lower()
    for required in (
        "openpyxl",
        "reportlab",
        "lxml",
        "sqlmodel",
        "sqlalchemy",
        "fastapi",
        "uvicorn",
    ):
        assert required in install_requires

    for development_only in (
        "pytest",
        "pyinstaller",
        "pandas",
        "python-dateutil",
        "requests",
    ):
        assert development_only not in install_requires

    assert (
        "aqorath = aqorath.entrypoint:main"
        in cfg["options.entry_points"]["console_scripts"]
    )
    assert "data/*.json" in cfg["options.package_data"]["aqorath"]


def test_runtime_catalog_resolves_from_package_not_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from aqorath.accounting_rules import load_catalog as load_rules_catalog
    from aqorath.catalog import get_catalog_path, load_catalog

    catalog_path = get_catalog_path()
    assert catalog_path.is_file()
    document = load_catalog()
    assert document.get("accounts")
    assert load_rules_catalog()


def test_product_bootstrap_creates_parent_and_uses_current_migration_authority(tmp_path, monkeypatch):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION
    from aqorath.product_bootstrap import bootstrap_local_product
    import aqorath.storage as storage

    db_path = tmp_path / "nested" / "local-data" / "aqorath.db"
    monkeypatch.setenv("AQORATH_DB", str(db_path))

    result = bootstrap_local_product()
    try:
        assert Path(result.db_path) == db_path.resolve()
        assert result.schema_version == CURRENT_SCHEMA_VERSION
        assert db_path.is_file()
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == CURRENT_SCHEMA_VERSION
    finally:
        engine = storage.get_engine()
        engine.dispose()


def test_console_entrypoint_is_only_bootstrap_then_existing_launcher(monkeypatch):
    import aqorath.entrypoint as entrypoint

    calls = []
    monkeypatch.setattr(
        entrypoint,
        "bootstrap_local_product",
        lambda: calls.append("bootstrap"),
    )
    monkeypatch.setattr(
        entrypoint,
        "run_local_surface",
        lambda: calls.append("launcher"),
    )

    entrypoint.main()
    assert calls == ["bootstrap", "launcher"]
