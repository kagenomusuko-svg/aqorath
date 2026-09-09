"""Phase 6N.1 book-state contracts adapted to the Phase 6BP persistence boundary.

The historical Phase 6N suite is preserved byte-for-byte in the adjacent contract
module.  This collector re-exports every unchanged test and replaces only corruption
fixtures that must model pre-existing or external database corruption without asking
the canonical Session persistence boundary to create that corruption itself.
"""

from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from sqlmodel import Session, select


def _load_contracts():
    path = Path(__file__).with_name("_p6n_fixed_asset_book_state_contracts.py")
    spec = spec_from_file_location("aqorath_p6n_fixed_asset_book_state_contracts", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load frozen Phase 6N fixed-asset book-state contracts")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_contracts = _load_contracts()
_OVERRIDDEN = {
    "test_linked_depreciation_entry_must_be_exact_two_line_balanced_positive_truth",
    "test_linked_depreciation_entry_rejects_corrupt_money_and_extra_lines",
}
for _name, _value in vars(_contracts).items():
    if _name.startswith("test_") and _name not in _OVERRIDDEN:
        globals()[_name] = _value


def _raw_set_journal_line(engine, line_id, *, column, value):
    """Simulate corruption that originated outside Aqorath's canonical Session path."""
    if column not in {"debit", "credit"}:
        raise ValueError("unsupported journal-line corruption column")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"UPDATE journalline SET {column} = ? WHERE id = ?",
            (value, line_id),
        )


def test_linked_depreciation_entry_must_be_exact_two_line_balanced_positive_truth(tmp_path, monkeypatch):
    from aqorath.models import JournalLine

    engine, entity_id, fixed_asset_id = _contracts._initialize_canonical_db(tmp_path, monkeypatch)
    asset = _contracts._domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    entry_id = _contracts._post_period(engine, asset, 1, date(2026, 2, 28))

    with Session(engine) as session:
        lines = session.exec(select(JournalLine).where(JournalLine.entry_id == entry_id)).all()
        assert len(lines) == 2
        line_id = lines[0].id

    # Deliberately bypass the canonical Session guard: this test is about defensive
    # reads from already-corrupt truth, not permission to persist an unbalanced entry.
    _raw_set_journal_line(engine, line_id, column="debit", value="33.32")

    with Session(engine) as session:
        with pytest.raises(ValueError):
            _contracts._load(session, entity_id, fixed_asset_id)


def test_linked_depreciation_entry_rejects_corrupt_money_and_extra_lines(tmp_path, monkeypatch):
    from aqorath.models import JournalLine

    engine, entity_id, fixed_asset_id = _contracts._initialize_canonical_db(tmp_path, monkeypatch)
    asset = _contracts._domain_asset(fixed_asset_id=fixed_asset_id, entity_id=entity_id)
    entry_id = _contracts._post_period(engine, asset, 1, date(2026, 2, 28))

    with Session(engine) as session:
        line = session.exec(select(JournalLine).where(JournalLine.entry_id == entry_id)).first()
        line_id = line.id

    _raw_set_journal_line(engine, line_id, column="debit", value="NaN")
    with Session(engine) as session:
        with pytest.raises(ValueError):
            _contracts._load(session, entity_id, fixed_asset_id)

    engine2, entity_id2, fixed_asset_id2 = _contracts._initialize_canonical_db(
        tmp_path / "second",
        monkeypatch,
    )
    asset2 = _contracts._domain_asset(fixed_asset_id=fixed_asset_id2, entity_id=entity_id2)
    entry_id2 = _contracts._post_period(engine2, asset2, 1, date(2026, 2, 28))

    with Session(engine2) as session:
        source = session.exec(
            select(JournalLine).where(JournalLine.entry_id == entry_id2)
        ).first()
        source_account_code = source.account_code
        source_account_id = source.account_id

    # Same corruption model as above, but insert a third ledger line directly so
    # the reader must reject non-canonical persisted shape.
    with engine2.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO journalline "
            "(entry_id, account_code, account_id, debit, credit, created_at) "
            "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (
                entry_id2,
                source_account_code,
                source_account_id,
                "0",
                "1.00",
            ),
        )

    with Session(engine2) as session:
        with pytest.raises(ValueError):
            _contracts._load(session, entity_id2, fixed_asset_id2)
