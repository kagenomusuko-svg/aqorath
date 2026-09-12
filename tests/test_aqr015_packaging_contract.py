"""AQR-015 — source-tree contracts for the installable product package."""

from configparser import ConfigParser
from pathlib import Path
import sqlite3

import pytest
from sqlmodel import Session, select


REPO_ROOT = Path(__file__).resolve().parents[1]


def _setup_config():
    parser = ConfigParser()
    parser.read(REPO_ROOT / "setup.cfg", encoding="utf-8")
    return parser


def _expected_curated_fiscal_reference_data():
    from aqorath.fiscal_rule_data_mx import CURATED_MX_FISCAL_RULE_SETS
    from aqorath.fiscal_rule_set import materialize_fiscal_rule_set

    expected = []
    for manifest in CURATED_MX_FISCAL_RULE_SETS:
        for registration in materialize_fiscal_rule_set(manifest):
            expected.append(
                (
                    registration.rule_key,
                    registration.context.jurisdiction,
                    registration.context.regime,
                    registration.context.entity_type,
                    registration.effective_from,
                    str(registration.value),
                    registration.unit,
                    registration.source_ref,
                )
            )
    return sorted(expected)


def _persisted_fiscal_reference_data(engine):
    from aqorath.models import FiscalRuleVersion

    with Session(engine) as session:
        rows = session.exec(select(FiscalRuleVersion)).all()
    return sorted(
        (
            row.rule_key,
            row.jurisdiction,
            row.regime,
            row.entity_type,
            row.effective_from,
            row.value,
            row.unit,
            row.source_ref,
        )
        for row in rows
    )


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


def test_product_bootstrap_ensures_curated_fiscal_reference_data_idempotently(tmp_path, monkeypatch):
    from aqorath.product_bootstrap import bootstrap_local_product
    import aqorath.storage as storage

    db_path = tmp_path / "fiscal-reference.db"
    monkeypatch.setenv("AQORATH_DB", str(db_path))

    bootstrap_local_product()
    expected = _expected_curated_fiscal_reference_data()
    first = _persisted_fiscal_reference_data(storage.get_engine())
    assert first == expected

    bootstrap_local_product()
    second = _persisted_fiscal_reference_data(storage.get_engine())
    assert second == expected
    assert second == first

    storage.get_engine().dispose()


def test_product_bootstrap_rejects_conflicting_curated_fiscal_reference_data(tmp_path, monkeypatch):
    from aqorath.models import FiscalRuleVersion
    from aqorath.product_bootstrap import bootstrap_local_product
    import aqorath.storage as storage

    db_path = tmp_path / "fiscal-conflict.db"
    monkeypatch.setenv("AQORATH_DB", str(db_path))
    bootstrap_local_product()

    with Session(storage.get_engine()) as session:
        row = session.exec(
            select(FiscalRuleVersion).where(
                FiscalRuleVersion.rule_key == "iva.general_rate",
                FiscalRuleVersion.jurisdiction == "MX",
                FiscalRuleVersion.regime == "general",
                FiscalRuleVersion.entity_type == "comercial",
            )
        ).one()
        row.value = "0.99"
        session.add(row)
        session.commit()

    with pytest.raises(ValueError, match="conflicts with persisted history"):
        bootstrap_local_product()

    with Session(storage.get_engine()) as session:
        row = session.exec(
            select(FiscalRuleVersion).where(
                FiscalRuleVersion.rule_key == "iva.general_rate",
                FiscalRuleVersion.jurisdiction == "MX",
                FiscalRuleVersion.regime == "general",
                FiscalRuleVersion.entity_type == "comercial",
            )
        ).one()
        assert row.value == "0.99"

    storage.get_engine().dispose()


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
