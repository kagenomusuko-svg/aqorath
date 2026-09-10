from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

import pytest


FIXTURE = Path(__file__).parent / "fixtures" / "cfdi40_ingreso.xml"


def _xml():
    return FIXTURE.read_bytes()


def _outgoing_xml():
    return (
        _xml()
        .replace(b'FormaPago="03"', b'FormaPago="01"')
        .replace(
            b'<cfdi:Emisor Rfc="AAA010101AAA" Nombre="Proveedor Ejemplo SA de CV" RegimenFiscal="601"/>',
            b'<cfdi:Emisor Rfc="MER260101AB1" Nombre="Meriadock A.C." RegimenFiscal="603"/>',
        )
        .replace(
            b'<cfdi:Receptor Rfc="MER260101AB1" Nombre="Meriadock A.C." DomicilioFiscalReceptor="06000" RegimenFiscalReceptor="603" UsoCFDI="G03"/>',
            b'<cfdi:Receptor Rfc="COSC8001137NA" Nombre="Cliente Ejemplo" DomicilioFiscalReceptor="06000" RegimenFiscalReceptor="612" UsoCFDI="G03"/>',
        )
        .replace(
            b'UUID="123e4567-e89b-12d3-a456-426614174000"',
            b'UUID="223e4567-e89b-12d3-a456-426614174000"',
        )
    )


def test_parse_cfdi_40_ingreso_extracts_exact_external_truth_without_accounting():
    from aqorath.cfdi_source import parse_cfdi_xml

    parsed = parse_cfdi_xml(_xml())

    assert parsed.version == "4.0"
    assert parsed.uuid == "123E4567-E89B-12D3-A456-426614174000"
    assert parsed.voucher_type == "I"
    assert parsed.issuer_rfc == "AAA010101AAA"
    assert parsed.receiver_rfc == "MER260101AB1"
    assert parsed.issuer_name == "Proveedor Ejemplo SA de CV"
    assert parsed.receiver_name == "Meriadock A.C."
    assert parsed.currency == "MXN"
    assert parsed.subtotal == Decimal("1000.10")
    assert parsed.discount == Decimal("0.10")
    assert parsed.total == Decimal("1160.00")
    assert parsed.total_transferred == Decimal("160.00")
    assert parsed.total_withheld == Decimal("0.00")
    assert parsed.payment_form == "03"
    assert parsed.payment_method == "PUE"
    assert parsed.document_number == "A-123"
    assert len(parsed.taxes) == 1
    assert parsed.taxes[0].direction == "transfer"
    assert parsed.taxes[0].base == Decimal("1000.00")
    assert parsed.taxes[0].tax_code == "002"
    assert parsed.taxes[0].factor_type == "Tasa"
    assert parsed.taxes[0].rate_or_quota == Decimal("0.160000")
    assert parsed.taxes[0].amount == Decimal("160.00")
    assert len(parsed.sha256) == 64
    assert parsed.xml_bytes == _xml()
    assert not hasattr(parsed, "journal_entry_id")
    assert not hasattr(parsed, "account_code")
    with pytest.raises(FrozenInstanceError):
        parsed.total = Decimal("1")


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (b'Version="4.0"', b'Version="3.3"', "only CFDI 4.0"),
        (b'TipoDeComprobante="I"', b'TipoDeComprobante="E"', "only CFDI ingreso"),
        (b'Moneda="MXN"', b'Moneda="XXX"', "currency XXX"),
        (b'Total="1160.00"', b'Total="NaN"', "Total must be a finite decimal"),
    ],
)
def test_parse_cfdi_rejects_out_of_scope_or_invalid_truth(old, new, message):
    from aqorath.cfdi_source import parse_cfdi_xml

    with pytest.raises(ValueError, match=message):
        parse_cfdi_xml(_xml().replace(old, new))


