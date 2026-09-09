"""Phase 6Q.1 contracts adapted to the Phase 6BP persistence boundary.

The historical Phase 6Q suite is preserved byte-for-byte in the adjacent contract
module.  This collector re-exports every unchanged test and replaces only the two
SQLite uniqueness fixtures that previously persisted empty JournalEntry rows.
"""

from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
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
}
for _name, _value in vars(_contracts).items():
    if _name.startswith("test_") and _name not in _OVERRIDDEN:
        globals()[_name] = _value


def _persist_balanced_placeholder_entry(session, *, when, concept):
    """Persist a minimal valid ledger entry for uniqueness-only registry tests."""
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
        first_entry = _persist_balanced_placeholder_entry(
            session,
            when=datetime(2026, 1, 15),
            concept="first",
        )
        second_entry = _persist_balanced_placeholder_entry(
            session,
            when=datetime(2026, 1, 16),
            concept="second",
        )

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
        entry = _persist_balanced_placeholder_entry(
            session,
            when=datetime(2026, 1, 15),
            concept="shared",
        )

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
