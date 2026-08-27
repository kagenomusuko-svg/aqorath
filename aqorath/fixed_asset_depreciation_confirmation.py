"""Configured confirmation boundary for dated fixed-asset depreciation truth."""

from dataclasses import dataclass

from . import account_bindings as _account_bindings
from . import account_resolution as _account_resolution
from . import confirmation as _confirmation
from .fixed_asset_depreciation_accounting import (
    FixedAssetDepreciationAccountingResolution,
)


_SNAPSHOT_FACTORY_TOKEN = object()
_CONFIRMED_FACTORY_TOKEN = object()
_POSITIVE_OUTCOME = "accounting_proposal"
_ZERO_OUTCOME = "zero_amount_no_entry"


def _require_accounting_resolution(value):
    if not isinstance(value, FixedAssetDepreciationAccountingResolution):
        raise TypeError(
            "accounting_resolution must be FixedAssetDepreciationAccountingResolution"
        )


def _validate_positive_snapshot(accounting_resolution, confirmation_snapshot):
    if accounting_resolution.outcome != _POSITIVE_OUTCOME:
        raise ValueError("positive confirmation snapshot requires accounting_proposal")
    proposal = accounting_resolution.proposal
    if proposal is None:
        raise ValueError("positive accounting resolution requires a proposal")
    if not isinstance(confirmation_snapshot, _confirmation.ConfirmationSnapshot):
        raise TypeError("positive depreciation requires ConfirmationSnapshot")
    if confirmation_snapshot.explanation != accounting_resolution.explanation:
        raise ValueError("confirmation explanation must preserve accounting truth exactly")
    if len(confirmation_snapshot.lines) != len(proposal.lines):
        raise ValueError("confirmation lines must match accounting proposal cardinality")

    for source_line, confirmed_line in zip(proposal.lines, confirmation_snapshot.lines):
        if confirmed_line.account_role != source_line.account_role:
            raise ValueError("confirmation account role does not match accounting truth")
        if confirmed_line.side != source_line.side:
            raise ValueError("confirmation side does not match accounting truth")
        if confirmed_line.amount.as_tuple() != source_line.amount.as_tuple():
            raise ValueError("confirmation amount must preserve exact Decimal scale")
        if confirmed_line.account_id is None:
            raise ValueError("confirmation line requires concrete account identity")
        if not isinstance(confirmed_line.account_code, str) or not confirmed_line.account_code:
            raise ValueError("confirmation line requires concrete account code")


@dataclass(frozen=True, init=False)
class FixedAssetDepreciationConfirmationSnapshot:
    """Prepared fixed-asset depreciation truth with dated provenance retained."""

    accounting_resolution: FixedAssetDepreciationAccountingResolution
    confirmation_snapshot: object

    def __init__(
        self,
        accounting_resolution,
        confirmation_snapshot,
        *,
        _factory_token=None,
    ):
        if _factory_token is not _SNAPSHOT_FACTORY_TOKEN:
            raise TypeError(
                "FixedAssetDepreciationConfirmationSnapshot must be created by its preparation factory"
            )
        object.__setattr__(self, "accounting_resolution", accounting_resolution)
        object.__setattr__(self, "confirmation_snapshot", confirmation_snapshot)
        self.__post_init__()

    def __post_init__(self):
        _require_accounting_resolution(self.accounting_resolution)
        if self.accounting_resolution.outcome == _ZERO_OUTCOME:
            if self.accounting_resolution.proposal is not None:
                raise ValueError("zero_amount_no_entry must not contain a proposal")
            if self.confirmation_snapshot is not None:
                raise ValueError("zero_amount_no_entry must not contain a confirmation snapshot")
            return
        _validate_positive_snapshot(
            self.accounting_resolution,
            self.confirmation_snapshot,
        )


