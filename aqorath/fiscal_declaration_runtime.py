"""Runtime for explicit fiscal-rate applicability declarations.

This module bridges the explicit 5I declaration to the existing version-resolved
fiscal runtime. It preserves the declaration and the returned calculation by
identity for auditability. It does not inspect the economic fact, infer fiscal
applicability, resolve or calculate independently, round, install rules, choose
accounts, build accounting proposals, persist, or post.
"""

from dataclasses import dataclass

from . import fiscal_applicability as _applicability
from . import fiscal_calculation as _calculation
from . import fiscal_runtime as _fiscal_runtime


@dataclass(frozen=True)
class DeclaredFiscalRateCalculation:
    """Immutable link between an explicit declaration and its exact calculation."""

    declaration: _applicability.FiscalRateApplicabilityDeclaration
    calculation: _calculation.FiscalRateCalculation

    def __post_init__(self):
        if not isinstance(
            self.declaration,
            _applicability.FiscalRateApplicabilityDeclaration,
        ):
            raise TypeError(
                "declaration must be a FiscalRateApplicabilityDeclaration"
            )
        if not isinstance(self.calculation, _calculation.FiscalRateCalculation):
            raise TypeError("calculation must be a FiscalRateCalculation")


def calculate_declared_fiscal_rate(session, declaration):
    """Calculate exactly the rate treatment already stated by one declaration."""
    if not isinstance(
        declaration,
        _applicability.FiscalRateApplicabilityDeclaration,
    ):
        raise TypeError("declaration must be a FiscalRateApplicabilityDeclaration")

    calculation = _fiscal_runtime.calculate_fiscal_rate_for_date(
        session,
        declaration.rule_key,
        declaration.effective_date,
        declaration.context,
        declaration.base,
    )
    return DeclaredFiscalRateCalculation(
        declaration=declaration,
        calculation=calculation,
    )


__all__ = [
    "DeclaredFiscalRateCalculation",
    "calculate_declared_fiscal_rate",
]
