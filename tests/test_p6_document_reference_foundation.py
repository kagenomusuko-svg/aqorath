"""Phase 6C.1 — DocumentReference foundation contracts.

Contracts only. A DocumentReference is structured source-evidence metadata linked to an
existing JournalEntry. It does not parse CFDI/XML, own accounting truth, mutate entries,
or establish a second document/storage authority.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import date as calendar_date, datetime, timezone
import inspect
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select


_SHA256 = "0123456789abcdef" * 4


def _entity():
    from aqorath.entity import Entity, EntityProfile

    return Entity(
        id=None,
        name="Meriadock A.C.",
        rfc=None,
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


def _third_party(entity_id, *, name="Contraparte documental", active=True):
    from aqorath.third_party import ThirdParty

    return ThirdParty(
        id=None,
        entity_id=entity_id,
        name=name,
        rfc="XAXX010101000",
        email=None,
        phone=None,
        party_type="supplier",
        address=None,
        contact_person=None,
        notes=None,
        is_active=active,
    )


def _document(
    entry_id,
    *,
    third_party_id=None,
    document_type="cfdi",
    document_number="DOC-001",
    issuer_name="Proveedor Demo",
    document_date=None,
    file_hash=_SHA256,
    file_path="documentos/fuente/doc-001.xml",
    external_url=None,
    is_validated=False,
    validation_notes=None,
):
    from aqorath.document_reference import DocumentReference

    if document_date is None:
        document_date = datetime(2026, 8, 27, 10, 30, tzinfo=timezone.utc)
    return DocumentReference(
        id=None,
        entry_id=entry_id,
        third_party_id=third_party_id,
        document_type=document_type,
        document_number=document_number,
        issuer_name=issuer_name,
        date=document_date,
        file_hash=file_hash,
        file_path=file_path,
        external_url=external_url,
        is_validated=is_validated,
        validation_notes=validation_notes,
    )


def _fresh_db(tmp_path, filename="document-reference.db"):
    from aqorath.migrations import migrate_database

    db_path = tmp_path / filename
    result = migrate_database(str(db_path))
    assert result["to_version"] == 4
    return db_path, create_engine(f"sqlite:///{db_path}")


def _create_entity(session):
    from aqorath.entity_repository import create_entity

    return create_entity(session, _entity())


def _create_third_party(session, entity_id, *, active=True):
    from aqorath.third_party_repository import create_third_party

    return create_third_party(
        session,
        _third_party(entity_id, active=active),
    )


def _ensure_accounts(session):
    from aqorath.models import Account

    existing = {row.code: row for row in session.exec(select(Account)).all()}
    if "1101" not in existing:
        session.add(Account(code="1101", name="Banco", nature="DEBIT"))
    if "4201" not in existing:
        session.add(Account(code="4201", name="Ingreso", nature="CREDIT"))
    session.commit()
    return {row.code: row for row in session.exec(select(Account)).all()}


def _create_entry(session, *, doc_ref="legacy-free-text"):
    from aqorath.models import JournalEntry, JournalLine

    accounts = _ensure_accounts(session)
    entry = JournalEntry(
        date=datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc),
        concept="Operación documental de prueba",
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


def test_document_reference_domain_is_pure_frozen_generic_source_evidence_not_accounting_or_cfdi_truth():
    import aqorath.document_reference as domain
    from aqorath.document_reference import DocumentReference

    document = DocumentReference(
        id=None,
        entry_id=7,
        third_party_id=None,
        document_type="contrato",
        document_number="C-2026-001",
        issuer_name=None,
        date=datetime(2026, 8, 27, tzinfo=timezone.utc),
        file_hash=None,
        file_path=None,
        external_url=None,
        is_validated=False,
        validation_notes=None,
    )
    assert [field.name for field in fields(DocumentReference)] == [
        "id",
        "entry_id",
        "third_party_id",
        "document_type",
        "document_number",
        "issuer_name",
        "date",
        "file_hash",
        "file_path",
        "external_url",
        "is_validated",
        "validation_notes",
    ]
    with pytest.raises(FrozenInstanceError):
        document.document_number = "changed"

    forbidden = {
        "entity_id",
        "account_id",
        "account_code",
        "debit",
        "credit",
        "amount",
        "cfdi_uuid",
        "sello_sat",
        "certificado",
        "fiscal_rule_set_id",
        "xml_bytes",
    }
    assert forbidden.isdisjoint({field.name for field in fields(DocumentReference)})
    source = inspect.getsource(domain).lower()
    assert "sqlmodel" not in source
    assert "sqlalchemy" not in source


def test_document_reference_validates_ids_text_datetime_boolean_and_sha256_fail_closed():
    from aqorath.document_reference import DocumentReference

    baseline = dict(
        id=None,
        entry_id=1,
        third_party_id=None,
        document_type="cfdi",
        document_number="ABC",
        issuer_name=None,
        date=datetime(2026, 8, 27, tzinfo=timezone.utc),
        file_hash=None,
        file_path=None,
        external_url=None,
        is_validated=False,
        validation_notes=None,
    )

    persisted = DocumentReference(**{**baseline, "id": 9, "third_party_id": 4})
    assert persisted.id == 9
    assert persisted.third_party_id == 4

    uppercase_hash = DocumentReference(**{**baseline, "file_hash": _SHA256.upper()})
    assert uppercase_hash.file_hash == _SHA256.upper()

    invalid = (
        {"id": 0},
        {"id": True},
        {"entry_id": 0},
        {"entry_id": True},
        {"third_party_id": 0},
        {"third_party_id": True},
        {"document_type": ""},
        {"document_type": "   "},
        {"document_number": ""},
        {"date": calendar_date(2026, 8, 27)},
        {"date": "2026-08-27"},
        {"is_validated": "yes"},
        {"file_hash": "abc"},
        {"file_hash": "z" * 64},
    )
    for patch in invalid:
        with pytest.raises((TypeError, ValueError)):
            DocumentReference(**{**baseline, **patch})

    for field_name in (
        "issuer_name",
        "file_path",
        "external_url",
        "validation_notes",
    ):
        with pytest.raises((TypeError, ValueError)):
            DocumentReference(**{**baseline, field_name: ""})


def test_document_type_is_explicit_extensible_and_never_inferred_from_number_path_or_url():
    from aqorath.document_reference import DocumentReference

    custom = DocumentReference(
        id=None,
        entry_id=1,
        third_party_id=None,
        document_type="bank_statement",
        document_number="550e8400-e29b-41d4-a716-446655440000",
        issuer_name="Banco",
        date=datetime(2026, 8, 27, tzinfo=timezone.utc),
        file_hash=None,
        file_path="evidencia/factura.xml",
        external_url="https://example.test/cfdi/550e8400",
        is_validated=False,
        validation_notes=None,
    )
    assert custom.document_type == "bank_statement"


def test_file_metadata_is_reference_only_and_never_reads_hashes_downloads_or_parses_content():
    import aqorath.document_reference as domain

    document = _document(
        1,
        file_path="/ruta/que/no/necesita/existir/archivo.xml",
        external_url="https://example.test/recurso.xml",
        file_hash=_SHA256,
    )
    assert document.file_hash == _SHA256
    assert document.file_path.endswith("archivo.xml")
    assert document.external_url.startswith("https://")

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "open(",
        "pathlib",
        "requests",
        "httpx",
        "urlopen",
        "lxml",
        "xml.etree",
        "hashlib",
    ):
        assert forbidden not in source


def test_document_reference_repository_public_contracts_are_minimal_exact_and_non_destructive():
    import aqorath.document_reference_repository as repository

    assert str(inspect.signature(repository.create_document_reference)) == (
        "(session, document_reference)"
    )
    assert str(inspect.signature(repository.get_document_reference)) == (
        "(session, document_reference_id)"
    )
    assert str(inspect.signature(repository.list_document_references)) == (
        "(session, entry_id)"
    )
    for forbidden in (
        "delete_document_reference",
        "parse_cfdi",
        "generate_cfdi",
        "import_xml",
        "stamp_cfdi",
    ):
        assert not hasattr(repository, forbidden)


def test_frozen_v4_additively_creates_document_reference_schema_with_entry_and_optional_third_party_foreign_keys(tmp_path):
    from aqorath.migrations import CURRENT_SCHEMA_VERSION
    from aqorath.models import DocumentReferenceRecord

    assert CURRENT_SCHEMA_VERSION == 4
    assert DocumentReferenceRecord.__tablename__ == "documentreference"

    db_path, engine = _fresh_db(tmp_path, "schema.db")
    engine.dispose()
    conn = sqlite3.connect(str(db_path))
    try:
        columns = {
            row[1]: row
            for row in conn.execute("PRAGMA table_info(documentreference)")
        }
        assert set(columns) == {
            "id",
            "entry_id",
            "third_party_id",
            "document_type",
            "document_number",
            "issuer_name",
            "date",
            "file_hash",
            "file_path",
            "external_url",
            "is_validated",
            "validation_notes",
            "created_at",
        }
        for required in (
            "entry_id",
            "document_type",
            "document_number",
            "date",
            "is_validated",
            "created_at",
        ):
            assert columns[required][3] == 1, required
        for optional in (
            "third_party_id",
            "issuer_name",
            "file_hash",
            "file_path",
            "external_url",
            "validation_notes",
        ):
            assert columns[optional][3] == 0, optional

        fks = conn.execute("PRAGMA foreign_key_list(documentreference)").fetchall()
        assert any(
            row[2] == "journalentry"
            and row[3] == "entry_id"
            and row[4] == "id"
            for row in fks
        )
        assert any(
            row[2] == "thirdparty"
            and row[3] == "third_party_id"
            and row[4] == "id"
            for row in fks
        )

        unique_indexes = [
            row
            for row in conn.execute(
                "PRAGMA index_list(documentreference)"
            ).fetchall()
            if row[2] == 1
        ]
        unique_column_sets = {
            tuple(
                col[2]
                for col in conn.execute(
                    f"PRAGMA index_info({row[1]})"
                ).fetchall()
            )
            for row in unique_indexes
        }
        assert ("document_number",) not in unique_column_sets
        assert ("file_hash",) not in unique_column_sets
    finally:
        conn.close()


def test_current_v4_additive_ensure_adds_document_reference_without_rewriting_existing_truth(tmp_path):
    from aqorath.migrations import get_schema_version, migrate_database

    db_path = tmp_path / "existing-v4.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE fiscalpostingauditrecord (id INTEGER PRIMARY KEY)"
        )
        conn.execute(
            "CREATE TABLE preserved_truth (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO preserved_truth VALUES (1, 'keep-me')")
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    finally:
        conn.close()

    result = migrate_database(str(db_path))
    assert result == {
        "from_version": 4,
        "to_version": 4,
        "migrated": False,
        "backup_path": None,
    }
    assert get_schema_version(str(db_path)) == 4

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute(
            "SELECT value FROM preserved_truth WHERE id=1"
        ).fetchone() == ("keep-me",)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "entity",
            "thirdparty",
            "documentreference",
        }.issubset(tables)
    finally:
        conn.close()


def test_create_document_reference_round_trip_preserves_every_value_and_allows_many_documents_per_entry(tmp_path):
    from aqorath.document_reference import DocumentReference
    from aqorath.document_reference_repository import (
        create_document_reference,
        get_document_reference,
        list_document_references,
    )
    from aqorath.models import DocumentReferenceRecord

    _, engine = _fresh_db(tmp_path, "round-trip.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            party = _create_third_party(session, entity.id)
            entry = _create_entry(session)

            first = create_document_reference(
                session,
                _document(
                    entry.id,
                    third_party_id=party.id,
                    document_number="CFDI-001",
                    is_validated=True,
                    validation_notes="Metadatos revisados",
                ),
            )
            second = create_document_reference(
                session,
                _document(
                    entry.id,
                    third_party_id=None,
                    document_type="contrato",
                    document_number="CONT-001",
                    issuer_name=None,
                    file_hash=None,
                    file_path=None,
                ),
            )

            assert isinstance(first, DocumentReference)
            assert isinstance(second, DocumentReference)
            assert first.id != second.id
            assert first.third_party_id == party.id
            assert first.validation_notes == "Metadatos revisados"
            assert second.third_party_id is None
            assert len(session.exec(select(DocumentReferenceRecord)).all()) == 2
            assert get_document_reference(session, first.id) == first
            assert list_document_references(session, entry.id) == (first, second)
    finally:
        engine.dispose()


def test_create_document_reference_requires_existing_entry_and_existing_optional_third_party(tmp_path):
    from aqorath.document_reference_repository import create_document_reference

    _, engine = _fresh_db(tmp_path, "references.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            party = _create_third_party(session, entity.id)
            entry = _create_entry(session)

            standalone = create_document_reference(
                session,
                _document(entry.id, third_party_id=None),
            )
            assert standalone.third_party_id is None

            with pytest.raises(LookupError, match="JournalEntry"):
                create_document_reference(
                    session,
                    _document(entry.id + 999, third_party_id=None),
                )
            with pytest.raises(LookupError, match="ThirdParty"):
                create_document_reference(
                    session,
                    _document(entry.id, third_party_id=party.id + 999),
                )
    finally:
        engine.dispose()


def test_document_can_preserve_reference_to_inactive_third_party_as_historical_evidence(tmp_path):
    from aqorath.document_reference_repository import create_document_reference
    from aqorath.third_party_repository import set_third_party_active

    _, engine = _fresh_db(tmp_path, "inactive-party.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            party = _create_third_party(session, entity.id)
            inactive = set_third_party_active(
                session,
                entity.id,
                party.id,
                False,
            )
            assert inactive.is_active is False
            entry = _create_entry(session)

            persisted = create_document_reference(
                session,
                _document(entry.id, third_party_id=party.id),
            )
            assert persisted.third_party_id == party.id
    finally:
        engine.dispose()


def test_create_document_reference_rolls_back_when_single_commit_fails(tmp_path, monkeypatch):
    from aqorath.document_reference_repository import create_document_reference
    from aqorath.models import DocumentReferenceRecord

    _, engine = _fresh_db(tmp_path, "rollback.db")
    try:
        with Session(engine) as session:
            entry = _create_entry(session)

            def fail_commit():
                raise RuntimeError("commit failed")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="commit failed"):
                create_document_reference(
                    session,
                    _document(entry.id),
                )
            assert session.exec(select(DocumentReferenceRecord)).all() == []
    finally:
        engine.dispose()


def test_get_and_list_document_references_fail_closed_and_list_is_entry_scoped_deterministic(tmp_path):
    from aqorath.document_reference_repository import (
        create_document_reference,
        get_document_reference,
        list_document_references,
    )

    _, engine = _fresh_db(tmp_path, "reads.db")
    try:
        with Session(engine) as session:
            first_entry = _create_entry(session, doc_ref="legacy-one")
            second_entry = _create_entry(session, doc_ref="legacy-two")

            one = create_document_reference(
                session,
                _document(first_entry.id, document_number="ONE"),
            )
            two = create_document_reference(
                session,
                _document(first_entry.id, document_number="TWO"),
            )
            three = create_document_reference(
                session,
                _document(second_entry.id, document_number="THREE"),
            )

            assert get_document_reference(session, one.id) == one
            assert list_document_references(session, first_entry.id) == (one, two)
            assert list_document_references(session, second_entry.id) == (three,)

            with pytest.raises(LookupError):
                get_document_reference(session, three.id + 999)
            with pytest.raises(LookupError, match="JournalEntry"):
                list_document_references(session, second_entry.id + 999)

            for bad in (0, True, "1"):
                with pytest.raises((TypeError, ValueError)):
                    get_document_reference(session, bad)
                with pytest.raises((TypeError, ValueError)):
                    list_document_references(session, bad)
    finally:
        engine.dispose()


def test_legacy_journalentry_doc_ref_is_not_structured_document_authority_or_auto_backfilled(tmp_path):
    from aqorath.document_reference_repository import list_document_references

    _, engine = _fresh_db(tmp_path, "legacy-doc-ref.db")
    try:
        with Session(engine) as session:
            entry = _create_entry(
                session,
                doc_ref="legacy-only-free-text-reference",
            )
            assert list_document_references(session, entry.id) == ()
    finally:
        engine.dispose()


def test_document_reference_persistence_does_not_mutate_accounting_fiscal_or_counterparty_truth(tmp_path):
    from aqorath.document_reference_repository import create_document_reference
    from aqorath.models import (
        Account,
        DocumentReferenceRecord,
        FiscalPostingAuditRecord,
        JournalEntry,
        JournalLine,
        ThirdPartyRecord,
    )

    _, engine = _fresh_db(tmp_path, "side-effects.db")
    try:
        with Session(engine) as session:
            entity = _create_entity(session)
            party = _create_third_party(session, entity.id)
            entry = _create_entry(session, doc_ref="keep-legacy-value")

            before = {
                "accounts": len(session.exec(select(Account)).all()),
                "entries": len(session.exec(select(JournalEntry)).all()),
                "lines": len(session.exec(select(JournalLine)).all()),
                "audits": len(
                    session.exec(select(FiscalPostingAuditRecord)).all()
                ),
                "parties": len(session.exec(select(ThirdPartyRecord)).all()),
            }

            create_document_reference(
                session,
                _document(entry.id, third_party_id=party.id),
            )

            after = {
                "accounts": len(session.exec(select(Account)).all()),
                "entries": len(session.exec(select(JournalEntry)).all()),
                "lines": len(session.exec(select(JournalLine)).all()),
                "audits": len(
                    session.exec(select(FiscalPostingAuditRecord)).all()
                ),
                "parties": len(session.exec(select(ThirdPartyRecord)).all()),
            }
            assert after == before
            assert len(
                session.exec(select(DocumentReferenceRecord)).all()
            ) == 1
            reloaded_entry = session.get(JournalEntry, entry.id)
            assert reloaded_entry.doc_ref == "keep-legacy-value"
    finally:
        engine.dispose()


def test_document_reference_repository_uses_only_supplied_session_and_no_filesystem_network_or_xml_authority():
    import aqorath.document_reference_repository as repository

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
    ):
        assert forbidden not in source


def test_application_exposes_document_reference_foundation_with_exact_signatures_and_delegates_only_to_repository(monkeypatch):
    import aqorath.application as application

    assert str(inspect.signature(application.create_document_reference)) == (
        "(session, document_reference)"
    )
    assert str(inspect.signature(application.get_document_reference)) == (
        "(session, document_reference_id)"
    )
    assert str(inspect.signature(application.list_document_references)) == (
        "(session, entry_id)"
    )

    calls = []

    def fake_create(session, document_reference):
        calls.append(("create", session, document_reference))
        return "created"

    def fake_get(session, document_reference_id):
        calls.append(("get", session, document_reference_id))
        return "loaded"

    def fake_list(session, entry_id):
        calls.append(("list", session, entry_id))
        return ("a", "b")

    monkeypatch.setattr(
        application._document_reference_repository,
        "create_document_reference",
        fake_create,
    )
    monkeypatch.setattr(
        application._document_reference_repository,
        "get_document_reference",
        fake_get,
    )
    monkeypatch.setattr(
        application._document_reference_repository,
        "list_document_references",
        fake_list,
    )

    session = object()
    document = object()
    assert application.create_document_reference(session, document) == "created"
    assert application.get_document_reference(session, 12) == "loaded"
    assert application.list_document_references(session, 44) == ("a", "b")
    assert calls == [
        ("create", session, document),
        ("get", session, 12),
        ("list", session, 44),
    ]
