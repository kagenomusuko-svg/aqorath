"""AQR-013 execution of owner-scoped CustomReportPackage selections.

Custom packages only choose/order already governed ReportDefinition values. They do
not carry SQL, accounting formulae, tax policy or renderer code.
"""

from datetime import date

from .custom_report_package import CustomReportPackage
from .report_preset import PersistedReportPreset
from . import report_product_catalog as _catalog
from .report_product_runtime import GeneratedReportPackage, generate_report
from .report_request import ReportRequest

_EXECUTION_ONLY_PARAMETERS = {"from_date", "to_date", "as_of_date", "format"}


def _require_date(value, field_name):
    if type(value) is not date:
        raise TypeError(f"{field_name} must be date")


def _normalized_item_parameters(package, item_parameters):
    if item_parameters is None:
        return tuple(() for _ in package.included_reports)
    if type(item_parameters) is not tuple or len(item_parameters) != len(package.included_reports):
        raise ValueError("item_parameters must align exactly with included_reports")
    normalized = []
    for selected, parameters in zip(package.included_reports, item_parameters):
        if type(parameters) is not tuple:
            raise TypeError("each item_parameters entry must be tuple")
        governance = _catalog.get_report_governance(selected)
        allowed = set(governance.allowed_parameters) - _EXECUTION_ONLY_PARAMETERS
        seen = set()
        values = []
        for pair in parameters:
            if type(pair) is not tuple or len(pair) != 2:
                raise TypeError("preset parameter must be a (key, value) tuple")
            key, value = pair
            if type(key) is not str or not key or key.strip() != key:
                raise ValueError("preset parameter key must be nonblank exact text")
            if key in seen:
                raise ValueError("preset parameter keys must be unique per report")
            seen.add(key)
            if key not in allowed:
                raise ValueError(
                    f"unsupported persisted parameter {key!r} for {governance.key!r}"
                )
            if type(value) is not str or not value or value.strip() != value:
                raise ValueError("preset parameter value must be nonblank exact text")
            values.append((key, value))
        if governance.key == "analytical.activity.period" and "dimension_key" not in seen:
            raise ValueError("analytical preset component requires dimension_key")
        normalized.append(tuple(values))
    return tuple(normalized)


def build_custom_package_requests(
    package,
    entity_id,
    from_date,
    to_date,
    format,
    item_parameters=None,
):
    if not isinstance(package, CustomReportPackage):
        raise TypeError("package must be CustomReportPackage")
    if type(entity_id) is not int or entity_id <= 0:
        raise ValueError("entity_id must be positive int")
    if package.owner_entity_id != entity_id:
        raise ValueError("custom package does not belong to requested Entity")
    _require_date(from_date, "from_date")
    _require_date(to_date, "to_date")
    if to_date < from_date:
        raise ValueError("to_date cannot precede from_date")
    if type(format) is not str or not format or format.strip() != format:
        raise ValueError("format must be nonblank str without surrounding whitespace")

    parameters_by_position = _normalized_item_parameters(package, item_parameters)
    requests = []
    for selected, parameters in zip(package.included_reports, parameters_by_position):
        canonical = _catalog.get_report_definition(selected.id)
        if canonical != selected:
            raise ValueError("custom package may contain only canonical governed definitions")
        governance = _catalog.get_report_governance(canonical)
        if format not in canonical.supported_formats:
            raise ValueError(
                f"format {format!r} is not supported by custom component {governance.key!r}"
            )
        dimensions = (
            ("analytical_value",)
            if governance.key == "analytical.activity.period"
            else ()
        )
        if governance.period_mode == "range":
            request = ReportRequest(
                id=None,
                report_definition_id=canonical.id,
                entity_id=entity_id,
                from_date=from_date,
                to_date=to_date,
                as_of_date=None,
                filters=parameters,
                dimensions_to_group=dimensions,
                format=format,
            )
        elif governance.period_mode == "as_of":
            request = ReportRequest(
                id=None,
                report_definition_id=canonical.id,
                entity_id=entity_id,
                from_date=to_date,
                to_date=to_date,
                as_of_date=to_date,
                filters=parameters,
                dimensions_to_group=dimensions,
                format=format,
            )
        else:
            raise ValueError(f"unsupported governed period mode: {governance.period_mode!r}")
        requests.append(request)
    return tuple(requests)


def generate_custom_report_package(
    package,
    entity_id,
    from_date,
    to_date,
    format="json",
    item_parameters=None,
):
    requests = build_custom_package_requests(
        package,
        entity_id,
        from_date,
        to_date,
        format,
        item_parameters=item_parameters,
    )
    reports = tuple(generate_report(request) for request in requests)
    return GeneratedReportPackage(package, requests, reports)


def generate_persisted_report_preset(preset, entity_id, from_date, to_date):
    if not isinstance(preset, PersistedReportPreset):
        raise TypeError("preset must be PersistedReportPreset")
    return generate_custom_report_package(
        preset.package,
        entity_id,
        from_date,
        to_date,
        preset.format,
        item_parameters=preset.item_parameters,
    )
