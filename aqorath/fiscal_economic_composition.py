"""Explicit fiscal/economic composition declaration.

Binds one provenance-aware economic accounting resolution to one or more already
confirmed fiscal accounting effects and records the caller's explicit monetary
basis plus the existing semantic role that the pure composition step may adjust.

This boundary validates cross-branch fact consistency and aggregate balance
direction only. It does not change amounts, create accounting lines, resolve
accounts, confirm, persist, or post.
"""

from dataclasses import dataclass
from decimal import Decimal

from . import economic_fact_accounting_provenance as _provenance
from . import fiscal_accounting_effect as _fiscal_effect
from . import fiscal_monetary_confirmation as _monetary_confirmation


_ALLOWED_AMOUNT_BASES = (
    "net_before_fiscal",
    "gross_including_fiscal",
    "base_before_fiscal_settlement",
)


def _require_nonempty_text(value, field_name):
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _normalize_effects(value):
    if isinstance(value, _fiscal_effect.FiscalAccountingEffect):
        return (value,)
    if not isinstance(value, tuple):
        raise TypeError("fiscal_effect must be FiscalAccountingEffect or a non-empty tuple")
    if not value:
        raise ValueError("fiscal effect tuple must not be empty")
    if not all(isinstance(effect, _fiscal_effect.FiscalAccountingEffect) for effect in value):
        raise TypeError("all fiscal effects must be FiscalAccountingEffect")
    return value


def _effect_snapshot(effect):
    monetary = effect.declaration.confirmed_monetary_amount
    snapshot = monetary.snapshot
    if not isinstance(
        snapshot,
        _monetary_confirmation.FiscalMonetaryConfirmationSnapshot,
    ):
        raise TypeError(
            "fiscal effect must preserve FiscalMonetaryConfirmationSnapshot"
        )
    return snapshot


def _aggregate_fiscal_delta(effects):
    debit = sum(
        (effect.line.amount for effect in effects if effect.line.side == "debit"),
        Decimal("0"),
    )
    credit = sum(
        (effect.line.amount for effect in effects if effect.line.side == "credit"),
        Decimal("0"),
    )
    return credit - debit


@dataclass(frozen=True)
class FiscalEconomicCompositionDeclaration:
    """Explicit, non-postable declaration for later economic/fiscal composition."""

    accounting_resolution: _provenance.EconomicFactAccountingResolution
    fiscal_effect: object
    amount_basis: str
    adjustment_role: str

    @property
    def fiscal_effects(self):
        """Canonical ordered immutable fiscal-effect collection."""
        if isinstance(self.fiscal_effect, tuple):
            return self.fiscal_effect
        return (self.fiscal_effect,)

    def __post_init__(self):
        if not isinstance(
            self.accounting_resolution,
            _provenance.EconomicFactAccountingResolution,
        ):
            raise TypeError(
                "accounting_resolution must be EconomicFactAccountingResolution"
            )
        effects = _normalize_effects(self.fiscal_effect)

        if not isinstance(self.amount_basis, str):
            raise TypeError("amount_basis must be a string")
        if self.amount_basis not in _ALLOWED_AMOUNT_BASES:
            raise ValueError(
                "amount_basis must be 'net_before_fiscal', "
                "'gross_including_fiscal' or 'base_before_fiscal_settlement'"
            )
        _require_nonempty_text(self.adjustment_role, "adjustment_role")

        fact = self.accounting_resolution.fact
        first_snapshot = None
        for effect in effects:
            snapshot = _effect_snapshot(effect)
            if fact.type != snapshot.fact_type:
                raise ValueError("economic and fiscal fact_type must match")
            if fact.payment_method != snapshot.payment_method:
                raise ValueError("economic and fiscal payment_method must match")
            if not isinstance(snapshot.fact_amount, Decimal):
                raise TypeError("fiscal fact_amount must be Decimal")
            if fact.amount.as_tuple() != snapshot.fact_amount.as_tuple():
                raise ValueError("economic and fiscal fact_amount must match exactly")
            if first_snapshot is None:
                first_snapshot = snapshot
            else:
                # Effective date and jurisdiction describe the one economic event.
                # Regime/entity_type remain per-rule registry scope: AQR-011 can
                # legitimately compose a recipient-PM VAT rule with a supplier-PF
                # ISR rule without falsifying either rule's provenance.
                for name in ("effective_date", "jurisdiction"):
                    if getattr(snapshot, name) != getattr(first_snapshot, name):
                        raise ValueError(
                            f"all fiscal effects must share {name} for one composition"
                        )

        matches = tuple(
            line
            for line in self.accounting_resolution.proposal.lines
            if line.account_role == self.adjustment_role
        )
        if len(matches) != 1:
            raise ValueError(
                "adjustment_role must identify exactly one existing proposal line"
            )

        adjustment_line = matches[0]
        delta = _aggregate_fiscal_delta(effects)
        if delta == Decimal("0"):
            return

        # AQR-011 paid purchases start from a pre-fiscal economic base. The
        # settlement line absorbs the aggregate tax/withholding delta regardless
        # of its sign; _adjusted_amount owns the exact arithmetic later. This is
        # distinct from the two historical sale-oriented basis contracts below.
        if self.amount_basis == "base_before_fiscal_settlement":
            return

        excess_side = "credit" if delta > Decimal("0") else "debit"
        if self.amount_basis == "net_before_fiscal":
            if adjustment_line.side == excess_side:
                raise ValueError(
                    "net_before_fiscal requires adjustment role opposite the "
                    "aggregate fiscal excess side"
                )
        else:
            if adjustment_line.side != excess_side:
                raise ValueError(
                    "gross_including_fiscal requires adjustment role on the "
                    "aggregate fiscal excess side"
                )


def declare_fiscal_economic_composition(
    accounting_resolution,
    fiscal_effect,
    amount_basis,
    adjustment_role,
):
    """Record explicit compatible economic/fiscal composition inputs."""
    return FiscalEconomicCompositionDeclaration(
        accounting_resolution=accounting_resolution,
        fiscal_effect=fiscal_effect,
        amount_basis=amount_basis,
        adjustment_role=adjustment_role,
    )


__all__ = [
    "FiscalEconomicCompositionDeclaration",
    "declare_fiscal_economic_composition",
]
