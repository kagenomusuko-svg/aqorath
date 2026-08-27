"""Phase 5AB.1 — fiscalized application boundary contracts."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from inspect import Parameter, signature
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session


_PUBLIC = {
    "resolve_economic_fact_with_provenance": ["fact"],
    "declare_fiscal_economic_composition": [
        "accounting_resolution",
        "fiscal_effect",
        "amount_basis",
        "adjustment_role",
    ],
    "compose_fiscal_economic_accounting": ["declaration"],
    "resolve_fiscalized_proposal_accounts": [
        "session",
        "fiscalized_proposal",
        "account_bindings",
    ],
    "prepare_fiscalized_confirmation": ["resolved_proposal"],
    "confirm_fiscalized_snapshot": ["snapshot"],
    "create_fiscalized_posting_instruction": [
        "confirmed_proposal",
        "zero_fiscal_line_policy",
    ],
    "execute_fiscalized_posting_instruction": ["instruction"],
}


def _assert_signature(fn, names):
    sig = signature(fn)
    assert list(sig.parameters) == names
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def _session(tmp_path):
    from aqorath.models import FiscalRuleVersion  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'application-fiscalized.db'}")
    SQLModel.metadata.create_all(engine)
    return engine, Session(engine)


def test_application_exposes_complete_fiscalized_boundary_with_exact_signatures():
    import aqorath.application as application

    for name, parameters in _PUBLIC.items():
        assert callable(getattr(application, name))
        _assert_signature(getattr(application, name), parameters)


def test_application_provenance_delegates_exact_fact_once(monkeypatch):
    import aqorath.application as application
    import aqorath.economic_fact_accounting_provenance as provenance

    fact = object()
    expected = object()
    calls = []
    monkeypatch.setattr(
        provenance,
        "resolve_economic_fact_with_provenance",
        lambda value: calls.append(value) or expected,
    )

    assert application.resolve_economic_fact_with_provenance(fact) is expected
    assert calls == [fact]


def test_application_composition_declaration_delegates_exact_arguments_once(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscal_economic_composition as composition

    accounting_resolution = object()
    fiscal_effect = object()
    expected = object()
    calls = []

    def fake(*args):
        calls.append(args)
        return expected

    monkeypatch.setattr(composition, "declare_fiscal_economic_composition", fake)
    result = application.declare_fiscal_economic_composition(
        accounting_resolution,
        fiscal_effect,
        "net_before_fiscal",
        "cash",
    )

    assert result is expected
    assert calls == [
        (accounting_resolution, fiscal_effect, "net_before_fiscal", "cash")
    ]


def test_application_composition_materialization_delegates_exact_declaration_once(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscalized_accounting_proposal as fiscalized

    declaration = object()
    expected = object()
    calls = []
    monkeypatch.setattr(
        fiscalized,
        "compose_fiscal_economic_accounting",
        lambda value: calls.append(value) or expected,
    )

    assert application.compose_fiscal_economic_accounting(declaration) is expected
    assert calls == [declaration]


def test_application_fiscalized_resolution_delegates_exact_session_proposal_and_bindings_once(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscalized_account_resolution as resolution

    session = object()
    proposal = object()
    bindings = {"cash": "1102"}
    expected = object()
    calls = []

    def fake(*args):
        calls.append(args)
        return expected

    monkeypatch.setattr(resolution, "resolve_fiscalized_proposal_accounts", fake)
    result = application.resolve_fiscalized_proposal_accounts(session, proposal, bindings)

    assert result is expected
    assert calls == [(session, proposal, bindings)]


def test_application_fiscalized_prepare_and_confirm_delegate_exact_objects_once(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscalized_confirmation as confirmation

    resolved = object()
    snapshot = object()
    confirmed = object()
    prepare_calls = []
    confirm_calls = []

    monkeypatch.setattr(
        confirmation,
        "create_fiscalized_confirmation_snapshot",
        lambda value: prepare_calls.append(value) or snapshot,
    )
    monkeypatch.setattr(
        confirmation,
        "confirm_fiscalized_snapshot",
        lambda value: confirm_calls.append(value) or confirmed,
    )

    assert application.prepare_fiscalized_confirmation(resolved) is snapshot
    assert application.confirm_fiscalized_snapshot(snapshot) is confirmed
    assert prepare_calls == [resolved]
    assert confirm_calls == [snapshot]


def test_application_fiscalized_instruction_delegates_exact_confirmed_truth_and_policy_once(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscalized_posting as posting

    confirmed = object()
    expected = object()
    calls = []

    def fake(*args):
        calls.append(args)
        return expected

    monkeypatch.setattr(posting, "create_fiscalized_posting_instruction", fake)
    result = application.create_fiscalized_posting_instruction(
        confirmed,
        "reject_zero_fiscal_line",
    )

    assert result is expected
    assert calls == [(confirmed, "reject_zero_fiscal_line")]


def test_application_fiscalized_execution_delegates_exact_instruction_once(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscalized_posting_execution as execution

    instruction = object()
    expected = object()
    calls = []
    monkeypatch.setattr(
        execution,
        "execute_fiscalized_posting_instruction",
        lambda value: calls.append(value) or expected,
    )

    assert application.execute_fiscalized_posting_instruction(instruction) is expected
    assert calls == [instruction]


def test_application_uses_module_lookup_not_captured_function_aliases(monkeypatch):
    import aqorath.application as application
    import aqorath.economic_fact_accounting_provenance as provenance
    import aqorath.fiscal_economic_composition as composition
    import aqorath.fiscalized_accounting_proposal as proposal
    import aqorath.fiscalized_account_resolution as resolution
    import aqorath.fiscalized_confirmation as confirmation
    import aqorath.fiscalized_posting as posting
    import aqorath.fiscalized_posting_execution as execution

    sentinels = [object() for _ in range(8)]
    monkeypatch.setattr(provenance, "resolve_economic_fact_with_provenance", lambda fact: sentinels[0])
    monkeypatch.setattr(composition, "declare_fiscal_economic_composition", lambda *args: sentinels[1])
    monkeypatch.setattr(proposal, "compose_fiscal_economic_accounting", lambda value: sentinels[2])
    monkeypatch.setattr(resolution, "resolve_fiscalized_proposal_accounts", lambda *args: sentinels[3])
    monkeypatch.setattr(confirmation, "create_fiscalized_confirmation_snapshot", lambda value: sentinels[4])
    monkeypatch.setattr(confirmation, "confirm_fiscalized_snapshot", lambda value: sentinels[5])
    monkeypatch.setattr(posting, "create_fiscalized_posting_instruction", lambda *args: sentinels[6])
    monkeypatch.setattr(execution, "execute_fiscalized_posting_instruction", lambda value: sentinels[7])

    assert application.resolve_economic_fact_with_provenance(object()) is sentinels[0]
    assert application.declare_fiscal_economic_composition(object(), object(), "net_before_fiscal", "cash") is sentinels[1]
    assert application.compose_fiscal_economic_accounting(object()) is sentinels[2]
    assert application.resolve_fiscalized_proposal_accounts(object(), object(), {}) is sentinels[3]
    assert application.prepare_fiscalized_confirmation(object()) is sentinels[4]
    assert application.confirm_fiscalized_snapshot(object()) is sentinels[5]
    assert application.create_fiscalized_posting_instruction(object(), "reject_zero_fiscal_line") is sentinels[6]
    assert application.execute_fiscalized_posting_instruction(object()) is sentinels[7]


def test_application_keeps_all_fiscalized_stages_explicit_and_never_collapses_pipeline(monkeypatch):
    import aqorath.application as application
    import aqorath.economic_fact_accounting_provenance as provenance
    import aqorath.fiscal_economic_composition as composition
    import aqorath.fiscalized_accounting_proposal as proposal
    import aqorath.fiscalized_account_resolution as resolution
    import aqorath.fiscalized_confirmation as confirmation
    import aqorath.fiscalized_posting as posting
    import aqorath.fiscalized_posting_execution as execution

    modules = (
        (provenance, "resolve_economic_fact_with_provenance"),
        (composition, "declare_fiscal_economic_composition"),
        (proposal, "compose_fiscal_economic_accounting"),
        (resolution, "resolve_fiscalized_proposal_accounts"),
        (confirmation, "create_fiscalized_confirmation_snapshot"),
        (confirmation, "confirm_fiscalized_snapshot"),
        (posting, "create_fiscalized_posting_instruction"),
        (execution, "execute_fiscalized_posting_instruction"),
    )

    for index, (module, attr) in enumerate(modules):
        called = []
        monkeypatch.setattr(module, attr, lambda *args, _i=index: called.append(_i) or object())
        for other_module, other_attr in modules:
            if other_module is module and other_attr == attr:
                continue
            monkeypatch.setattr(
                other_module,
                other_attr,
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("application must not collapse fiscalized stages")
                ),
            )

        if index == 0:
            application.resolve_economic_fact_with_provenance(object())
        elif index == 1:
            application.declare_fiscal_economic_composition(object(), object(), "net_before_fiscal", "cash")
        elif index == 2:
            application.compose_fiscal_economic_accounting(object())
        elif index == 3:
            application.resolve_fiscalized_proposal_accounts(object(), object(), {})
        elif index == 4:
            application.prepare_fiscalized_confirmation(object())
        elif index == 5:
            application.confirm_fiscalized_snapshot(object())
        elif index == 6:
            application.create_fiscalized_posting_instruction(object(), "reject_zero_fiscal_line")
        else:
            application.execute_fiscalized_posting_instruction(object())
        assert called == [index]
        monkeypatch.undo()


def test_application_fiscalized_failures_propagate_without_retry(monkeypatch):
    import aqorath.application as application
    import aqorath.fiscalized_posting_execution as execution

    calls = []

    def fail(value):
        calls.append(value)
        raise RuntimeError("fiscalized execution failed")

    monkeypatch.setattr(execution, "execute_fiscalized_posting_instruction", fail)
    marker = object()
    with pytest.raises(RuntimeError, match="fiscalized execution failed"):
        application.execute_fiscalized_posting_instruction(marker)
    assert calls == [marker]


def test_application_nonexecution_stages_do_not_call_core_storage_or_historical_posting(monkeypatch):
    import aqorath.application as application
    import aqorath.core as core
    import aqorath.posting as historical_posting
    import aqorath.posting_execution as historical_execution
    import aqorath.storage as storage
    import aqorath.fiscalized_posting as fiscalized_posting

    def forbidden(*args, **kwargs):
        raise AssertionError("application fiscalized preparation must not use hidden persistence authority")

    monkeypatch.setattr(core, "post_entry", forbidden)
    monkeypatch.setattr(storage, "get_session", forbidden)
    monkeypatch.setattr(historical_posting, "create_posting_instruction", forbidden)
    monkeypatch.setattr(historical_execution, "execute_posting_instruction", forbidden)
    monkeypatch.setattr(
        fiscalized_posting,
        "create_fiscalized_posting_instruction",
        lambda confirmed, policy: (confirmed, policy),
    )

    marker = object()
    assert application.create_fiscalized_posting_instruction(marker, "reject_zero_fiscal_line") == (
        marker,
        "reject_zero_fiscal_line",
    )


def test_real_explicit_application_fiscalized_flow_reaches_exact_core_payload(monkeypatch, tmp_path):
    import aqorath.application as application
    import aqorath.catalog as catalog
    import aqorath.core as core
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_rounding import FiscalRoundingPolicy
    from aqorath.fiscal_rule_install import install_fiscal_rule_set

    engine, session = _session(tmp_path)
    try:
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
        fact = EconomicFact("sale", Decimal("100.00"), "cash")

        accounting_resolution = application.resolve_economic_fact_with_provenance(fact)
        applicability = application.declare_fiscal_rate_applicability(
            fact,
            date(2026, 8, 27),
            data.MX_GENERAL_COMMERCIAL_IVA.context,
            "iva.general_rate",
            Decimal("100.00"),
        )
        calculated = application.calculate_declared_fiscal_rate(session, applicability)
        fiscal_snapshot = application.prepare_fiscal_confirmation(calculated)
        confirmed_fiscal = application.confirm_fiscal_treatment(fiscal_snapshot)
        rounded = application.round_confirmed_fiscal_amount(
            confirmed_fiscal,
            FiscalRoundingPolicy(
                "two-decimals",
                Decimal("0.01"),
                ROUND_HALF_UP,
                "EXPLICIT:APPLICATION-5AB",
            ),
        )
        monetary_snapshot = application.prepare_fiscal_monetary_confirmation(rounded)
        monetary_confirmed = application.confirm_fiscal_monetary_amount(monetary_snapshot)
        treatment = application.declare_fiscal_accounting_treatment(
            monetary_confirmed,
            "tax_payable",
            "credit",
        )
        effect = application.build_fiscal_accounting_effect(treatment)

        declaration = application.declare_fiscal_economic_composition(
            accounting_resolution,
            effect,
            "net_before_fiscal",
            "cash",
        )
        fiscalized = application.compose_fiscal_economic_accounting(declaration)

        accounts = {
            "CASH": SimpleNamespace(id=101, code="CASH", name="Caja"),
            "SALES": SimpleNamespace(id=202, code="SALES", name="Ventas"),
            "TAX": SimpleNamespace(id=303, code="TAX", name="IVA por pagar"),
        }
        monkeypatch.setattr(catalog, "resolve_account_by_code", lambda supplied_session, code: accounts[code])
        resolved = application.resolve_fiscalized_proposal_accounts(
            session,
            fiscalized,
            {
                "cash": "CASH",
                "sales_revenue": "SALES",
                "tax_payable": "TAX",
            },
        )
        snapshot = application.prepare_fiscalized_confirmation(resolved)
        confirmed = application.confirm_fiscalized_snapshot(snapshot)
        instruction = application.create_fiscalized_posting_instruction(
            confirmed,
            "reject_zero_fiscal_line",
        )

        calls = []
        sentinel = {"ok": True, "entry_id": 999}
        monkeypatch.setattr(core, "post_entry", lambda payload: calls.append(payload) or sentinel)
        result = application.execute_fiscalized_posting_instruction(instruction)

        assert result is sentinel
        assert calls == [
            {
                "description": instruction.description,
                "lines": [
                    {
                        "account_id": 101,
                        "account_code": "CASH",
                        "debit": Decimal("116.00"),
                        "credit": Decimal("0"),
                    },
                    {
                        "account_id": 202,
                        "account_code": "SALES",
                        "debit": Decimal("0"),
                        "credit": Decimal("100.00"),
                    },
                    {
                        "account_id": 303,
                        "account_code": "TAX",
                        "debit": Decimal("0"),
                        "credit": Decimal("16.00"),
                    },
                ],
            }
        ]
    finally:
        session.close()
        engine.dispose()