def test_parse_cfdi_rejects_missing_stamp_namespace_and_ambiguous_duplicate_nodes():
    from aqorath.cfdi_source import parse_cfdi_xml

    without_stamp = _xml().replace(
        b'<tfd:TimbreFiscalDigital Version="1.1" UUID="123e4567-e89b-12d3-a456-426614174000" FechaTimbrado="2026-09-10T09:16:00" RfcProvCertif="SAT970701NN3" SelloCFD="SELLO-CFD" NoCertificadoSAT="00001000000504465028" SelloSAT="SELLO-SAT"/>',
        b"",
    )
    with pytest.raises(ValueError, match="exactly one TimbreFiscalDigital"):
        parse_cfdi_xml(without_stamp)

    wrong_namespace = _xml().replace(
        b'http://www.sat.gob.mx/cfd/4', b'http://example.test/not-cfdi',
    )
    with pytest.raises(ValueError, match="CFDI 4.0 namespace"):
        parse_cfdi_xml(wrong_namespace)

    duplicate_emisor = _xml().replace(
        b'<cfdi:Receptor ',
        b'<cfdi:Emisor Rfc="BBB010101BBB" Nombre="Otro" RegimenFiscal="601"/><cfdi:Receptor ',
    )
    with pytest.raises(ValueError, match="exactly one Emisor"):
        parse_cfdi_xml(duplicate_emisor)


def test_parse_cfdi_is_offline_and_rejects_doctype_entities_and_oversized_input():
    from aqorath.cfdi_source import MAX_CFDI_BYTES, parse_cfdi_xml

    malicious = b'''<?xml version="1.0"?><!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><x>&x;</x>'''
    with pytest.raises(ValueError, match="DOCTYPE and ENTITY"):
        parse_cfdi_xml(malicious)
    with pytest.raises(ValueError, match="maximum size"):
        parse_cfdi_xml(b"x" * (MAX_CFDI_BYTES + 1))
    with pytest.raises(TypeError, match="bytes"):
        parse_cfdi_xml("not bytes")


def test_parse_cfdi_fails_closed_when_tax_totals_disagree_with_components():
    from aqorath.cfdi_source import parse_cfdi_xml

    inconsistent = _xml().replace(
        b'TotalImpuestosTrasladados="160.00"',
        b'TotalImpuestosTrasladados="159.99"',
    )
    with pytest.raises(ValueError, match="transferred tax total"):
        parse_cfdi_xml(inconsistent)


def test_parse_cfdi_rejects_invalid_rfc_totals_dates_and_missing_concepts():
    from aqorath.cfdi_source import parse_cfdi_xml

    cases = (
        (_xml().replace(b'Rfc="AAA010101AAA"', b'Rfc="INVALID"'), "Emisor Rfc"),
        (_xml().replace(b'Total="1160.00"', b'Total="1159.99"'), "document total"),
        (_xml().replace(b'FechaTimbrado="2026-09-10T09:16:00"', b'FechaTimbrado="2026-09-10T09:14:00"'), "stamp cannot precede"),
        (_xml().replace(b'<cfdi:Conceptos>', b'<cfdi:Conceptos><cfdi:Concepto ClaveProdServ="x"/>'), "concept Importe"),
    )
    for content, message in cases:
        with pytest.raises(ValueError, match=message):
            parse_cfdi_xml(content)


def _entity():
    from aqorath.entity import Entity, EntityProfile

    return Entity(
        None,
        "Meriadock A.C.",
        "MER260101AB1",
        "persona_moral",
        "A.C.",
        EntityProfile("no_lucrativo", False, ("osc",), ("accounting",)),
        True,
    )


def _party(entity_id, *, rfc="AAA010101AAA", name="Proveedor Ejemplo SA de CV", party_type="supplier"):
    from aqorath.third_party import ThirdParty

    return ThirdParty(
        None, entity_id, name, rfc, None, None, party_type, None, None, None, True
    )


def _database(tmp_path):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION, migrate_database
    from sqlalchemy import create_engine

    path = tmp_path / "aqr010.db"
    result = migrate_database(path)
    assert result["to_version"] == CURRENT_SCHEMA_VERSION
    return path, create_engine(f"sqlite:///{path}")


