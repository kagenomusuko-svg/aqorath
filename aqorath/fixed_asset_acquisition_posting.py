"""Dated posting boundary for confirmed canonical fixed-asset acquisitions."""

from dataclasses import dataclass
from datetime import date

from . import core as _core
from . import posting as _posting
from .fixed_asset_acquisition_confirmation import ConfirmedFixedAssetAcquisition


_INSTRUCTION_FACTORY_TOKEN = object()


@dataclass(frozen=True, init=False)
class FixedAssetAcquisitionPostingInstruction:
    """One confirmed acquisition paired with its authoritative posting date."""

    confirmed_acquisition: ConfirmedFixedAssetAcquisition
    posting_instruction: object
    posting_date: date

    def __init__(
        self,
        *,
        confirmed_acquisition,
        posting_instruction,
        posting_date,
        _factory_token=None,
    ):
        if _factory_token is not _INSTRUCTION_FACTORY_TOKEN:
            raise TypeError("FixedAssetAcquisitionPostingInstruction is factory-only")
        if not isinstance(confirmed_acquisition, ConfirmedFixedAssetAcquisition):
            raise TypeError(
                "confirmed_acquisition must be ConfirmedFixedAssetAcquisition"
            )
        if posting_instruction is None:
            raise ValueError("posting_instruction is required")
        if type(posting_date) is not date:
            raise TypeError("posting_date must be a date")

        expected_date = (
            confirmed_acquisition.snapshot.accounting_resolution.acquisition_fact.acquisition_date
        )
        if posting_date != expected_date:
            raise ValueError("posting_date must match confirmed acquisition date")

        object.__setattr__(self, "confirmed_acquisition", confirmed_acquisition)
        object.__setattr__(self, "posting_instruction", posting_instruction)
        object.__setattr__(self, "posting_date", posting_date)


def create_fixed_asset_acquisition_posting_instruction(confirmed_acquisition):
    """Create one dated instruction from explicit confirmed acquisition truth."""
    if not isinstance(confirmed_acquisition, ConfirmedFixedAssetAcquisition):
        raise TypeError(
            "confirmed_acquisition must be ConfirmedFixedAssetAcquisition"
        )

    generic_instruction = _posting.create_posting_instruction(
        confirmed_acquisition.confirmed_proposal
    )
    acquisition_date = (
        confirmed_acquisition.snapshot.accounting_resolution.acquisition_fact.acquisition_date
    )
    return FixedAssetAcquisitionPostingInstruction(
        confirmed_acquisition=confirmed_acquisition,
        posting_instruction=generic_instruction,
        posting_date=acquisition_date,
        _factory_token=_INSTRUCTION_FACTORY_TOKEN,
    )


def execute_fixed_asset_acquisition_posting(instruction):
    """Execute one acquisition instruction through the canonical core authority."""
    if not isinstance(instruction, FixedAssetAcquisitionPostingInstruction):
        raise TypeError(
            "instruction must be FixedAssetAcquisitionPostingInstruction"
        )

    generic_instruction = instruction.posting_instruction
    payload = {
        "date": instruction.posting_date,
        "description": generic_instruction.description,
        "lines": [
            {
                "account_id": line.account_id,
                "account_code": line.account_code,
                "debit": line.debit,
                "credit": line.credit,
            }
            for line in generic_instruction.lines
        ],
    }
    return _core.post_entry(payload)


__all__ = [
    "FixedAssetAcquisitionPostingInstruction",
    "create_fixed_asset_acquisition_posting_instruction",
    "execute_fixed_asset_acquisition_posting",
]
