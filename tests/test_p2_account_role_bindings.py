"""Phase 2D.1 — persistent Account Role Binding authority contracts.

SQLite is the sole authority. A binding stores role -> Account identity by account_id;
account_code is derived from the real Account and is never duplicated as persistent
binding state.
"""

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_account_bindings_module_exists():
    import aqorath.account_bindings


def test_account_bindings_public_contract_and_exact_signatures_exist():
    from inspect import Parameter, signature
    import aqorath.account_bindings as bindings

    for name in ("set_account_binding", "get_account_binding", "get_account_bindings"):
        assert hasattr(bindings, name)
        assert callable(getattr(bindings, name))

    expected = {
        "set_account_binding": ["session", "role", "account_code"],
        "get_account_binding": ["session", "role"],
        "get_account_bindings": ["session", "roles"],
    }
    for name, parameter_names in expected.items():
        sig = signature(getattr(bindings, name))
        assert list(sig.parameters) == parameter_names
        for parameter in sig.parameters.values():
            assert parameter.default is Parameter.empty
            assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
            assert parameter.kind not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD)


def test_account_role_binding_model_has_unique_role_and_account_foreign_key():
    from dataclasses import is_dataclass
    from aqorath.models import AccountRoleBinding

    table = AccountRoleBinding.__table__
    assert list(table.columns.keys()) == ["id", "role", "account_id", "created_at"]
    assert table.c.role.nullable is False
    assert table.c.role.unique is True
    assert table.c.account_id.nullable is False

    foreign_keys = list(table.c.account_id.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "account.id"
    assert "account_code" not in table.columns

    # SQLModel table classes are not dataclasses; this assertion prevents accidentally
    # freezing the persistence row as a parallel domain value object.
    assert not is_dataclass(AccountRoleBinding)


def test_account_role_binding_schema_is_versioned_and_created_for_fresh_database(tmp_path):
    from aqorath import migrations

    assert migrations.CURRENT_SCHEMA_VERSION >= 2
    assert 2 in migrations.MIGRATIONS

    db_path = tmp_path / "fresh-bindings.db"
    result = migrations.migrate_database(str(db_path))
    assert result["to_version"] == migrations.CURRENT_SCHEMA_VERSION
    assert migrations.get_schema_version(str(db_path)) == migrations.CURRENT_SCHEMA_VERSION

    conn = sqlite3.connect(str(db_path))
    try:
        columns = conn.execute("PRAGMA table_info(accountrolebinding)").fetchall()
        names = [row[1] for row in columns]
        assert names == ["id", "role", "account_id", "created_at"]

        indexes = conn.execute("PRAGMA index_list(accountrolebinding)").fetchall()
        assert any(row[2] == 1 for row in indexes), "role must have a UNIQUE index"

        foreign_keys = conn.execute("PRAGMA foreign_key_list(accountrolebinding)").fetchall()
        assert any(row[2] == "account" and row[3] == "account_id" and row[4] == "id" for row in foreign_keys)
    finally:
        conn.close()


def test_schema_v1_migrates_to_binding_schema_without_losing_existing_accounts(tmp_path):
    from aqorath import migrations

    db_path = tmp_path / "v1-bindings.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE account (
                id INTEGER PRIMARY KEY,
                code VARCHAR UNIQUE NOT NULL,
                name VARCHAR NOT NULL,
                nature VARCHAR NOT NULL,
                vat_flag BOOLEAN NOT NULL DEFAULT 0,
                origin VARCHAR NOT NULL DEFAULT 'canonical',
                parent_id INTEGER,
                created_at DATETIME
            )
        """)
        conn.execute(
            "INSERT INTO account (id, code, name, nature, origin) VALUES (1, '1101', 'Bancos', 'DEBIT', 'canonical')"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    finally:
        conn.close()

    result = migrations.migrate_database(str(db_path))
    assert result["from_version"] == 1
    assert result["to_version"] == migrations.CURRENT_SCHEMA_VERSION

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT id, code, name FROM account WHERE id = 1").fetchone()
        assert row == (1, "1101", "Bancos")
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='accountrolebinding'"
        ).fetchone()
        assert table == ("accountrolebinding",)
    finally:
        conn.close()


def test_set_account_binding_uses_supplied_session_catalog_and_persists_account_id(monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session, select
    import aqorath.catalog
    from aqorath.models import AccountRoleBinding
    from aqorath.account_bindings import set_account_binding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    calls = []

    account = SimpleNamespace(id=101, code="TEST-CASH-001", name="Caja principal")

    def resolver(session, code):
        calls.append((session, code))
        return account

    monkeypatch.setattr(aqorath.catalog, "resolve_account_by_code", resolver)

    with Session(engine) as session:
        result = set_account_binding(session, "cash", "TEST-CASH-001")
        assert result is None
        assert calls == [(session, "TEST-CASH-001")]

        rows = session.exec(select(AccountRoleBinding)).all()
        assert len(rows) == 1
        assert rows[0].role == "cash"
        assert rows[0].account_id == 101
        assert not hasattr(rows[0], "account_code")


def test_set_account_binding_rebinds_existing_role_without_duplicate_row(monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session, select
    import aqorath.catalog
    from aqorath.models import AccountRoleBinding
    from aqorath.account_bindings import set_account_binding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    accounts = {
        "CASH-A": SimpleNamespace(id=101, code="CASH-A", name="Caja A"),
        "CASH-B": SimpleNamespace(id=102, code="CASH-B", name="Caja B"),
    }
    monkeypatch.setattr(
        aqorath.catalog,
        "resolve_account_by_code",
        lambda session, code: accounts.get(code),
    )

    with Session(engine) as session:
        set_account_binding(session, "cash", "CASH-A")
        set_account_binding(session, "cash", "CASH-B")

        rows = session.exec(select(AccountRoleBinding)).all()
        assert len(rows) == 1
        assert rows[0].role == "cash"
        assert rows[0].account_id == 102


def test_get_account_binding_derives_current_code_from_account_and_missing_is_none():
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session
    from aqorath.models import Account, AccountRoleBinding
    from aqorath.account_bindings import get_account_binding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        account = Account(code="1101", name="Bancos", nature="DEBIT")
        session.add(account)
        session.commit()
        session.refresh(account)
        session.add(AccountRoleBinding(role="cash", account_id=account.id))
        session.commit()

        assert get_account_binding(session, "cash") == "1101"
        assert get_account_binding(session, "sales_revenue") is None


def test_get_account_bindings_returns_exact_requested_mapping_and_rejects_missing_role():
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session
    from aqorath.models import Account, AccountRoleBinding
    from aqorath.account_bindings import get_account_bindings

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        cash = Account(code="1101", name="Bancos", nature="DEBIT")
        sales = Account(code="4101", name="Ventas", nature="CREDIT")
        session.add(cash)
        session.add(sales)
        session.commit()
        session.refresh(cash)
        session.refresh(sales)
        session.add(AccountRoleBinding(role="cash", account_id=cash.id))
        session.add(AccountRoleBinding(role="sales_revenue", account_id=sales.id))
        session.commit()

        result = get_account_bindings(session, ("cash", "sales_revenue"))
        assert result == {"cash": "1101", "sales_revenue": "4101"}
        assert list(result) == ["cash", "sales_revenue"]

        with pytest.raises((KeyError, ValueError)):
            get_account_bindings(session, ("cash", "missing_role"))


def test_set_account_binding_rejects_invalid_role_or_missing_account_without_auto_creation(monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session, select
    import aqorath.catalog
    from aqorath.models import AccountRoleBinding
    from aqorath.account_bindings import set_account_binding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    def forbidden_create(*args, **kwargs):
        raise AssertionError("binding configuration must never auto-create accounts")

    monkeypatch.setattr(aqorath.catalog, "create_entity_account", forbidden_create)
    monkeypatch.setattr(aqorath.catalog, "resolve_account_by_code", lambda session, code: None)

    with Session(engine) as session:
        for invalid_role in ("", " cash ", None):
            with pytest.raises((TypeError, ValueError)):
                set_account_binding(session, invalid_role, "MISSING")

        with pytest.raises((LookupError, ValueError)):
            set_account_binding(session, "cash", "MISSING")

        assert session.exec(select(AccountRoleBinding)).all() == []


def test_account_bindings_use_only_supplied_session_without_json_or_direct_sqlite(monkeypatch):
    import importlib
    import sqlite3 as sqlite3_module
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session
    import aqorath.account_bindings as bindings
    import aqorath.storage
    import aqorath.config
    from aqorath.models import Account, AccountRoleBinding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        account = Account(code="1101", name="Bancos", nature="DEBIT")
        session.add(account)
        session.commit()
        session.refresh(account)
        session.add(AccountRoleBinding(role="cash", account_id=account.id))
        session.commit()

        def bomb(*args, **kwargs):
            raise AssertionError("binding authority must use only the supplied ORM session")

        with monkeypatch.context() as m:
            m.setattr(aqorath.storage, "get_session", bomb)
            m.setattr(aqorath.config, "_read_fallback_file", bomb)
            m.setattr(aqorath.config, "_write_fallback_file", bomb)
            m.setattr(sqlite3_module, "connect", bomb)
            bindings = importlib.reload(bindings)
            assert bindings.get_account_binding(session, "cash") == "1101"
        importlib.reload(bindings)


def test_set_account_binding_rolls_back_and_propagates_commit_failure(monkeypatch):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel, Session, select
    import aqorath.catalog
    from aqorath.models import AccountRoleBinding
    from aqorath.account_bindings import set_account_binding

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    account = SimpleNamespace(id=101, code="CASH-A", name="Caja A")
    monkeypatch.setattr(
        aqorath.catalog,
        "resolve_account_by_code",
        lambda session, code: account,
    )

    with Session(engine) as session:
        rollback_calls = []
        original_rollback = session.rollback
        error = RuntimeError("commit sentinel")

        def failing_commit():
            raise error

        def tracking_rollback():
            rollback_calls.append(True)
            return original_rollback()

        monkeypatch.setattr(session, "commit", failing_commit)
        monkeypatch.setattr(session, "rollback", tracking_rollback)

        with pytest.raises(RuntimeError) as exc_info:
            set_account_binding(session, "cash", "CASH-A")

        assert exc_info.value is error
        assert rollback_calls == [True]
        assert session.exec(select(AccountRoleBinding)).all() == []
