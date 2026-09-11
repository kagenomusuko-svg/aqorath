"""AQR-013 validation of concrete requests against governed report products."""

from . import report_product_catalog as _catalog
from .report_request_compatibility import validate_report_request_against_definition


def validate_governed_report_request(definition, request):
    """Fail closed when a concrete request exceeds its 1:1 product governance."""
    validate_report_request_against_definition(definition, request)
    governance = _catalog.get_report_governance(definition)

    allowed = set(governance.allowed_parameters)
    for key, _value in request.filters:
        if key not in allowed:
            raise ValueError(f"unsupported report parameter: {key!r}")

    unsupported_dimensions = [
        value
        for value in request.dimensions_to_group
        if value not in governance.allowed_dimensions
    ]
    if unsupported_dimensions:
        raise ValueError(
            f"unsupported report dimensions: {unsupported_dimensions!r}"
        )

    if governance.period_mode == "range":
        if request.as_of_date is not None:
            raise ValueError("range report must not set as_of_date")
    elif governance.period_mode == "as_of":
        if request.as_of_date is None:
            raise ValueError("as-of report requires as_of_date")
        if not request.from_date == request.to_date == request.as_of_date:
            raise ValueError("as-of report dates must equal as_of_date")
    else:
        raise ValueError(f"unsupported report period mode: {governance.period_mode!r}")

    return request
