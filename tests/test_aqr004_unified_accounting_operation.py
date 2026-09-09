"""AQR-004 — one application use case over existing accounting authorities."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

from period_fixtures import seed_engine_calendar


@pytest.fixture
def configured_engine(tmp_path, monkeypatch):
    import aqorath.accounting_operation_persistence as persistence
    import aqorath.storage as storage
    from aqorath.account_bindings import set_account_binding
    from aqorath.models import Account

    path = tmp_path / "aqr004.db"
    monkeypatch.setenv("AQORATH_DB", str(path))
    engine = storage.init_db(str(path))
    seed_engine_calendar(engine)

    with Session(engine) as session:
        cash = Account(code="1102", name="Caja", nature="DEBIT")
        sales = Account(code="4201", name="Ventas", nature="CREDIT")
        session.add_all([cash, sales])
        session.commit()
        set_account_binding(session, "cash", "1102")
        set_account_binding(session, "sales_revenue", "4201")

    monkeypatch.setattr(persistence._storage, "get_session", lambda: Session(engine))
    yield engine
    engine.dispose()


def _prepare(engine, amount="200.00"):
    from aqorath.accounting_operation import prepare_accounting_operation
    from aqorath.economic_facts import EconomicFact

    with Session(engine) as session:
        return prepare_accounting_operation(
            session,
            EconomicFact("sale", Decimal(amount), "cash"),
            date.today(),
        )


def test_prepare_requires_only_fact_date_and_configured_authorities(configured_engine):
    from aqorath.accounting_decision import AccountingDecision

    decision = _prepare(configured_engine)

    assert isinstance(decision, AccountingDecision)
    assert decision.fact.type == "sale"
    assert decision.fact.amount == Decimal("200.00")
    assert decision.posting_date == date.today()
    assert decision.rule_id == "economic_fact:sale:cash"
    assert decision.rule_version == "economic-fact-v1"
    assert tuple(line.account_role for line in decision.resolved_proposal.lines) == (
        "cash",
        "sales_revenue",
    )
    assert tuple(line.account_code for line in decision.resolved_proposal.lines) == (
        "1102",
        "4201",
    )
    assert decision.explanation.professional_summary == decision.confirmation_snapshot.explanation


def test_explicit_confirmation_preserves_exact_prepared_snapshot(configured_engine):
    from aqorath.accounting_decision import ConfirmedAccountingDecision
    from aqorath.accounting_operation import confirm_accounting_operation

    decision = _prepare(configured_engine)
    confirmed = confirm_accounting_operation(decision)

    assert isinstance(confirmed, ConfirmedAccountingDecision)
    assert confirmed.decision is decision
    assert confirmed.confirmed_proposal.snapshot == decision.confirmation_snapshot


def test_complete_operation_posts_once_and_persists_recoverable_audit(configured_engine):
    from aqorath.accounting_operation import (
        confirm_accounting_operation,
        execute_accounting_operation,
        load_accounting_operation_audit,
    )
    from aqorath.models import JournalEntry, JournalLine

    decision = _prepare(configured_engine)
    result = execute_accounting_operation(confirm_accounting_operation(decision))

    assert result.state == "posted"
    with Session(configured_engine) as session:
        entry = session.get(JournalEntry, result.entry_id)
        assert entry is not None
        assert entry.state == "posted"
        assert entry.date.date() == date.today()
        lines = session.exec(
            select(JournalLine).where(JournalLine.entry_id == result.entry_id)
        ).all()
        assert len(lines) == 2
        by_code = {line.account_code: line for line in lines}
        assert Decimal(str(by_code["1102"].debit)) == Decimal("200.00")
        assert Decimal(str(by_code["4201"].credit)) == Decimal("200.00")

        entity_id = session.execute(
            text("SELECT entity_id FROM accountingcalendar WHERE id=1")
        ).scalar_one()
        audit = load_accounting_operation_audit(
            session,
            entity_id,
            result.entry_id,
        )

    assert audit.id == result.audit_event_id
    assert audit.event_type == "entry_posted"
    assert audit.details["entry_id"] == result.entry_id
    durable = audit.details["decision"]
    assert durable["fact"] == {
        "type": "sale",
        "amount": "200.00",
        "payment_method": "cash",
    }
    assert durable["posting_date"] == date.today().isoformat()
    assert durable["rule_id"] == "economic_fact:sale:cash"
    assert durable["rule_version"] == "economic-fact-v1"
    assert durable["consent"] == "explicit_confirmation"
    assert durable["explanation"]["effects"] == [
        {"account_role": "cash", "side": "debit", "amount": "200.00"},
        {"account_role": "sales_revenue", "side": "credit", "amount": "200.00"},
    ]
    # Concrete accounts remain ledger truth; audit does not create a shadow ledger.
    assert "account_code" not in str(durable)


def test_period_is_rechecked_at_posting_and_closed_period_leaves_no_partial_truth(configured_engine):
    from aqorath.accounting_operation import (
        confirm_accounting_operation,
        execute_accounting_operation,
    )
    from aqorath.accounting_operation_persistence import AccountingOperationPersistenceError
    from aqorath.accounting_period_repository import close_period, require_open_period

    decision = _prepare(configured_engine)
    confirmed = confirm_accounting_operation(decision)

    with Session(configured_engine) as session:
        period = require_open_period(session, date.today())
        close_period(session, period.id)
        session.commit()

    with pytest.raises(AccountingOperationPersistenceError, match="closed"):
        execute_accounting_operation(confirmed)

    with Session(configured_engine) as session:
        assert session.execute(text("SELECT COUNT(*) FROM journalentry")).scalar_one() == 0
        assert session.execute(text("SELECT COUNT(*) FROM auditevent")).scalar_one() == 0


def test_audit_failure_rolls_back_canonical_posting(configured_engine, monkeypatch):
    import aqorath.accounting_operation_persistence as persistence
    from aqorath.accounting_operation import (
        confirm_accounting_operation,
        execute_accounting_operation,
    )

    decision = _prepare(configured_engine)
    confirmed = confirm_accounting_operation(decision)

    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(persistence._audit_repository, "stage_audit_event", fail)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        execute_accounting_operation(confirmed)

    with Session(configured_engine) as session:
        assert session.execute(text("SELECT COUNT(*) FROM journalentry")).scalar_one() == 0
        assert session.execute(text("SELECT COUNT(*) FROM journalline")).scalar_one() == 0
        assert session.execute(text("SELECT COUNT(*) FROM auditevent")).scalar_one() == 0


def test_posted_result_is_protected_by_aqr003_invariants(configured_engine):
    from aqorath.accounting_operation import (
        confirm_accounting_operation,
        execute_accounting_operation,
    )
    from aqorath.ledger_invariants import LedgerInvariantError
    from aqorath.models import JournalLine

    result = execute_accounting_operation(
        confirm_accounting_operation(_prepare(configured_engine))
    )

    with Session(configured_engine) as session:
        lines = session.exec(
            select(JournalLine).where(JournalLine.entry_id == result.entry_id)
        ).all()
        lines[0].debit = "175"
        lines[1].credit = "175"
        with pytest.raises(LedgerInvariantError, match="immutable"):
            session.commit()


def test_fiscalized_execution_delegates_existing_posting_and_audit_authorities(monkeypatch):
    import aqorath.accounting_operation as operation

    confirmed = object()
    instruction = object()
    expected = {"ok": True, "entry_id": 77}
    calls = []

    class NominalConfirmed:
        pass

    monkeypatch.setattr(
        operation._fiscalized_confirmation,
        "ConfirmedFiscalizedProposal",
        NominalConfirmed,
    )
    confirmed = NominalConfirmed()
    monkeypatch.setattr(
        operation._fiscalized_posting,
        "create_fiscalized_posting_instruction",
        lambda received, policy: calls.append(("build", received, policy)) or instruction,
    )
    monkeypatch.setattr(
        operation._fiscalized_persistence,
        "execute_fiscalized_posting_with_audit",
        lambda received: calls.append(("persist", received)) or expected,
    )

    result = operation.execute_fiscalized_accounting_operation(
        confirmed,
        "reject_zero_fiscal_line",
    )

    assert result is expected
    assert calls == [
        ("build", confirmed, "reject_zero_fiscal_line"),
        ("persist", instruction),
    ]


def test_prepare_does_not_post_or_create_audit(configured_engine):
    _prepare(configured_engine)
    with Session(configured_engine) as session:
        assert session.execute(text("SELECT COUNT(*) FROM journalentry")).scalar_one() == 0
        assert session.execute(text("SELECT COUNT(*) FROM auditevent")).scalar_one() == 0
