"""AQR-006 operational receivable/payable subledger acceptance tests.

The tests deliberately assert that money remains authoritative in JournalLine and
that OpenItem/OpenItemApplication persist relationships only.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect
from sqlmodel import Session, select


def _create_schema_6_fixture(db_path):
    """Materialize frozen historical DDL, independent of all runtime metadata."""
    from pathlib import Path

    snapshot = Path(__file__).parent / "fixtures" / "schema6.sql"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(snapshot.read_text())


def _seed_runtime(tmp_path, monkeypatch, name="aqr006.db"):
    import aqorath.storage as storage
    import aqorath.core  # Bind legacy imports before the temporary session factory.
    from aqorath import migrations
    from aqorath.models import (
        Account,
        AccountRoleBinding,
        EntityRecord,
        EntityProfileRecord,
        ThirdPartyRecord,
    )

    db_path = tmp_path / name
    migrations.migrate_database(db_path)
    engine = create_engine(f"sqlite:///{db_path}")

    with Session(engine) as session:
        from aqorath.entity import Entity, EntityProfile
        from aqorath.entity_repository import create_entity
        entity = create_entity(session, Entity(
            None, "Entidad AQR006", "AAA010101AAA", "persona_moral", "A.C.",
            EntityProfile("no_lucrativo", False, (), ()), True,
        ))

        accounts = {
            "bank": Account(code="1101", name="Bancos", nature="DEBIT"),
            "accounts_receivable": Account(code="1103", name="Clientes", nature="DEBIT"),
            "sales_revenue": Account(code="4201", name="Ingresos", nature="CREDIT"),
            "utilities_expense": Account(code="5102", name="Servicios", nature="DEBIT"),
            "accounts_payable": Account(code="2101", name="Proveedores", nature="CREDIT"),
        }
        for account in accounts.values():
            session.add(account)
        session.commit()
        for account in accounts.values():
            session.refresh(account)
        for role, account in accounts.items():
            session.add(AccountRoleBinding(role=role, account_id=account.id))
        customer = ThirdPartyRecord(
            entity_id=entity.id,
            name="Ana Cliente",
            rfc=None,
            email=None,
            phone=None,
            party_type="customer",
            address=None,
            contact_person=None,
            notes=None,
            is_active=True,
        )
        supplier = ThirdPartyRecord(
            entity_id=entity.id,
            name="Proveedor Uno",
            rfc=None,
            email=None,
            phone=None,
            party_type="supplier",
            address=None,
            contact_person=None,
            notes=None,
            is_active=True,
        )
        session.add(customer)
        session.add(supplier)
        session.commit()
        session.refresh(customer)
        session.refresh(supplier)
        entity_id = entity.id
        customer_id = customer.id
        supplier_id = supplier.id

    # AQR-002 calendar authority is seeded by the shared test fixture helper.
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)

    monkeypatch.setattr(storage, "get_session", lambda: Session(engine))
    return engine, db_path, entity_id, customer_id, supplier_id


def _origin(kind, party_id, amount, posting_date, due_date, number):
    import aqorath.subledger_operations as ops
    import aqorath.storage as storage

    operation_key = "sale_credit" if kind == "receivable" else "utility_credit"
    with storage.get_session() as session:
        prepared = ops.prepare_open_item_origin(
            session,
            operation_key,
            Decimal(amount),
            posting_date,
            party_id,
            due_date,
            "invoice",
            number,
            posting_date,
        )
    return ops.execute_open_item_origin(ops.confirm_open_item_origin(prepared))


def _application(open_item_id, amount, posting_date, number):
    import aqorath.subledger_operations as ops
    import aqorath.storage as storage

    with storage.get_session() as session:
        prepared = ops.prepare_open_item_application(
            session,
            open_item_id,
            Decimal(amount),
            posting_date,
            "payment",
            number,
            posting_date,
        )
    return ops.execute_open_item_application(ops.confirm_open_item_application(prepared))


def test_schema_7_relationship_only_tables_and_no_money_columns(tmp_path, monkeypatch):
    from aqorath import migrations
    from aqorath.open_item_models import OpenItemApplicationRecord, OpenItemRecord

    engine, db_path, *_ = _seed_runtime(tmp_path, monkeypatch, "schema7.db")
    assert migrations.CURRENT_SCHEMA_VERSION >= 7
    assert migrations.get_schema_version(db_path) == migrations.CURRENT_SCHEMA_VERSION

    inspector = sa_inspect(engine)
    assert set(column["name"] for column in inspector.get_columns("openitem")) == {
        "id", "entity_id", "third_party_id", "kind", "source_entry_id",
        "source_line_id", "source_document_reference_id", "due_date", "created_at",
    }
    assert set(column["name"] for column in inspector.get_columns("openitemapplication")) == {
        "id", "open_item_id", "application_entry_id", "application_line_id",
        "application_document_reference_id", "created_at",
    }
    forbidden = {
        "amount", "original_amount", "applied_amount", "open_balance", "balance",
        "status", "settled", "cancelled", "aging", "aging_bucket",
    }
    assert forbidden.isdisjoint(OpenItemRecord.__table__.columns.keys())
    assert forbidden.isdisjoint(OpenItemApplicationRecord.__table__.columns.keys())


def test_schema_6_to_7_does_not_invent_historical_provenance(tmp_path):
    from aqorath import migrations

    db = tmp_path / "historical-v6.db"
    _create_schema_6_fixture(db)

    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert {
            "account", "journalentry", "journalline", "fiscalpostingauditrecord",
            "accountingcalendar", "fiscalyear", "accountingperiod",
            "journalentryreversal", "thirdparty", "documentreference", "auditevent",
        }.issubset(tables)
        assert "openitem" not in tables
        assert "openitemapplication" not in tables
        historical_tables = tables.copy()
        historical_schema = conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        ).fetchall()
        assert {r[1] for r in conn.execute("PRAGMA table_info(journalline)")} == {
            "id", "entry_id", "account_code", "account_id", "debit", "credit",
            "description", "created_at",
        }
        assert {r[1] for r in conn.execute("PRAGMA table_info(journalentry)")} == {
            "id", "date", "concept", "doc_ref", "period_id", "posted_by", "state", "created_at",
        }

        conn.execute(
            "INSERT INTO account(code,name,nature,vat_flag,origin,parent_id,created_at) "
            "VALUES ('1103','Clientes','DEBIT',0,'canonical',NULL,?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        account_id = conn.execute("SELECT id FROM account WHERE code='1103'").fetchone()[0]
        conn.execute(
            "INSERT INTO journalentry(date,concept,period_id,state,created_at) VALUES (?,?,?,?,?)",
            ("2026-01-15T00:00:00+00:00", "historical", 1, "posted", datetime.now(timezone.utc).isoformat()),
        )
        entry_id = conn.execute("SELECT max(id) FROM journalentry").fetchone()[0]
        conn.execute(
            "INSERT INTO journalline(entry_id,account_code,account_id,debit,credit,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (entry_id, "1103", account_id, "123.45", "0", datetime.now(timezone.utc).isoformat()),
        )
        line_id = conn.execute("SELECT max(id) FROM journalline").fetchone()[0]
        before = conn.execute(
            "SELECT * FROM journalline WHERE id=?",
            (line_id,),
        ).fetchone()
        assert before is not None
        assert conn.execute("SELECT count(*) FROM thirdparty").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM documentreference").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM auditevent").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM fiscalpostingauditrecord").fetchone()[0] == 0
        conn.commit()

    result = migrations.migrate_database(db)
    assert result["from_version"] == 6
    assert result["to_version"] == migrations.CURRENT_SCHEMA_VERSION
    assert migrations.get_schema_version(db) == migrations.CURRENT_SCHEMA_VERSION
    assert migrations.validate_sqlite_integrity(db)

    expected_open_item_columns = {
        "id", "entity_id", "third_party_id", "kind", "source_entry_id",
        "source_line_id", "source_document_reference_id", "due_date", "created_at",
    }
    expected_application_columns = {
        "id", "open_item_id", "application_entry_id", "application_line_id",
        "application_document_reference_id", "created_at",
    }

    with sqlite3.connect(db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert tables - historical_tables == {
            "openitem", "openitemapplication", "bankaccount", "bankstatement",
                "banktransaction", "reconciliation", "reconciliationmatch",
                    "reconciliationmatchrevocation", "fund", "fundingsource",
                        "fundreceipt", "fundapplication", "inkinddonation",
                        "cfdisource", "cfditaxevidence", "cfdisourcelink",
                }
        assert [r for r in conn.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
        ) if r[2] in historical_tables] == historical_schema
        assert "openitem" in tables
        assert "openitemapplication" in tables
        assert {row[1] for row in conn.execute("PRAGMA table_info(openitem)")} == expected_open_item_columns
        assert {
            row[1] for row in conn.execute("PRAGMA table_info(openitemapplication)")
        } == expected_application_columns

        expected_fks = {
            "openitem": {("entity_id", "entity"), ("third_party_id", "thirdparty"),
                         ("source_entry_id", "journalentry"), ("source_line_id", "journalline"),
                         ("source_document_reference_id", "documentreference")},
            "openitemapplication": {("open_item_id", "openitem"),
                         ("application_entry_id", "journalentry"),
                         ("application_line_id", "journalline"),
                         ("application_document_reference_id", "documentreference")},
        }
        for table, expected in expected_fks.items():
            assert {(r[3], r[2]) for r in conn.execute(f"PRAGMA foreign_key_list({table})")} == expected
            assert all(r[4] == "id" for r in conn.execute(f"PRAGMA foreign_key_list({table})"))
            columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
            assert all(r[3] == 1 for r in columns)
            assert [r[1] for r in columns if r[5]] == ["id"]
        ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='openitem'").fetchone()[0]
        assert "CHECK (kind IN ('receivable','payable'))" in ddl
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

        def unique_column_sets(table):
            result = set()
            for row in conn.execute(f"PRAGMA index_list({table})"):
                if row[2] != 1:
                    continue
                result.add(
                    tuple(
                        index_row[2]
                        for index_row in conn.execute(f"PRAGMA index_info({row[1]})")
                    )
                )
            return result

        assert ("source_line_id",) in unique_column_sets("openitem")
        assert ("application_line_id",) in unique_column_sets("openitemapplication")

        after = conn.execute(
            "SELECT * FROM journalline WHERE id=?",
            (line_id,),
        ).fetchone()
        assert after == before
        assert conn.execute("SELECT count(*) FROM openitem").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM openitemapplication").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM thirdparty").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM documentreference").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM auditevent").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM fiscalpostingauditrecord").fetchone()[0] == 0

        conn.execute("SAVEPOINT source_line_uniqueness")
        conn.execute(
            "INSERT INTO openitem(entity_id,third_party_id,kind,source_entry_id,source_line_id,"
            "source_document_reference_id,due_date,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (1, 1, "receivable", entry_id, line_id, 1, "2026-01-31", datetime.now(timezone.utc).isoformat()),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO openitem(entity_id,third_party_id,kind,source_entry_id,source_line_id,"
                "source_document_reference_id,due_date,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (1, 1, "receivable", entry_id, line_id, 1, "2026-02-28", datetime.now(timezone.utc).isoformat()),
            )
        conn.execute("ROLLBACK TO source_line_uniqueness")
        conn.execute("RELEASE source_line_uniqueness")

        conn.execute("SAVEPOINT application_line_uniqueness")
        open_item_id = conn.execute(
            "INSERT INTO openitem(entity_id,third_party_id,kind,source_entry_id,source_line_id,"
            "source_document_reference_id,due_date,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (1, 1, "receivable", entry_id, line_id, 1, "2026-01-31", datetime.now(timezone.utc).isoformat()),
        ).lastrowid
        conn.execute(
            "INSERT INTO openitemapplication(open_item_id,application_entry_id,application_line_id,"
            "application_document_reference_id,created_at) VALUES (?,?,?,?,?)",
            (open_item_id, entry_id, line_id, 1, datetime.now(timezone.utc).isoformat()),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO openitemapplication(open_item_id,application_entry_id,application_line_id,"
                "application_document_reference_id,created_at) VALUES (?,?,?,?,?)",
                (open_item_id, entry_id, line_id, 1, datetime.now(timezone.utc).isoformat()),
            )
        conn.execute("ROLLBACK TO application_line_uniqueness")
        conn.execute("RELEASE application_line_uniqueness")

        assert conn.execute("SELECT count(*) FROM openitem").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM openitemapplication").fetchone()[0] == 0


def test_receivable_partial_total_aging_and_reconciliation(tmp_path, monkeypatch):
    import aqorath.open_item_repository as repo
    import aqorath.storage as storage

    _, _, _, customer_id, _ = _seed_runtime(tmp_path, monkeypatch)
    origin = _origin("receivable", customer_id, "200", date(2026, 1, 10), date(2026, 1, 31), "F-1")
    with storage.get_session() as session:
        before = repo.load_open_item(session, origin["open_item_id"], as_of=date(2026, 2, 15))
        assert before.original_amount == Decimal("200")
        assert before.applied_amount == Decimal("0")
        assert before.open_balance == Decimal("200")
        assert before.status == "open"
        assert before.aging_bucket == "1-30"
        assert repo.assert_subledger_reconciled(session, "receivable", as_of=date(2026, 2, 15)).is_reconciled

    partial = _application(origin["open_item_id"], "80", date(2026, 2, 16), "C-1")
    assert partial["open_balance"] == Decimal("120")
    total = _application(origin["open_item_id"], "120", date(2026, 2, 20), "C-2")
    assert total["status"] == "settled"
    assert total["open_balance"] == Decimal("0")
    with storage.get_session() as session:
        view = repo.load_open_item(session, origin["open_item_id"], as_of=date(2026, 2, 20))
        assert [app.amount for app in view.applications] == [Decimal("80"), Decimal("120")]
        assert view.applied_amount == Decimal("200")
        assert view.aging_bucket == "settled"
        assert repo.assert_subledger_reconciled(session, "receivable", as_of=date(2026, 2, 20)).is_reconciled


def test_payable_partial_and_overapplication_rolls_back_without_partial_truth(tmp_path, monkeypatch):
    import aqorath.open_item_repository as repo
    import aqorath.storage as storage
    from aqorath.models import AuditEventRecord, DocumentReferenceRecord, JournalEntry
    from aqorath.open_item_models import OpenItemApplicationRecord

    _, _, _, _, supplier_id = _seed_runtime(tmp_path, monkeypatch)
    origin = _origin("payable", supplier_id, "1500", date(2026, 3, 1), date(2026, 3, 31), "P-1")
    _application(origin["open_item_id"], "500", date(2026, 3, 10), "PAY-1")

    with storage.get_session() as session:
        counts = (
            len(session.exec(select(JournalEntry)).all()),
            len(session.exec(select(AuditEventRecord)).all()),
            len(session.exec(select(DocumentReferenceRecord)).all()),
            len(session.exec(select(OpenItemApplicationRecord)).all()),
        )
    with pytest.raises(ValueError, match="exceeds"):
        _application(origin["open_item_id"], "1001", date(2026, 3, 11), "PAY-X")
    with storage.get_session() as session:
        assert counts == (
            len(session.exec(select(JournalEntry)).all()),
            len(session.exec(select(AuditEventRecord)).all()),
            len(session.exec(select(DocumentReferenceRecord)).all()),
            len(session.exec(select(OpenItemApplicationRecord)).all()),
        )
        view = repo.load_open_item(session, origin["open_item_id"], as_of=date(2026, 3, 11))
        assert view.open_balance == Decimal("1000")


def test_one_payment_across_two_obligations_is_split_in_journal_lines(tmp_path, monkeypatch):
    import aqorath.subledger_operations as ops
    import aqorath.open_item_repository as repo
    import aqorath.storage as storage
    from aqorath.models import DocumentReferenceRecord, JournalLine
    from aqorath.open_item_models import OpenItemApplicationRecord

    _, _, _, customer_id, _ = _seed_runtime(tmp_path, monkeypatch)
    first = _origin("receivable", customer_id, "600", date(2026, 4, 1), date(2026, 4, 30), "F-600")
    second = _origin("receivable", customer_id, "400", date(2026, 4, 2), date(2026, 4, 30), "F-400")

    with storage.get_session() as session:
        prepared = ops.prepare_open_item_application_batch(
            session,
            [(first["open_item_id"], Decimal("600")), (second["open_item_id"], Decimal("400"))],
            date(2026, 4, 20),
            "bank_receipt",
            "DEP-1000",
            date(2026, 4, 20),
        )
    result = ops.execute_open_item_application_batch(
        ops.confirm_open_item_application_batch(prepared)
    )

    with storage.get_session() as session:
        lines = session.exec(
            select(JournalLine).where(JournalLine.entry_id == result["entry_id"]).order_by(JournalLine.id)
        ).all()
        bank = [line for line in lines if line.account_code == "1101"]
        ar = [line for line in lines if line.account_code == "1103"]
        assert len(bank) == 1
        assert Decimal(bank[0].debit) == Decimal("1000")
        assert Decimal(bank[0].credit) == Decimal("0")
        assert [Decimal(line.credit) for line in ar] == [Decimal("600"), Decimal("400")]
        assert all(Decimal(line.debit) == 0 for line in ar)

        apps = session.exec(
            select(OpenItemApplicationRecord).where(
                OpenItemApplicationRecord.application_entry_id == result["entry_id"]
            ).order_by(OpenItemApplicationRecord.id)
        ).all()
        assert [app.application_line_id for app in apps] == [line.id for line in ar]
        assert len(set(app.application_line_id for app in apps)) == 2
        documents = session.exec(
            select(DocumentReferenceRecord).where(DocumentReferenceRecord.entry_id == result["entry_id"])
        ).all()
        assert len(documents) == 1
        assert {app.application_document_reference_id for app in apps} == {documents[0].id}
        assert repo.load_open_item(session, first["open_item_id"], as_of=date(2026, 4, 20)).status == "settled"
        assert repo.load_open_item(session, second["open_item_id"], as_of=date(2026, 4, 20)).status == "settled"
        assert repo.assert_subledger_reconciled(session, "receivable", as_of=date(2026, 4, 20)).is_reconciled


def test_control_line_identity_cannot_be_reused(tmp_path, monkeypatch):
    import aqorath.open_item_repository as repo
    import aqorath.storage as storage
    from aqorath.models import DocumentReferenceRecord, JournalLine

    _, _, entity_id, customer_id, _ = _seed_runtime(tmp_path, monkeypatch)
    origin = _origin("receivable", customer_id, "100", date(2026, 5, 1), date(2026, 5, 31), "F-ID")
    with storage.get_session() as session:
        item = repo.load_open_item(session, origin["open_item_id"], as_of=date(2026, 5, 1))
        with pytest.raises(ValueError, match="already identifies"):
            repo.stage_open_item(
                session,
                entity_id=entity_id,
                third_party_id=customer_id,
                kind="receivable",
                source_entry_id=item.source_entry_id,
                source_line_id=item.source_line_id,
                source_document_reference_id=item.source_document_reference_id,
                due_date=item.due_date,
            )
        session.rollback()

    app = _application(origin["open_item_id"], "50", date(2026, 5, 10), "C-ID")
    with storage.get_session() as session:
        application = session.exec(
            select(__import__("aqorath.open_item_models", fromlist=["OpenItemApplicationRecord"]).OpenItemApplicationRecord)
        ).first()
        with pytest.raises(ValueError, match="already belongs"):
            repo.stage_open_item_application(
                session,
                open_item_id=origin["open_item_id"],
                application_entry_id=app["entry_id"],
                application_line_id=application.application_line_id,
                application_document_reference_id=application.application_document_reference_id,
            )
        session.rollback()


def test_reversing_application_reopens_item_and_origin_requires_app_reversal(tmp_path, monkeypatch):
    import aqorath.open_item_repository as repo
    import aqorath.storage as storage
    from aqorath.reversal import reverse_posted_entry

    _, _, _, customer_id, _ = _seed_runtime(tmp_path, monkeypatch)
    origin = _origin("receivable", customer_id, "200", date(2026, 6, 1), date(2026, 6, 30), "F-R")
    application = _application(origin["open_item_id"], "80", date(2026, 6, 10), "C-R")

    with storage.get_session() as session:
        with pytest.raises(ValueError, match="applications"):
            reverse_posted_entry(session, origin["entry_id"], "cancel source", date(2026, 6, 11))
        session.rollback()

    with storage.get_session() as session:
        reverse_posted_entry(session, application["entry_id"], "collection reversed", date(2026, 6, 12))
        session.commit()
    with storage.get_session() as session:
        reopened = repo.load_open_item(session, origin["open_item_id"], as_of=date(2026, 6, 12))
        assert reopened.open_balance == Decimal("200")
        assert reopened.applied_amount == Decimal("0")
        assert reopened.status == "open"
        assert repo.assert_subledger_reconciled(session, "receivable", as_of=date(2026, 6, 12)).is_reconciled
        reverse_posted_entry(session, origin["entry_id"], "sale cancelled", date(2026, 6, 13))
        session.commit()
    with storage.get_session() as session:
        cancelled = repo.load_open_item(session, origin["open_item_id"], as_of=date(2026, 6, 13))
        assert cancelled.status == "cancelled"
        assert cancelled.open_balance == Decimal("0")
        assert repo.assert_subledger_reconciled(session, "receivable", as_of=date(2026, 6, 13)).is_reconciled


def test_unassigned_control_line_is_detected_without_inventing_open_item(tmp_path, monkeypatch):
    import aqorath.open_item_repository as repo
    import aqorath.storage as storage
    from aqorath.models import Account, AccountRoleBinding, JournalEntry, JournalLine

    _, _, _, _, _ = _seed_runtime(tmp_path, monkeypatch)
    with storage.get_session() as session:
        ar = session.exec(select(Account).where(Account.code == "1103")).one()
        revenue = session.exec(select(Account).where(Account.code == "4201")).one()
        entry = JournalEntry(
            date=datetime(2026, 7, 1, tzinfo=timezone.utc),
            concept="legacy-unassigned",
            period_id=7,
            state="posted",
        )
        session.add(entry)
        session.flush()
        session.add(JournalLine(entry_id=entry.id, account_id=ar.id, account_code=ar.code, debit="77", credit="0"))
        session.add(JournalLine(entry_id=entry.id, account_id=revenue.id, account_code=revenue.code, debit="0", credit="77"))
        session.commit()
        result = repo.reconcile_subledger(session, "receivable", as_of=date(2026, 7, 1))
        assert result.ledger_balance == Decimal("77")
        assert result.subledger_balance == Decimal("0")
        assert result.difference == Decimal("77")
        assert len(result.unassigned_line_ids) == 1
        with pytest.raises(repo.SubledgerDivergenceError):
            repo.assert_subledger_reconciled(session, "receivable", as_of=date(2026, 7, 1))


def test_atomicity_rolls_back_posting_audit_document_and_open_item(tmp_path, monkeypatch):
    import aqorath.open_item_repository as repo
    import aqorath.subledger_operations as ops
    import aqorath.storage as storage
    from aqorath.models import AuditEventRecord, DocumentReferenceRecord, JournalEntry
    from aqorath.open_item_models import OpenItemRecord

    _, _, _, customer_id, _ = _seed_runtime(tmp_path, monkeypatch)
    with storage.get_session() as session:
        prepared = ops.prepare_open_item_origin(
            session,
            "sale_credit", Decimal("99"), date(2026, 8, 1), customer_id,
            date(2026, 8, 31), "invoice", "ATOMIC", date(2026, 8, 1),
        )
    confirmed = ops.confirm_open_item_origin(prepared)
    real_stage = repo.stage_open_item

    def fail_after_ledger(*args, **kwargs):
        raise RuntimeError("subledger staging failure")

    monkeypatch.setattr(repo, "stage_open_item", fail_after_ledger)
    with pytest.raises(RuntimeError, match="subledger staging failure"):
        ops.execute_open_item_origin(confirmed)
    monkeypatch.setattr(repo, "stage_open_item", real_stage)

    with storage.get_session() as session:
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(AuditEventRecord)).all() == []
        assert session.exec(select(DocumentReferenceRecord)).all() == []
        assert session.exec(select(OpenItemRecord)).all() == []

@pytest.mark.parametrize('kind', ['receivable', 'payable'])
def test_backdated_application_cannot_overapply_before_future_reversal(tmp_path, monkeypatch, kind):
    import aqorath.storage as storage
    from aqorath.reversal import reverse_posted_entry
    _, _, _, customer, supplier = _seed_runtime(tmp_path, monkeypatch)
    origin = _origin(kind, customer if kind == 'receivable' else supplier,
                     '100', date(2026,1,1), date(2026,1,31), 'BACKDATED')
    app = _application(origin['open_item_id'], '100', date(2026,2,1), 'FIRST')
    with storage.get_session() as session:
        reverse_posted_entry(session, app['entry_id'], 'cancel', date(2026,3,1))
        session.commit()
    with pytest.raises(ValueError, match='exceed'):
        _application(origin['open_item_id'], '100', date(2026,1,15), 'SECOND')


def test_origin_reversal_cannot_precede_application_reversal(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.reversal import reverse_posted_entry
    _, _, _, customer, _ = _seed_runtime(tmp_path, monkeypatch)
    origin = _origin('receivable', customer,'100',date(2026,1,1),date(2026,1,31),'R-TIME')
    app = _application(origin['open_item_id'],'100',date(2026,2,1),'APP-TIME')
    with storage.get_session() as session:
        reverse_posted_entry(session,app['entry_id'],'cancel',date(2026,3,1));session.commit()
    with storage.get_session() as session:
        with pytest.raises(ValueError, match='application'):
            reverse_posted_entry(session,origin['entry_id'],'cancel origin',date(2026,1,15))


@pytest.mark.parametrize('failure_stage',['document','application','audit','reconciliation'])
def test_batch_atomicity_at_every_metadata_boundary(tmp_path, monkeypatch, failure_stage):
    import aqorath.storage as storage
    import aqorath.subledger_operations as ops
    import aqorath.open_item_repository as repo
    from sqlalchemy import text
    _, _, _, customer, _ = _seed_runtime(tmp_path, monkeypatch)
    first=_origin('receivable',customer,'50',date(2026,1,1),date(2026,1,31),'A')
    second=_origin('receivable',customer,'50',date(2026,1,1),date(2026,1,31),'B')
    tables=('journalentry','journalline','auditevent','documentreference','openitem','openitemapplication')
    def counts():
        with storage.get_session() as session:
            return [session.execute(text('SELECT count(*) FROM '+t)).scalar_one() for t in tables]
    before=counts()
    with storage.get_session() as session:
        draft=ops.prepare_open_item_application_batch(session,[(first['open_item_id'],Decimal('50')),
            (second['open_item_id'],Decimal('50'))],date(2026,1,10),'payment','BATCH',date(2026,1,10))
    target, name = {'document':(ops,'_stage_document'), 'application':(repo,'stage_open_item_application'),
                    'audit':(ops,'_stage_subledger_audit'), 'reconciliation':(ops,'_transition_after')}[failure_stage]
    original=getattr(target,name)
    calls=[]
    def fail(*a,**kw):
        result=original(*a,**kw);calls.append(1)
        if failure_stage!='application' or len(calls)==2:
            raise RuntimeError('injected boundary failure')
        return result
    monkeypatch.setattr(target,name,fail)
    with pytest.raises(RuntimeError,match='injected'):
        ops.execute_open_item_application_batch(ops.confirm_open_item_application_batch(draft))
    assert counts()==before


@pytest.mark.parametrize('day,bucket', [('2026-01-31','current'),('2026-02-01','1-30'),
    ('2026-03-02','1-30'),('2026-03-03','31-60'),('2026-04-01','31-60'),
    ('2026-04-02','61-90'),('2026-05-01','61-90'),('2026-05-02','91+')])
def test_aging_boundaries_are_derived_at_as_of(tmp_path, monkeypatch, day, bucket):
    import aqorath.storage as storage
    from aqorath.open_item_repository import load_open_item
    _, _, _, customer, _ = _seed_runtime(tmp_path, monkeypatch)
    origin=_origin('receivable',customer,'100',date(2026,1,1),date(2026,1,31),'AGE')
    with storage.get_session() as session:
        view=load_open_item(session,origin['open_item_id'],date.fromisoformat(day))
        assert view.aging_bucket==bucket and view.open_balance==Decimal('100')


def test_stale_prepared_application_revalidates_before_commit(tmp_path, monkeypatch):
    import aqorath.storage as storage
    import aqorath.subledger_operations as ops
    _, _, _, customer, _ = _seed_runtime(tmp_path, monkeypatch)
    origin=_origin('receivable',customer,'100',date(2026,1,1),date(2026,1,31),'STALE')
    with storage.get_session() as session:
        prepared=ops.prepare_open_item_application(session,origin['open_item_id'],Decimal('100'),
            date(2026,2,1),'payment','STALE-P',date(2026,2,1))
    _application(origin['open_item_id'],'60',date(2026,2,1),'OTHER')
    with pytest.raises(ValueError,match='exceeds'):
        ops.execute_open_item_application(ops.confirm_open_item_application(prepared))
