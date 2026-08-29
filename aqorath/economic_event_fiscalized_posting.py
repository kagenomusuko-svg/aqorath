"""Prepare one fiscalized posting instruction from confirmed EconomicEvent truth."""

from . import fiscalized_posting as _posting


def create_fiscalized_economic_event_posting_instruction(
    confirmed_proposal,
    zero_fiscal_line_policy,
):
    """Delegate exact confirmed truth and zero-line policy to posting authority."""
    return _posting.create_fiscalized_posting_instruction(
        confirmed_proposal,
        zero_fiscal_line_policy,
    )
