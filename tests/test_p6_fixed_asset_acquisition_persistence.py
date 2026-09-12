"""Phase 6Q acquisition contracts plus AQR-015 posted/audit regressions."""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest
from sqlmodel import Session, select


def _load_contracts():
    path = Path(__file__).with_name("_p6q_fixed_asset_acquisition_contracts.py")
    spec = spec_from_file_location("aqorath_p6q_fixed_asset_acquisition_contracts", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load frozen Phase 6Q fixed-asset acquisition contracts")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_contracts = _load_contracts()
_OVERRIDDEN = {
    "test_sqlite_enforces_one_acquisition_record_per_asset_even_if_executor_guard_is_bypassed",
    "test_sqlite_enforces_one_acquisition_identity_per_journal_entry",
    "test_executor_uses_existing_core_staging_once_with_exact_6p_payload",
    "test_loader_reconstructs_identity_date_and_structured_provenance_without_parsing_description",
}
for _name, _value in vars(_contracts).items():
    if _name.startswith("test_") and _name not in _OVERRIDDEN:
        globals()[_name] = _value


def _persist_balanced_placeholder_entry(session, *, when, concept):
    from aqorath.models import Account, JournalEntry, JournalLine

    debit_account = session.exec(select(Account).where(Account.code == "1203")).one()
    credit_account = session.exec(select(Account).where(Account.code == "1101")).one()
    entry = JournalEntry(date=when, concept=concept)
    session.add(entry)
    session.flush()
    session.add_all(
        (
            JournalLine(
                entry_id=entry.id,
                account_id=debit_account.id,
                account_code=debit_account.code,
                debit="1.00",
                credit="0",
            ),
            JournalLine(
                entry_id=entry.id,
                account_id=credit_account.id,
                account_code=credit_account.code,
                debit="0",
                credit="1.00",
            ),
        )
    )
    session.commit()
    session.refresh(entry)
    return entry


def test_sqlite_enforces_one_acquisition_record_per_asset_even_if_executor_guard_is_bypassed(tmp_path, monkeypatch):
    from aqorath.models import FixedAssetAcquisitionPostingRecord

    engine, _, _, fixed_asset_id = _contracts._initialize_canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        first_entry = _persist_balanced_placeholder_entry(session, when=datetime(2026, 1, 15), concept="first")
        second_entry = _persist_balanced_placeholder_entry(session, when=datetime(2026, 1, 16), concept="second")
        session.add(
            FixedAssetAcquisitionPostingRecord(
                fixed_asset_id=fixed_asset_id,
                entry_id=first_entry.id,
                asset_class="computer_equipment",
                settlement_method="bank",
            )
        )
        session.commit()
        session.add(
            FixedAssetAcquisitionPostingRecord(
                fixed_asset_id=fixed_asset_id,
                entry_id=second_entry.id,
                asset_class="computer_equipment",
                settlement_method="cash",
            )
        )
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


def test_sqlite_enforces_one_acquisition_identity_per_journal_entry(tmp_path, monkeypatch):
    from aqorath.models import FixedAssetAcquisitionPostingRecord

    engine, _, entity_id, fixed_asset_id = _contracts._initialize_canonical_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        second_asset = _contracts._persist_second_asset(session, entity_id)
        entry = _persist_balanced_placeholder_entry(session, when=datetime(2026, 1, 15), concept="shared")
        session.add(
            FixedAssetAcquisitionPostingRecord(
                fixed_asset_id=fixed_asset_id,
                entry_id=entry.id,
                asset_class="computer_equipment",
                settlement_method="bank",
            )
        )
        session.commit()
        session.add(
            FixedAssetAcquisitionPostingRecord(
                fixed_asset_id=second_asset.id,
                entry_id=entry.id,
                asset_class="computer_equipment",
                settlement_method="bank",
            )
        )
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


def test_executor_uses_existing_core_staging_once_with_posted_6p_payload(tmp_path, monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_acquisition_persistence import execute_fixed_asset_acquisition_posting_once

    engine, _, entity_id, fixed_asset_id = _contracts._initialize_canonical_db(tmp_path, monkeypatch)
    asset = _contracts._domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _contracts._instruction(session, asset, settlement_method="credit")

    real_stage = aqorath.core._stage_entry_in_session
    calls = []

    def stage_once(session, payload):
        calls.append(payload)
        return real_stage(session, payload)

    monkeypatch.setattr(aqorath.core, "_stage_entry_in_session", stage_once)
    result = execute_fixed_asset_acquisition_posting_once(instruction)

    assert result["ok"] is True
    assert calls == [
        {
            "date": date(2026, 1, 15),
            "description": instruction.posting_instruction.description,
            "state": "posted",
            "lines": [
                {
                    "account_id": instruction.posting_instruction.lines[0].account_id,
                    "account_code": "1203",
                    "debit": Decimal("100.00"),
                    "credit": Decimal("0"),
                },
                {
                    "account_id": instruction.posting_instruction.lines[1].account_id,
                    "account_code": "2101",
                    "debit": Decimal("0"),
                    "credit": Decimal("100.00"),
                },
            ],
        }
    ]


def test_loader_reconstructs_identity_date_and_structured_provenance_without_parsing_description(tmp_path, monkeypatch):
    import aqorath.posting as posting
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
        load_fixed_asset_acquisition_posting,
    )

    engine, _, entity_id, fixed_asset_id = _contracts._initialize_canonical_db(tmp_path, monkeypatch)
    asset = _contracts._domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)

    real_factory = posting.create_posting_instruction

    def poisoned_factory(confirmed_proposal):
        generic = real_factory(confirmed_proposal)
        return replace(generic, description="POISONED HUMAN DESCRIPTION — DO NOT PARSE")

    monkeypatch.setattr(posting, "create_posting_instruction", poisoned_factory)
    with Session(engine) as session:
        instruction = _contracts._instruction(session, asset, settlement_method="credit")

    assert instruction.posting_instruction.description == "POISONED HUMAN DESCRIPTION — DO NOT PARSE"
    result = execute_fixed_asset_acquisition_posting_once(instruction)
    assert result["ok"] is True

    with Session(engine) as session:
        loaded = load_fixed_asset_acquisition_posting(session, fixed_asset_id)
        assert loaded.fixed_asset_id == fixed_asset_id
        assert loaded.entry_id == result["entry_id"]
        assert loaded.posting_date == date(2026, 1, 15)
        assert loaded.asset_class == "computer_equipment"
        assert loaded.settlement_method == "credit"


