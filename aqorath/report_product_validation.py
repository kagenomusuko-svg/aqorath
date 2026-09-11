"""AQR-013 validation of concrete requests against governed report products."""

from .report_request_compatibility import validate_report_request_against_definition


def validate_governed_report_request(definition, request):
    """Fail closed when a concrete request exceeds its governed definition."""
    validate_report_request_against_definition(definition, request)

    if definition.key is None or definition.report_type is None:
        raise ValueError("report definition is not product-governed")
    if definition.period_mode is None or definition.version is None:
        raise ValueError("report definition lacks period/version governance")

    allowed = set(definition.allowed_parameters)
    for key, _value in request.filters:
        if key not in allowed:
            raise ValueError(f"unsupported report parameter: {key!r}")

    unsupported_dimensions = [
        value for value in request.dimensions_to_group
        if value not in definition.allowed_dimensions
    ]
    if unsupported_dimensions:
        raise ValueError(
            f"unsupported report dimensions: {unsupported_dimensions!r}"
        )

    if definition.period_mode == "range":
        if request.as_of_date is not None:
            raise ValueError("range report must not set as_of_date")
    elif definition.period_mode == "as_of":
        if request.as_of_date is None:
            raise ValueError("as-of report requires as_of_date")
        if not (
            request.from_date == request.to_date == request.as_of_date
        ):
            raise ValueError("as-of report dates must equal as_of_date")
    else:
        raise ValueError(f"unsupported report period mode: {definition.period_mode!r}")

    return request
