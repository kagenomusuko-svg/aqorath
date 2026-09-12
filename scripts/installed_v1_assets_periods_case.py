"""Installed-wheel technical acceptance for V1-08, V1-09 and V1-10."""

from decimal import Decimal
from pathlib import Path
import sqlite3

import _installed_v1_core_cases as core


ASSET_BINDINGS = {
    "fixed_asset_computer_equipment": "1202",
    "depreciation_expense": "5106",
    "accumulated_depreciation": "1205",
}


def _asset_onboarding():
    payload = core._onboarding_payload()
    payload["name"] = "Entidad activos V1-08 V1-09"
    payload["bindings"] = {**core.CORE_BINDINGS, **ASSET_BINDINGS}
    return payload


def _book_ok(book, expected):
    if (
        book.get("asset", {}).get("id") != expected["asset_id"]
        or book.get("asset_class") != "computer_equipment"
        or book.get("settlement_method") != "bank"
        or book.get("acquisition_entry_id") != expected["acquisition_entry_id"]
    ):
        raise AssertionError(f"V1-08/09: book-state identity/classification differs: {book}")
    for field, value in (
        ("acquisition_cost", "12000.00"),
        ("residual_value", "0.00"),
        ("accumulated_depreciation", "1000.00"),
        ("carrying_value", "11000.00"),
    ):
        if core._decimal(book.get(field), f"V1-08/09 {field}") != Decimal(value):
            raise AssertionError(f"V1-08/09: {field} differs: {book}")
    periods = book.get("recognized_periods", [])
    if len(periods) != 1:
        raise AssertionError(f"V1-09: recognized periods differ: {periods}")
    period = periods[0]
    if (
        period.get("period_number") != 1
        or period.get("entry_id") != expected["depreciation_entry_id"]
        or period.get("posting_date") != "2026-02-28"
        or period.get("recognition_source_ref")
        != f"AQR-015:V1-09:asset={expected['asset_id']}:period=1"
        or core._decimal(period.get("amount"), "V1-09 period amount")
        != Decimal("1000.00")
    ):
        raise AssertionError(f"V1-09: depreciation provenance differs: {period}")


def _professional_lines(value, label):
    return [
        (
            line.get("account_code"),
            line.get("side"),
            core._decimal(line.get("amount"), label),
        )
        for line in value.get("accounting", {}).get("lines", [])
    ]


def _asset_audit_ok(ledger, *, entry_id, asset_id, authority, period_number=None):
    audit = ledger.get("audit") or {}
    details = audit.get("details") or {}
    decision = details.get("decision") or {}
    if (
        audit.get("event_type") != "entry_posted"
        or details.get("entry_id") != entry_id
        or decision.get("specialized_authority") != authority
        or decision.get("fixed_asset_id") != asset_id
        or decision.get("consent") != "explicit_confirmation"
    ):
        raise AssertionError(
            f"V1-08/09: installed fixed-asset audit differs for {authority}: {audit}"
        )
    if authority == "fixed_asset_acquisition":
        if (
            decision.get("asset_class") != "computer_equipment"
            or decision.get("settlement_method") != "bank"
        ):
            raise AssertionError(f"V1-08: acquisition audit provenance differs: {audit}")
    else:
        expected_ref = f"AQR-015:V1-09:asset={asset_id}:period={period_number}"
        if (
            decision.get("period_number") != period_number
            or decision.get("recognition_source_ref") != expected_ref
        ):
            raise AssertionError(f"V1-09: depreciation audit provenance differs: {audit}")


