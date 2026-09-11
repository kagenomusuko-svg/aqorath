"""AQR-013 execution of owner-scoped CustomReportPackage selections.

Custom packages only choose/order already governed ReportDefinition values. They do
not carry SQL, accounting formulae, tax policy or renderer code.
"""

from datetime import date

from .custom_report_package import CustomReportPackage
from . import report_product_catalog as _catalog
from .report_product_runtime import GeneratedReportPackage, generate_report
from .report_request import ReportRequest


def _require_date(value, field_name):
    if type(value) is not date:
        raise TypeError(f"{field_name} must be date")


def build_custom_package_requests(package, entity_id, from_date, to_date, format):
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

    requests = []
    for selected in package.included_reports:
        canonical = _catalog.get_report_definition(selected.id)
        if canonical != selected:
            raise ValueError("custom package may contain only canonical governed definitions")
        governance = _catalog.get_report_governance(canonical)
        if format not in canonical.supported_formats:
            raise ValueError(
                f"format {format!r} is not supported by custom component {governance.key!r}"
            )
        if governance.period_mode == "range":
            request = ReportRequest(
                id=None,
                report_definition_id=canonical.id,
                entity_id=entity_id,
                from_date=from_date,
                to_date=to_date,
                as_of_date=None,
                filters=(),
                dimensions_to_group=(),
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
                filters=(),
                dimensions_to_group=(),
                format=format,
            )
        else:
            raise ValueError(f"unsupported governed period mode: {governance.period_mode!r}")
        requests.append(request)
    return tuple(requests)


def generate_custom_report_package(package, entity_id, from_date, to_date, format="json"):
    requests = build_custom_package_requests(package, entity_id, from_date, to_date, format)
    reports = tuple(generate_report(request) for request in requests)
    return GeneratedReportPackage(package, requests, reports)
