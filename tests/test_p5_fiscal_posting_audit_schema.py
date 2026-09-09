"""Phase 5AE.1 — fiscal posting audit persistence schema contracts."""

import sqlite3
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select


_DECIMAL_TEXT_FIELDS = {
    "fact_amount",
    "base",
    "rate",
    "exact_fiscal_amount",
    "rounding_quantizer",
    "rounded_fiscal_amount",
    "omitted_zero_amount",
}

_EXPECTED_FIELDS = [
    "id",
    "entry_id",
    "fact_type",
    "fact_amount",
    "payment_method",
    "effective_date",
    "jurisdiction",
    "regime",
    "entity_type",
    "rule_key",
    "base",
    "rate",
    "unit",
    "rule_effective_from",
    "rule_effective_to",
    "rule_source_ref",
    "exact_fiscal_amount",
    "rounding_policy_key",
    "rounding_quantizer",
    "rounding_mode",
    "rounding_source_ref",
    "rounded_fiscal_amount",
    "amount_basis",
    "adjustment_role",
    "fiscal_role",
    "fiscal_side",
    "zero_fiscal_line_policy",
    "omitted_zero_account_role",
    "omitted_zero_account_id",
    "omitted_zero_account_code",
    "omitted_zero_account_name",
    "omitted_zero_side",
    "omitted_zero_amount",
    "created_at",
]


def _column_map(conn, table):
    return {row[1]: row for row in conn.execute(f"PRAGMA table_info({table})")}


def _is_text_type(declared_type):
    declared = str(declared_type).upper()
    return (
        "REAL" not in declared
        and "FLOAT" not in declared
        and any(token in declared for token in ("TEXT", "CHAR", "VARCHAR", "STRING"))
    )


def _audit_record(entry_id, **overrides):
    from aqorath.models import FiscalPostingAuditRecord

    values = {
        "entry_id": entry_id,
        "fact_type": "sale",
        "fact_amount": "100.00",
        "payment_method": "cash",
        "effective_date": date(2026, 8, 27),
        "jurisdiction": "MX",
        "regime": "general",
        "entity_type": "commercial",
        "rule_key": "iva.general_rate",
        "base": "100.00",
        "rate": "0.1600",
        "unit": "rate",
        "rule_effective_from": date(2010, 1, 1),
        "rule_effective_to": None,
        "rule_source_ref": "CURATED:IVA",
        "exact_fiscal_amount": "16.0000",
        "rounding_policy_key": "two-decimals",
        "rounding_quantizer": "0.01",
        "rounding_mode": "ROUND_HALF_UP",
        "rounding_source_ref": "EXPLICIT:TEST",
        "rounded_fiscal_amount": "16.00",
        "amount_basis": "net_before_fiscal",
        "adjustment_role": "cash",
        "fiscal_role": "tax_payable",
        "fiscal_side": "credit",
        "zero_fiscal_line_policy": "reject_zero_fiscal_line",
        "omitted_zero_account_role": None,
        "omitted_zero_account_id": None,
        "omitted_zero_account_code": None,
        "omitted_zero_account_name": None,
        "omitted_zero_side": None,
        "omitted_zero_amount": None,
    }
    values.update(overrides)
    return FiscalPostingAuditRecord(**values)


def test_audit_record_model_and_schema_version_contract_exist():
    from aqorath import migrations
    from aqorath.models import FiscalPostingAuditRecord

    assert migrations.CURRENT_SCHEMA_VERSION in migrations.MIGRATIONS
    assert 4 in migrations.MIGRATIONS
    assert FiscalPostingAuditRecord.__tablename__ == "fiscalpostingauditrecord"
    assert list(FiscalPostingAuditRecord.model_fields) == _EXPECTED_FIELDS