def assert_v1_08_v1_09_assets(db_path: Path):
    if core._request_json("GET", "/api/onboarding").get("configured") is not False:
        raise AssertionError("V1-08/09: asset SQLite was not clean")
    configured = core._request_json("POST", "/api/onboarding", _asset_onboarding())
    if configured.get("bindings") != {**core.CORE_BINDINGS, **ASSET_BINDINGS}:
        raise AssertionError(f"V1-08/09: governed bindings differ: {configured}")

    options = core._request_json("GET", "/api/fixed-assets/options")
    classes = {item.get("key") for item in options.get("asset_classes", [])}
    dep_policy = options.get("depreciation", {})
    if "computer_equipment" not in classes or (
        dep_policy.get("method") != "straight_line"
        or core._decimal(dep_policy.get("quantizer"), "V1-09 quantizer")
        != Decimal("0.01")
        or dep_policy.get("rounding") != "ROUND_HALF_UP"
        or dep_policy.get("remainder") != "final_period"
    ):
        raise AssertionError(f"V1-08/09: governed class/policy differs: {options}")

    asset = core._request_json(
        "POST",
        "/api/fixed-assets",
        {
            "code": "EQ-COMP-001",
            "name": "Computadora",
            "acquisition_date": "2026-01-15",
            "in_service_date": "2026-02-01",
            "acquisition_cost": "12000.00",
            "residual_value": "0.00",
            "useful_life_months": 12,
        },
    )
    asset_id = asset.get("id")
    if (
        not asset_id
        or asset.get("code") != "EQ-COMP-001"
        or core._decimal(asset.get("acquisition_cost"), "V1-08 cost")
        != Decimal("12000.00")
    ):
        raise AssertionError(f"V1-08: asset registry differs: {asset}")
    listed = core._request_json("GET", "/api/fixed-assets")
    if (
        len(listed) != 1
        or listed[0].get("id") != asset_id
        or listed[0].get("acquisition_posted") is not False
    ):
        raise AssertionError(
            f"V1-08: asset did not persist independently of ledger: {listed}"
        )
    with sqlite3.connect(db_path) as conn:
        if conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0] != 0:
            raise AssertionError("V1-08: registering an asset created a JournalEntry")

    acq_payload = {
        "fixed_asset_id": asset_id,
        "asset_class": "computer_equipment",
        "settlement_method": "bank",
    }
    prepared = core._request_json(
        "POST", "/api/fixed-assets/acquisition/prepare", acq_payload
    )
    token = core._assert_common_preview(prepared, amount="12000.00")
    if (
        prepared["preview"].get("already_posted") is not False
        or "account_code" in str(prepared["preview"])
    ):
        raise AssertionError(f"V1-08: common acquisition preview differs: {prepared}")
    pro = core._request_json(
        "GET", f"/api/fixed-assets/decisions/{token}/professional-preview"
    )
    if _professional_lines(pro, "V1-08 preview") != [
        ("1202", "debit", Decimal("12000.00")),
        ("1101", "credit", Decimal("12000.00")),
    ]:
        raise AssertionError(f"V1-08: professional acquisition proposal differs: {pro}")
    posted = core._request_json(
        "POST", f"/api/fixed-assets/decisions/{token}/confirm"
    )
    acq_entry = posted.get("entry_id")
    if (
        posted.get("ok") is not True
        or not acq_entry
        or posted.get("fixed_asset_id") != asset_id
        or posted.get("already_posted") is not False
    ):
        raise AssertionError(f"V1-08: acquisition confirmation differs: {posted}")
    ledger = core._request_json("GET", f"/api/operations/{acq_entry}/professional")
    actual = [
        (
            line["account_code"],
            core._decimal(line["debit"], "V1-08 debit"),
            core._decimal(line["credit"], "V1-08 credit"),
        )
        for line in ledger.get("lines", [])
    ]
    if ledger.get("state") != "posted" or actual != [
        ("1202", Decimal("12000.00"), Decimal("0")),
        ("1101", Decimal("0"), Decimal("12000.00")),
    ]:
        raise AssertionError(f"V1-08: canonical acquisition posting differs: {ledger}")
    _asset_audit_ok(
        ledger,
        entry_id=acq_entry,
        asset_id=asset_id,
        authority="fixed_asset_acquisition",
    )

    retry = core._request_json(
        "POST", "/api/fixed-assets/acquisition/prepare", acq_payload
    )
    retry_token = core._assert_common_preview(retry, amount="12000.00")
    retry_pro = core._request_json(
        "GET", f"/api/fixed-assets/decisions/{retry_token}/professional-preview"
    )
    retried = core._request_json(
        "POST", f"/api/fixed-assets/decisions/{retry_token}/confirm"
    )
    if (
        retry["preview"].get("already_posted") is not True
        or retry_pro.get("persisted_entry_id") != acq_entry
        or retried.get("entry_id") != acq_entry
        or retried.get("already_posted") is not True
    ):
        raise AssertionError(
            f"V1-08: acquisition idempotence differs: {retry}, {retry_pro}, {retried}"
        )

    dep_payload = {
        "fixed_asset_id": asset_id,
        "period_number": 1,
        "recognition_date": "2026-02-28",
    }
    dep = core._request_json(
        "POST", "/api/fixed-assets/depreciation/prepare", dep_payload
    )
    dep_token = core._assert_common_preview(dep, amount="1000.00")
    if (
        dep["preview"].get("already_posted") is not False
        or "account_code" in str(dep["preview"])
    ):
        raise AssertionError(f"V1-09: common depreciation preview differs: {dep}")
    dep_pro = core._request_json(
        "GET", f"/api/fixed-assets/decisions/{dep_token}/professional-preview"
    )
    if _professional_lines(dep_pro, "V1-09 preview") != [
        ("5106", "debit", Decimal("1000.00")),
        ("1205", "credit", Decimal("1000.00")),
    ]:
        raise AssertionError(
            f"V1-09: professional depreciation proposal differs: {dep_pro}"
        )
    dep_posted = core._request_json(
        "POST", f"/api/fixed-assets/decisions/{dep_token}/confirm"
    )
    dep_entry = dep_posted.get("entry_id")
    if (
        dep_posted.get("ok") is not True
        or not dep_entry
        or dep_posted.get("period_number") != 1
        or dep_posted.get("already_posted") is not False
    ):
        raise AssertionError(
            f"V1-09: depreciation confirmation differs: {dep_posted}"
        )
    dep_ledger = core._request_json("GET", f"/api/operations/{dep_entry}/professional")
    dep_actual = [
        (
            line["account_code"],
            core._decimal(line["debit"], "V1-09 debit"),
            core._decimal(line["credit"], "V1-09 credit"),
        )
        for line in dep_ledger.get("lines", [])
    ]
    if dep_ledger.get("state") != "posted" or dep_actual != [
        ("5106", Decimal("1000.00"), Decimal("0")),
        ("1205", Decimal("0"), Decimal("1000.00")),
    ]:
        raise AssertionError(
            f"V1-09: canonical depreciation posting differs: {dep_ledger}"
        )
    _asset_audit_ok(
        dep_ledger,
        entry_id=dep_entry,
        asset_id=asset_id,
        authority="fixed_asset_depreciation",
        period_number=1,
    )

    dep_retry = core._request_json(
        "POST", "/api/fixed-assets/depreciation/prepare", dep_payload
    )
    dep_retry_token = core._assert_common_preview(dep_retry, amount=None)
    dep_retry_pro = core._request_json(
        "GET", f"/api/fixed-assets/decisions/{dep_retry_token}/professional-preview"
    )
    dep_retried = core._request_json(
        "POST", f"/api/fixed-assets/decisions/{dep_retry_token}/confirm"
    )
    if (
        dep_retry["preview"].get("already_posted") is not True
        or dep_retry_pro.get("persisted_entry_id") != dep_entry
        or dep_retried.get("entry_id") != dep_entry
        or dep_retried.get("already_posted") is not True
    ):
        raise AssertionError(
            f"V1-09: depreciation idempotence differs: "
            f"{dep_retry}, {dep_retry_pro}, {dep_retried}"
        )

    expected = {
        "asset_id": asset_id,
        "acquisition_entry_id": acq_entry,
        "depreciation_entry_id": dep_entry,
    }
    book = core._request_json("GET", f"/api/fixed-assets/{asset_id}/book-state")
    _book_ok(book, expected)
    listed = core._request_json("GET", "/api/fixed-assets")
    if (
        len(listed) != 1
        or listed[0].get("acquisition_entry_id") != acq_entry
        or core._decimal(
            listed[0].get("carrying_value"), "V1-09 list carrying"
        )
        != Decimal("11000.00")
    ):
        raise AssertionError(f"V1-08/09: asset list projection differs: {listed}")
    with sqlite3.connect(db_path) as conn:
        entries = conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0]
        assets = conn.execute("SELECT COUNT(*) FROM fixedasset").fetchone()[0]
        audits = conn.execute(
            "SELECT COUNT(*) FROM auditevent WHERE event_type='entry_posted'"
        ).fetchone()[0]
        acq_records = conn.execute(
            "SELECT COUNT(*) FROM fixedassetacquisitionpostingrecord"
        ).fetchone()[0]
        dep_records = conn.execute(
            "SELECT COUNT(*) FROM fixedassetdepreciationpostingrecord"
        ).fetchone()[0]
    if (entries, assets, audits, acq_records, dep_records) != (2, 1, 2, 1, 1):
        raise AssertionError(
            "V1-08/09: durable idempotence/audit/cardinality differs: "
            f"{entries, assets, audits, acq_records, dep_records}"
        )
    return {**expected, "book": book}


