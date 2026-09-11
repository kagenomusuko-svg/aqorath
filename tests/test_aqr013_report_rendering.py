from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook


def _generated(format="json"):
    from aqorath.period_reporting import PeriodTrialBalanceLine, PeriodTrialBalanceView
    from aqorath.report_product_catalog import TRIAL_BALANCE_PERIOD
    from aqorath.report_product_runtime import GeneratedReport
    from aqorath.report_request import ReportRequest

    request = ReportRequest(
        id=None,
        report_definition_id=TRIAL_BALANCE_PERIOD.id,
        entity_id=1,
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31),
        as_of_date=None,
        filters=(),
        dimensions_to_group=(),
        format=format,
    )
    content = PeriodTrialBalanceView(
        from_date=request.from_date,
        to_date=request.to_date,
        lines=(
            PeriodTrialBalanceLine(
                "1101",
                "Bancos",
                "DEBIT",
                Decimal("1000.00"),
                Decimal("200.00"),
                Decimal("50.00"),
                Decimal("1150.00"),
            ),
        ),
        total_debit=Decimal("250.00"),
        total_credit=Decimal("250.00"),
    )
    return GeneratedReport(
        TRIAL_BALANCE_PERIOD,
        request,
        content,
        ("JournalEntry", "JournalLine", "Account"),
    )


def test_json_render_is_deterministic_and_preserves_decimal_text():
    from aqorath.report_product_rendering import render_generated_report

    first = render_generated_report(_generated("json"))
    second = render_generated_report(_generated("json"))
    assert first == second
    assert first.media_type == "application/json"
    assert '"opening_balance":"1000.00"' in first.payload
    assert '"debit":"200.00"' in first.payload
    assert '"source_authorities":["JournalEntry","JournalLine","Account"]' in first.payload


def test_xlsx_render_uses_existing_in_memory_writer_and_exact_text():
    from aqorath.report_product_rendering import render_generated_report

    rendered = render_generated_report(_generated("xlsx"))
    assert rendered.media_type.endswith("spreadsheetml.sheet")
    workbook = load_workbook(BytesIO(rendered.payload), data_only=False)
    try:
        assert workbook.sheetnames == ["Balanza"]
        sheet = workbook["Balanza"]
        values = [cell.value for row in sheet.iter_rows() for cell in row]
        assert "1000.00" in values
        assert "200.00" in values
        assert "50.00" in values
        assert "1150.00" in values
    finally:
        workbook.close()


def test_renderer_has_no_silent_format_fallback():
    from dataclasses import replace
    import pytest
    from aqorath.report_product_rendering import render_generated_report

    report = _generated("json")
    broken_request = replace(report.request, format="pdf")
    broken_report = replace(report, request=broken_request)
    with pytest.raises(ValueError, match="not supported"):
        render_generated_report(broken_report)