def test_fresh_v4_schema_has_exact_audit_columns_and_decimal_text_authority(tmp_path):
    from aqorath import migrations

    db = tmp_path / "fresh-v4.db"
    result = migrations.migrate_database(db)
    assert result["from_version"] == 0
    assert result["to_version"] == migrations.CURRENT_SCHEMA_VERSION
    assert migrations.get_schema_version(db) == migrations.CURRENT_SCHEMA_VERSION

    conn = sqlite3.connect(str(db))
    try:
        columns = _column_map(conn, "fiscalpostingauditrecord")
        assert list(columns) == _EXPECTED_FIELDS
        for field in _DECIMAL_TEXT_FIELDS:
            assert _is_text_type(columns[field][2]), (field, columns[field][2])

        for required in (
            "entry_id",
            "fact_type",
            "fact_amount",
            "payment_method",
            "effective_date",
            "jurisdiction",
            "regime",
            "entity_type",
            "rule_key",
            "base",
            "rate",
            "unit",
            "rule_effective_from",
            "rule_source_ref",
            "exact_fiscal_amount",
            "rounding_policy_key",
            "rounding_quantizer",
            "rounding_mode",
            "rounding_source_ref",
            "rounded_fiscal_amount",
            "amount_basis",
            "adjustment_role",
            "fiscal_role",
            "fiscal_side",
            "zero_fiscal_line_policy",
            "created_at",
        ):
            assert columns[required][3] == 1, required

        for optional in (
            "rule_effective_to",
            "omitted_zero_account_role",
            "omitted_zero_account_id",
            "omitted_zero_account_code",
            "omitted_zero_account_name",
            "omitted_zero_side",
            "omitted_zero_amount",
        ):
            assert columns[optional][3] == 0, optional
    finally:
        conn.close()


def test_audit_schema_is_metadata_only_and_does_not_duplicate_accounting_truth(tmp_path):
    from aqorath import migrations

    db = tmp_path / "metadata-only.db"
    migrations.migrate_database(db)
    conn = sqlite3.connect(str(db))
    try:
        columns = set(_column_map(conn, "fiscalpostingauditrecord"))
        assert "description" not in columns
        assert "concept" not in columns
        assert "debit" not in columns
        assert "credit" not in columns
        assert "account_bindings" not in columns
        assert "posting_lines" not in columns
    finally:
        conn.close()


def test_audit_entry_relation_is_one_to_one_foreign_key_to_journalentry(tmp_path):
    from aqorath import migrations

    db = tmp_path / "relation.db"
    migrations.migrate_database(db)
    conn = sqlite3.connect(str(db))
    try:
        fks = conn.execute("PRAGMA foreign_key_list(fiscalpostingauditrecord)").fetchall()
        assert any(row[2] == "journalentry" and row[3] == "entry_id" and row[4] == "id" for row in fks)

        indexes = conn.execute("PRAGMA index_list(fiscalpostingauditrecord)").fetchall()
        unique_indexes = [row for row in indexes if row[2] == 1]
        assert unique_indexes
        unique_columns = {
            tuple(
                column[2]
                for column in conn.execute(f"PRAGMA index_info({row[1]})").fetchall()
            )
            for row in unique_indexes
        }
        assert ("entry_id",) in unique_columns
    finally:
        conn.close()