def assert_v1_08_v1_09_reopen(db_path: Path, expected):
    assets = core._request_json("GET", "/api/fixed-assets")
    book = core._request_json(
        "GET", f"/api/fixed-assets/{expected['asset_id']}/book-state"
    )
    if (
        len(assets) != 1
        or assets[0].get("id") != expected["asset_id"]
        or book != expected["book"]
    ):
        raise AssertionError(
            f"V1-08/09 reopen: durable asset/book truth changed: {assets}, {book}"
        )
    _book_ok(book, expected)

    acq_ledger = core._request_json(
        "GET", f"/api/operations/{expected['acquisition_entry_id']}/professional"
    )
    _asset_audit_ok(
        acq_ledger,
        entry_id=expected["acquisition_entry_id"],
        asset_id=expected["asset_id"],
        authority="fixed_asset_acquisition",
    )
    dep_ledger = core._request_json(
        "GET", f"/api/operations/{expected['depreciation_entry_id']}/professional"
    )
    _asset_audit_ok(
        dep_ledger,
        entry_id=expected["depreciation_entry_id"],
        asset_id=expected["asset_id"],
        authority="fixed_asset_depreciation",
        period_number=1,
    )

    acq = core._request_json(
        "POST",
        "/api/fixed-assets/acquisition/prepare",
        {
            "fixed_asset_id": expected["asset_id"],
            "asset_class": "computer_equipment",
            "settlement_method": "bank",
        },
    )
    token = core._assert_common_preview(acq, amount="12000.00")
    acq_result = core._request_json(
        "POST", f"/api/fixed-assets/decisions/{token}/confirm"
    )
    dep = core._request_json(
        "POST",
        "/api/fixed-assets/depreciation/prepare",
        {
            "fixed_asset_id": expected["asset_id"],
            "period_number": 1,
            "recognition_date": "2026-02-28",
        },
    )
    dep_token = core._assert_common_preview(dep, amount=None)
    dep_result = core._request_json(
        "POST", f"/api/fixed-assets/decisions/{dep_token}/confirm"
    )
    if (
        acq_result.get("entry_id") != expected["acquisition_entry_id"]
        or acq_result.get("already_posted") is not True
        or dep_result.get("entry_id") != expected["depreciation_entry_id"]
        or dep_result.get("already_posted") is not True
    ):
        raise AssertionError(
            f"V1-08/09 reopen: idempotence failed: {acq_result}, {dep_result}"
        )
    with sqlite3.connect(db_path) as conn:
        entries = conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0]
        audits = conn.execute(
            "SELECT COUNT(*) FROM auditevent WHERE event_type='entry_posted'"
        ).fetchone()[0]
    if (entries, audits) != (2, 2):
        raise AssertionError(
            f"V1-08/09 reopen: duplicate durable truth created: entries={entries}, audits={audits}"
        )
    return {
        "asset_id": expected["asset_id"],
        "acquisition_entry_id": expected["acquisition_entry_id"],
        "depreciation_entry_id": expected["depreciation_entry_id"],
        "carrying_value": book["carrying_value"],
    }