def _schema10_snapshot(path):
    """Frozen schema 10 fixture: historical literal DDL, never runtime metadata."""
    from test_aqr008_funds import _schema8_snapshot

    _schema8_snapshot(path)
    additions = """
    CREATE TABLE fund (id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL, code VARCHAR NOT NULL, name VARCHAR NOT NULL, restriction VARCHAR NOT NULL, purpose TEXT, program_id INTEGER, valid_from VARCHAR, valid_until VARCHAR, created_at DATETIME NOT NULL, CONSTRAINT uq_fund_entity_code UNIQUE(entity_id,code), FOREIGN KEY(entity_id) REFERENCES entity(id), FOREIGN KEY(program_id) REFERENCES program(id));
    CREATE TABLE fundingsource (id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL, name VARCHAR NOT NULL, donor_third_party_id INTEGER, external_reference VARCHAR, created_at DATETIME NOT NULL, CONSTRAINT uq_funding_source_entity_name UNIQUE(entity_id,name), FOREIGN KEY(entity_id) REFERENCES entity(id), FOREIGN KEY(donor_third_party_id) REFERENCES thirdparty(id));
    CREATE TABLE fundreceipt (id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL, fund_id INTEGER NOT NULL, funding_source_id INTEGER NOT NULL, journal_line_id INTEGER NOT NULL, donation_id INTEGER, amount TEXT NOT NULL, received_at VARCHAR NOT NULL, created_at DATETIME NOT NULL, CONSTRAINT uq_fund_receipt_line UNIQUE(journal_line_id), FOREIGN KEY(entity_id) REFERENCES entity(id), FOREIGN KEY(fund_id) REFERENCES fund(id), FOREIGN KEY(funding_source_id) REFERENCES fundingsource(id), FOREIGN KEY(journal_line_id) REFERENCES journalline(id), FOREIGN KEY(donation_id) REFERENCES donation(id));
    CREATE TABLE fundapplication (id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL, fund_id INTEGER NOT NULL, program_id INTEGER NOT NULL, journal_line_id INTEGER NOT NULL, receipt_id INTEGER, amount TEXT NOT NULL, applied_at VARCHAR NOT NULL, purpose TEXT, created_at DATETIME NOT NULL, FOREIGN KEY(entity_id) REFERENCES entity(id), FOREIGN KEY(fund_id) REFERENCES fund(id), FOREIGN KEY(program_id) REFERENCES program(id), FOREIGN KEY(journal_line_id) REFERENCES journalline(id), FOREIGN KEY(receipt_id) REFERENCES fundreceipt(id));
    CREATE TABLE inkinddonation (id INTEGER PRIMARY KEY, entity_id INTEGER NOT NULL, donor_third_party_id INTEGER, document_reference_id INTEGER, fund_id INTEGER, program_id INTEGER, journal_line_id INTEGER, fixed_asset_id INTEGER, received_at VARCHAR NOT NULL, description TEXT NOT NULL, quantity TEXT, valuation_amount TEXT NOT NULL, valuation_currency VARCHAR NOT NULL, valuation_method VARCHAR NOT NULL, valuation_evidence TEXT NOT NULL, external_reference VARCHAR NOT NULL, created_at DATETIME NOT NULL, CONSTRAINT uq_inkind_entity_reference UNIQUE(entity_id,external_reference), FOREIGN KEY(entity_id) REFERENCES entity(id), FOREIGN KEY(donor_third_party_id) REFERENCES thirdparty(id), FOREIGN KEY(document_reference_id) REFERENCES documentreference(id), FOREIGN KEY(fund_id) REFERENCES fund(id), FOREIGN KEY(program_id) REFERENCES program(id), FOREIGN KEY(journal_line_id) REFERENCES journalline(id), FOREIGN KEY(fixed_asset_id) REFERENCES fixedasset(id));
    PRAGMA user_version=10;
    """
    import sqlite3
    with sqlite3.connect(path) as conn:
        conn.executescript(additions)


def _identity(session):
    from aqorath.entity_repository import create_entity
    from aqorath.third_party_repository import create_third_party

    entity = create_entity(session, _entity())
    party = create_third_party(session, _party(entity.id))
    return entity, party


def test_import_cfdi_persists_external_evidence_atomically_without_posting(tmp_path):
    from aqorath.cfdi_models import CfdiSourceRecord, CfdiTaxEvidenceRecord
    from aqorath.cfdi_source_repository import import_cfdi_source, load_cfdi_source
    from aqorath.models import AuditEventRecord, CfdiImportMetadataRecord, DocumentReferenceRecord, JournalEntry
    from sqlmodel import Session, select

    _path, engine = _database(tmp_path)
    imported_at = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        entity, party = _identity(session)
        result = import_cfdi_source(session, _xml(), imported_at=imported_at)
        assert result.duplicate is False
        assert result.source.entity_id == entity.id
        assert result.source.third_party_id == party.id
        assert result.source.relationship == "purchase"
        assert result.source.total == Decimal("1160.00")
        assert result.source.xml_bytes == _xml()
        loaded = load_cfdi_source(session, entity.id, result.source.id)
        assert loaded == result.source
        row = session.exec(select(CfdiSourceRecord)).one()
        assert row.total == "1160.00"
        assert row.xml_bytes == _xml()
        tax = session.exec(select(CfdiTaxEvidenceRecord)).one()
        assert tax.base == "1000.00"
        assert tax.rate_or_quota == "0.160000"
        assert tax.amount == "160.00"
        audit = session.exec(select(AuditEventRecord)).one()
        assert audit.event_type == "cfdi_source_imported"
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(DocumentReferenceRecord)).all() == []
        assert session.exec(select(CfdiImportMetadataRecord)).all() == []


