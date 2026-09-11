"""Render AQR-013 generated products without changing their accounting truth."""

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import json

from openpyxl import Workbook
from openpyxl.styles import Font

from . import reporting_xlsx as _xlsx
from .report_product_runtime import GeneratedReport, GeneratedReportPackage


@dataclass(frozen=True)
class RenderedReport:
    format: str
    media_type: str
    payload: str | bytes


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported report serialization value: {type(value).__name__}")


def _render_json(value):
    return json.dumps(
        _json_value(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _title(worksheet, title, metadata):
    worksheet["A1"] = title
    worksheet["A1"].font = Font(bold=True, size=14)
    row = 2
    for label, value in metadata:
        worksheet.cell(row=row, column=1, value=label).font = Font(bold=True)
        worksheet.cell(row=row, column=2, value=value)
        row += 1
    return row + 1


def _headers(worksheet, row, labels):
    for col, label in enumerate(labels, start=1):
        worksheet.cell(row=row, column=col, value=label).font = Font(bold=True)
    return row + 1


def _write_trial_balance(worksheet, report):
    view = report.content
    row = _title(
        worksheet,
        "Balanza por período",
        (("Desde", view.from_date.isoformat()), ("Hasta", view.to_date.isoformat())),
    )
    row = _headers(
        worksheet,
        row,
        ("Código", "Cuenta", "Naturaleza", "Saldo inicial", "Debe", "Haber", "Saldo final"),
    )
    for line in view.lines:
        values = (
            line.account_code,
            line.account_name,
            line.nature,
            str(line.opening_balance),
            str(line.debit),
            str(line.credit),
            str(line.closing_balance),
        )
        for col, value in enumerate(values, start=1):
            worksheet.cell(row=row, column=col, value=value)
        row += 1
    row += 1
    worksheet.cell(row=row, column=4, value="Totales").font = Font(bold=True)
    worksheet.cell(row=row, column=5, value=str(view.total_debit)).font = Font(bold=True)
    worksheet.cell(row=row, column=6, value=str(view.total_credit)).font = Font(bold=True)


def _write_income_statement(worksheet, report):
    view = report.content
    row = _title(
        worksheet,
        "Estado de resultados por período",
        (("Desde", report.request.from_date.isoformat()), ("Hasta", report.request.to_date.isoformat())),
    )
    row = _headers(worksheet, row, ("Tipo", "Código", "Cuenta", "Importe"))
    for section_label, section in (
        ("Ingreso", view.income),
        ("Costo", view.costs),
        ("Gasto", view.expenses),
    ):
        for line in section.lines:
            amount = -line.ledger_balance if section_label == "Ingreso" else line.ledger_balance
            for col, value in enumerate(
                (section_label, line.account_code, line.account_name, str(amount)), start=1
            ):
                worksheet.cell(row=row, column=col, value=value)
            row += 1
        worksheet.cell(row=row, column=3, value=f"Total {section_label.lower()}").font = Font(bold=True)
        worksheet.cell(row=row, column=4, value=str(section.total)).font = Font(bold=True)
        row += 1
    worksheet.cell(row=row, column=3, value="Resultado").font = Font(bold=True)
    worksheet.cell(row=row, column=4, value=str(view.result)).font = Font(bold=True)


def _write_balance_sheet(worksheet, report):
    view = report.content
    row = _title(
        worksheet,
        "Estado de situación financiera",
        (("Al", report.request.as_of_date.isoformat()),),
    )
    row = _headers(worksheet, row, ("Tipo", "Código", "Cuenta", "Importe"))
    for section_label, section in (
        ("Activo", view.assets),
        ("Pasivo", view.liabilities),
        ("Patrimonio", view.recorded_equity),
    ):
        for line in section.lines:
            for col, value in enumerate(
                (section_label, line.account_code, line.account_name, str(line.amount)), start=1
            ):
                worksheet.cell(row=row, column=col, value=value)
            row += 1
        worksheet.cell(row=row, column=3, value=f"Total {section_label.lower()}").font = Font(bold=True)
        worksheet.cell(row=row, column=4, value=str(section.total)).font = Font(bold=True)
        row += 1
    for label, value in (
        ("Resultado del período", view.current_result),
        ("Patrimonio total", view.total_equity),
        ("Pasivo + patrimonio", view.liabilities_and_equity),
        ("Diferencia de balance", view.balance_difference),
    ):
        worksheet.cell(row=row, column=3, value=label).font = Font(bold=True)
        worksheet.cell(row=row, column=4, value=str(value)).font = Font(bold=True)
        row += 1


_WRITERS = {
    "financial.trial_balance.period": _write_trial_balance,
    "financial.income_statement.period": _write_income_statement,
    "financial.balance_sheet.as_of": _write_balance_sheet,
}


def _render_reports_xlsx(reports):
    workbook = Workbook()
    first = True
    names = {
        "financial.trial_balance.period": "Balanza",
        "financial.income_statement.period": "Resultados",
        "financial.balance_sheet.as_of": "Situación financiera",
    }
    for report in reports:
        key = report.definition.key
        try:
            writer = _WRITERS[key]
        except KeyError as exc:
            workbook.close()
            raise ValueError(f"xlsx rendering is not supported for report {key!r}") from exc
        worksheet = workbook.active if first else workbook.create_sheet()
        first = False
        worksheet.title = names[key]
        writer(worksheet, report)
    data = _xlsx._save_workbook_in_memory(workbook)
    workbook.close()
    return data


def render_generated_report(report):
    if not isinstance(report, GeneratedReport):
        raise TypeError("report must be GeneratedReport")
    if report.request.format not in report.definition.supported_formats:
        raise ValueError("requested format is not supported by definition")
    if report.request.format == "json":
        return RenderedReport("json", "application/json", _render_json(report))
    if report.request.format == "xlsx":
        return RenderedReport(
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            _render_reports_xlsx((report,)),
        )
    raise ValueError(f"unsupported report format: {report.request.format!r}")


def render_generated_package(package):
    if not isinstance(package, GeneratedReportPackage):
        raise TypeError("package must be GeneratedReportPackage")
    formats = {report.request.format for report in package.reports}
    if len(formats) != 1:
        raise ValueError("package reports must use one explicit format")
    format = next(iter(formats))
    if format == "json":
        return RenderedReport("json", "application/json", _render_json(package))
    if format == "xlsx":
        return RenderedReport(
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            _render_reports_xlsx(package.reports),
        )
    raise ValueError(f"unsupported package format: {format!r}")
