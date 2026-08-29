"""Pure exact balance-sign semantics for accounting amounts."""

from decimal import Decimal, localcontext

from .account import Account
from .journal_entry import JournalEntry
from .journal_line import JournalLine


_ALLOWED_NATURES = frozenset({"debit", "credit"})


def _require_decimal(value, field_name):
    if type(value) is not Decimal:
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")


def _exact_decimal_sum(values):
    """Sum finite Decimals exactly without depending on ambient context precision."""
    if not values:
        return Decimal("0")

    parts_list = [value.as_tuple() for value in values]
    common_exponent = min(parts.exponent for parts in parts_list)
    total_coefficient = 0

    for parts in parts_list:
        coefficient = 0
        for digit in parts.digits:
            coefficient = coefficient * 10 + digit
        if parts.sign:
            coefficient = -coefficient
        total_coefficient += coefficient * (10 ** (parts.exponent - common_exponent))

    sign = int(total_coefficient < 0)
    magnitude = abs(total_coefficient)
    if magnitude == 0:
        digits = (0,)
    else:
        reversed_digits = []
        while magnitude:
            magnitude, digit = divmod(magnitude, 10)
            reversed_digits.append(digit)
        digits = tuple(reversed(reversed_digits))

    return Decimal((sign, digits, common_exponent))


def ledger_signed_balance(debit_total, credit_total):
    """Return the exact algebraic balance: debit total minus credit total."""
    _require_decimal(debit_total, "debit_total")
    _require_decimal(credit_total, "credit_total")

    if debit_total < Decimal("0"):
        raise ValueError("debit_total must be nonnegative")
    if credit_total < Decimal("0"):
        raise ValueError("credit_total must be nonnegative")

    debit_parts = debit_total.as_tuple()
    credit_parts = credit_total.as_tuple()
    common_exponent = min(debit_parts.exponent, credit_parts.exponent)
    required_precision = max(
        len(debit_parts.digits) + debit_parts.exponent - common_exponent,
        len(credit_parts.digits) + credit_parts.exponent - common_exponent,
    ) + 1
    with localcontext() as context:
        context.prec = required_precision
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
    if ledger_signed_balance.is_zero():
        return ledger_signed_balance.copy_abs()
    return ledger_signed_balance.copy_negate()


def normal_balance_for_account(account, debit_total, credit_total):
    """Return the exact normal balance for one explicit Account."""
    if not isinstance(account, Account):
        raise TypeError("account must be Account")

    signed_balance = ledger_signed_balance(debit_total, credit_total)
    return normal_balance_amount(signed_balance, account.nature)


def journal_line_totals(lines):
    """Sum exact debit and credit monetary truth from explicit lines."""
    if type(lines) is not tuple:
        raise TypeError("lines must be tuple")

    debit_values = []
    credit_values = []
    for line in lines:
        if not isinstance(line, JournalLine):
            raise TypeError("lines items must be JournalLine")
        debit_values.append(line.debit)
        credit_values.append(line.credit)

    return _exact_decimal_sum(debit_values), _exact_decimal_sum(credit_values)


def journal_entry_totals(entry):
    """Project exact debit and credit totals from one explicit JournalEntry."""
    if not isinstance(entry, JournalEntry):
        raise TypeError("entry must be JournalEntry")

    return journal_line_totals(entry.lines)


def journal_entry_signed_balance(entry):
    """Return the exact debit-minus-credit signed balance of one JournalEntry."""
    if not isinstance(entry, JournalEntry):
        raise TypeError("entry must be JournalEntry")

    debit_total, credit_total = journal_entry_totals(entry)
    return ledger_signed_balance(debit_total, credit_total)


def journal_line_normal_balance(line):
    """Return one JournalLine's exact normal-balance effect."""
    if not isinstance(line, JournalLine):
        raise TypeError("line must be JournalLine")

    return normal_balance_for_account(line.account, line.debit, line.credit)


def journal_line_signed_balance(line):
    """Return one JournalLine's exact debit-minus-credit signed effect."""
    if not isinstance(line, JournalLine):
        raise TypeError("line must be JournalLine")

    return ledger_signed_balance(line.debit, line.credit)


def journal_lines_signed_balance(lines):
    """Return exact debit-minus-credit signed balance for explicit lines."""
    debit_total, credit_total = journal_line_totals(lines)
    return ledger_signed_balance(debit_total, credit_total)


def journal_lines_are_balanced(lines):
    """Return whether explicit lines have exact zero signed balance."""
    return journal_lines_signed_balance(lines) == Decimal("0")
