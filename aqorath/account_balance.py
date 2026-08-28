"""Pure exact balance-sign semantics for accounting amounts."""

from decimal import Decimal


_ALLOWED_NATURES = frozenset({"debit", "credit"})


def _require_decimal(value, field_name):
    if type(value) is not Decimal:
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")


def ledger_signed_balance(debit_total, credit_total):
    """Return the exact algebraic balance: debit total minus credit total."""
    _require_decimal(debit_total, "debit_total")
    _require_decimal(credit_total, "credit_total")

    if debit_total < Decimal("0"):
        raise ValueError("debit_total must be nonnegative")
    if credit_total < Decimal("0"):
        raise ValueError("credit_total must be nonnegative")

    return debit_total - credit_total


def normal_balance_amount(ledger_signed_balance, nature):
    """Interpret one exact signed balance through an explicit account nature."""
    _require_decimal(ledger_signed_balance, "ledger_signed_balance")

    if type(nature) is not str:
        raise TypeError("nature must be str")
    if nature not in _ALLOWED_NATURES:
        raise ValueError("nature must be debit or credit")

    if nature == "debit":
        return ledger_signed_balance
    return -ledger_signed_balance
