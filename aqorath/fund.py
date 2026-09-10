"""Pure OSC fund, source, receipt and application values."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

def _id(value, name):
    if type(value) is not int or value <= 0: raise ValueError(f"{name} must be a positive int")
def _text(value, name):
    if type(value) is not str or not value or value.strip() != value: raise ValueError(f"{name} must be nonblank text without surrounding whitespace")
def _amount(value, name):
    if type(value) is not Decimal or not value.is_finite() or value <= 0: raise ValueError(f"{name} must be a finite positive Decimal")

@dataclass(frozen=True)
class Fund:
    id: int | None; entity_id: int; code: str; name: str; restriction: str; purpose: str | None = None; program_id: int | None = None; valid_from: date | None = None; valid_until: date | None = None
    def __post_init__(self):
        if self.id is not None: _id(self.id, "id")
        _id(self.entity_id, "entity_id"); _text(self.code, "code"); _text(self.name, "name")
        if self.restriction not in ("restricted", "unrestricted"): raise ValueError("restriction must be restricted or unrestricted")
        if self.purpose is not None: _text(self.purpose, "purpose")
        if self.program_id is not None: _id(self.program_id, "program_id")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from: raise ValueError("valid_until cannot precede valid_from")

@dataclass(frozen=True)
class FundingSource:
    id: int | None; entity_id: int; name: str; donor_third_party_id: int | None = None; external_reference: str | None = None
    def __post_init__(self):
        if self.id is not None: _id(self.id, "id")
        _id(self.entity_id, "entity_id"); _text(self.name, "name")
        if self.donor_third_party_id is not None: _id(self.donor_third_party_id, "donor_third_party_id")
        if self.external_reference is not None: _text(self.external_reference, "external_reference")

@dataclass(frozen=True)
class FundReceipt:
    id: int | None; entity_id: int; fund_id: int; funding_source_id: int; journal_line_id: int; amount: Decimal; received_at: datetime; donation_id: int | None = None
    def __post_init__(self):
        if self.id is not None: _id(self.id, "id")
        for name, value in (("entity_id", self.entity_id), ("fund_id", self.fund_id), ("funding_source_id", self.funding_source_id), ("journal_line_id", self.journal_line_id)): _id(value, name)
        _amount(self.amount, "amount")
        if type(self.received_at) is not datetime: raise TypeError("received_at must be datetime")
        if self.donation_id is not None: _id(self.donation_id, "donation_id")

@dataclass(frozen=True)
class FundApplication:
    id: int | None; entity_id: int; fund_id: int; program_id: int; journal_line_id: int; amount: Decimal; applied_at: datetime; receipt_id: int | None = None; purpose: str | None = None
    def __post_init__(self):
        if self.id is not None: _id(self.id, "id")
        for name, value in (("entity_id", self.entity_id), ("fund_id", self.fund_id), ("program_id", self.program_id), ("journal_line_id", self.journal_line_id)): _id(value, name)
        _amount(self.amount, "amount")
        if type(self.applied_at) is not datetime: raise TypeError("applied_at must be datetime")
        if self.receipt_id is not None: _id(self.receipt_id, "receipt_id")
        if self.purpose is not None: _text(self.purpose, "purpose")


@dataclass(frozen=True)
class FundBalance:
    fund_id: int
    as_of: date
    received: Decimal
    applied: Decimal
    available: Decimal
    restriction: str
    program_id: int | None

    def __post_init__(self):
        _id(self.fund_id, "fund_id")
        if type(self.as_of) is not date: raise TypeError("as_of must be date")
        for name, value in (("received", self.received), ("applied", self.applied), ("available", self.available)):
            if type(value) is not Decimal or not value.is_finite(): raise TypeError(f"{name} must be finite Decimal")
        if self.received < 0 or self.applied < 0 or self.available < 0: raise ValueError("fund balances cannot be negative")
        if self.available != self.received - self.applied: raise ValueError("available must equal received minus applied")
