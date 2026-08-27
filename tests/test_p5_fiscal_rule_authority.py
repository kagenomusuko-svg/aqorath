"""Phase 5A.1 — versioned fiscal-rule authority contracts.

These contracts introduce only rule authority/resolution. They do not calculate
IVA/ISR, choose accounts, build accounting proposals, or migrate legacy templates.
"""

import sqlite3
from dataclasses import fields, FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal
from inspect import signature

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session


def _rule(**overrides):
    from aqorath.models import FiscalRuleVersion

    values = {
        "rule_key": "iva.general_rate",
        "jurisdiction": "MX",
        "regime": "general",
        "entity_type": "comercial",
        "effective_from": date(2024, 1, 1),
        "effective_to": date(2024, 12, 31),
        "value": "0.160000",
        "unit": "rate",
        "source_ref": "DOF:test-2024",
    }
    values.update(overrides)
    return FiscalRuleVersion(**values)


def _session(tmp_path, name="fiscal.db"):
    # Import the future model before create_all so metadata contains its table.
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    db = tmp_path / name
    engine = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def _context(**overrides):
    from aqorath.fiscal_rules import FiscalContext

    values = {
        "jurisdiction": "MX",
        "regime": "general",
        "entity_type": "comercial",
    }
    values.update(overrides)
    return FiscalContext(**values)


def test_fiscal_rule_public_contract_and_exact_signature_exist():
    import aqorath.fiscal_rules as fiscal_rules

    assert callable(fiscal_rules.resolve_fiscal_rule)
    assert list(signature(fiscal_rules.resolve_fiscal_rule).parameters) == [
        "session",
        "rule_key",
        "effective_date",
        "context",
    ]

    assert [field.name for field in fields(fiscal_rules.FiscalContext)] == [
        "jurisdiction",
        "regime",
        "entity_type",
    ]
    assert [field.name for field in fields(fiscal_rules.ResolvedFiscalRule)] == [
        "rule_key",
        "value",
        "unit",
        "effective_from",
        "effective_to",
        "jurisdiction",
        "regime",
        "entity_type",
        "source_ref",
    ]

    context = fiscal_rules.FiscalContext("MX", "general", "comercial")
    with pytest.raises(FrozenInstanceError):
        context.regime = "changed"


def test_fiscal_rule_model_and_fresh_schema_are_versioned_and_store_values_as_text(tmp_path):
    from aqorath import migrations
    from aqorath.models import FiscalRuleVersion

    assert migrations.CURRENT_SCHEMA_VERSION >= 3
    assert FiscalRuleVersion.__tablename__ == "fiscalruleversion"

    db = tmp_path / "fresh-v3.db"
    result = migrations.migrate_database(db)
    assert result["to_version"] == migrations.CURRENT_SCHEMA_VERSION
    assert migrations.get_schema_version(db) == migrations.CURRENT_SCHEMA_VERSION

    conn = sqlite3.connect(str(db))
    try:
        columns = {row[1]: row for row in conn.execute("PRAGMA table_info(fiscalruleversion)")}
        assert set(columns) >= {
            "id",
            "rule_key",
            "jurisdiction",
            "regime",
            "entity_type",
            "effective_from",
            "effective_to",
            "value",
            "unit",
            "source_ref",
            "created_at",
        }
        value_type = str(columns["value"][2]).upper()
        assert "REAL" not in value_type
        assert "FLOAT" not in value_type
        assert any(token in value_type for token in ("TEXT", "CHAR", "VARCHAR", "STRING"))
    finally:
        conn.close()


def test_schema_v2_migrates_to_fiscal_rule_schema_without_losing_existing_truth(tmp_path):
    from aqorath import migrations

    db = tmp_path / "v2.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(
            """
            CREATE TABLE account (
                id INTEGER PRIMARY KEY,
                code VARCHAR UNIQUE,
                name VARCHAR,
                nature VARCHAR,
                vat_flag BOOLEAN,
                origin VARCHAR,
                parent_id INTEGER,
                created_at DATETIME
            );
            CREATE TABLE accountrolebinding (
                id INTEGER PRIMARY KEY,
                role VARCHAR NOT NULL UNIQUE,
                account_id INTEGER NOT NULL,
                created_at DATETIME NOT NULL
            );
            INSERT INTO account(id, code, name, nature, vat_flag, origin, parent_id, created_at)
            VALUES (7, '1101.001', 'BBVA', 'DEBIT', 0, 'entity', NULL, '2026-01-01');
            INSERT INTO accountrolebinding(id, role, account_id, created_at)
            VALUES (3, 'bank', 7, '2026-01-02');
            PRAGMA user_version = 2;
            """
        )
        conn.commit()
    finally:
        conn.close()

    result = migrations.migrate_database(db)
    assert result["from_version"] == 2
    assert result["to_version"] == migrations.CURRENT_SCHEMA_VERSION
    assert migrations.get_schema_version(db) == migrations.CURRENT_SCHEMA_VERSION

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT code, name FROM account WHERE id = 7").fetchone() == (
            "1101.001",
            "BBVA",
        )
        assert conn.execute(
            "SELECT role, account_id FROM accountrolebinding WHERE id = 3"
        ).fetchone() == ("bank", 7)
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fiscalruleversion'"
        ).fetchone() == ("fiscalruleversion",)
    finally:
        conn.close()


