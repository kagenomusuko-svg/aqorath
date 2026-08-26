"""Phase 4B.1 — explicit same-SQLite financial reporting source contracts."""

from decimal import Decimal
from inspect import signature

import pytest


def _catalog():
    return {
        "1101": {"tipo": "Activo", "subtipo": "Circulante", "naturaleza": "Deudora"},
        "1103": {"tipo": "Activo", "subtipo": "Circulante", "naturaleza": "Deudora"},
        "2101": {"tipo": "Pasivo", "subtipo": "Corto plazo", "naturaleza": "Acreedora"},
        "4201": {"tipo": "Ingreso", "subtipo": "Ventas", "naturaleza": "Acreedora"},
        "5102": {"tipo": "Gasto", "subtipo": "Operación", "naturaleza": "Deudora"},
    }


def _create_db(path):
    import sqlite3

    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(
            """
            CREATE TABLE account (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                nature TEXT NOT NULL,
                origin TEXT DEFAULT 'canonical',
                parent_id INTEGER
            );
            CREATE TABLE journalentry (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                concept TEXT
            );
            CREATE TABLE journalline (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER,
                account_code TEXT,
                account_id INTEGER,
                debit TEXT NOT NULL DEFAULT '0',
                credit TEXT NOT NULL DEFAULT '0'
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_reporting_source_public_contract_and_exact_signature_exist():
    import aqorath.reporting_source as source

    assert callable(source.build_financial_report_snapshot_from_sqlite)
    params = signature(source.build_financial_report_snapshot_from_sqlite).parameters
    assert list(params) == ["db_path", "catalog", "as_of"]
    assert params["as_of"].default is None


def test_reporting_source_reads_balances_and_account_identity_from_exact_same_explicit_db(tmp_path):
    import sqlite3
    import aqorath.reporting_source as source

    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    _create_db(db_a)
    _create_db(db_b)

    for path, bank_name, amount in (
        (db_a, "Banco A", "100.00"),
        (db_b, "Banco B", "999.00"),
    ):
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                "INSERT INTO account(id, code, name, nature) VALUES (1, '1101', ?, 'DEBIT')",
                (bank_name,),
            )
            conn.execute(
                "INSERT INTO journalentry(id, date, concept) VALUES (1, '2026-08-01', 'seed')"
            )
            conn.execute(
                "INSERT INTO journalline(entry_id, account_code, account_id, debit, credit) "
                "VALUES (1, '1101', 1, ?, '0')",
                (amount,),
            )
            conn.commit()
        finally:
            conn.close()

    snapshot = source.build_financial_report_snapshot_from_sqlite(db_a, _catalog())
    assert len(snapshot.lines) == 1
    assert snapshot.lines[0].account_name == "Banco A"
    assert snapshot.lines[0].ledger_balance == Decimal("100.00")


def test_reporting_source_real_sqlite_builds_exact_financial_snapshot(tmp_path):
    import sqlite3
    import aqorath.reporting_source as source

    db = tmp_path / "report.db"
    _create_db(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.executemany(
            "INSERT INTO account(id, code, name, nature) VALUES (?, ?, ?, ?)",
            [
                (1, "1101", "Bancos", "DEBIT"),
                (2, "2101", "Proveedores", "CREDIT"),
                (3, "4201", "Ventas", "CREDIT"),
                (4, "5102", "Servicios básicos", "DEBIT"),
            ],
        )
        conn.execute("INSERT INTO journalentry(id, date, concept) VALUES (1, '2026-08-01', 'seed')")
        conn.executemany(
            "INSERT INTO journalline(entry_id, account_code, account_id, debit, credit) VALUES (1, ?, ?, ?, ?)",
            [
                ("1101", 1, "150.00", "0"),
                ("2101", 2, "0", "40.00"),
                ("4201", 3, "0", "200.00"),
                ("5102", 4, "50.00", "0"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    snapshot = source.build_financial_report_snapshot_from_sqlite(db, _catalog())
    assert {line.account_code: line.normal_balance for line in snapshot.lines} == {
        "1101": Decimal("150.00"),
        "2101": Decimal("40.00"),
        "4201": Decimal("200.00"),
        "5102": Decimal("50.00"),
    }
    assert snapshot.result == Decimal("150.00")


def test_reporting_source_preserves_zero_balance_accounts_from_same_sqlite(tmp_path):
    import sqlite3
    import aqorath.reporting_source as source

    db = tmp_path / "zeros.db"
    _create_db(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.executemany(
            "INSERT INTO account(id, code, name, nature) VALUES (?, ?, ?, ?)",
            [
                (1, "1101", "Bancos", "DEBIT"),
                (2, "1103", "Clientes", "DEBIT"),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    snapshot = source.build_financial_report_snapshot_from_sqlite(db, _catalog())
    assert [line.account_code for line in snapshot.lines] == ["1101", "1103"]
    assert all(line.ledger_balance == Decimal("0") for line in snapshot.lines)


def test_reporting_source_preserves_entity_identity_and_parent_classification(tmp_path):
    import sqlite3
    import aqorath.reporting_source as source

    db = tmp_path / "entity.db"
    _create_db(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO account(id, code, name, nature, origin, parent_id) "
            "VALUES (1, '1101', 'Bancos', 'DEBIT', 'canonical', NULL)"
        )
        conn.execute(
            "INSERT INTO account(id, code, name, nature, origin, parent_id) "
            "VALUES (2, '1101.001', 'BBVA principal', 'DEBIT', 'entity', 1)"
        )
        conn.execute("INSERT INTO journalentry(id, date, concept) VALUES (1, '2026-08-01', 'seed')")
        conn.execute(
            "INSERT INTO journalline(entry_id, account_code, account_id, debit, credit) "
            "VALUES (1, '1101.001', 2, '321.45', '0')"
        )
        conn.commit()
    finally:
        conn.close()

    snapshot = source.build_financial_report_snapshot_from_sqlite(db, _catalog())
    by_code = {line.account_code: line for line in snapshot.lines}
    line = by_code["1101.001"]
    assert line.account_name == "BBVA principal"
    assert line.account_type == "Activo"
    assert line.account_subtype == "Circulante"
    assert line.normal_balance == Decimal("321.45")


def test_reporting_source_as_of_filters_same_database_and_is_preserved(tmp_path):
    import sqlite3
    import aqorath.reporting_source as source

    db = tmp_path / "as-of.db"
    _create_db(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("INSERT INTO account(id, code, name, nature) VALUES (1, '1101', 'Bancos', 'DEBIT')")
        conn.executemany(
            "INSERT INTO journalentry(id, date, concept) VALUES (?, ?, ?)",
            [
                (1, "2026-07-31T12:00:00", "before"),
                (2, "2026-08-01T12:00:00", "after"),
            ],
        )
        conn.executemany(
            "INSERT INTO journalline(entry_id, account_code, account_id, debit, credit) VALUES (?, '1101', 1, ?, '0')",
            [(1, "100.00"), (2, "50.00")],
        )
        conn.commit()
    finally:
        conn.close()

    snapshot = source.build_financial_report_snapshot_from_sqlite(
        db,
        _catalog(),
        as_of="2026-07-31",
    )
    assert snapshot.as_of == "2026-07-31"
    assert snapshot.lines[0].ledger_balance == Decimal("100.00")


def test_reporting_source_does_not_use_hidden_storage_path_or_trial_balance(monkeypatch, tmp_path):
    import sqlite3
    import aqorath.core as core
    import aqorath.reporting_source as source
    import aqorath.storage as storage

    db = tmp_path / "explicit.db"
    _create_db(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("INSERT INTO account(id, code, name, nature) VALUES (1, '1101', 'Bancos', 'DEBIT')")
        conn.commit()
    finally:
        conn.close()

    def forbidden(*args, **kwargs):
        raise AssertionError("hidden DB-path/trial-balance authority must not be consulted")

    monkeypatch.setattr(storage, "get_db_path", forbidden)
    monkeypatch.setattr(core, "_find_db_path", forbidden)
    monkeypatch.setattr(core, "trial_balance", forbidden)

    snapshot = source.build_financial_report_snapshot_from_sqlite(db, _catalog())
    assert snapshot.lines[0].account_code == "1101"


def test_reporting_source_rejects_missing_account_identity_table_or_classification(tmp_path):
    import sqlite3
    import aqorath.reporting_source as source

    missing_table = tmp_path / "missing-account.db"
    conn = sqlite3.connect(str(missing_table))
    try:
        conn.executescript(
            "CREATE TABLE journalentry(id INTEGER PRIMARY KEY, date TEXT);"
            "CREATE TABLE journalline(id INTEGER PRIMARY KEY, entry_id INTEGER, account_code TEXT, account_id INTEGER, debit TEXT, credit TEXT);"
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(Exception):
        source.build_financial_report_snapshot_from_sqlite(missing_table, _catalog())

    unclassified = tmp_path / "unclassified.db"
    _create_db(unclassified)
    conn = sqlite3.connect(str(unclassified))
    try:
        conn.execute("INSERT INTO account(id, code, name, nature) VALUES (1, '9999', 'Unknown', 'DEBIT')")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises((KeyError, LookupError, ValueError)):
        source.build_financial_report_snapshot_from_sqlite(unclassified, _catalog())


def test_reporting_source_is_read_only(tmp_path):
    import sqlite3
    import aqorath.reporting_source as source

    db = tmp_path / "readonly.db"
    _create_db(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("INSERT INTO account(id, code, name, nature) VALUES (1, '1101', 'Bancos', 'DEBIT')")
        conn.execute("INSERT INTO journalentry(id, date, concept) VALUES (1, '2026-08-01', 'seed')")
        conn.execute(
            "INSERT INTO journalline(id, entry_id, account_code, account_id, debit, credit) "
            "VALUES (1, 1, '1101', 1, '10.00', '0')"
        )
        conn.commit()
        before = {
            "account": conn.execute("SELECT COUNT(*) FROM account").fetchone()[0],
            "journalentry": conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0],
            "journalline": conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0],
        }
    finally:
        conn.close()

    source.build_financial_report_snapshot_from_sqlite(db, _catalog())

    conn = sqlite3.connect(str(db))
    try:
        after = {
            "account": conn.execute("SELECT COUNT(*) FROM account").fetchone()[0],
            "journalentry": conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0],
            "journalline": conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0],
        }
    finally:
        conn.close()
    assert after == before


def test_reporting_source_propagates_invalid_as_of_and_decimal_integrity_errors(tmp_path):
    import sqlite3
    import aqorath.reporting_source as source

    db = tmp_path / "errors.db"
    _create_db(db)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("INSERT INTO account(id, code, name, nature) VALUES (1, '1101', 'Bancos', 'DEBIT')")
        conn.execute("INSERT INTO journalentry(id, date, concept) VALUES (1, '2026-08-01', 'seed')")
        conn.execute(
            "INSERT INTO journalline(entry_id, account_code, account_id, debit, credit) "
            "VALUES (1, '1101', 1, 'not-money', '0')"
        )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(Exception):
        source.build_financial_report_snapshot_from_sqlite(db, _catalog())

    clean = tmp_path / "bad-date.db"
    _create_db(clean)
    conn = sqlite3.connect(str(clean))
    try:
        conn.execute("INSERT INTO account(id, code, name, nature) VALUES (1, '1101', 'Bancos', 'DEBIT')")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError):
        source.build_financial_report_snapshot_from_sqlite(
            clean,
            _catalog(),
            as_of="not-a-date",
        )