def test_reimport_same_cfdi_is_idempotent_but_uuid_or_file_conflict_fails(tmp_path):
    from aqorath.cfdi_models import CfdiSourceRecord
    from aqorath.cfdi_source_repository import import_cfdi_source
    from aqorath.models import AuditEventRecord
    from sqlmodel import Session, select

    _path, engine = _database(tmp_path)
    imported_at = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        _identity(session)
        first = import_cfdi_source(session, _xml(), imported_at=imported_at)
        again = import_cfdi_source(session, _xml(), imported_at=imported_at)
        assert again.duplicate is True
        assert again.source.id == first.source.id
        assert len(session.exec(select(CfdiSourceRecord)).all()) == 1
        assert len(session.exec(select(AuditEventRecord)).all()) == 1

        changed_same_uuid = _xml().replace(
            b'Descripcion="Computadora"', b'Descripcion="Computadora alterada"'
        )
        with pytest.raises(ValueError, match="UUID already exists with different XML"):
            import_cfdi_source(session, changed_same_uuid, imported_at=imported_at)


def test_import_cfdi_requires_active_entity_and_unambiguous_owned_counterparty(tmp_path):
    from aqorath.cfdi_source_repository import import_cfdi_source
    from aqorath.entity_repository import create_entity
    from aqorath.third_party_repository import create_third_party
    from sqlmodel import Session

    _path, engine = _database(tmp_path)
    with Session(engine) as session:
        entity = create_entity(session, _entity())
        with pytest.raises(LookupError, match="counterparty RFC"):
            import_cfdi_source(session, _xml())
        create_third_party(session, _party(entity.id))
        alien = _xml().replace(b'MER260101AB1', b'ZZZ010101ZZZ')
        with pytest.raises(ValueError, match="active Entity must be issuer or receiver"):
            import_cfdi_source(session, alien)


def test_import_cfdi_rolls_back_source_taxes_and_audit_on_late_failure(tmp_path, monkeypatch):
    import aqorath.cfdi_source_repository as repository
    from aqorath.cfdi_models import CfdiSourceRecord, CfdiTaxEvidenceRecord
    from aqorath.models import AuditEventRecord
    from sqlmodel import Session, select

    _path, engine = _database(tmp_path)
    with Session(engine) as session:
        _identity(session)

        def fail(*_args, **_kwargs):
            raise RuntimeError("forced audit failure")

        monkeypatch.setattr(repository._audit_events, "stage_audit_event", fail)
        with pytest.raises(RuntimeError, match="forced audit failure"):
            repository.import_cfdi_source(session, _xml())
        assert session.exec(select(CfdiSourceRecord)).all() == []
        assert session.exec(select(CfdiTaxEvidenceRecord)).all() == []
        assert session.exec(select(AuditEventRecord)).all() == []


def _posted_entry(session, entity_id, *, total="1160.00", day=10):
    import json
    from aqorath.models import Account, AuditEventRecord, JournalEntry, JournalLine

    bank = Account(code="1101", name="Banco", nature="DEBIT")
    income = Account(code="4201", name="Contrapartida", nature="CREDIT")
    session.add_all([bank, income])
    session.flush()
    entry = JournalEntry(
        date=datetime(2026, 9, day, 9, 15, tzinfo=timezone.utc),
        concept="Operación tomada del CFDI",
        state="posted",
    )
    session.add(entry)
    session.flush()
    session.add_all([
        JournalLine(entry_id=entry.id, account_code=bank.code, account_id=bank.id, debit=total, credit="0", description="Banco"),
        JournalLine(entry_id=entry.id, account_code=income.code, account_id=income.id, debit="0", credit=total, description="Contrapartida"),
    ])
    session.add(AuditEventRecord(
        entity_id=entity_id,
        event_type="entry_posted",
        timestamp=datetime(2026, 9, day, 10, tzinfo=timezone.utc).isoformat(),
        details_json=json.dumps({"entry_id": entry.id, "decision": {"fact": {"type": "sale"}}}),
    ))
    session.commit()
    return entry