def test_resolver_selects_historical_version_by_effective_date(tmp_path):
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        session.add(_rule(value="0.160000", source_ref="DOF:2024"))
        session.add(
            _rule(
                effective_from=date(2025, 1, 1),
                effective_to=None,
                value="0.170000",
                source_ref="DOF:2025",
            )
        )
        session.commit()

        old = resolve_fiscal_rule(session, "iva.general_rate", date(2024, 6, 30), _context())
        new = resolve_fiscal_rule(session, "iva.general_rate", date(2026, 6, 30), _context())

        assert old.value == Decimal("0.160000")
        assert old.source_ref == "DOF:2024"
        assert old.effective_from == date(2024, 1, 1)
        assert old.effective_to == date(2024, 12, 31)
        assert new.value == Decimal("0.170000")
        assert new.source_ref == "DOF:2025"
        assert new.effective_from == date(2025, 1, 1)
        assert new.effective_to is None
    finally:
        session.close()
        engine.dispose()


def test_resolver_uses_inclusive_boundaries_and_open_ended_versions(tmp_path):
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        session.add(_rule())
        session.add(
            _rule(
                effective_from=date(2025, 1, 1),
                effective_to=None,
                value="0.170000",
                source_ref="DOF:open",
            )
        )
        session.commit()

        assert resolve_fiscal_rule(
            session, "iva.general_rate", date(2024, 1, 1), _context()
        ).value == Decimal("0.160000")
        assert resolve_fiscal_rule(
            session, "iva.general_rate", date(2024, 12, 31), _context()
        ).value == Decimal("0.160000")
        assert resolve_fiscal_rule(
            session, "iva.general_rate", date(2099, 12, 31), _context()
        ).value == Decimal("0.170000")
    finally:
        session.close()
        engine.dispose()


def test_resolver_requires_exact_context_and_never_falls_back_to_other_regime_or_entity_type(tmp_path):
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        session.add(_rule(effective_to=None))
        session.add(
            _rule(
                regime="resico",
                effective_to=None,
                value="0.080000",
                source_ref="DOF:resico",
            )
        )
        session.commit()

        assert resolve_fiscal_rule(
            session,
            "iva.general_rate",
            date(2026, 1, 1),
            _context(regime="resico"),
        ).value == Decimal("0.080000")

        with pytest.raises(LookupError):
            resolve_fiscal_rule(
                session,
                "iva.general_rate",
                date(2026, 1, 1),
                _context(entity_type="sin_fines"),
            )
    finally:
        session.close()
        engine.dispose()


def test_resolver_missing_rule_or_date_fails_explicitly_without_latest_rule_fallback(tmp_path):
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        session.add(_rule(effective_from=date(2025, 1, 1), effective_to=None))
        session.commit()

        with pytest.raises(LookupError):
            resolve_fiscal_rule(session, "iva.missing", date(2026, 1, 1), _context())
        with pytest.raises(LookupError):
            resolve_fiscal_rule(session, "iva.general_rate", date(2024, 12, 31), _context())
    finally:
        session.close()
        engine.dispose()


def test_resolver_rejects_overlapping_applicable_versions_instead_of_picking_one(tmp_path):
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        session.add(_rule(effective_to=None, source_ref="DOF:A"))
        session.add(
            _rule(
                effective_from=date(2024, 6, 1),
                effective_to=None,
                value="0.170000",
                source_ref="DOF:B",
            )
        )
        session.commit()

        with pytest.raises(ValueError, match="ambiguous|overlap|multiple"):
            resolve_fiscal_rule(session, "iva.general_rate", date(2024, 7, 1), _context())
    finally:
        session.close()
        engine.dispose()


