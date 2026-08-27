"""Phase 5T.1 — fiscal accounting treatment/effect application contracts."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from inspect import Parameter, signature

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session, select


def _assert_signature(fn, names):
    sig = signature(fn)
    assert list(sig.parameters) == names
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'application-fiscal-effect.db'}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_application_exposes_fiscal_accounting_treatment_and_effect_exact_signatures():
    import aqorath.application as application

    _assert_signature(
        application.declare_fiscal_accounting_treatment,
        ["confirmed_monetary_amount", "account_role", "side"],
    )
    _assert_signature(
        application.build_fiscal_accounting_effect,
        ["declaration"],
    )


def test_application_declare_fiscal_accounting_treatment_delegates_exact_arguments_once(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_accounting_treatment as treatment

    confirmed = object()
    expected = object()
    calls = []

    def fake(confirmed_arg, role_arg, side_arg):
        calls.append((confirmed_arg, role_arg, side_arg))
        return expected

    monkeypatch.setattr(treatment, "declare_fiscal_accounting_treatment", fake)
    result = application.declare_fiscal_accounting_treatment(
        confirmed, "tax_payable", "credit"
    )

    assert result is expected
    assert calls == [(confirmed, "tax_payable", "credit")]


def test_application_build_fiscal_accounting_effect_delegates_exact_declaration_once(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_accounting_effect as effect

    declaration = object()
    expected = object()
    calls = []

    def fake(value):
        calls.append(value)
        return expected

    monkeypatch.setattr(effect, "build_fiscal_accounting_effect", fake)
    result = application.build_fiscal_accounting_effect(declaration)

    assert result is expected
    assert calls == [declaration]


def test_application_uses_module_lookup_not_captured_aliases_for_fiscal_accounting_boundaries(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_accounting_effect as effect
    import aqorath.fiscal_accounting_treatment as treatment

    declared = object()
    built = object()
    monkeypatch.setattr(
        treatment,
        "declare_fiscal_accounting_treatment",
        lambda confirmed, role, side: declared,
    )
    monkeypatch.setattr(effect, "build_fiscal_accounting_effect", lambda declaration: built)

    assert application.declare_fiscal_accounting_treatment(object(), "r", "debit") is declared
    assert application.build_fiscal_accounting_effect(object()) is built


def test_application_keeps_treatment_declaration_and_effect_build_as_separate_explicit_acts(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_accounting_effect as effect
    import aqorath.fiscal_accounting_treatment as treatment

    declaration = object()
    built = object()

    def forbidden(*args, **kwargs):
        raise AssertionError("application must not collapse declaration and effect")

    monkeypatch.setattr(effect, "build_fiscal_accounting_effect", forbidden)
    monkeypatch.setattr(
        treatment,
        "declare_fiscal_accounting_treatment",
        lambda confirmed, role, side: declaration,
    )
    assert application.declare_fiscal_accounting_treatment(object(), "r", "credit") is declaration

    monkeypatch.setattr(treatment, "declare_fiscal_accounting_treatment", forbidden)
    monkeypatch.setattr(effect, "build_fiscal_accounting_effect", lambda value: built)
    assert application.build_fiscal_accounting_effect(declaration) is built


def test_application_fiscal_accounting_boundary_failures_propagate_without_retry(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_accounting_effect as effect
    import aqorath.fiscal_accounting_treatment as treatment

    declaration_calls = []
    effect_calls = []

    def fail_declare(*args):
        declaration_calls.append(args)
        raise ValueError("treatment failed")

    def fail_effect(value):
        effect_calls.append(value)
        raise ValueError("effect failed")

    monkeypatch.setattr(treatment, "declare_fiscal_accounting_treatment", fail_declare)
    with pytest.raises(ValueError, match="treatment failed"):
        application.declare_fiscal_accounting_treatment(object(), "r", "debit")
    assert len(declaration_calls) == 1

    monkeypatch.setattr(effect, "build_fiscal_accounting_effect", fail_effect)
    with pytest.raises(ValueError, match="effect failed"):
        application.build_fiscal_accounting_effect(object())
    assert len(effect_calls) == 1


def test_application_does_not_resolve_accounts_compose_balance_confirm_post_or_open_session(monkeypatch):
    import aqorath.account_bindings as bindings
    import aqorath.account_resolution as resolution
    import aqorath.application as application
    import aqorath.confirmation as confirmation
    import aqorath.fiscal_accounting_effect as effect
    import aqorath.fiscal_accounting_treatment as treatment
    import aqorath.posting as posting
    import aqorath.storage as storage

    def forbidden(*args, **kwargs):
        raise AssertionError("application must not own fiscal/accounting composition")

    monkeypatch.setattr(bindings, "get_account_binding", forbidden)
    monkeypatch.setattr(resolution, "resolve_proposal_accounts", forbidden)
    monkeypatch.setattr(confirmation, "create_confirmation_snapshot", forbidden)
    monkeypatch.setattr(posting, "create_posting_instruction", forbidden)
    monkeypatch.setattr(storage, "get_session", forbidden)

    declared = object()
    built = object()
    monkeypatch.setattr(
        treatment,
        "declare_fiscal_accounting_treatment",
        lambda confirmed, role, side: declared,
    )
    monkeypatch.setattr(effect, "build_fiscal_accounting_effect", lambda value: built)

    assert application.declare_fiscal_accounting_treatment(object(), "r", "credit") is declared
    assert application.build_fiscal_accounting_effect(declared) is built


def test_application_real_explicit_fiscal_flow_reaches_semantic_effect_without_journal_entry(tmp_path):
    import aqorath.application as application
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_rounding import FiscalRoundingPolicy
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.models import JournalEntry

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        fact = EconomicFact("sale", Decimal("250.00"), "cash")
        applicability = application.declare_fiscal_rate_applicability(
            fact,
            date(2026, 8, 27),
            data.MX_GENERAL_COMMERCIAL_IVA.context,
            "iva.general_rate",
            Decimal("250.00"),
        )
        calculated = application.calculate_declared_fiscal_rate(session, applicability)
        fiscal_snapshot = application.prepare_fiscal_confirmation(calculated)
        fiscal_confirmed = application.confirm_fiscal_treatment(fiscal_snapshot)
        policy = FiscalRoundingPolicy(
            "two-decimals", Decimal("0.01"), ROUND_HALF_UP, "EXPLICIT:TEST"
        )
        rounded = application.round_confirmed_fiscal_amount(fiscal_confirmed, policy)
        monetary_snapshot = application.prepare_fiscal_monetary_confirmation(rounded)
        monetary_confirmed = application.confirm_fiscal_monetary_amount(monetary_snapshot)

        before = session.exec(select(JournalEntry)).all()
        declaration = application.declare_fiscal_accounting_treatment(
            monetary_confirmed,
            "tax_payable",
            "credit",
        )
        effect = application.build_fiscal_accounting_effect(declaration)
        after = session.exec(select(JournalEntry)).all()

        assert effect.declaration is declaration
        assert effect.line.account_role == "tax_payable"
        assert effect.line.side == "credit"
        assert effect.line.amount == Decimal("40.00")
        assert before == after == []
    finally:
        session.close()
        engine.dispose()


def test_existing_application_api_remains_available_after_fiscal_accounting_effect_boundary():
    import aqorath.application as application

    for name in (
        "preview_economic_fact",
        "confirm_economic_fact",
        "post_confirmed_economic_fact",
        "declare_fiscal_rate_applicability",
        "calculate_declared_fiscal_rate",
        "prepare_fiscal_confirmation",
        "confirm_fiscal_treatment",
        "round_confirmed_fiscal_amount",
        "prepare_fiscal_monetary_confirmation",
        "confirm_fiscal_monetary_amount",
        "declare_fiscal_accounting_treatment",
        "build_fiscal_accounting_effect",
    ):
        assert callable(getattr(application, name))