def _post_common(kind, amount, day):
    prepared = core._request_json(
        "POST",
        "/api/operations/prepare",
        {"operation_key": kind, "amount": amount, "posting_date": day},
    )
    token = core._assert_common_preview(prepared, amount=amount)
    result = core._request_json("POST", f"/api/operations/{token}/confirm")
    if result.get("state") != "posted" or not result.get("entry_id"):
        raise AssertionError(f"V1-10: fixture posting failed: {result}")
    return result


def _period_shape(value, closing_entry_id=None):
    if value.get("year") != 2026 or len(value.get("periods", [])) != 12:
        raise AssertionError(f"V1-10: fiscal-year shape differs: {value}")
    if (
        closing_entry_id is not None
        and value.get("closing_entry_id") != closing_entry_id
    ):
        raise AssertionError(f"V1-10: closing-entry identity differs: {value}")


def assert_v1_10_periods(db_path: Path, backup_root: Path):
    if core._request_json("GET", "/api/onboarding").get("configured") is not False:
        raise AssertionError("V1-10: periods SQLite was not clean")
    core._request_json("POST", "/api/onboarding", core._onboarding_payload())
    initial = core._request_json("GET", "/api/periods/2026")
    _period_shape(initial)
    if initial.get("state") != "open" or any(
        item.get("state") != "open" for item in initial["periods"]
    ):
        raise AssertionError(f"V1-10: clean year is not open: {initial}")

    sale = _post_common("sale_cash", "200.00", "2026-12-15")
    expense = _post_common("utility_bank", "150.00", "2026-12-20")
    closed = core._request_json("POST", "/api/periods/202601/close")
    closed_again = core._request_json("POST", "/api/periods/202601/close")
    if (
        closed
        != {"period_id": 202601, "state": "closed", "already_closed": False}
        or closed_again
        != {"period_id": 202601, "state": "closed", "already_closed": True}
    ):
        raise AssertionError(
            f"V1-10: monthly close/idempotence differs: {closed}, {closed_again}"
        )
    before = core._request_json("GET", "/api/periods/2026")
    if (
        next(p for p in before["periods"] if p["id"] == 202601)["state"]
        != "closed"
        or next(p for p in before["periods"] if p["id"] == 202612)["state"]
        != "open"
    ):
        raise AssertionError(f"V1-10: monthly state differs: {before}")

    jan = core._request_json(
        "POST",
        "/api/operations/prepare",
        {
            "operation_key": "sale_cash",
            "amount": "10.00",
            "posting_date": "2026-01-20",
        },
    )
    jan_token = core._assert_common_preview(jan, amount="10.00")
    rejected = core._request_error(
        "POST", f"/api/operations/{jan_token}/confirm", expected_status=400
    )
    if "closed" not in rejected.get("detail", "").lower():
        raise AssertionError(
            f"V1-10: closed-period posting failed for wrong reason: {rejected}"
        )
    core._request_json("DELETE", f"/api/operations/{jan_token}")
    with sqlite3.connect(db_path) as conn:
        if conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0] != 2:
            raise AssertionError(
                "V1-10: rejected monthly posting left partial ledger truth"
            )

    annual = core._request_json(
        "POST",
        "/api/periods/years/2026/close",
        {"backup_root": str(backup_root)},
    )
    closing_id = annual.get("entry_id")
    if (
        annual.get("ok") is not True
        or annual.get("already_closed") is not False
        or not closing_id
        or core._decimal(annual.get("transferred"), "V1-10 transferred")
        != Decimal("50.00")
    ):
        raise AssertionError(f"V1-10: annual close differs: {annual}")
    backup_path = Path(annual.get("backup_path", ""))
    if not backup_path.is_file() or backup_root not in backup_path.parents:
        raise AssertionError(f"V1-10: annual pre-close backup missing: {annual}")
    with sqlite3.connect(backup_path) as backup:
        backup_integrity = backup.execute("PRAGMA integrity_check").fetchall()
        backup_entries = backup.execute(
            "SELECT COUNT(*) FROM journalentry"
        ).fetchone()[0]
        backup_fy = backup.execute(
            "SELECT state,closing_entry_id FROM fiscalyear WHERE year=2026"
        ).fetchone()
    if (
        backup_integrity != [("ok",)]
        or backup_entries != 2
        or backup_fy != ("open", None)
    ):
        raise AssertionError(
            "V1-10: backup is not valid pre-close truth: "
            f"integrity={backup_integrity}, entries={backup_entries}, fy={backup_fy}"
        )

    after = core._request_json("GET", "/api/periods/2026")
    _period_shape(after, closing_id)
    if after.get("state") != "closed" or any(
        item.get("state") != "closed" for item in after["periods"]
    ):
        raise AssertionError(
            f"V1-10: annual close did not close all periods: {after}"
        )
    closing = core._request_json(
        "GET", f"/api/operations/{closing_id}/professional"
    )
    lines = [
        (
            line["account_code"],
            core._decimal(line["debit"], "V1-10 close debit"),
            core._decimal(line["credit"], "V1-10 close credit"),
        )
        for line in closing.get("lines", [])
    ]
    if (
        closing.get("state") != "posted"
        or closing.get("posting_date") != "2026-12-31"
        or closing.get("period", {}).get("id") != 202612
        or ("3104", Decimal("0"), Decimal("50.00")) not in lines
        or sum((d for _, d, _ in lines), Decimal("0"))
        != sum((c for _, _, c in lines), Decimal("0"))
    ):
        raise AssertionError(
            f"V1-10: canonical closing entry differs: {closing}"
        )

    annual_retry = core._request_json(
        "POST",
        "/api/periods/years/2026/close",
        {"backup_root": str(backup_root)},
    )
    if (
        annual_retry.get("ok") is not True
        or annual_retry.get("entry_id") != closing_id
        or annual_retry.get("already_closed") is not True
    ):
        raise AssertionError(
            f"V1-10: annual close is not durable/idempotent: {annual_retry}"
        )
    with sqlite3.connect(db_path) as conn:
        entries = conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0]
        fy = conn.execute(
            "SELECT state,closing_entry_id FROM fiscalyear WHERE year=2026"
        ).fetchone()
    if entries != 3 or fy != ("closed", closing_id):
        raise AssertionError(
            f"V1-10: annual-close persistence differs: entries={entries}, fy={fy}"
        )
    return {
        "sale_entry_id": sale["entry_id"],
        "expense_entry_id": expense["entry_id"],
        "closing_entry_id": closing_id,
        "transferred": annual["transferred"],
        "backup_path": str(backup_path),
        "period_state": after,
        "closing": closing,
    }