def test_link_cfdi_creates_canonical_document_and_legacy_metadata_for_real_posting(tmp_path):
    from aqorath.cfdi_models import CfdiSourceLinkRecord
    from aqorath.cfdi_source_repository import import_cfdi_source, link_cfdi_source_to_entry
    from aqorath.models import AuditEventRecord, CfdiImportMetadataRecord, DocumentReferenceRecord
    from sqlmodel import Session, select

    _path, engine = _database(tmp_path)
    with Session(engine) as session:
        entity, party = _identity(session)
        source = import_cfdi_source(session, _xml()).source
        entry = _posted_entry(session, entity.id)
        link = link_cfdi_source_to_entry(session, entity.id, source.id, entry.id)
        assert link.id is not None
        document = session.exec(select(DocumentReferenceRecord)).one()
        assert document.entry_id == entry.id
        assert document.third_party_id == party.id
        assert document.document_type == "cfdi"
        assert document.file_hash == source.parsed.sha256
        assert "SAT status not consulted" in document.validation_notes
        metadata = session.exec(select(CfdiImportMetadataRecord)).one()
        assert metadata.document_reference_id == document.id
        assert metadata.uuid == source.parsed.uuid
        assert session.exec(select(CfdiSourceLinkRecord)).one().cfdi_source_id == source.id
        assert [row.event_type for row in session.exec(select(AuditEventRecord)).all()].count("cfdi_source_linked") == 1

        same = link_cfdi_source_to_entry(session, entity.id, source.id, entry.id)
        assert same.id == link.id
        assert len(session.exec(select(DocumentReferenceRecord)).all()) == 1
        assert len(session.exec(select(CfdiImportMetadataRecord)).all()) == 1


@pytest.mark.parametrize(
    ("total", "day", "message"),
    [
        ("1159.99", 10, "CFDI total differs"),
        ("1160.00", 11, "CFDI issue date differs"),
    ],
)
def test_link_cfdi_fails_closed_on_ledger_amount_or_date_difference(tmp_path, total, day, message):
    from aqorath.cfdi_source_repository import import_cfdi_source, link_cfdi_source_to_entry
    from aqorath.models import CfdiImportMetadataRecord, DocumentReferenceRecord
    from sqlmodel import Session, select

    _path, engine = _database(tmp_path)
    with Session(engine) as session:
        entity, _party_row = _identity(session)
        source = import_cfdi_source(session, _xml()).source
        entry = _posted_entry(session, entity.id, total=total, day=day)
        with pytest.raises(ValueError, match=message):
            link_cfdi_source_to_entry(session, entity.id, source.id, entry.id)
        assert session.exec(select(DocumentReferenceRecord)).all() == []
        assert session.exec(select(CfdiImportMetadataRecord)).all() == []


def test_link_cfdi_rolls_back_document_metadata_link_and_audit_on_late_failure(tmp_path, monkeypatch):
    import aqorath.cfdi_source_repository as repository
    from aqorath.cfdi_models import CfdiSourceLinkRecord
    from aqorath.models import AuditEventRecord, CfdiImportMetadataRecord, DocumentReferenceRecord
    from sqlmodel import Session, select

    _path, engine = _database(tmp_path)
    with Session(engine) as session:
        entity, _party_row = _identity(session)
        source = repository.import_cfdi_source(session, _xml()).source
        entry = _posted_entry(session, entity.id)
        real = repository._audit_events.stage_audit_event

        def fail_link_audit(inner_session, event):
            if event.event_type == "cfdi_source_linked":
                raise RuntimeError("forced link audit failure")
            return real(inner_session, event)

        monkeypatch.setattr(repository._audit_events, "stage_audit_event", fail_link_audit)
        with pytest.raises(RuntimeError, match="forced link audit failure"):
            repository.link_cfdi_source_to_entry(session, entity.id, source.id, entry.id)
        assert session.exec(select(DocumentReferenceRecord)).all() == []
        assert session.exec(select(CfdiImportMetadataRecord)).all() == []
        assert session.exec(select(CfdiSourceLinkRecord)).all() == []
        assert [row for row in session.exec(select(AuditEventRecord)).all() if row.event_type == "cfdi_source_linked"] == []


