"""Version-resolved fiscal rate calculation runtime.

This module composes fiscal rule resolution with the pure rate calculation
primitive. It does not determine rule applicability, install rules, round
currency, choose accounts, build proposals, post, or persist.
"""

from . import fiscal_calculation as _calculation
from . import fiscal_rules as _fiscal_rules


def calculate_fiscal_rate_for_date(session, rule_key, effective_date, context, base):
    """Resolve one exact dated rule and calculate its exact rate amount."""
    rule = _fiscal_rules.resolve_fiscal_rule(
        session,
        rule_key,
        effective_date,
        context,
    )
    return _calculation.calculate_fiscal_rate_amount(base, rule)


__all__ = ["calculate_fiscal_rate_for_date"]