def test_schema_v3_migrates_to_v4_without_losing_existing_accounting_or_fiscal_truth(tmp_path):
    from aqorath import migrations

    db = tmp_path / "v3.db"
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
            CREATE TABLE fiscalruleversion (
                id INTEGER PRIMARY KEY,
                rule_key VARCHAR NOT NULL,
                jurisdiction VARCHAR NOT NULL,
                regime VARCHAR NOT NULL,
                entity_type VARCHAR NOT NULL,
                effective_from DATE NOT NULL,
                effective_to DATE,
                value TEXT NOT NULL,
                unit VARCHAR NOT NULL,
                source_ref VARCHAR NOT NULL,
                created_at DATETIME NOT NULL
            );
            CREATE TABLE journalentry (
                id INTEGER PRIMARY KEY,
                date DATETIME NOT NULL,
                concept VARCHAR,
                doc_ref VARCHAR,
                period_id INTEGER,
                posted_by VARCHAR,
                state VARCHAR NOT NULL,
                created_at DATETIME NOT NULL
            );
            CREATE TABLE journalline (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER,
                account_code VARCHAR,
                account_id INTEGER,
                debit TEXT NOT NULL,
                credit TEXT NOT NULL,
                description VARCHAR,
                created_at DATETIME
            );
            INSERT INTO account VALUES (7, '1102', 'Caja chica', 'DEBIT', 0, 'canonical', NULL, '2026-01-01');
            INSERT INTO accountrolebinding VALUES (3, 'cash', 7, '2026-01-02');
            INSERT INTO fiscalruleversion VALUES (
                9, 'iva.general_rate', 'MX', 'general', 'commercial',
                '2010-01-01', NULL, '0.1600', 'rate', 'CURATED:IVA', '2026-01-03'
            );
            INSERT INTO journalentry VALUES (
                11, '2026-08-27', 'Venta confirmada', NULL, NULL, NULL, 'posted', '2026-08-27'
            );
            INSERT INTO journalline VALUES (
                12, 11, '1102', 7, '116.00', '0', NULL, '2026-08-27'
            );
            PRAGMA user_version = 3;
            """
        )
        conn.commit()
    finally:
        conn.close()

    result = migrations.migrate_database(db)
    assert result["from_version"] == 3
    assert result["to_version"] == migrations.CURRENT_SCHEMA_VERSION
    assert migrations.get_schema_version(db) == migrations.CURRENT_SCHEMA_VERSION

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT code, name FROM account WHERE id=7").fetchone() == ("1102", "Caja chica")
        assert conn.execute("SELECT role, account_id FROM accountrolebinding WHERE id=3").fetchone() == ("cash", 7)
        assert conn.execute("SELECT value, source_ref FROM fiscalruleversion WHERE id=9").fetchone() == ("0.1600", "CURATED:IVA")
        assert conn.execute("SELECT concept FROM journalentry WHERE id=11").fetchone() == ("Venta confirmada",)
        assert conn.execute("SELECT debit, credit FROM journalline WHERE id=12").fetchone() == ("116.00", "0")
        assert conn.execute("SELECT COUNT(*) FROM fiscalpostingauditrecord").fetchone() == (0,)
    finally:
        conn.close()


def test_migration_does_not_backfill_or_invent_audit_records_for_historical_entries(tmp_path):
    from aqorath import migrations

    db = tmp_path / "no-invent.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(
            """
            CREATE TABLE journalentry (
                id INTEGER PRIMARY KEY,
                date DATETIME NOT NULL,
                concept VARCHAR,
                doc_ref VARCHAR,
                period_id INTEGER,
                posted_by VARCHAR,
                state VARCHAR NOT NULL,
                created_at DATETIME NOT NULL
            );
            INSERT INTO journalentry VALUES (1, '2026-01-01', 'Histórico', NULL, NULL, NULL, 'posted', '2026-01-01');
            PRAGMA user_version = 3;
            """
        )
        conn.commit()
    finally:
        conn.close()

    migrations.migrate_database(db)
    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM journalentry").fetchone() == (1,)
        assert conn.execute("SELECT COUNT(*) FROM fiscalpostingauditrecord").fetchone() == (0,)
    finally:
        conn.close()


def test_audit_record_round_trip_preserves_exact_decimal_text_and_null_omission(tmp_path):
    from aqorath.models import FiscalPostingAuditRecord, JournalEntry

    db = tmp_path / "round-trip.db"
    engine = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            entry = JournalEntry(
                date=datetime(2026, 8, 27, tzinfo=timezone.utc),
                concept="Venta fiscalizada confirmada",
                state="posted",
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)

            record = _audit_record(
                entry.id,
                fact_amount="12345678901234567890.0100",
                base="0.1000",
                rate="0.160000",
                exact_fiscal_amount="0.0160000",
                rounding_quantizer="0.010",
                rounded_fiscal_amount="0.02",
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            record_id = record.id

        with Session(engine) as session:
            loaded = session.exec(
                select(FiscalPostingAuditRecord).where(FiscalPostingAuditRecord.id == record_id)
            ).one()
            assert loaded.fact_amount == "12345678901234567890.0100"
            assert loaded.base == "0.1000"
            assert loaded.rate == "0.160000"
            assert loaded.exact_fiscal_amount == "0.0160000"
            assert loaded.rounding_quantizer == "0.010"
            assert loaded.rounded_fiscal_amount == "0.02"
            assert loaded.omitted_zero_account_role is None
            assert loaded.omitted_zero_account_id is None
            assert loaded.omitted_zero_account_code is None
            assert loaded.omitted_zero_account_name is None
            assert loaded.omitted_zero_side is None
            assert loaded.omitted_zero_amount is None
    finally:
        engine.dispose()


def test_audit_record_can_preserve_explicit_omitted_zero_line_metadata(tmp_path):
    from aqorath.models import FiscalPostingAuditRecord, JournalEntry

    db = tmp_path / "zero-omission.db"
    engine = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            entry = JournalEntry(
                date=datetime(2026, 8, 27, tzinfo=timezone.utc),
                concept="Venta tasa cero confirmada",
                state="posted",
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)

            record = _audit_record(
                entry.id,
                rate="0.00",
                exact_fiscal_amount="0.00",
                rounded_fiscal_amount="0.00",
                zero_fiscal_line_policy="omit_confirmed_zero_fiscal_line",
                omitted_zero_account_role="tax_payable",
                omitted_zero_account_id=88,
                omitted_zero_account_code="2103",
                omitted_zero_account_name="Impuestos por pagar",
                omitted_zero_side="credit",
                omitted_zero_amount="0.00",
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            record_id = record.id

        with Session(engine) as session:
            loaded = session.get(FiscalPostingAuditRecord, record_id)
            assert loaded.zero_fiscal_line_policy == "omit_confirmed_zero_fiscal_line"
            assert loaded.omitted_zero_account_role == "tax_payable"
            assert loaded.omitted_zero_account_id == 88
            assert loaded.omitted_zero_account_code == "2103"
            assert loaded.omitted_zero_account_name == "Impuestos por pagar"
            assert loaded.omitted_zero_side == "credit"
            assert loaded.omitted_zero_amount == "0.00"
    finally:
        engine.dispose()


def test_one_journal_entry_cannot_have_two_audit_records(tmp_path):
    from aqorath.models import JournalEntry

    db = tmp_path / "unique-entry.db"
    engine = create_engine(f"sqlite:///{db}")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            entry = JournalEntry(
                date=datetime(2026, 8, 27, tzinfo=timezone.utc),
                concept="Venta",
                state="posted",
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)

            session.add(_audit_record(entry.id))
            session.commit()
            session.add(_audit_record(entry.id, rule_source_ref="DUPLICATE"))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_v4_migration_is_idempotent_and_preserves_existing_audit_rows(tmp_path):
    from aqorath import migrations
    from aqorath.models import FiscalPostingAuditRecord, JournalEntry

    db = tmp_path / "idempotent-v4.db"
    migrations.migrate_database(db)
    engine = create_engine(f"sqlite:///{db}")
    try:
        with Session(engine) as session:
            entry = JournalEntry(
                date=datetime(2026, 8, 27, tzinfo=timezone.utc),
                concept="Venta",
                state="posted",
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            session.add(_audit_record(entry.id))
            session.commit()

        result = migrations.migrate_database(db)
        assert result == {
            "from_version": migrations.CURRENT_SCHEMA_VERSION,
            "to_version": migrations.CURRENT_SCHEMA_VERSION,
            "migrated": False,
            "backup_path": None,
        }

        with Session(engine) as session:
            records = session.exec(select(FiscalPostingAuditRecord)).all()
            assert len(records) == 1
            assert records[0].fact_amount == "100.00"
            assert records[0].rounded_fiscal_amount == "16.00"
    finally:
        engine.dispose()


def test_migration_registry_v4_failure_does_not_advance_schema_version(tmp_path, monkeypatch):
    from aqorath import migrations

    db = tmp_path / "failed-v4.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE sentinel (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sentinel(value) VALUES ('preserve-me')")
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
    finally:
        conn.close()

    original = migrations.MIGRATIONS[4]

    def fail(path):
        conn = sqlite3.connect(str(path))
        try:
            conn.execute("CREATE TABLE should_rollback (id INTEGER)")
            conn.commit()
        finally:
            conn.close()
        raise RuntimeError("v4 migration failed")

    monkeypatch.setitem(migrations.MIGRATIONS, 4, fail)
    with pytest.raises(RuntimeError, match="v4 migration failed"):
        migrations.migrate_database(db)

    assert migrations.get_schema_version(db) == 3
    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT value FROM sentinel").fetchone() == ("preserve-me",)
    finally:
        conn.close()

    monkeypatch.setitem(migrations.MIGRATIONS, 4, original)