def assert_v1_10_reopen(db_path: Path, expected):
    state = core._request_json("GET", "/api/periods/2026")
    closing = core._request_json(
        "GET", f"/api/operations/{expected['closing_entry_id']}/professional"
    )
    if (
        state != expected["period_state"]
        or closing != expected["closing"]
        or not Path(expected["backup_path"]).is_file()
    ):
        raise AssertionError(
            "V1-10 reopen: durable period/closing/backup truth changed"
        )
    prepared = core._request_json(
        "POST",
        "/api/operations/prepare",
        {
            "operation_key": "sale_cash",
            "amount": "1.00",
            "posting_date": "2026-12-30",
        },
    )
    token = core._assert_common_preview(prepared, amount="1.00")
    rejected = core._request_error(
        "POST", f"/api/operations/{token}/confirm", expected_status=400
    )
    if "closed" not in rejected.get("detail", "").lower():
        raise AssertionError(
            f"V1-10 reopen: closed FY failed for wrong reason: {rejected}"
        )
    core._request_json("DELETE", f"/api/operations/{token}")
    with sqlite3.connect(db_path) as conn:
        if conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0] != 3:
            raise AssertionError(
                "V1-10 reopen: rejected posting changed ledger cardinality"
            )
    return {
        "closing_entry_id": expected["closing_entry_id"],
        "transferred": expected["transferred"],
        "backup_path": expected["backup_path"],
        "fiscal_year_state": state["state"],
    }


__all__ = [
    "assert_v1_08_v1_09_assets",
    "assert_v1_08_v1_09_reopen",
    "assert_v1_10_periods",
    "assert_v1_10_reopen",
]