def test_resolved_rule_preserves_exact_decimal_and_full_provenance(tmp_path):
    from aqorath.fiscal_rules import ResolvedFiscalRule, resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        session.add(
            _rule(
                value="0.1234567890123456789012345678",
                unit="rate",
                source_ref="DOF:exact-source",
            )
        )
        session.commit()

        result = resolve_fiscal_rule(
            session, "iva.general_rate", date(2024, 7, 1), _context()
        )
        assert isinstance(result, ResolvedFiscalRule)
        assert result.rule_key == "iva.general_rate"
        assert result.value == Decimal("0.1234567890123456789012345678")
        assert result.unit == "rate"
        assert result.jurisdiction == "MX"
        assert result.regime == "general"
        assert result.entity_type == "comercial"
        assert result.source_ref == "DOF:exact-source"
        with pytest.raises(FrozenInstanceError):
            result.value = Decimal("9")
    finally:
        session.close()
        engine.dispose()


def test_resolver_uses_exact_supplied_session_and_does_not_open_hidden_database(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine_a, session_a = _session(tmp_path, "a.db")
    engine_b, session_b = _session(tmp_path, "b.db")
    try:
        session_a.add(_rule(value="0.111111", source_ref="A"))
        session_a.commit()
        session_b.add(_rule(value="0.222222", source_ref="B"))
        session_b.commit()

        def forbidden(*args, **kwargs):
            raise AssertionError("fiscal resolver must use only its supplied session")

        monkeypatch.setattr(storage, "get_session", forbidden)

        result_a = resolve_fiscal_rule(session_a, "iva.general_rate", date(2024, 7, 1), _context())
        result_b = resolve_fiscal_rule(session_b, "iva.general_rate", date(2024, 7, 1), _context())
        assert result_a.value == Decimal("0.111111")
        assert result_a.source_ref == "A"
        assert result_b.value == Decimal("0.222222")
        assert result_b.source_ref == "B"
    finally:
        session_a.close()
        session_b.close()
        engine_a.dispose()
        engine_b.dispose()

def test_resolver_validates_nominal_context_effective_date_and_nonempty_identity(tmp_path):
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        session.add(_rule())
        session.commit()

        with pytest.raises(TypeError):
            resolve_fiscal_rule(session, "iva.general_rate", "2024-07-01", _context())
        with pytest.raises(TypeError):
            resolve_fiscal_rule(session, "iva.general_rate", datetime(2024, 7, 1), _context())
        with pytest.raises(TypeError):
            resolve_fiscal_rule(session, "iva.general_rate", date(2024, 7, 1), {"regime": "general"})
        with pytest.raises(ValueError):
            resolve_fiscal_rule(session, "", date(2024, 7, 1), _context())
        with pytest.raises(ValueError):
            resolve_fiscal_rule(
                session,
                "iva.general_rate",
                date(2024, 7, 1),
                _context(jurisdiction=""),
            )
    finally:
        session.close()
        engine.dispose()


def test_resolver_fails_closed_on_invalid_persisted_decimal(tmp_path):
    from aqorath.fiscal_rules import resolve_fiscal_rule

    engine, session = _session(tmp_path)
    try:
        session.add(_rule(value="not-a-decimal"))
        session.commit()

        with pytest.raises((ValueError, ArithmeticError)):
            resolve_fiscal_rule(session, "iva.general_rate", date(2024, 7, 1), _context())
    finally:
        session.close()
        engine.dispose()


def test_resolver_is_read_only_and_does_not_call_legacy_tax_templates_or_config(tmp_path, monkeypatch):
    import aqorath.config as config
    import aqorath.tax as legacy_tax
    import aqorath.templates as templates
    from aqorath.fiscal_rules import resolve_fiscal_rule
    from aqorath.models import FiscalRuleVersion
    from sqlmodel import select

    engine, session = _session(tmp_path)
    try:
        session.add(_rule())
        session.commit()
        before = tuple(session.exec(select(FiscalRuleVersion)).all())

        def forbidden(*args, **kwargs):
            raise AssertionError("fiscal rule resolution must be read-only and authority-isolated")

        monkeypatch.setattr(legacy_tax, "calculate_taxes", forbidden)
        monkeypatch.setattr(templates, "get_template", forbidden)
        monkeypatch.setattr(config, "get_accounting_model", forbidden)
        monkeypatch.setattr(session, "add", forbidden)
        monkeypatch.setattr(session, "delete", forbidden)
        monkeypatch.setattr(session, "commit", forbidden)

        result = resolve_fiscal_rule(
            session, "iva.general_rate", date(2024, 7, 1), _context()
        )
        assert result.value == Decimal("0.160000")

        # Read through a separate session so the resolver cannot satisfy this check
        # by mutating only the in-memory identity map.
        with Session(engine) as verification:
            after = tuple(verification.exec(select(FiscalRuleVersion)).all())
        assert [(row.id, row.value, row.source_ref) for row in after] == [
            (row.id, row.value, row.source_ref) for row in before
        ]
    finally:
        session.close()
        engine.dispose()