@dataclass(frozen=True, init=False)
class ConfirmedFixedAssetDepreciation:
    """Explicit confirmation of one prepared positive depreciation entry."""

    snapshot: FixedAssetDepreciationConfirmationSnapshot
    confirmed_proposal: _confirmation.ConfirmedProposal

    def __init__(self, snapshot, confirmed_proposal, *, _factory_token=None):
        if _factory_token is not _CONFIRMED_FACTORY_TOKEN:
            raise TypeError(
                "ConfirmedFixedAssetDepreciation must be created by its confirmation factory"
            )
        object.__setattr__(self, "snapshot", snapshot)
        object.__setattr__(self, "confirmed_proposal", confirmed_proposal)
        self.__post_init__()

    def __post_init__(self):
        if not isinstance(self.snapshot, FixedAssetDepreciationConfirmationSnapshot):
            raise TypeError("snapshot must be FixedAssetDepreciationConfirmationSnapshot")
        if self.snapshot.accounting_resolution.outcome != _POSITIVE_OUTCOME:
            raise ValueError("only accounting_proposal depreciation can be confirmed")
        if self.snapshot.confirmation_snapshot is None:
            raise ValueError("confirmed depreciation requires a prepared confirmation snapshot")
        if not isinstance(self.confirmed_proposal, _confirmation.ConfirmedProposal):
            raise TypeError("confirmed_proposal must be ConfirmedProposal")
        if self.confirmed_proposal.snapshot is not self.snapshot.confirmation_snapshot:
            raise ValueError("confirmed proposal must preserve the exact prepared snapshot")


def prepare_fixed_asset_depreciation_confirmation(session, accounting_resolution):
    """Prepare configured concrete-account confirmation from one Phase 6J result."""
    _require_accounting_resolution(accounting_resolution)

    if accounting_resolution.outcome == _ZERO_OUTCOME:
        if accounting_resolution.proposal is not None:
            raise ValueError("zero_amount_no_entry must not contain a proposal")
        return FixedAssetDepreciationConfirmationSnapshot(
            accounting_resolution=accounting_resolution,
            confirmation_snapshot=None,
            _factory_token=_SNAPSHOT_FACTORY_TOKEN,
        )

    if accounting_resolution.outcome != _POSITIVE_OUTCOME:
        raise ValueError("unsupported depreciation accounting outcome")
    proposal = accounting_resolution.proposal
    if proposal is None:
        raise ValueError("accounting_proposal outcome requires a proposal")

    roles = tuple(line.account_role for line in proposal.lines)
    bindings = _account_bindings.get_account_bindings(session, roles)
    resolved = _account_resolution.resolve_proposal_accounts(
        session,
        proposal,
        bindings,
    )
    confirmation_snapshot = _confirmation.create_confirmation_snapshot(resolved)
    return FixedAssetDepreciationConfirmationSnapshot(
        accounting_resolution=accounting_resolution,
        confirmation_snapshot=confirmation_snapshot,
        _factory_token=_SNAPSHOT_FACTORY_TOKEN,
    )


def confirm_fixed_asset_depreciation(snapshot):
    """Confirm one prepared positive depreciation entry without posting it."""
    if not isinstance(snapshot, FixedAssetDepreciationConfirmationSnapshot):
        raise TypeError("snapshot must be FixedAssetDepreciationConfirmationSnapshot")
    if snapshot.accounting_resolution.outcome == _ZERO_OUTCOME:
        raise ValueError("zero_amount_no_entry has no entry to confirm")
    if snapshot.confirmation_snapshot is None:
        raise ValueError("prepared depreciation has no entry to confirm")

    confirmed_proposal = _confirmation.confirm_snapshot(snapshot.confirmation_snapshot)
    return ConfirmedFixedAssetDepreciation(
        snapshot=snapshot,
        confirmed_proposal=confirmed_proposal,
        _factory_token=_CONFIRMED_FACTORY_TOKEN,
    )


__all__ = [
    "FixedAssetDepreciationConfirmationSnapshot",
    "ConfirmedFixedAssetDepreciation",
    "prepare_fixed_asset_depreciation_confirmation",
    "confirm_fixed_asset_depreciation",
]
