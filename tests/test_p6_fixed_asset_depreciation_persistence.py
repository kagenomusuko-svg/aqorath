"""Frozen Phase 6M contracts plus AQR-015 posted/audit regressions.

Run #697 proved that the historical persistence contract allowed a valid ledger entry
to remain ``draft`` and omitted the general ``entry_posted`` audit. The old suite is
kept byte-for-byte in ``_p6m_fixed_asset_depreciation_contracts.py``; this collector
replaces only the exact payload expectation and adds regressions for posted state,
general audit, idempotence and late-failure atomicity.
"""

from datetime import date
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from sqlmodel import Session, select


def _load_contracts():
    path = Path(__file__).with_name("_p6m_fixed_asset_depreciation_contracts.py")
    spec = spec_from_file_location("aqorath_p6m_fixed_asset_depreciation_contracts", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load frozen Phase 6M fixed-asset depreciation contracts")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_contracts = _load_contracts()
_initialize_canonical_db = _contracts._initialize_canonical_db
_domain_asset = _contracts._domain_asset
_instruction = _contracts._instruction
_persist_second_asset = _contracts._persist_second_asset

_OVERRIDDEN = {
    "test_executor_uses_existing_core_staging_once_with_exact_6l_payload",
}
for _name, _value in vars(_contracts).items():
    if _name.startswith("test_") and _name not in _OVERRIDDEN:
        globals()[_name] = _value


def test_executor_uses_existing_core_staging_once_with_posted_6l_payload(tmp_path, monkeypatch):
    import aqorath.core
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(
            session,
            asset,
            period_number=3,
            recognition_date=date(2026, 4, 30),
        )

    real_stage = aqorath.core._stage_entry_in_session
    calls = []

    def stage_once(session, payload):
        calls.append(payload)
        return real_stage(session, payload)

    monkeypatch.setattr(aqorath.core, "_stage_entry_in_session", stage_once)
    result = execute_fixed_asset_depreciation_posting_once(instruction)

    assert result["ok"] is True
    assert calls == [
        {
            "date": date(2026, 4, 30),
            "description": instruction.posting_instruction.description,
            "state": "posted",
            "lines": [
                {
                    "account_id": instruction.posting_instruction.lines[0].account_id,
                    "account_code": "5106",
                    "debit": Decimal("33.34"),
                    "credit": Decimal("0"),
                },
                {
                    "account_id": instruction.posting_instruction.lines[1].account_id,
                    "account_code": "1205",
                    "debit": Decimal("0"),
                    "credit": Decimal("33.34"),
                },
            ],
        }
    ]


def test_depreciation_persists_posted_entry_one_audit_and_specialized_identity(tmp_path, monkeypatch):
    from aqorath.fixed_asset_depreciation_persistence import (
        execute_fixed_asset_depreciation_posting_once,
        load_fixed_asset_depreciation_posting,
    )
    from aqorath.models import (
        AuditEventRecord,
        FixedAssetDepreciationPostingRecord,
        JournalEntry,
        JournalLine,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)

    result = execute_fixed_asset_depreciation_posting_once(instruction)
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
        records = session.exec(select(FixedAssetDepreciationPostingRecord)).all()

        assert entry is not None
        assert entry.state == "posted"
        assert entry.period_id == 202602
        assert [(line.account_code, line.debit, line.credit) for line in lines] == [
            ("5106", "33.33", "0"),
            ("1205", "0", "33.33"),
        ]
        assert len(audits) == 1
        details = json.loads(audits[0].details_json)
        decision = details["decision"]
        assert details["entry_id"] == entry.id
        assert decision["specialized_authority"] == "fixed_asset_depreciation"
        assert decision["fixed_asset_id"] == fixed_asset_id
        assert decision["period_number"] == 1
        assert decision["recognition_source_ref"] == "EXPLICIT:6M"
        assert decision["consent"] == "explicit_confirmation"
        assert len(records) == 1
        assert records[0].entry_id == entry.id
        assert records[0].fixed_asset_id == fixed_asset_id
        assert records[0].period_number == 1

        loaded = load_fixed_asset_depreciation_posting(session, fixed_asset_id, 1)
        assert loaded.entry_id == entry.id
        assert loaded.fixed_asset_id == fixed_asset_id
        assert loaded.period_number == 1
        assert loaded.recognition_source_ref == "EXPLICIT:6M"


def test_depreciation_retry_creates_no_second_entry_audit_or_specialized_record(tmp_path, monkeypatch):
    from aqorath.fixed_asset_depreciation_persistence import execute_fixed_asset_depreciation_posting_once
    from aqorath.models import AuditEventRecord, FixedAssetDepreciationPostingRecord, JournalEntry

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)

    first = execute_fixed_asset_depreciation_posting_once(instruction)
    second = execute_fixed_asset_depreciation_posting_once(instruction)
    assert first["ok"] is True
    assert second["ok"] is False

    with Session(engine) as session:
        assert len(session.exec(select(JournalEntry)).all()) == 1
        assert len(session.exec(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "entry_posted")
        ).all()) == 1
        assert len(session.exec(select(FixedAssetDepreciationPostingRecord)).all()) == 1


def test_depreciation_late_specialized_failure_rolls_back_entry_lines_audit_and_registry(tmp_path, monkeypatch):
    from sqlmodel import Session as SQLModelSession
    from aqorath.fixed_asset_depreciation_persistence import execute_fixed_asset_depreciation_posting_once
    from aqorath.models import (
        AuditEventRecord,
        FixedAssetDepreciationPostingRecord,
        JournalEntry,
        JournalLine,
    )

    engine, _, entity_id, fixed_asset_id = _initialize_canonical_db(tmp_path, monkeypatch)
    asset = _domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    with Session(engine) as session:
        instruction = _instruction(session, asset)

    real_add = SQLModelSession.add

    def fail_specialized(self, instance, *args, **kwargs):
        if isinstance(instance, FixedAssetDepreciationPostingRecord):
            raise RuntimeError("forced late depreciation registry failure")
        return real_add(self, instance, *args, **kwargs)

    monkeypatch.setattr(SQLModelSession, "add", fail_specialized)
    result = execute_fixed_asset_depreciation_posting_once(instruction)
    assert result["ok"] is False
    assert "forced late depreciation registry failure" in result["error"]

    with Session(engine) as session:
        assert session.exec(select(JournalEntry)).all() == []
        assert session.exec(select(JournalLine)).all() == []
        assert session.exec(select(AuditEventRecord)).all() == []
        assert session.exec(select(FixedAssetDepreciationPostingRecord)).all() == []