def test_schema10_to_11_uses_historical_snapshot_preserves_history_and_adds_no_cfdi_backfill(tmp_path):
    import sqlite3
    from aqorath.migrations import CURRENT_SCHEMA_VERSION, migrate_database, validate_sqlite_integrity

    path = tmp_path / "historical-schema10.db"
    _schema10_snapshot(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
        before_tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"cfdisource", "cfditaxevidence", "cfdisourcelink"}.isdisjoint(before_tables)
        conn.execute("INSERT INTO account(code,name,nature,vat_flag,origin,created_at) VALUES ('4201','Ingreso histórico','CREDIT',0,'canonical','2026-01-01')")
        account_id = conn.execute("SELECT id FROM account WHERE code='4201'").fetchone()[0]
        conn.execute("INSERT INTO journalentry(id,date,concept,state,created_at) VALUES (701,'2026-01-10T00:00:00+00:00','historia schema 10','posted','2026-01-10')")
        conn.execute("INSERT INTO journalline(id,entry_id,account_code,account_id,debit,credit,created_at) VALUES (801,701,'4201',?,'0','77.35','2026-01-10')", (account_id,))
        before = conn.execute("SELECT * FROM journalline WHERE id=801").fetchone()
        conn.commit()

    result = migrate_database(path)
    assert result["from_version"] == 10
    assert result["to_version"] == CURRENT_SCHEMA_VERSION == 11
    assert validate_sqlite_integrity(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 11
        assert conn.execute("SELECT * FROM journalline WHERE id=801").fetchone() == before
        assert conn.execute("SELECT count(*) FROM cfdisource").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM cfditaxevidence").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM cfdisourcelink").fetchone()[0] == 0
        assert {row[1] for row in conn.execute("PRAGMA table_info(cfdisource)")} >= {
            "entity_id", "third_party_id", "uuid", "file_hash", "xml_bytes",
            "subtotal", "total", "total_transferred", "total_withheld",
        }
        unique_source = {
            tuple(item[2] for item in conn.execute(f"PRAGMA index_info('{row[1]}')"))
            for row in conn.execute("PRAGMA index_list(cfdisource)") if row[2] == 1
        }
        assert ("uuid",) in unique_source
        assert ("file_hash",) in unique_source
        unique_link = {
            tuple(item[2] for item in conn.execute(f"PRAGMA index_info('{row[1]}')"))
            for row in conn.execute("PRAGMA index_list(cfdisourcelink)") if row[2] == 1
        }
        assert {("cfdi_source_id",), ("document_reference_id",)} <= unique_link


