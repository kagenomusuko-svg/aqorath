"""Pure intrinsic compatibility between one report definition and request."""

from .report_definition import ReportDefinition
from .report_request import ReportRequest


def validate_report_request_against_definition(definition, request):
    """Return the exact request when its definition identity and format match."""
    if not isinstance(definition, ReportDefinition):
        raise TypeError("definition must be ReportDefinition")
    if definition.id is None:
        raise ValueError("definition must have persisted identity")
    if not isinstance(request, ReportRequest):
        raise TypeError("request must be ReportRequest")
    if request.report_definition_id != definition.id:
        raise ValueError("request does not reference supplied definition")
    if request.format not in definition.supported_formats:
        raise ValueError("requested format is not supported by definition")
    return request
