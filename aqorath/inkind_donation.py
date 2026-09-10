"""Pure non-cash donation evidence; accounting remains canonical JournalLine."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class InKindDonation:
    id: int | None
    entity_id: int
    donor_third_party_id: int | None
    document_reference_id: int | None
    fund_id: int | None
    program_id: int | None
    journal_line_id: int | None
    received_at: datetime
    description: str
    quantity: Decimal | None
    valuation_amount: Decimal
    valuation_currency: str
    valuation_method: str
    valuation_evidence: str
    external_reference: str

    def __post_init__(self):
        for name, value in (("entity_id", self.entity_id),):
            if type(value) is not int or value <= 0: raise ValueError(f"{name} must be positive")
        for name, value in (("id", self.id), ("donor_third_party_id", self.donor_third_party_id), ("document_reference_id", self.document_reference_id), ("fund_id", self.fund_id), ("program_id", self.program_id), ("journal_line_id", self.journal_line_id)):
            if value is not None and (type(value) is not int or value <= 0): raise ValueError(f"{name} must be positive")
        if type(self.received_at) is not datetime: raise TypeError("received_at must be datetime")
        if type(self.valuation_amount) is not Decimal or not self.valuation_amount.is_finite() or self.valuation_amount <= 0: raise ValueError("valuation_amount must be a positive Decimal")
        if self.quantity is not None and (type(self.quantity) is not Decimal or not self.quantity.is_finite() or self.quantity <= 0): raise ValueError("quantity must be a positive Decimal")
        for name, value in (("description", self.description), ("valuation_currency", self.valuation_currency), ("valuation_method", self.valuation_method), ("valuation_evidence", self.valuation_evidence), ("external_reference", self.external_reference)):
            if type(value) is not str or not value or value.strip() != value: raise ValueError(f"{name} must be nonblank text")