def test_schema11_validation_rejects_missing_or_malformed_cfdi_tables(tmp_path):
    import sqlite3
    from aqorath.migrations import migrate_database

    path, _engine = _database(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE cfdisourcelink")
        conn.commit()
    with pytest.raises(RuntimeError, match="Invalid schema 11 CFDI table"):
        migrate_database(path)


def _accounting_runtime(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.account_bindings import set_account_binding
    from aqorath.models import Account
    from sqlmodel import Session

    path, engine = _database(tmp_path)
    with Session(engine) as session:
        entity, party = _identity(session)
        bank = Account(code="1101", name="Banco", nature="DEBIT")
        expense = Account(code="5102", name="Servicios", nature="DEBIT")
        cash = Account(code="1102", name="Caja", nature="DEBIT")
        sales = Account(code="4201", name="Ventas", nature="CREDIT")
        session.add_all([bank, expense, cash, sales])
        session.commit()
        set_account_binding(session, "bank", bank.code)
        set_account_binding(session, "utilities_expense", expense.code)
        set_account_binding(session, "cash", cash.code)
        set_account_binding(session, "sales_revenue", sales.code)
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)
    monkeypatch.setattr(storage, "get_session", lambda: Session(engine))
    return engine, entity, party


def test_cfdi_prepare_confirm_posts_exact_snapshot_and_links_all_evidence_once(tmp_path, monkeypatch):
    from aqorath.application import import_cfdi_source, prepare_cfdi_accounting, confirm_cfdi_accounting
    from aqorath.cfdi_models import CfdiSourceLinkRecord
    from aqorath.models import AuditEventRecord, CfdiImportMetadataRecord, DocumentReferenceRecord, JournalEntry, JournalLine
    from sqlmodel import Session, select

    engine, entity, party = _accounting_runtime(tmp_path, monkeypatch)
    with Session(engine) as session:
        source = import_cfdi_source(session, _xml()).source
        prepared = prepare_cfdi_accounting(session, source.id, "purchase_utility_bank")
        assert prepared.decision.fact.amount == Decimal("1160.00")
        assert prepared.decision.posting_date.isoformat() == "2026-09-10"
        assert session.exec(select(JournalEntry)).all() == []

    first = confirm_cfdi_accounting(prepared)
    assert confirm_cfdi_accounting(prepared) == first
    with Session(engine) as session:
        entries = session.exec(select(JournalEntry)).all()
        assert len(entries) == 1
        lines = session.exec(select(JournalLine).where(JournalLine.entry_id == first["entry_id"])).all()
        assert sorted((line.debit, line.credit) for line in lines) == [("0", "1160.00"), ("1160.00", "0")]
        document = session.exec(select(DocumentReferenceRecord)).one()
        assert document.third_party_id == party.id
        assert document.file_hash == source.parsed.sha256
        assert session.exec(select(CfdiImportMetadataRecord)).one().uuid == source.parsed.uuid
        assert session.exec(select(CfdiSourceLinkRecord)).one().cfdi_source_id == source.id
        audits = session.exec(select(AuditEventRecord)).all()
        assert [item.event_type for item in audits].count("entry_posted") == 1
        assert [item.event_type for item in audits].count("cfdi_source_linked") == 1


def test_cfdi_confirm_rolls_back_posting_document_metadata_link_and_audits(tmp_path, monkeypatch):
    import aqorath.cfdi_accounting as accounting
    from aqorath.application import import_cfdi_source, prepare_cfdi_accounting
    from aqorath.cfdi_models import CfdiSourceLinkRecord, CfdiSourceRecord
    from aqorath.models import AuditEventRecord, CfdiImportMetadataRecord, DocumentReferenceRecord, JournalEntry
    from sqlmodel import Session, select

    engine, entity, _party_row = _accounting_runtime(tmp_path, monkeypatch)
    with Session(engine) as session:
        source = import_cfdi_source(session, _xml()).source
        prepared = prepare_cfdi_accounting(session, source.id, "purchase_utility_bank")

    def fail(*_args, **_kwargs):
        raise RuntimeError("forced late CFDI link failure")

    monkeypatch.setattr(accounting._sources, "stage_cfdi_source_link", fail)
    with pytest.raises(RuntimeError, match="forced late CFDI link failure"):
        accounting.confirm_cfdi_accounting(prepared)
    with Session(engine) as session:
        assert len(session.exec(select(CfdiSourceRecord)).all()) == 1
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(DocumentReferenceRecord)).all() == []
        assert session.exec(select(CfdiImportMetadataRecord)).all() == []
        assert session.exec(select(CfdiSourceLinkRecord)).all() == []
        assert [item.event_type for item in session.exec(select(AuditEventRecord)).all()] == ["cfdi_source_imported"]


def test_outgoing_cfdi_requires_explicit_compatible_sale_and_reuses_customer(tmp_path, monkeypatch):
    from aqorath.application import import_cfdi_source, prepare_cfdi_accounting
    from aqorath.third_party_repository import create_third_party
    from sqlmodel import Session

    engine, entity, _supplier = _accounting_runtime(tmp_path, monkeypatch)
    with Session(engine) as session:
        customer = create_third_party(
            session,
            _party(entity.id, rfc="COSC8001137NA", name="Cliente Ejemplo", party_type="customer"),
        )
        source = import_cfdi_source(session, _outgoing_xml()).source
        assert source.relationship == "sale"
        assert source.third_party_id == customer.id
        prepared = prepare_cfdi_accounting(session, source.id, "sale_cash")
        assert prepared.decision.fact.type == "sale"
        with pytest.raises(ValueError, match="issuer/receiver relationship"):
            prepare_cfdi_accounting(session, source.id, "purchase_utility_bank")
        with pytest.raises(ValueError, match="FormaPago"):
            purchase = import_cfdi_source(
                session,
                _xml().replace(b'FormaPago="03"', b'FormaPago="01"').replace(
                    b'UUID="123e4567-e89b-12d3-a456-426614174000"',
                    b'UUID="323e4567-e89b-12d3-a456-426614174000"',
                ),
            ).source
            prepare_cfdi_accounting(session, purchase.id, "purchase_utility_bank")


