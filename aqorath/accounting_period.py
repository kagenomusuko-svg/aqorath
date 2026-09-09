"""AQR-002: the single, pure calendar authority for posting dates."""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime


class PeriodError(ValueError):
    """An explicit temporal contract violation; never a reason for a fallback."""


def accounting_date(value):
    """Preserve the declared civil date; do not reinterpret it in another timezone."""
    if isinstance(value, datetime):
        return value.date()
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
        except ValueError as exc:
            raise PeriodError('Invalid accounting date') from exc
    raise PeriodError('An explicit accounting date is required')


def _day(value):
    if type(value) is not date:
        raise PeriodError('Calendar boundaries must be dates')
    return value


@dataclass(frozen=True)
class FiscalYear:
    year: int
    activity_start: date
    state: str = 'open'

    def __post_init__(self):
        _day(self.activity_start)
        if type(self.year) is not int or not self.activity_start.year <= self.year <= 9999:
            raise PeriodError('Fiscal year precedes activity start or is invalid')
        if self.state not in ('open', 'closed'):
            raise PeriodError('Invalid fiscal year state')

    @property
    def start(self):
        return max(self.activity_start, date(self.year, 1, 1))

    @property
    def end(self):
        return date(self.year, 12, 31)

    def periods(self):
        return tuple(AccountingPeriod(self, month) for month in range(self.start.month, 13))


@dataclass(frozen=True)
class AccountingPeriod:
    fiscal_year: FiscalYear
    month: int
    state: str = 'open'

    def __post_init__(self):
        if type(self.fiscal_year) is not FiscalYear:
            raise PeriodError('FiscalYear required')
        if type(self.month) is not int or not self.fiscal_year.start.month <= self.month <= 12:
            raise PeriodError('Month outside fiscal year')
        if self.state not in ('open', 'closed'):
            raise PeriodError('Invalid accounting period state')

    @property
    def id(self):
        return self.fiscal_year.year * 100 + self.month

    @property
    def start(self):
        return max(self.fiscal_year.start, date(self.fiscal_year.year, self.month, 1))

    @property
    def end(self):
        y = self.fiscal_year.year
        return date(y, self.month, monthrange(y, self.month)[1])


def resolve_posting_period(value, fiscal_year, periods, supplied_id=None, *, annual_closing=False):
    """Resolve a declared date against explicit, persisted open calendar state."""
    day = accounting_date(value)
    if not fiscal_year.start <= day <= fiscal_year.end:
        raise PeriodError('Posting date outside fiscal year or before activity start')
    closing = annual_closing and day == fiscal_year.end
    if annual_closing and not closing:
        raise PeriodError('Annual closing must use fiscal year end')
    if fiscal_year.state != 'open' and not closing:
        raise PeriodError('Fiscal year is closed')
    matches = [p for p in periods if p.start <= day <= p.end]
    if len(matches) != 1:
        raise PeriodError('Posting requires exactly one existing accounting period')
    period = matches[0]
    if period.fiscal_year != fiscal_year:
        raise PeriodError('Period belongs to a different fiscal year')
    if period.state != 'open' and not closing:
        raise PeriodError('Accounting period is closed')
    if supplied_id is not None and (type(supplied_id) is not int or supplied_id != period.id):
        raise PeriodError('period_id does not match accounting date')
    return period
