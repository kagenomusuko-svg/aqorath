"""Phase 6BC.1 — frozen finite-money authority contracts for legacy economic facts.

EconomicFact and ProposalLine already require positive Decimal amounts. R5 and the newer
pure domain values establish that authoritative monetary Decimal values must also be
finite. This phase freezes only that convergence: exact positive finite Decimal values
remain valid and preserve precision; NaN and infinities fail closed. It does not change
semantic event vocabularies, account-role resolution, proposal shape, posting, fiscal
logic, persistence, reporting, EconomicEvent lifecycle, or Application.
"""

from dataclasses import fields
from decimal import Decimal
import inspect

import pytest


def _fact(amount):
    from aqorath.economic_facts import EconomicFact

    return EconomicFact(type="sale", amount=amount, payment_method="cash")


def _line(amount):
    from aqorath.economic_facts import ProposalLine

    return ProposalLine(account_role="cash", side="debit", amount=amount)


def test_economic_fact_public_shape_remains_unchanged():
    from aqorath.economic_facts import EconomicFact

    assert tuple(field.name for field in fields(EconomicFact)) == (
        "type",
        "amount",
        "payment_method",
    )
    assert tuple(inspect.signature(EconomicFact).parameters) == (
        "type",
        "amount",
        "payment_method",
    )


def test_economic_fact_preserves_exact_positive_finite_decimal_identity_and_precision():
    amount = Decimal("123.4500000000000000000000000001")
    fact = _fact(amount)

    assert fact.amount is amount
    assert fact.amount.as_tuple() == amount.as_tuple()


def test_economic_fact_rejects_non_decimal_without_numeric_coercion():
    for invalid in (1, 1.0, "1.00", True, None):
        with pytest.raises(TypeError):
            _fact(invalid)


def test_economic_fact_rejects_every_nonfinite_decimal_with_value_error():
    for invalid in (
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ):
        with pytest.raises(ValueError):
            _fact(invalid)


def test_economic_fact_rejects_zero_signed_zero_and_negative_finite_amounts():
    for invalid in (
        Decimal("0"),
        Decimal("-0"),
        Decimal("-0.0001"),
        Decimal("-999999999.99"),
    ):
        with pytest.raises(ValueError):
            _fact(invalid)


def test_economic_fact_accepts_arbitrarily_small_positive_finite_decimal_exactly():
    amount = Decimal("0.0000000000000000000000000001")
    fact = _fact(amount)
    assert fact.amount is amount


def test_proposal_line_public_shape_remains_unchanged():
    from aqorath.economic_facts import ProposalLine

    assert tuple(field.name for field in fields(ProposalLine)) == (
        "account_role",
        "side",
        "amount",
    )
    assert tuple(inspect.signature(ProposalLine).parameters) == (
        "account_role",
        "side",
        "amount",
    )


def test_proposal_line_preserves_exact_positive_finite_decimal_identity_and_precision():
    amount = Decimal("987.6500000000000000000000000001")
    line = _line(amount)

    assert line.amount is amount
    assert line.amount.as_tuple() == amount.as_tuple()


def test_proposal_line_rejects_non_decimal_without_numeric_coercion():
    for invalid in (1, 1.0, "1.00", True, None):
        with pytest.raises(TypeError):
            _line(invalid)


def test_proposal_line_rejects_every_nonfinite_decimal_with_value_error():
    for invalid in (
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ):
        with pytest.raises(ValueError):
            _line(invalid)


def test_proposal_line_rejects_zero_signed_zero_and_negative_finite_amounts():
    for invalid in (
        Decimal("0"),
        Decimal("-0"),
        Decimal("-0.0001"),
        Decimal("-999999999.99"),
    ):
        with pytest.raises(ValueError):
            _line(invalid)


def test_proposal_line_accepts_arbitrarily_small_positive_finite_decimal_exactly():
    amount = Decimal("0.0000000000000000000000000001")
    line = _line(amount)
    assert line.amount is amount


def test_resolver_preserves_the_same_authoritative_fact_amount_on_both_proposal_lines():
    from aqorath.economic_facts import resolve_economic_fact

    amount = Decimal("45.6700000000000000000000000001")
    fact = _fact(amount)
    proposal = resolve_economic_fact(fact)

    assert proposal.lines[0].amount is amount
    assert proposal.lines[1].amount is amount


def test_high_precision_finite_fact_resolves_without_rounding_or_quantization():
    from aqorath.economic_facts import resolve_economic_fact

    amount = Decimal("1.0000000000000000000000000001")
    proposal = resolve_economic_fact(_fact(amount))

    assert proposal.lines[0].amount.as_tuple() == amount.as_tuple()
    assert proposal.lines[1].amount.as_tuple() == amount.as_tuple()


def test_both_monetary_ingress_points_explicitly_check_finiteness_without_coercion():
    from aqorath.economic_facts import EconomicFact, ProposalLine

    fact_source = inspect.getsource(EconomicFact.__post_init__).lower()
    line_source = inspect.getsource(ProposalLine.__post_init__).lower()

    assert "is_finite" in fact_source
    assert "is_finite" in line_source
    for source in (fact_source, line_source):
        for forbidden in (
            "quantize",
            "round(",
            "float(",
            "decimal(str",
        ):
            assert forbidden not in source


def test_finite_money_convergence_does_not_expand_legacy_semantic_scope():
    import aqorath.economic_facts as domain

    source = inspect.getsource(domain).lower()
    for forbidden in (
        "economic_event",
        "journalentry",
        "journalline",
        "accountingdecision",
        "sqlmodel",
        "sqlalchemy",
        "sqlite3",
        "repository",
        "get_session",
        "posting",
        "fiscal_rule",
        "trial_balance",
        "income_statement",
        "balance_sheet",
        "aqorath.application",
    ):
        assert forbidden not in source