def test_cfdi_common_surface_import_prepare_cancel_confirm_and_professional_truth(tmp_path, monkeypatch):
    import base64
    from aqorath.presentation_controller import LocalPresentationController
    from aqorath.models import DocumentReferenceRecord, JournalEntry
    from sqlmodel import Session, select

    engine, _entity_row, _party_row = _accounting_runtime(tmp_path, monkeypatch)
    controller = LocalPresentationController()
    imported = controller.import_cfdi({"xml_base64": base64.b64encode(_xml()).decode("ascii")})
    assert imported["duplicate"] is False
    assert imported["source"]["uuid"] == "123E4567-E89B-12D3-A456-426614174000"
    assert imported["source"]["total"] == "1160.00"
    assert imported["source"]["total_transferred"] == "160.00"
    assert controller.professional_cfdi(imported["source"]["uuid"])["status"] == "imported_unposted"

    payload = {"uuid": imported["source"]["uuid"], "operation_kind": "purchase_utility_bank"}
    cancelled = controller.prepare_cfdi(payload)
    assert cancelled["preview"]["document_total"] == "1160.00"
    assert "Importar no contabiliza" in cancelled["preview"]["warning"]
    assert controller.cancel(cancelled["token"]) == {"cancelled": True}
    with Session(engine) as session:
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(DocumentReferenceRecord)).all() == []

    pending = controller.prepare_cfdi(payload)
    payload["operation_kind"] = "sale_cash"
    result = controller.confirm(pending["token"])
    professional = controller.professional_cfdi(imported["source"]["uuid"])
    assert professional["status"] == "linked_to_posted_accounting"
    assert professional["accounting"]["entry_id"] == result["entry_id"]
    assert professional["source"]["total"] == "1160.00"
    assert sorted((line["debit"], line["credit"]) for line in professional["accounting"]["lines"]) == [("0", "1160.00"), ("1160.00", "0")]
    assert "evidencia externa" in professional["distinction"]


def test_cfdi_http_routes_delegate_and_present_errors_explicitly(monkeypatch):
    import aqorath.web_surface as web

    calls = []
    monkeypatch.setattr(web.controller, "import_cfdi", lambda payload: calls.append(("import", payload)) or {"ok": True})
    monkeypatch.setattr(web.controller, "cfdi_sources", lambda: [{"uuid": "U"}])
    monkeypatch.setattr(web.controller, "prepare_cfdi", lambda payload: calls.append(("prepare", payload)) or {"token": "T"})
    monkeypatch.setattr(web.controller, "professional_cfdi", lambda uuid: {"uuid": uuid})
    assert web.import_cfdi({"xml_base64": "WA=="}) == {"ok": True}
    assert web.cfdi_sources() == [{"uuid": "U"}]
    assert web.prepare_cfdi({"uuid": "U", "operation_kind": "sale_cash"}) == {"token": "T"}
    assert web.professional_cfdi("U") == {"uuid": "U"}
    assert calls == [
        ("import", {"xml_base64": "WA=="}),
        ("prepare", {"uuid": "U", "operation_kind": "sale_cash"}),
    ]


def test_cfdi_browser_surface_is_a_human_file_preview_confirm_flow_not_accounting_logic():
    import inspect
    import aqorath.presentation_controller as presentation
    from aqorath.web_assets import APP_HTML

    for marker in (
        'id="cfdiFile" type="file"',
        "Importar y revisar evidencia",
        "Importarlo conserva evidencia; no crea una póliza",
        "Preparar con los datos del XML",
        "Confirmar y contabilizar",
        "CFDI fuente · evidencia y contabilidad",
        "el XML no sustituyó al ledger",
        "tratamiento fiscal específico pendiente/no cubierto",
    ):
        assert marker.lower() in APP_HTML.lower()
    common = APP_HTML.split('<section id="common"', 1)[1].split('<section id="professional"', 1)[0]
    assert "account_code" not in common
    assert "journal_line_id" not in common
    assert "Debe/Haber" not in common
    source = inspect.getsource(presentation)
    assert "sqlmodel" not in source.lower()
    assert "cfdi_models" not in source
    assert "journalentry" not in source.lower()