def test_acquisition_persists_posted_entry_one_audit_and_specialized_identity(tmp_path, monkeypatch):
    from aqorath.fixed_asset_acquisition_persistence import (
        execute_fixed_asset_acquisition_posting_once,
        load_fixed_asset_acquisition_posting,
    )
    from aqorath.models import (
        AuditEventRecord,
        FixedAssetAcquisitionPostingRecord,
        JournalEntry,
        JournalLine,
    )

    engine, _, entity_id, fixed_asset_id = _contracts._initialize_canonical_db(tmp_path, monkeypatch)
    asset = _contracts._domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _contracts._instruction(
            session,
            asset,
            asset_class="computer_equipment",
            settlement_method="cash",
        )

    result = execute_fixed_asset_acquisition_posting_once(instruction)
    assert result["ok"] is True

    with Session(engine) as session:
        entry = session.get(JournalEntry, result["entry_id"])
        lines = session.exec(
            select(JournalLine)
            .where(JournalLine.entry_id == result["entry_id"])
            .order_by(JournalLine.id)
        ).all()
        audits = session.exec(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "entry_posted")
        ).all()
        records = session.exec(select(FixedAssetAcquisitionPostingRecord)).all()

        assert entry is not None
        assert entry.state == "posted"
        assert entry.period_id == 202601
        assert [(line.account_code, line.debit, line.credit) for line in lines] == [
            ("1203", "100.00", "0"),
            ("1102", "0", "100.00"),
        ]
        assert len(audits) == 1
        details = json.loads(audits[0].details_json)
        decision = details["decision"]
        assert details["entry_id"] == entry.id
        assert decision["specialized_authority"] == "fixed_asset_acquisition"
        assert decision["fixed_asset_id"] == fixed_asset_id
        assert decision["asset_class"] == "computer_equipment"
        assert decision["settlement_method"] == "cash"
        assert decision["consent"] == "explicit_confirmation"
        assert len(records) == 1
        assert records[0].entry_id == entry.id
        assert records[0].fixed_asset_id == fixed_asset_id

        loaded = load_fixed_asset_acquisition_posting(session, fixed_asset_id)
        assert loaded.entry_id == entry.id
        assert loaded.fixed_asset_id == fixed_asset_id
        assert loaded.asset_class == "computer_equipment"
        assert loaded.settlement_method == "cash"


def test_acquisition_retry_creates_no_second_entry_audit_or_specialized_record(tmp_path, monkeypatch):
    from aqorath.fixed_asset_acquisition_persistence import execute_fixed_asset_acquisition_posting_once
    from aqorath.models import AuditEventRecord, FixedAssetAcquisitionPostingRecord, JournalEntry

    engine, _, entity_id, fixed_asset_id = _contracts._initialize_canonical_db(tmp_path, monkeypatch)
    asset = _contracts._domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _contracts._instruction(session, asset)

    first = execute_fixed_asset_acquisition_posting_once(instruction)
    second = execute_fixed_asset_acquisition_posting_once(instruction)
    assert first["ok"] is True
    assert second["ok"] is False

    with Session(engine) as session:
        assert len(session.exec(select(JournalEntry)).all()) == 1
        assert len(
            session.exec(
                select(AuditEventRecord).where(AuditEventRecord.event_type == "entry_posted")
            ).all()
        ) == 1
        assert len(session.exec(select(FixedAssetAcquisitionPostingRecord)).all()) == 1


def test_acquisition_late_specialized_failure_rolls_back_entry_lines_audit_and_registry(tmp_path, monkeypatch):
    from sqlmodel import Session as SQLModelSession
    from aqorath.fixed_asset_acquisition_persistence import execute_fixed_asset_acquisition_posting_once
    from aqorath.models import (
        AuditEventRecord,
        FixedAssetAcquisitionPostingRecord,
        JournalEntry,
        JournalLine,
    )

    engine, _, entity_id, fixed_asset_id = _contracts._initialize_canonical_db(tmp_path, monkeypatch)
    asset = _contracts._domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _contracts._instruction(session, asset)

    real_add = SQLModelSession.add

    def fail_specialized(self, instance, *args, **kwargs):
        if isinstance(instance, FixedAssetAcquisitionPostingRecord):
            raise RuntimeError("forced late acquisition registry failure")
        return real_add(self, instance, *args, **kwargs)

    monkeypatch.setattr(SQLModelSession, "add", fail_specialized)
    result = execute_fixed_asset_acquisition_posting_once(instruction)
    assert result["ok"] is False
    assert "forced late acquisition registry failure" in result["error"]

    with Session(engine) as session:
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(JournalLine)).all() == []
        assert session.exec(select(AuditEventRecord)).all() == []
        assert session.exec(select(FixedAssetAcquisitionPostingRecord)).all() == []
