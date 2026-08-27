"""Configured confirmation boundary for canonical fixed-asset acquisitions."""

from dataclasses import dataclass

from . import account_bindings as _account_bindings
from . import account_resolution as _account_resolution
from . import confirmation as _confirmation
from .fixed_asset_acquisition import FixedAssetAcquisitionAccountingResolution


_POSITIVE_OUTCOME = "accounting_proposal"
_ZERO_OUTCOME = "zero_cost_no_entry"
_SNAPSHOT_FACTORY_TOKEN = object()
_CONFIRMED_FACTORY_TOKEN = object()


def _require_accounting_resolution(value):
    if not isinstance(value, FixedAssetAcquisitionAccountingResolution):
        raise TypeError(
            "accounting_resolution must be FixedAssetAcquisitionAccountingResolution"
        )


@dataclass(frozen=True, init=False)
class FixedAssetAcquisitionConfirmationSnapshot:
    """Prepared acquisition truth plus its configured generic snapshot."""

    accounting_resolution: FixedAssetAcquisitionAccountingResolution
    confirmation_snapshot: object

    def __init__(
        self,
        *,
        accounting_resolution,
        confirmation_snapshot,
        _factory_token=None,
    ):
        if _factory_token is not _SNAPSHOT_FACTORY_TOKEN:
            raise TypeError(
                "FixedAssetAcquisitionConfirmationSnapshot is factory-only"
            )
        _require_accounting_resolution(accounting_resolution)

        if accounting_resolution.outcome == _ZERO_OUTCOME:
            if accounting_resolution.proposal is not None:
                raise ValueError("zero-cost acquisition must not contain a proposal")
            if confirmation_snapshot is not None:
                raise ValueError(
                    "zero-cost acquisition must not contain confirmation truth"
                )
        elif accounting_resolution.outcome == _POSITIVE_OUTCOME:
            if accounting_resolution.proposal is None:
                raise ValueError("positive acquisition requires a proposal")
            if confirmation_snapshot is None:
                raise ValueError(
                    "positive acquisition requires configured confirmation truth"
                )
        else:
            raise ValueError("unknown acquisition accounting outcome")

        object.__setattr__(self, "accounting_resolution", accounting_resolution)
        object.__setattr__(self, "confirmation_snapshot", confirmation_snapshot)


@dataclass(frozen=True, init=False)
class ConfirmedFixedAssetAcquisition:
    """Explicit confirmation of one prepared positive acquisition."""

    snapshot: FixedAssetAcquisitionConfirmationSnapshot
    confirmed_proposal: object

    def __init__(self, *, snapshot, confirmed_proposal, _factory_token=None):
        if _factory_token is not _CONFIRMED_FACTORY_TOKEN:
            raise TypeError("ConfirmedFixedAssetAcquisition is factory-only")
        if not isinstance(snapshot, FixedAssetAcquisitionConfirmationSnapshot):
            raise TypeError(
                "snapshot must be FixedAssetAcquisitionConfirmationSnapshot"
            )
        if snapshot.accounting_resolution.outcome != _POSITIVE_OUTCOME:
            raise ValueError("only positive acquisition truth can be confirmed")
        if snapshot.confirmation_snapshot is None:
            raise ValueError("positive acquisition requires prepared confirmation truth")
        if confirmed_proposal is None:
            raise ValueError("confirmed_proposal is required")

        object.__setattr__(self, "snapshot", snapshot)
        object.__setattr__(self, "confirmed_proposal", confirmed_proposal)


def prepare_fixed_asset_acquisition_confirmation(session, accounting_resolution):
    """Resolve configured accounts and freeze one acquisition for confirmation."""
    _require_accounting_resolution(accounting_resolution)

    if accounting_resolution.outcome == _ZERO_OUTCOME:
        return FixedAssetAcquisitionConfirmationSnapshot(
            accounting_resolution=accounting_resolution,
            confirmation_snapshot=None,
            _factory_token=_SNAPSHOT_FACTORY_TOKEN,
        )
    if accounting_resolution.outcome != _POSITIVE_OUTCOME:
        raise ValueError("unknown acquisition accounting outcome")

    proposal = accounting_resolution.proposal
    if proposal is None:
        raise ValueError("positive acquisition requires a proposal")
    roles = tuple(line.account_role for line in proposal.lines)
    bindings = _account_bindings.get_account_bindings(session, roles)
    resolved = _account_resolution.resolve_proposal_accounts(
        session,
        proposal,
        bindings,
    )
    generic_snapshot = _confirmation.create_confirmation_snapshot(resolved)
    return FixedAssetAcquisitionConfirmationSnapshot(
        accounting_resolution=accounting_resolution,
        confirmation_snapshot=generic_snapshot,
        _factory_token=_SNAPSHOT_FACTORY_TOKEN,
    )


def confirm_fixed_asset_acquisition(snapshot):
    """Confirm exactly one previously prepared positive acquisition."""
    if not isinstance(snapshot, FixedAssetAcquisitionConfirmationSnapshot):
        raise TypeError(
            "snapshot must be FixedAssetAcquisitionConfirmationSnapshot"
        )
    if snapshot.accounting_resolution.outcome != _POSITIVE_OUTCOME:
        raise ValueError("zero-cost acquisition has no accounting entry to confirm")
    if snapshot.confirmation_snapshot is None:
        raise ValueError("positive acquisition requires prepared confirmation truth")

    confirmed = _confirmation.confirm_snapshot(snapshot.confirmation_snapshot)
    return ConfirmedFixedAssetAcquisition(
        snapshot=snapshot,
        confirmed_proposal=confirmed,
        _factory_token=_CONFIRMED_FACTORY_TOKEN,
    )


__all__ = [
    "FixedAssetAcquisitionConfirmationSnapshot",
    "ConfirmedFixedAssetAcquisition",
    "prepare_fixed_asset_acquisition_confirmation",
    "confirm_fixed_asset_acquisition",
]
