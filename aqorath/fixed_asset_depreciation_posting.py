"""Explicit dated posting boundary for confirmed fixed-asset depreciation."""

from dataclasses import dataclass
from datetime import date

from . import core as _core
from . import posting as _posting
from .fixed_asset_depreciation_confirmation import ConfirmedFixedAssetDepreciation


_FACTORY_TOKEN = object()


@dataclass(frozen=True, init=False)
class FixedAssetDepreciationPostingInstruction:
    """Immutable posting instruction that preserves confirmed dated provenance."""

    confirmed_depreciation: ConfirmedFixedAssetDepreciation
    posting_instruction: _posting.PostingInstruction
    posting_date: date

    def __init__(
        self,
        confirmed_depreciation,
        posting_instruction,
        posting_date,
        *,
        _token=None,
    ):
        if _token is not _FACTORY_TOKEN:
            raise TypeError("FixedAssetDepreciationPostingInstruction is factory-only")
        if not isinstance(confirmed_depreciation, ConfirmedFixedAssetDepreciation):
            raise TypeError("confirmed_depreciation must be ConfirmedFixedAssetDepreciation")
        if not isinstance(posting_instruction, _posting.PostingInstruction):
            raise TypeError("posting_instruction must be PostingInstruction")
        if not isinstance(posting_date, date):
            raise TypeError("posting_date must be date")

        expected_date = (
            confirmed_depreciation.snapshot.accounting_resolution.recognition_fact.recognition_date
        )
        if posting_date != expected_date:
            raise ValueError("posting_date must equal confirmed recognition date")

        object.__setattr__(self, "confirmed_depreciation", confirmed_depreciation)
        object.__setattr__(self, "posting_instruction", posting_instruction)
        object.__setattr__(self, "posting_date", posting_date)


def create_fixed_asset_depreciation_posting_instruction(confirmed_depreciation):
    """Create dated posting truth from one nominal confirmed depreciation."""
    if not isinstance(confirmed_depreciation, ConfirmedFixedAssetDepreciation):
        raise TypeError("confirmed_depreciation must be ConfirmedFixedAssetDepreciation")

    posting_instruction = _posting.create_posting_instruction(
        confirmed_depreciation.confirmed_proposal
    )
    posting_date = (
        confirmed_depreciation.snapshot.accounting_resolution.recognition_fact.recognition_date
    )
    return FixedAssetDepreciationPostingInstruction(
        confirmed_depreciation,
        posting_instruction,
        posting_date,
        _token=_FACTORY_TOKEN,
    )


def execute_fixed_asset_depreciation_posting(instruction):
    """Execute one dated depreciation instruction through the canonical core."""
    if not isinstance(instruction, FixedAssetDepreciationPostingInstruction):
        raise TypeError("instruction must be FixedAssetDepreciationPostingInstruction")

    payload = {
        "date": instruction.posting_date,
        "description": instruction.posting_instruction.description,
        "lines": [
            {
                "account_id": line.account_id,
                "account_code": line.account_code,
                "debit": line.debit,
                "credit": line.credit,
            }
            for line in instruction.posting_instruction.lines
        ],
    }
    return _core.post_entry(payload)
