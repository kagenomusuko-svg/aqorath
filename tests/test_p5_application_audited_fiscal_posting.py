"""Phase 5AG.1 — application boundary for atomic audited fiscal posting."""

from datetime import date
from decimal import Decimal
from inspect import Parameter, signature

import pytest
from sqlmodel import Session, select


def _assert_signature(fn, names):
    sig = signature(fn)
    assert list(sig.parameters) == names
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def _instruction(ids=(1, 2, 3)):
    from aqorath.fiscalized_confirmation import (
        ConfirmedFiscalizedProposal,
        FiscalizedConfirmationLine,
        FiscalizedConfirmationProvenance,
        FiscalizedConfirmationSnapshot,
    )
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    provenance = FiscalizedConfirmationProvenance(
        fact_type="sale",
        fact_amount=Decimal("100.00"),
        payment_method="cash",
        effective_date=date(2026, 8, 27),
        jurisdiction="MX",
        regime="general",
        entity_type="commercial",
        rule_key="iva.general_rate",
        base=Decimal("100.00"),
        rate=Decimal("0.16"),
        unit="rate",
        rule_effective_from=date(2010, 1, 1),
        rule_effective_to=None,
        rule_source_ref="CURATED:IVA",
        exact_fiscal_amount=Decimal("16.00"),
        rounding_policy_key="two-decimals",
        rounding_quantizer=Decimal("0.01"),
        rounding_mode="ROUND_HALF_UP",
        rounding_source_ref="EXPLICIT:5AG",
        rounded_fiscal_amount=Decimal("16.00"),
        amount_basis="net_before_fiscal",
        adjustment_role="cash",
        fiscal_role="tax_payable",
        fiscal_side="credit",
    )
    snapshot = FiscalizedConfirmationSnapshot(
        lines=(
            FiscalizedConfirmationLine(
                account_role="cash",
                account_id=ids[0],
                account_code="1102",
                account_name="Caja chica",
                side="debit",
                amount=Decimal("116.00"),
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
                amount=Decimal("16.00"),
            ),
        ),
        explanation="Venta fiscalizada confirmada",
        provenance=provenance,
    )
    return create_fiscalized_posting_instruction(
        ConfirmedFiscalizedProposal(snapshot=snapshot),
        "reject_zero_fiscal_line",
    )


def _canonical_db(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.models import Account

    db = tmp_path / "application-audited-posting.db"
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


def test_application_exposes_atomic_audited_fiscal_posting_with_exact_signature():
    import aqorath.application as application

    assert callable(application.execute_fiscalized_posting_with_audit)
    _assert_signature(application.execute_fiscalized_posting_with_audit, ["instruction"])


def test_application_audited_posting_delegates_exact_instruction_once(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscalized_posting_persistence as persistence

    instruction = object()
    expected = {"ok": True, "entry_id": 77}
    calls = []
    monkeypatch.setattr(
        persistence,
        "execute_fiscalized_posting_with_audit",
        lambda value: calls.append(value) or expected,
    )

    result = application.execute_fiscalized_posting_with_audit(instruction)
    assert result is expected
    assert calls == [instruction]


def test_application_audited_posting_uses_module_lookup_not_captured_alias(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscalized_posting_persistence as persistence

    sentinel = object()
    monkeypatch.setattr(
        persistence,
        "execute_fiscalized_posting_with_audit",
        lambda value: sentinel,
    )
    assert application.execute_fiscalized_posting_with_audit(object()) is sentinel


def test_application_audited_posting_does_not_use_old_executor_core_storage_or_rebuild_audit(monkeypatch):
    import aqorath.application as application
    import aqorath.core as core
    import aqorath.fiscal_posting_audit as audit
    import aqorath.fiscalized_posting_execution as old_execution
    import aqorath.fiscalized_posting_persistence as persistence
    import aqorath.storage as storage

    def forbidden(*args, **kwargs):
        raise AssertionError("application must delegate only to audited persistence authority")

    monkeypatch.setattr(core, "post_entry", forbidden)
    monkeypatch.setattr(storage, "get_session", forbidden)
    monkeypatch.setattr(audit, "create_fiscal_posting_audit_snapshot", forbidden)
    monkeypatch.setattr(old_execution, "execute_fiscalized_posting_instruction", forbidden)
    marker = object()
    expected = object()
    monkeypatch.setattr(
        persistence,
        "execute_fiscalized_posting_with_audit",
        lambda value: expected if value is marker else forbidden(),
    )

    assert application.execute_fiscalized_posting_with_audit(marker) is expected


def test_application_keeps_historical_and_audited_fiscal_execution_distinct(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscalized_posting_execution as old_execution
    import aqorath.fiscalized_posting_persistence as persistence

    marker = object()
    old_result = object()
    audited_result = object()
    old_calls = []
    audited_calls = []
    monkeypatch.setattr(
        old_execution,
        "execute_fiscalized_posting_instruction",
        lambda value: old_calls.append(value) or old_result,
    )
    monkeypatch.setattr(
        persistence,
        "execute_fiscalized_posting_with_audit",
        lambda value: audited_calls.append(value) or audited_result,
    )

    assert application.execute_fiscalized_posting_instruction(marker) is old_result
    assert old_calls == [marker]
    assert audited_calls == []

    assert application.execute_fiscalized_posting_with_audit(marker) is audited_result
    assert old_calls == [marker]
    assert audited_calls == [marker]


def test_application_audited_persistence_failure_is_returned_verbatim_without_retry(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscalized_posting_persistence as persistence

    marker = object()
    failure = {"ok": False, "error": "atomic persistence failed"}
    calls = []
    monkeypatch.setattr(
        persistence,
        "execute_fiscalized_posting_with_audit",
        lambda value: calls.append(value) or failure,
    )

    assert application.execute_fiscalized_posting_with_audit(marker) is failure
    assert calls == [marker]


def test_real_application_audited_posting_persists_entry_lines_and_fiscal_provenance_atomically(
    tmp_path,
    monkeypatch,
):
    import aqorath.application as application
    from aqorath.models import FiscalPostingAuditRecord, JournalEntry, JournalLine

    engine, ids = _canonical_db(tmp_path, monkeypatch)
    try:
        instruction = _instruction(ids=ids)
        result = application.execute_fiscalized_posting_with_audit(instruction)
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
            assert [(line.account_code, line.debit, line.credit) for line in lines] == [
                ("1102", "116.00", "0"),
                ("4201", "0", "100.00"),
                ("2103", "0", "16.00"),
            ]
            audit = audits[0]
            assert audit.entry_id == entries[0].id
            assert audit.rule_key == "iva.general_rate"
            assert audit.fact_amount == "100.00"
            assert audit.base == "100.00"
            assert audit.rate == "0.16"
            assert audit.rounded_fiscal_amount == "16.00"
            assert audit.zero_fiscal_line_policy == "reject_zero_fiscal_line"
    finally:
        engine.dispose()
