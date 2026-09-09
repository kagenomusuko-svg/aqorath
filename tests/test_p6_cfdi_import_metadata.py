"""Phase 6D.1 — CFDI import metadata/provenance contracts.

Contracts only. A CfdiImportMetadata record is immutable stamped-CFDI evidence attached
one-to-one to an existing DocumentReference whose explicit document_type is ``cfdi``.
It does not parse XML, validate against SAT, calculate taxes, select accounts, post,
timbrar, generate CFDI, or establish a second document/storage authority.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import date as calendar_date, datetime, timezone
import inspect
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select


_SHA256 = "0123456789abcdef" * 4
_UUID = "123E4567-E89B-12D3-A456-426614174000"
_OTHER_UUID = "223E4567-E89B-12D3-A456-426614174000"


def _entity():
    from aqorath.entity import Entity, EntityProfile

    return Entity(
        id=None,
        name="Meriadock A.C.",
        rfc="MER260101AB1",
        legal_personality="persona_moral",
        legal_form="A.C.",
        profile=EntityProfile(
            economic_purpose="no_lucrativo",
            is_donor_authorized=False,
            special_capabilities=("osc",),
            modules_enabled=("banking",),
        ),
        is_active=True,
    )


def _third_party(entity_id):
    from aqorath.third_party import ThirdParty

    return ThirdParty(
        id=None,
        entity_id=entity_id,
        name="Proveedor CFDI",
        rfc="AAA010101AAA",
        email=None,
        phone=None,
        party_type="supplier",
        address=None,
        contact_person=None,
        notes=None,
        is_active=True,
    )


def _fresh_db(tmp_path, filename="cfdi-import-metadata.db"):
    from aqorath.migrations import migrate_database

    db_path = tmp_path / filename
    result = migrate_database(str(db_path))
    assert result["to_version"] == 5
    return db_path, create_engine(f"sqlite:///{db_path}")


def _ensure_accounts(session):
    from aqorath.models import Account

    existing = {row.code: row for row in session.exec(select(Account)).all()}
    if "1101" not in existing:
        session.add(Account(code="1101", name="Banco", nature="DEBIT"))
    if "4201" not in existing:
        session.add(Account(code="4201", name="Ingreso", nature="CREDIT"))
    session.commit()
    return {row.code: row for row in session.exec(select(Account)).all()}


def _create_entry(session, *, doc_ref="legacy-cfdi-free-text"):
    from aqorath.models import JournalEntry, JournalLine

    accounts = _ensure_accounts(session)
    entry = JournalEntry(
        date=datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc),
        concept="Operación respaldada por CFDI",
        doc_ref=doc_ref,
        state="posted",
    )
    session.add(entry)
    session.flush()
    assert entry.id is not None
    session.add(
        JournalLine(
            entry_id=entry.id,
            account_code="1101",
            account_id=accounts["1101"].id,
            debit="100.00",
            credit="0",
            description="Banco",
        )
    )
    session.add(
        JournalLine(
            entry_id=entry.id,
            account_code="4201",
            account_id=accounts["4201"].id,
            debit="0",
            credit="100.00",
            description="Ingreso",
        )
    )
    session.commit()
    session.refresh(entry)
    return entry


def _create_document(
    session,
    entry_id,
    *,
    third_party_id=None,
    document_type="cfdi",
    document_number="FOLIO-001",
    validated=False,
):
    from aqorath.document_reference import DocumentReference
    from aqorath.document_reference_repository import create_document_reference

    document = DocumentReference(
        id=None,
        entry_id=entry_id,
        third_party_id=third_party_id,
        document_type=document_type,
        document_number=document_number,
        issuer_name="Proveedor CFDI",
        date=datetime(2026, 8, 27, 8, 30, tzinfo=timezone.utc),
        file_hash=_SHA256,
        file_path="documentos/cfdi/folio-001.xml",
        external_url=None,
        is_validated=validated,
        validation_notes=None,
    )
    return create_document_reference(session, document)


def _metadata(
    document_reference_id,
    *,
    uuid=_UUID,
    cfdi_version="4.0",
    issuer_rfc="AAA010101AAA",
    receiver_rfc="MER260101AB1",
    issued_at=None,
    stamped_at=None,
    imported_at=None,
):
    from aqorath.cfdi_metadata import CfdiImportMetadata

    if issued_at is None:
        issued_at = datetime(2026, 8, 27, 8, 30, tzinfo=timezone.utc)
    if stamped_at is None:
        stamped_at = datetime(2026, 8, 27, 8, 31, 5, tzinfo=timezone.utc)
    if imported_at is None:
        imported_at = datetime(2026, 8, 27, 12, 45, 9, tzinfo=timezone.utc)
    return CfdiImportMetadata(
        id=None,
        document_reference_id=document_reference_id,
        cfdi_version=cfdi_version,
        uuid=uuid,
        issuer_rfc=issuer_rfc,
        receiver_rfc=receiver_rfc,
        issued_at=issued_at,
        stamped_at=stamped_at,
        sello_sat="SELLO-SAT-EXACTO-BASE64-SIN-INTERPRETAR",
        sat_certificate_number="00001000000700000001",
        imported_at=imported_at,
    )


def _create_entity_and_party(session):
    from aqorath.entity_repository import create_entity
    from aqorath.third_party_repository import create_third_party

    entity = create_entity(session, _entity())
    party = create_third_party(session, _third_party(entity.id))
    return entity, party


def test_cfdi_import_metadata_domain_is_pure_frozen_stamped_evidence_not_accounting_or_fiscal_truth():
    import aqorath.cfdi_metadata as domain
    from aqorath.cfdi_metadata import CfdiImportMetadata

    metadata = CfdiImportMetadata(
        id=None,
        document_reference_id=7,
        cfdi_version="4.0",
        uuid=_UUID,
        issuer_rfc="AAA010101AAA",
        receiver_rfc="MER260101AB1",
        issued_at=datetime(2026, 8, 27, 8, 30, tzinfo=timezone.utc),
        stamped_at=datetime(2026, 8, 27, 8, 31, tzinfo=timezone.utc),
        sello_sat="SELLO",
        sat_certificate_number="00001000000700000001",
        imported_at=datetime(2026, 8, 27, 12, 45, tzinfo=timezone.utc),
    )

    assert [field.name for field in fields(CfdiImportMetadata)] == [
        "id",
        "document_reference_id",
        "cfdi_version",
        "uuid",
        "issuer_rfc",
        "receiver_rfc",
        "issued_at",
        "stamped_at",
        "sello_sat",
        "sat_certificate_number",
        "imported_at",
    ]
    with pytest.raises(FrozenInstanceError):
        metadata.uuid = _OTHER_UUID

    forbidden = {
        "entry_id",
        "third_party_id",
        "file_hash",
        "file_path",
        "external_url",
        "issuer_name",
        "document_number",
        "amount",
        "subtotal",
        "total",
        "debit",
        "credit",
        "account_id",
        "account_code",
        "fiscal_rule_set_id",
        "tax_rate",
        "tax_amount",
        "xml_bytes",
    }
    assert forbidden.isdisjoint({field.name for field in fields(CfdiImportMetadata)})

    source = inspect.getsource(domain).lower()
    for forbidden_import in (
        "sqlmodel",
        "sqlalchemy",
        "lxml",
        "xml.etree",
        "requests",
        "httpx",
    ):
        assert forbidden_import not in source


def test_cfdi_import_metadata_validates_ids_text_datetimes_and_uuid_fail_closed_without_normalization():
    from aqorath.cfdi_metadata import CfdiImportMetadata

    baseline = dict(
        id=None,
        document_reference_id=1,
        cfdi_version="4.0",
        uuid=_UUID,
        issuer_rfc="AAA010101AAA",
        receiver_rfc="MER260101AB1",
        issued_at=datetime(2026, 8, 27, 8, 30, tzinfo=timezone.utc),
        stamped_at=datetime(2026, 8, 27, 8, 31, tzinfo=timezone.utc),
        sello_sat="SELLO",
        sat_certificate_number="00001000000700000001",
        imported_at=datetime(2026, 8, 27, 12, 45, tzinfo=timezone.utc),
    )

    persisted = CfdiImportMetadata(**{**baseline, "id": 9})
    assert persisted.id == 9
    assert persisted.uuid == _UUID
    assert persisted.cfdi_version == "4.0"

    lowercase_uuid = _UUID.lower()
    preserved = CfdiImportMetadata(**{**baseline, "uuid": lowercase_uuid})
    assert preserved.uuid == lowercase_uuid

    invalid = (
        {"id": 0},
        {"id": True},
        {"document_reference_id": 0},
        {"document_reference_id": True},
        {"cfdi_version": ""},
        {"cfdi_version": "   "},
        {"uuid": ""},
        {"uuid": "123"},
        {"uuid": "Z" * 36},
        {"uuid": "123E4567E89B12D3A456426614174000"},
        {"issuer_rfc": ""},
        {"receiver_rfc": "   "},
        {"issued_at": calendar_date(2026, 8, 27)},
        {"stamped_at": "2026-08-27T08:31:00"},
        {"imported_at": None},
        {"sello_sat": ""},
        {"sat_certificate_number": "   "},
    )
    for override in invalid:
        with pytest.raises((TypeError, ValueError)):
            CfdiImportMetadata(**{**baseline, **override})


def test_cfdi_version_rfc_and_timestamps_are_explicit_provenance_not_inferred_or_rewritten():
    from aqorath.cfdi_metadata import CfdiImportMetadata

    issued = datetime(2019, 5, 1, 9, 10, 11)
    stamped = datetime(2019, 5, 1, 9, 12, 13)
    imported = datetime(2026, 8, 27, 13, 14, 15, tzinfo=timezone.utc)
    metadata = CfdiImportMetadata(
        id=None,
        document_reference_id=3,
        cfdi_version="3.3",
        uuid=_OTHER_UUID.lower(),
        issuer_rfc="Issuer-Imported-Exactly",
        receiver_rfc="Receiver-Imported-Exactly",
        issued_at=issued,
        stamped_at=stamped,
        sello_sat="opaque-sello",
        sat_certificate_number="opaque-cert-number",
        imported_at=imported,
    )

    assert metadata.cfdi_version == "3.3"
    assert metadata.uuid == _OTHER_UUID.lower()
    assert metadata.issuer_rfc == "Issuer-Imported-Exactly"
    assert metadata.receiver_rfc == "Receiver-Imported-Exactly"
    assert metadata.issued_at is issued
    assert metadata.stamped_at is stamped
    assert metadata.imported_at is imported


def test_cfdi_metadata_repository_public_contracts_are_minimal_and_exact():
    import aqorath.cfdi_metadata_repository as repository

    assert str(inspect.signature(repository.register_cfdi_import_metadata)) == (
        "(session, metadata)"
    )
    assert str(inspect.signature(repository.get_cfdi_import_metadata)) == (
        "(session, document_reference_id)"
    )
    public = {
        name
        for name, value in vars(repository).items()
        if callable(value) and not name.startswith("_")
    }
    assert {"register_cfdi_import_metadata", "get_cfdi_import_metadata"} <= public


def test_frozen_v4_additively_creates_cfdi_metadata_schema_with_one_to_one_document_fk_and_unique_uuid(tmp_path):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION

    db_path, engine = _fresh_db(tmp_path, "schema.db")
    try:
        assert CURRENT_SCHEMA_VERSION == 5
        conn = sqlite3.connect(str(db_path))
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "cfdiimportmetadata" in tables

            columns = {
                row[1]: row
                for row in conn.execute(
                    "PRAGMA table_info(cfdiimportmetadata)"
                ).fetchall()
            }
            assert tuple(columns) == (
                "id",
                "document_reference_id",
                "cfdi_version",
                "uuid",
                "issuer_rfc",
                "receiver_rfc",
                "issued_at",
                "stamped_at",
                "sello_sat",
                "sat_certificate_number",
                "imported_at",
                "created_at",
            )
            for required in (
                "document_reference_id",
                "cfdi_version",
                "uuid",
                "issuer_rfc",
                "receiver_rfc",
                "issued_at",
                "stamped_at",
                "sello_sat",
                "sat_certificate_number",
                "imported_at",
                "created_at",
            ):
                assert columns[required][3] == 1

            foreign_keys = conn.execute(
                "PRAGMA foreign_key_list(cfdiimportmetadata)"
            ).fetchall()
            assert any(
                row[2] == "documentreference"
                and row[3] == "document_reference_id"
                and row[4] == "id"
                for row in foreign_keys
            )

            indexes = conn.execute(
                "PRAGMA index_list(cfdiimportmetadata)"
            ).fetchall()
            unique_indexes = {
                row[1]
                for row in indexes
                if row[2] == 1
            }
            indexed_columns = {
                index_name: tuple(
                    row[2]
                    for row in conn.execute(
                        f"PRAGMA index_info('{index_name}')"
                    ).fetchall()
                )
                for index_name in unique_indexes
            }
            assert ("document_reference_id",) in indexed_columns.values()
            assert ("uuid",) in indexed_columns.values()
        finally:
            conn.close()
    finally:
        engine.dispose()


def test_current_v4_additive_ensure_adds_cfdi_metadata_without_rewriting_existing_document_truth(tmp_path):
    from aqorath.migrations import migrate_database
    from aqorath.models import DocumentReferenceRecord

    db_path, engine = _fresh_db(tmp_path, "additive.db")
    try:
        with Session(engine) as session:
            _, party = _create_entity_and_party(session)
            entry = _create_entry(session)
            document = _create_document(
                session,
                entry.id,
                third_party_id=party.id,
                document_number="KEEP-ME",
            )
            before = session.get(DocumentReferenceRecord, document.id)
            before_values = (
                before.entry_id,
                before.third_party_id,
                before.document_type,
                before.document_number,
                before.file_hash,
                before.file_path,
                before.is_validated,
            )

        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("DROP TABLE cfdiimportmetadata")
            conn.commit()
            version_before = conn.execute("PRAGMA user_version").fetchone()[0]
            assert version_before == 5
        finally:
            conn.close()

        result = migrate_database(str(db_path))
        assert result == {
            "from_version": 5,
            "to_version": 5,
            "migrated": False,
            "backup_path": None,
        }

        with Session(engine) as session:
            after = session.get(DocumentReferenceRecord, document.id)
            assert (
                after.entry_id,
                after.third_party_id,
                after.document_type,
                after.document_number,
                after.file_hash,
                after.file_path,
                after.is_validated,
            ) == before_values
    finally:
        engine.dispose()


def test_register_cfdi_import_metadata_round_trip_preserves_every_value_exactly(tmp_path):
    from aqorath.cfdi_metadata_repository import (
        get_cfdi_import_metadata,
        register_cfdi_import_metadata,
    )
    from aqorath.models import CfdiImportMetadataRecord

    _, engine = _fresh_db(tmp_path, "round-trip.db")
    try:
        with Session(engine) as session:
            _, party = _create_entity_and_party(session)
            entry = _create_entry(session)
            document = _create_document(session, entry.id, third_party_id=party.id)
            expected = _metadata(document.id)

            persisted = register_cfdi_import_metadata(session, expected)
            assert persisted.id is not None
            assert persisted.document_reference_id == document.id
            assert persisted.cfdi_version == expected.cfdi_version
            assert persisted.uuid == expected.uuid
            assert persisted.issuer_rfc == expected.issuer_rfc
            assert persisted.receiver_rfc == expected.receiver_rfc
            assert persisted.issued_at == expected.issued_at
            assert persisted.stamped_at == expected.stamped_at
            assert persisted.sello_sat == expected.sello_sat
            assert persisted.sat_certificate_number == expected.sat_certificate_number
            assert persisted.imported_at == expected.imported_at

            loaded = get_cfdi_import_metadata(session, document.id)
            assert loaded == persisted

            row = session.exec(select(CfdiImportMetadataRecord)).one()
            assert row.document_reference_id == document.id
            assert row.issued_at == expected.issued_at.isoformat()
            assert row.stamped_at == expected.stamped_at.isoformat()
            assert row.imported_at == expected.imported_at.isoformat()
    finally:
        engine.dispose()


def test_register_cfdi_metadata_requires_existing_explicit_cfdi_document_reference(tmp_path):
    from aqorath.cfdi_metadata_repository import register_cfdi_import_metadata

    _, engine = _fresh_db(tmp_path, "document-type.db")
    try:
        with Session(engine) as session:
            entry = _create_entry(session)
            cfdi = _create_document(session, entry.id, document_type="cfdi")
            receipt = _create_document(
                session,
                entry.id,
                document_type="recibo",
                document_number="REC-001",
            )

            persisted = register_cfdi_import_metadata(
                session,
                _metadata(cfdi.id),
            )
            assert persisted.document_reference_id == cfdi.id

            with pytest.raises(LookupError, match="DocumentReference"):
                register_cfdi_import_metadata(
                    session,
                    _metadata(cfdi.id + 999, uuid=_OTHER_UUID),
                )

            with pytest.raises(ValueError, match="cfdi"):
                register_cfdi_import_metadata(
                    session,
                    _metadata(receipt.id, uuid=_OTHER_UUID),
                )
    finally:
        engine.dispose()


def test_cfdi_metadata_is_one_to_one_per_document_and_uuid_is_unique_across_installation(tmp_path):
    from aqorath.cfdi_metadata_repository import register_cfdi_import_metadata
    from aqorath.models import CfdiImportMetadataRecord

    _, engine = _fresh_db(tmp_path, "uniqueness.db")
    try:
        with Session(engine) as session:
            entry = _create_entry(session)
            first_doc = _create_document(
                session,
                entry.id,
                document_number="FOLIO-ONE",
            )
            second_doc = _create_document(
                session,
                entry.id,
                document_number="FOLIO-TWO",
            )

            first = register_cfdi_import_metadata(
                session,
                _metadata(first_doc.id),
            )
            assert first.id is not None

            with pytest.raises(Exception):
                register_cfdi_import_metadata(
                    session,
                    _metadata(first_doc.id, uuid=_OTHER_UUID),
                )
            with pytest.raises(Exception):
                register_cfdi_import_metadata(
                    session,
                    _metadata(second_doc.id, uuid=_UUID),
                )

            rows = session.exec(select(CfdiImportMetadataRecord)).all()
            assert len(rows) == 1
            assert rows[0].document_reference_id == first_doc.id
            assert rows[0].uuid == _UUID
    finally:
        engine.dispose()


def test_register_cfdi_metadata_rolls_back_when_single_commit_fails(tmp_path, monkeypatch):
    from aqorath.cfdi_metadata_repository import register_cfdi_import_metadata
    from aqorath.models import CfdiImportMetadataRecord

    _, engine = _fresh_db(tmp_path, "rollback.db")
    try:
        with Session(engine) as session:
            entry = _create_entry(session)
            document = _create_document(session, entry.id)

            def fail_commit():
                raise RuntimeError("commit failed")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="commit failed"):
                register_cfdi_import_metadata(
                    session,
                    _metadata(document.id),
                )
            assert session.exec(select(CfdiImportMetadataRecord)).all() == []
    finally:
        engine.dispose()


def test_get_cfdi_import_metadata_fails_closed_for_invalid_missing_or_unregistered_document(tmp_path):
    from aqorath.cfdi_metadata_repository import (
        get_cfdi_import_metadata,
        register_cfdi_import_metadata,
    )

    _, engine = _fresh_db(tmp_path, "reads.db")
    try:
        with Session(engine) as session:
            entry = _create_entry(session)
            registered_doc = _create_document(
                session,
                entry.id,
                document_number="REGISTERED",
            )
            unregistered_doc = _create_document(
                session,
                entry.id,
                document_number="UNREGISTERED",
            )
            registered = register_cfdi_import_metadata(
                session,
                _metadata(registered_doc.id),
            )
            assert get_cfdi_import_metadata(session, registered_doc.id) == registered

            with pytest.raises(LookupError):
                get_cfdi_import_metadata(session, unregistered_doc.id)
            with pytest.raises(LookupError):
                get_cfdi_import_metadata(session, registered_doc.id + 999)

            for bad in (0, True, "1"):
                with pytest.raises((TypeError, ValueError)):
                    get_cfdi_import_metadata(session, bad)
    finally:
        engine.dispose()


def test_cfdi_metadata_persistence_never_mutates_document_entry_third_party_accounting_or_fiscal_truth(tmp_path):
    from aqorath.cfdi_metadata_repository import register_cfdi_import_metadata
    from aqorath.models import (
        Account,
        CfdiImportMetadataRecord,
        DocumentReferenceRecord,
        FiscalPostingAuditRecord,
        FiscalRuleVersion,
        JournalEntry,
        JournalLine,
        ThirdPartyRecord,
    )

    _, engine = _fresh_db(tmp_path, "side-effects.db")
    try:
        with Session(engine) as session:
            _, party = _create_entity_and_party(session)
            entry = _create_entry(session, doc_ref="keep-this-legacy-reference")
            document = _create_document(
                session,
                entry.id,
                third_party_id=party.id,
                validated=False,
            )

            before_counts = {
                "accounts": len(session.exec(select(Account)).all()),
                "entries": len(session.exec(select(JournalEntry)).all()),
                "lines": len(session.exec(select(JournalLine)).all()),
                "audits": len(session.exec(select(FiscalPostingAuditRecord)).all()),
                "rules": len(session.exec(select(FiscalRuleVersion)).all()),
                "parties": len(session.exec(select(ThirdPartyRecord)).all()),
                "documents": len(session.exec(select(DocumentReferenceRecord)).all()),
            }

            register_cfdi_import_metadata(session, _metadata(document.id))

            after_counts = {
                "accounts": len(session.exec(select(Account)).all()),
                "entries": len(session.exec(select(JournalEntry)).all()),
                "lines": len(session.exec(select(JournalLine)).all()),
                "audits": len(session.exec(select(FiscalPostingAuditRecord)).all()),
                "rules": len(session.exec(select(FiscalRuleVersion)).all()),
                "parties": len(session.exec(select(ThirdPartyRecord)).all()),
                "documents": len(session.exec(select(DocumentReferenceRecord)).all()),
            }
            assert after_counts == before_counts
            assert len(session.exec(select(CfdiImportMetadataRecord)).all()) == 1

            reloaded_document = session.get(DocumentReferenceRecord, document.id)
            assert reloaded_document.is_validated is False
            assert reloaded_document.validation_notes is None
            assert reloaded_document.file_hash == _SHA256
            assert reloaded_document.file_path == "documentos/cfdi/folio-001.xml"

            reloaded_entry = session.get(JournalEntry, entry.id)
            assert reloaded_entry.doc_ref == "keep-this-legacy-reference"
            assert reloaded_entry.state == "posted"

            reloaded_party = session.get(ThirdPartyRecord, party.id)
            assert reloaded_party.rfc == "AAA010101AAA"
            assert reloaded_party.is_active is True
    finally:
        engine.dispose()


def test_cfdi_metadata_repository_uses_only_supplied_session_and_no_filesystem_network_xml_or_legacy_cfdi_authority():
    import aqorath.cfdi_metadata_repository as repository

    source = inspect.getsource(repository).lower()
    for forbidden in (
        "get_engine",
        "session(",
        "sqlite3",
        "aqorath_db",
        "os.getenv",
        "pathlib",
        "requests",
        "httpx",
        "open(",
        "lxml",
        "xml.etree",
        "generate_cfdi",
        "import_timbrado",
        "modelos.",
        "pac",
    ):
        assert forbidden not in source


def test_cfdi_metadata_does_not_duplicate_document_storage_or_monetary_fiscal_fields():
    from aqorath.cfdi_metadata import CfdiImportMetadata

    names = {field.name for field in fields(CfdiImportMetadata)}
    assert {
        "file_hash",
        "file_path",
        "external_url",
        "document_number",
        "issuer_name",
        "third_party_id",
        "entry_id",
        "amount",
        "subtotal",
        "total",
        "currency",
        "iva",
        "isr",
        "taxes",
        "account_code",
        "account_id",
    }.isdisjoint(names)


def test_application_exposes_cfdi_import_metadata_with_exact_signatures_and_delegates_only_to_repository(monkeypatch):
    import aqorath.application as application

    assert str(inspect.signature(application.register_cfdi_import_metadata)) == (
        "(session, metadata)"
    )
    assert str(inspect.signature(application.get_cfdi_import_metadata)) == (
        "(session, document_reference_id)"
    )

    calls = []

    def fake_register(session, metadata):
        calls.append(("register", session, metadata))
        return "registered"

    def fake_get(session, document_reference_id):
        calls.append(("get", session, document_reference_id))
        return "loaded"

    monkeypatch.setattr(
        application._cfdi_metadata_repository,
        "register_cfdi_import_metadata",
        fake_register,
    )
    monkeypatch.setattr(
        application._cfdi_metadata_repository,
        "get_cfdi_import_metadata",
        fake_get,
    )

    session = object()
    metadata = object()
    assert application.register_cfdi_import_metadata(session, metadata) == "registered"
    assert application.get_cfdi_import_metadata(session, 12) == "loaded"
    assert calls == [
        ("register", session, metadata),
        ("get", session, 12),
    ]

    source = inspect.getsource(application)
    register_body = source.split(
        "def register_cfdi_import_metadata", 1
    )[1].split("\ndef ", 1)[0]
    get_body = source.split(
        "def get_cfdi_import_metadata", 1
    )[1].split("\ndef ", 1)[0]
    for body in (register_body, get_body):
        lowered = body.lower()
        assert "generate_cfdi" not in lowered
        assert "import_timbrado" not in lowered
        assert "_fiscal_" not in lowered
        assert "_account_" not in lowered
        assert "_posting" not in lowered
