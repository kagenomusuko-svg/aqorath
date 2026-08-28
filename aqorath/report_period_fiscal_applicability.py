"""Pure fiscal applicability across one explicit report period."""

from datetime import timedelta

from .entity import FiscalProfile
from .report_definition import ReportDefinition
from .report_fiscal_applicability import (
    is_report_definition_fiscally_applicable_on,
)
from .report_request import ReportRequest


def is_report_request_period_fiscally_applicable(
    definition,
    request,
    fiscal_profiles,
):
    """Return whether explicit fiscal history supports the whole request period."""
    if not isinstance(definition, ReportDefinition):
        raise TypeError("definition must be ReportDefinition")
    if not isinstance(request, ReportRequest):
        raise TypeError("request must be ReportRequest")
    if type(fiscal_profiles) is not tuple:
        raise TypeError("fiscal_profiles must be tuple")
    for profile in fiscal_profiles:
        if not isinstance(profile, FiscalProfile):
            raise TypeError("fiscal_profiles items must be FiscalProfile")

    if not definition.required_fiscal_features:
        return True

    relevant = []
    for profile in fiscal_profiles:
        if profile.entity_id != request.entity_id:
            continue
        if profile.effective_from > request.to_date:
            continue
        if (
            profile.effective_to is not None
            and profile.effective_to < request.from_date
        ):
            continue
        relevant.append(profile)

    if not relevant:
        return False

    relevant.sort(key=lambda profile: profile.effective_from)
    segments = []
    for profile in relevant:
        segment_start = max(profile.effective_from, request.from_date)
        segment_end = min(
            profile.effective_to
            if profile.effective_to is not None
            else request.to_date,
            request.to_date,
        )
        segments.append((segment_start, segment_end, profile))

    for index in range(1, len(segments)):
        previous_end = segments[index - 1][1]
        current_start = segments[index][0]
        if current_start <= previous_end:
            raise ValueError("fiscal profile history is ambiguous")

    if segments[0][0] > request.from_date:
        return False

    covered_through = None
    for segment_start, segment_end, profile in segments:
        if covered_through is not None:
            if segment_start > covered_through + timedelta(days=1):
                return False

        if not is_report_definition_fiscally_applicable_on(
            definition,
            profile,
            segment_start,
        ):
            return False

        covered_through = segment_end

    return covered_through is not None and covered_through >= request.to_date
