"""Phase 5AF.1 — atomic fiscalized posting + audit persistence contracts."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select


def _assert_signature(fn, names):
    sig = signature(fn)
    assert list(sig.parameters) == names
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def _provenance(*, rounded="16.00", rate="0.16"):
    from aqorath.fiscalized_confirmation import FiscalizedConfirmationProvenance

    return FiscalizedConfirmationProvenance(
        fact_type="sale",
        fact_amount=Decimal("100.00"),
        payment_method="cash",
        effective_date=date(2026, 8, 27),
        jurisdiction="MX",
        regime="general",
        entity_type="commercial",
        rule_key="iva.general_rate",
        base=Decimal("100.00"),
        rate=Decimal(rate),
        unit="rate",
        rule_effective_from=date(2010, 1, 1),
        rule_effective_to=None,
        rule_source_ref="CURATED:IVA",
        exact_fiscal_amount=Decimal(rounded),
        rounding_policy_key="two-decimals",
        rounding_quantizer=Decimal("0.01"),
        rounding_mode="ROUND_HALF_UP",
        rounding_source_ref="EXPLICIT:5AF",
        rounded_fiscal_amount=Decimal(rounded),
        amount_basis="net_before_fiscal",
        adjustment_role="cash",
        fiscal_role="tax_payable",
        fiscal_side="credit",
    )


def _instruction(ids=(1, 2, 3), *, rounded="16.00", policy="reject_zero_fiscal_line"):
    from aqorath.fiscalized_confirmation import (
        ConfirmedFiscalizedProposal,
        FiscalizedConfirmationLine,
        FiscalizedConfirmationSnapshot,
    )
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    fiscal_amount = Decimal(rounded)
    lines = (
        FiscalizedConfirmationLine(
            account_role="cash",
            account_id=ids[0],
            account_code="1102",
            account_name="Caja chica",
            side="debit",
            amount=Decimal("100.00") + fiscal_amount,
        ),
        FiscalizedConfirmationLine(
            account_role="sales_revenue",
            account_id=ids[1],
            account_code="4201",
            account_name="Venta de productos elaborados",
            side="credit",
            amount=Decimal("100.00"),
        ),
        FiscalizedConfirmationLine(
            account_role="tax_payable",
            account_id=ids[2],
            account_code="2103",
            account_name="Impuestos por pagar",
            side="credit",
            amount=fiscal_amount,
        ),
    )
    snapshot = FiscalizedConfirmationSnapshot(
        lines=lines,
        explanation="Venta fiscalizada confirmada",
        provenance=_provenance(
            rounded=rounded,
            rate="0.00" if fiscal_amount == Decimal("0") else "0.16",
        ),
    )
    return create_fiscalized_posting_instruction(
        ConfirmedFiscalizedProposal(snapshot=snapshot),
        policy,
    )


class _FakeSession:
    def __init__(self, *, commit_error=None):
        self.added = []
        self.commit_calls = 0
        self.rollback_calls = 0
        self.commit_error = commit_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commit_calls += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self):
        self.rollback_calls += 1


def _canonical_db(tmp_path, monkeypatch, name="atomic-audit.db"):
    import aqorath.storage as storage
    from aqorath.models import Account

    db = tmp_path / name
    monkeypatch.setenv("AQORATH_DB", str(db))
    engine = storage.init_db(str(db), create_tables=True)
    with Session(engine) as session:
        accounts = (
            Account(code="1102", name="Caja chica", nature="DEBIT"),
            Account(code="4201", name="Venta de productos elaborados", nature="CREDIT"),
            Account(code="2103", name="Impuestos por pagar", nature="CREDIT"),
        )
        session.add_all(accounts)
        session.commit()
        for account in accounts:
            session.refresh(account)
        ids = tuple(account.id for account in accounts)
    return engine, ids


def test_atomic_fiscalized_persistence_public_contracts_and_exact_signatures_exist():
    import aqorath.core as core
    import aqorath.fiscalized_posting_persistence as persistence

    assert callable(persistence.execute_fiscalized_posting_with_audit)
    _assert_signature(persistence.execute_fiscalized_posting_with_audit, ["instruction"])
    assert callable(core._stage_entry_in_session)
    _assert_signature(core._stage_entry_in_session, ["session", "entry"])


def test_atomic_execution_builds_exact_minimal_entry_payload_and_stages_once(monkeypatch):
    import aqorath.core as core
    import aqorath.fiscal_posting_audit as audit
    import aqorath.fiscalized_posting_persistence as persistence
    import aqorath.storage as storage

    instruction = _instruction()
    fake_session = _FakeSession()
    audit_snapshot = object()
    audit_calls = []
    stage_calls = []

    monkeypatch.setattr(storage, "get_session", lambda: fake_session)
    monkeypatch.setattr(
        audit,
        "create_fiscal_posting_audit_snapshot",
        lambda value: audit_calls.append(value) or audit_snapshot,
    )
    monkeypatch.setattr(
        core,
        "_stage_entry_in_session",
        lambda session, entry: stage_calls.append((session, entry))
        or (SimpleNamespace(id=77), None),
    )
    monkeypatch.setattr(
        persistence,
        "_build_audit_record",
        lambda snapshot, entry_id: SimpleNamespace(snapshot=snapshot, entry_id=entry_id),
    )

    result = persistence.execute_fiscalized_posting_with_audit(instruction)

    assert audit_calls == [instruction]
    assert len(stage_calls) == 1
    assert stage_calls[0][0] is fake_session
    assert stage_calls[0][1] == {
        "description": instruction.description,
        "lines": [
            {"account_id": 1, "account_code": "1102", "debit": Decimal("116.00"), "credit": Decimal("0")},
            {"account_id": 2, "account_code": "4201", "debit": Decimal("0"), "credit": Decimal("100.00")},
            {"account_id": 3, "account_code": "2103", "debit": Decimal("0"), "credit": Decimal("16.00")},
        ],
    }
    assert fake_session.commit_calls == 1
    assert fake_session.rollback_calls == 0
    assert len(fake_session.added) == 1
    assert result == {"ok": True, "entry_id": 77}


def test_atomic_execution_requires_nominal_instruction_before_audit_or_session(monkeypatch):
    import aqorath.fiscal_posting_audit as audit
    import aqorath.fiscalized_posting_persistence as persistence
    import aqorath.storage as storage

    monkeypatch.setattr(
        audit,
        "create_fiscal_posting_audit_snapshot",
        lambda value: (_ for _ in ()).throw(AssertionError("must reject before audit")),
    )
    monkeypatch.setattr(
        storage,
        "get_session",
        lambda: (_ for _ in ()).throw(AssertionError("must reject before session")),
    )

    with pytest.raises(TypeError, match="FiscalizedPostingInstruction"):
        persistence.execute_fiscalized_posting_with_audit(
            SimpleNamespace(description="shape", lines=())
        )


def test_atomic_execution_never_calls_core_post_entry_or_legacy_execution(monkeypatch):
    import aqorath.core as core
    import aqorath.fiscalized_posting_execution as old_execution
    import aqorath.fiscalized_posting_persistence as persistence
    import aqorath.storage as storage

    instruction = _instruction()
    fake_session = _FakeSession()

    def forbidden(*args, **kwargs):
        raise AssertionError("atomic persistence must not use already-committing execution paths")

    monkeypatch.setattr(core, "post_entry", forbidden)
    monkeypatch.setattr(old_execution, "execute_fiscalized_posting_instruction", forbidden)
    monkeypatch.setattr(storage, "get_session", lambda: fake_session)
    monkeypatch.setattr(
        core,
        "_stage_entry_in_session",
        lambda session, entry: (SimpleNamespace(id=10), None),
    )
    monkeypatch.setattr(
        persistence,
        "_build_audit_record",
        lambda snapshot, entry_id: SimpleNamespace(entry_id=entry_id),
    )

    assert persistence.execute_fiscalized_posting_with_audit(instruction) == {
        "ok": True,
        "entry_id": 10,
    }


def test_audit_record_builder_maps_exact_snapshot_metadata_without_recalculation():
    import aqorath.fiscal_posting_audit as audit
    import aqorath.fiscalized_posting_persistence as persistence

    snapshot = audit.create_fiscal_posting_audit_snapshot(_instruction())
    record = persistence._build_audit_record(snapshot, 55)
    p = snapshot.provenance

    assert record.entry_id == 55
    assert record.fact_type == p.fact_type
    assert record.fact_amount == str(p.fact_amount)
    assert record.payment_method == p.payment_method
    assert record.effective_date == p.effective_date
    assert record.jurisdiction == p.jurisdiction
    assert record.regime == p.regime
    assert record.entity_type == p.entity_type
    assert record.rule_key == p.rule_key
    assert record.base == str(p.base)
    assert record.rate == str(p.rate)
    assert record.unit == p.unit
    assert record.rule_effective_from == p.rule_effective_from
    assert record.rule_effective_to is p.rule_effective_to
    assert record.rule_source_ref == p.rule_source_ref
    assert record.exact_fiscal_amount == str(p.exact_fiscal_amount)
    assert record.rounding_policy_key == p.rounding_policy_key
    assert record.rounding_quantizer == str(p.rounding_quantizer)
    assert record.rounding_mode == p.rounding_mode
    assert record.rounding_source_ref == p.rounding_source_ref
    assert record.rounded_fiscal_amount == str(p.rounded_fiscal_amount)
    assert record.amount_basis == p.amount_basis
    assert record.adjustment_role == p.adjustment_role
    assert record.fiscal_role == p.fiscal_role
    assert record.fiscal_side == p.fiscal_side
    assert record.zero_fiscal_line_policy == snapshot.zero_fiscal_line_policy
    assert record.omitted_zero_account_role is None
    assert record.omitted_zero_account_id is None
    assert record.omitted_zero_account_code is None
    assert record.omitted_zero_account_name is None
    assert record.omitted_zero_side is None
    assert record.omitted_zero_amount is None


def test_audit_record_builder_preserves_decimal_scale_and_zero_omission_metadata():
    import aqorath.fiscal_posting_audit as audit
    import aqorath.fiscalized_posting_persistence as persistence

    instruction = _instruction(
        rounded="0.00",
        policy="omit_confirmed_zero_fiscal_line",
    )
    source = audit.create_fiscal_posting_audit_snapshot(instruction)
    source = replace(
        source,
        provenance=replace(
            source.provenance,
            fact_amount=Decimal("100.0000"),
            base=Decimal("100.000"),
            rate=Decimal("0.0000"),
            exact_fiscal_amount=Decimal("0.000"),
            rounding_quantizer=Decimal("0.010"),
            rounded_fiscal_amount=Decimal("0.00"),
        ),
    )
    record = persistence._build_audit_record(source, 91)

    assert record.fact_amount == "100.0000"
    assert record.base == "100.000"
    assert record.rate == "0.0000"
    assert record.exact_fiscal_amount == "0.000"
    assert record.rounding_quantizer == "0.010"
    assert record.rounded_fiscal_amount == "0.00"
    assert record.omitted_zero_account_role == "tax_payable"
    assert record.omitted_zero_account_id == 3
    assert record.omitted_zero_account_code == "2103"
    assert record.omitted_zero_account_name == "Impuestos por pagar"
    assert record.omitted_zero_side == "credit"
    assert record.omitted_zero_amount == "0.00"


def test_staging_failure_returns_failure_without_audit_insert_or_commit(monkeypatch):
    import aqorath.core as core
    import aqorath.fiscalized_posting_persistence as persistence
    import aqorath.storage as storage

    fake_session = _FakeSession()
    monkeypatch.setattr(storage, "get_session", lambda: fake_session)
    monkeypatch.setattr(
        core,
        "_stage_entry_in_session",
        lambda session, entry: (None, "account mismatch"),
    )
    monkeypatch.setattr(
        persistence,
        "_build_audit_record",
        lambda *args: (_ for _ in ()).throw(AssertionError("no audit on staging failure")),
    )

    result = persistence.execute_fiscalized_posting_with_audit(_instruction())
    assert result == {"ok": False, "error": "account mismatch"}
    assert fake_session.added == []
    assert fake_session.commit_calls == 0
    assert fake_session.rollback_calls == 1


def test_audit_build_failure_rolls_back_staged_entry_without_commit(monkeypatch):
    import aqorath.core as core
    import aqorath.fiscalized_posting_persistence as persistence
    import aqorath.storage as storage

    fake_session = _FakeSession()
    monkeypatch.setattr(storage, "get_session", lambda: fake_session)
    monkeypatch.setattr(
        core,
        "_stage_entry_in_session",
        lambda session, entry: (SimpleNamespace(id=123), None),
    )
    monkeypatch.setattr(
        persistence,
        "_build_audit_record",
        lambda *args: (_ for _ in ()).throw(RuntimeError("audit build failed")),
    )

    result = persistence.execute_fiscalized_posting_with_audit(_instruction())
    assert result["ok"] is False
    assert "audit build failed" in result["error"]
    assert fake_session.commit_calls == 0
    assert fake_session.rollback_calls == 1


def test_single_commit_failure_rolls_back_entire_atomic_operation(monkeypatch):
    import aqorath.core as core
    import aqorath.fiscalized_posting_persistence as persistence
    import aqorath.storage as storage

    fake_session = _FakeSession(commit_error=RuntimeError("commit failed"))
    monkeypatch.setattr(storage, "get_session", lambda: fake_session)
    monkeypatch.setattr(
        core,
        "_stage_entry_in_session",
        lambda session, entry: (SimpleNamespace(id=123), None),
    )
    monkeypatch.setattr(
        persistence,
        "_build_audit_record",
        lambda snapshot, entry_id: SimpleNamespace(entry_id=entry_id),
    )

    result = persistence.execute_fiscalized_posting_with_audit(_instruction())
    assert result["ok"] is False
    assert "commit failed" in result["error"]
    assert fake_session.commit_calls == 1
    assert fake_session.rollback_calls == 1


def test_real_positive_atomic_persistence_writes_entry_lines_and_one_exact_audit_record(
    tmp_path,
    monkeypatch,
):
    import aqorath.fiscalized_posting_persistence as persistence
    from aqorath.models import FiscalPostingAuditRecord, JournalEntry, JournalLine

    engine, ids = _canonical_db(tmp_path, monkeypatch, "positive.db")
    try:
        instruction = _instruction(ids=ids)
        result = persistence.execute_fiscalized_posting_with_audit(instruction)
        assert result["ok"] is True

        with Session(engine) as session:
            entries = session.exec(select(JournalEntry)).all()
            lines = session.exec(select(JournalLine)).all()
            audits = session.exec(select(FiscalPostingAuditRecord)).all()

            assert len(entries) == 1
            assert len(lines) == 3
            assert len(audits) == 1
            assert entries[0].id == result["entry_id"]
            assert entries[0].concept == instruction.description
            assert audits[0].entry_id == entries[0].id
            assert audits[0].fact_amount == "100.00"
            assert audits[0].base == "100.00"
            assert audits[0].rate == "0.16"
            assert audits[0].exact_fiscal_amount == "16.00"
            assert audits[0].rounded_fiscal_amount == "16.00"
            assert audits[0].zero_fiscal_line_policy == "reject_zero_fiscal_line"
            assert audits[0].omitted_zero_amount is None
            assert [(line.account_code, line.debit, line.credit) for line in lines] == [
                ("1102", "116.00", "0"),
                ("4201", "0", "100.00"),
                ("2103", "0", "16.00"),
            ]
    finally:
        engine.dispose()


def test_real_zero_omission_atomic_persistence_writes_two_lines_and_audits_omitted_fiscal_line(
    tmp_path,
    monkeypatch,
):
    import aqorath.fiscalized_posting_persistence as persistence
    from aqorath.models import FiscalPostingAuditRecord, JournalEntry, JournalLine

    engine, ids = _canonical_db(tmp_path, monkeypatch, "zero.db")
    try:
        instruction = _instruction(
            ids=ids,
            rounded="0.00",
            policy="omit_confirmed_zero_fiscal_line",
        )
        result = persistence.execute_fiscalized_posting_with_audit(instruction)
        assert result["ok"] is True

        with Session(engine) as session:
            assert len(session.exec(select(JournalEntry)).all()) == 1
            lines = session.exec(select(JournalLine)).all()
            audits = session.exec(select(FiscalPostingAuditRecord)).all()
            assert len(lines) == 2
            assert [(line.account_code, line.debit, line.credit) for line in lines] == [
                ("1102", "100.00", "0"),
                ("4201", "0", "100.00"),
            ]
            assert len(audits) == 1
            record = audits[0]
            assert record.zero_fiscal_line_policy == "omit_confirmed_zero_fiscal_line"
            assert record.rounded_fiscal_amount == "0.00"
            assert record.omitted_zero_account_role == "tax_payable"
            assert record.omitted_zero_account_id == ids[2]
            assert record.omitted_zero_account_code == "2103"
            assert record.omitted_zero_account_name == "Impuestos por pagar"
            assert record.omitted_zero_side == "credit"
            assert record.omitted_zero_amount == "0.00"
    finally:
        engine.dispose()


def test_real_audit_insert_failure_rolls_back_journal_entry_and_lines(tmp_path, monkeypatch):
    import aqorath.fiscalized_posting_persistence as persistence
    from aqorath.models import FiscalPostingAuditRecord, JournalEntry, JournalLine

    engine, ids = _canonical_db(tmp_path, monkeypatch, "rollback.db")
    real_builder = persistence._build_audit_record

    def fail_after_build(snapshot, entry_id):
        real_builder(snapshot, entry_id)
        raise RuntimeError("forced audit failure")

    monkeypatch.setattr(persistence, "_build_audit_record", fail_after_build)
    try:
        result = persistence.execute_fiscalized_posting_with_audit(_instruction(ids=ids))
        assert result["ok"] is False
        assert "forced audit failure" in result["error"]

        with Session(engine) as session:
            assert session.exec(select(JournalEntry)).all() == []
            assert session.exec(select(JournalLine)).all() == []
            assert session.exec(select(FiscalPostingAuditRecord)).all() == []
    finally:
        engine.dispose()


def test_historical_core_post_entry_remains_non_fiscal_and_creates_no_audit_record(tmp_path, monkeypatch):
    import aqorath.core as core
    from aqorath.models import FiscalPostingAuditRecord, JournalEntry, JournalLine

    engine, ids = _canonical_db(tmp_path, monkeypatch, "historical.db")
    try:
        result = core.post_entry(
            {
                "description": "Asiento histórico no fiscalizado",
                "lines": [
                    {"account_id": ids[0], "account_code": "1102", "debit": Decimal("50.00"), "credit": Decimal("0")},
                    {"account_id": ids[1], "account_code": "4201", "debit": Decimal("0"), "credit": Decimal("50.00")},
                ],
            }
        )
        assert result["ok"] is True

        with Session(engine) as session:
            assert len(session.exec(select(JournalEntry)).all()) == 1
            assert len(session.exec(select(JournalLine)).all()) == 2
            assert session.exec(select(FiscalPostingAuditRecord)).all() == []
    finally:
        engine.dispose()
