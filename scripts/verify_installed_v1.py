#!/usr/bin/env python3
"""AQR-015 clean-wheel installed-product acceptance smoke.

This harness deliberately runs the product from an isolated virtual environment
and a working directory outside the repository. It drives the canonical loopback
HTTP surface through onboarding and representative V1 journeys while an offline
guard rejects any non-loopback network access.

The harness is evidence of technical product composition. It does not claim the
professional-review or human-acceptance gates required by PRODUCT_ACCEPTANCE_V1.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import venv

from verify_distribution import (
    DEFAULT_PORT,
    REPO_ROOT,
    _post_artifact,
    _run,
    _venv_bin,
    _wait_for_surface,
    _write_offline_guard,
)


CORE_BINDINGS = {
    "bank": "1101",
    "cash": "1102",
    "accounts_receivable": "1103",
    "accounts_payable": "2101",
    "sales_revenue": "4201",
    "utilities_expense": "5102",
}


def _request_json(method: str, path: str, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(
        f"http://127.0.0.1:{DEFAULT_PORT}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8")
        if response.status != 200:
            raise AssertionError(f"{method} {path} returned {response.status}: {body}")
        return json.loads(body)


def _request_error(method: str, path: str, payload=None, expected_status=400):
    try:
        _request_json(method, path, payload)
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        if exc.code != expected_status:
            raise AssertionError(
                f"{method} {path} returned {exc.code}, expected {expected_status}: {body}"
            ) from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"detail": body}
    raise AssertionError(f"{method} {path} unexpectedly succeeded")


def _onboarding_payload() -> dict:
    return {
        "name": "Negocio AQR-015 instalado",
        "rfc": "AAA010101AAA",
        "legal_personality": "persona_moral",
        "legal_form": "sociedad mercantil",
        "economic_purpose": "lucrativo",
        "is_donor_authorized": False,
        "special_capabilities": [],
        "modules_enabled": [],
        "activity_start": "2026-01-01",
        "bindings": dict(CORE_BINDINGS),
        "fiscal_profile": {
            "jurisdiction": "MX",
            "fiscal_regime_code": "603",
            "tax_characteristics": [],
            "effective_from": "2026-01-01",
            "effective_to": None,
        },
    }


def _assert_common_preview(prepared: dict, *, amount: str | None = None) -> str:
    token = prepared.get("token")
    common = prepared.get("preview", {})
    if not token:
        raise AssertionError(f"prepared operation lacks consent token: {prepared}")
    if amount is not None and common.get("amount") != amount:
        raise AssertionError(f"unexpected common preview amount: {prepared}")
    if "account_code" in json.dumps(common, sort_keys=True):
        raise AssertionError(f"common preview leaked professional account codes: {common}")
    if common.get("requires_confirmation") is not True:
        raise AssertionError(f"common preview did not require confirmation: {common}")
    return token


def _assert_v1_01_http_flow() -> int:
    initial = _request_json("GET", "/api/onboarding")
    if initial.get("configured") is not False:
        raise AssertionError(f"clean wheel unexpectedly already configured: {initial}")

    configured = _request_json("POST", "/api/onboarding", _onboarding_payload())
    if configured.get("configured") is not True:
        raise AssertionError(f"onboarding did not configure entity: {configured}")
    if configured.get("bindings") != CORE_BINDINGS:
        raise AssertionError(f"unexpected installed bindings: {configured.get('bindings')}")

    prepared = _request_json(
        "POST",
        "/api/operations/prepare",
        {
            "operation_key": "sale_cash",
            "amount": "200.00",
            "posting_date": "2026-09-10",
        },
    )
    token = _assert_common_preview(prepared, amount="200.00")

    professional_preview = _request_json(
        "GET", f"/api/operations/{token}/professional-preview"
    )
    preview_lines = professional_preview.get("lines", [])
    if [line.get("account_code") for line in preview_lines] != ["1102", "4201"]:
        raise AssertionError(f"unexpected professional preview accounts: {professional_preview}")
    if [line.get("amount") for line in preview_lines] != ["200.00", "200.00"]:
        raise AssertionError(f"unexpected professional preview amounts: {professional_preview}")

    posted = _request_json("POST", f"/api/operations/{token}/confirm")
    if posted.get("state") != "posted" or not posted.get("entry_id"):
        raise AssertionError(f"V1-01 did not post canonically: {posted}")

    entry_id = int(posted["entry_id"])
    professional = _request_json(
        "GET", f"/api/operations/{entry_id}/professional"
    )
    if professional.get("state") != "posted":
        raise AssertionError(f"professional readback is not posted: {professional}")
    if professional.get("period", {}).get("id") != 202609:
        raise AssertionError(f"unexpected V1-01 period: {professional.get('period')}")
    actual_lines = [
        (line.get("account_code"), line.get("debit"), line.get("credit"))
        for line in professional.get("lines", [])
    ]
    expected_lines = [("1102", "200.00", "0"), ("4201", "0", "200.00")]
    if actual_lines != expected_lines:
        raise AssertionError(
            f"professional truth differs from V1-01 expectation: {actual_lines}"
        )
    consent = (
        professional.get("audit", {})
        .get("details", {})
        .get("decision", {})
        .get("consent")
    )
    if consent != "explicit_confirmation":
        raise AssertionError(f"unexpected persisted consent: {consent}")
    return entry_id


def _create_party(name: str, party_type: str) -> dict:
    party = _request_json(
        "POST",
        "/api/subledger/third-parties",
        {"name": name, "party_type": party_type},
    )
    parties = _request_json("GET", "/api/subledger/third-parties")
    if party not in parties:
        raise AssertionError(f"created ThirdParty is not reusable from product surface: {party}")
    return party


def _prepare_credit_origin(
    *,
    operation_key: str,
    amount: str,
    posting_date: str,
    party_id: int,
    due_date: str,
    document_number: str,
) -> dict:
    prepared = _request_json(
        "POST",
        "/api/subledger/origins/prepare",
        {
            "operation_key": operation_key,
            "amount": amount,
            "posting_date": posting_date,
            "third_party_id": party_id,
            "due_date": due_date,
            "document_type": "invoice",
            "document_number": document_number,
            "document_date": posting_date,
        },
    )
    token = _assert_common_preview(prepared, amount=amount)
    professional = _request_json(
        "GET", f"/api/operations/{token}/professional-preview"
    )
    if professional.get("subledger", {}).get("third_party_id") != party_id:
        raise AssertionError(f"professional preview lost ThirdParty provenance: {professional}")
    return prepared


def _apply_open_item(
    open_item_id: int,
    amount: str,
    posting_date: str,
    document_number: str,
) -> dict:
    prepared = _request_json(
        "POST",
        "/api/subledger/applications/batch/prepare",
        {
            "allocations": [{"open_item_id": open_item_id, "amount": amount}],
            "posting_date": posting_date,
            "document_type": "payment",
            "document_number": document_number,
            "document_date": posting_date,
        },
    )
    token = _assert_common_preview(prepared, amount=amount)
    professional = _request_json(
        "GET", f"/api/operations/{token}/professional-preview"
    )
    allocations = professional.get("subledger", {}).get("allocations", [])
    if len(allocations) != 1 or allocations[0].get("open_item_id") != open_item_id:
        raise AssertionError(f"professional preview lost OpenItem allocation: {professional}")
    result = _request_json("POST", f"/api/operations/{token}/confirm")
    if result.get("state") != "posted" or not result.get("entry_id"):
        raise AssertionError(f"subledger application did not post canonically: {result}")
    return result


def _assert_credit_journey(
    *,
    case_id: str,
    kind: str,
    operation_key: str,
    party_name: str,
    party_type: str,
    original_amount: str,
    first_amount: str,
    second_amount: str,
    balance_after_first: str,
    source_date: str,
    due_date: str,
    first_date: str,
    second_date: str,
) -> dict:
    party = _create_party(party_name, party_type)

    # Cancellation is a real product action: a prepared decision must leave no ledger
    # or subledger truth if the user declines consent.
    cancelled = _prepare_credit_origin(
        operation_key=operation_key,
        amount="1.00",
        posting_date=source_date,
        party_id=party["id"],
        due_date=due_date,
        document_number=f"{case_id}-CANCEL",
    )
    _request_json("DELETE", f"/api/operations/{cancelled['token']}")
    before = _request_json(
        "GET", f"/api/subledger/open-items?kind={kind}&as_of={source_date}"
    )
    if before:
        raise AssertionError(f"{case_id} cancelled preview persisted an OpenItem: {before}")

    origin = _prepare_credit_origin(
        operation_key=operation_key,
        amount=original_amount,
        posting_date=source_date,
        party_id=party["id"],
        due_date=due_date,
        document_number=f"{case_id}-SOURCE",
    )
    posted = _request_json("POST", f"/api/operations/{origin['token']}/confirm")
    if posted.get("state") != "posted" or not posted.get("open_item_id"):
        raise AssertionError(f"{case_id} credit origin did not post: {posted}")
    open_item_id = int(posted["open_item_id"])

    source_view = _request_json(
        "GET", f"/api/subledger/open-items/{open_item_id}?as_of={source_date}"
    )
    if source_view.get("original_amount") != original_amount:
        raise AssertionError(f"{case_id} original amount differs: {source_view}")
    if source_view.get("third_party_id") != party["id"]:
        raise AssertionError(f"{case_id} OpenItem lost ThirdParty: {source_view}")
    if source_view.get("document_number") != f"{case_id}-SOURCE":
        raise AssertionError(f"{case_id} OpenItem lost source document: {source_view}")

    first = _apply_open_item(
        open_item_id,
        first_amount,
        first_date,
        f"{case_id}-PARTIAL",
    )
    partial = _request_json(
        "GET", f"/api/subledger/open-items/{open_item_id}?as_of={first_date}"
    )
    if (
        Decimal(partial.get("open_balance", "NaN")) != Decimal(balance_after_first)
        or partial.get("status") != "open"
    ):
        raise AssertionError(f"{case_id} partial settlement is wrong: {partial}")

    rejected = _request_error(
        "POST",
        "/api/subledger/applications/batch/prepare",
        {
            "allocations": [
                {
                    "open_item_id": open_item_id,
                    "amount": str(Decimal(balance_after_first) + Decimal("1.00")),
                }
            ],
            "posting_date": second_date,
            "document_type": "payment",
            "document_number": f"{case_id}-OVER",
            "document_date": second_date,
        },
    )
    if "exceeds" not in rejected.get("detail", ""):
        raise AssertionError(f"{case_id} overapplication failed for the wrong reason: {rejected}")

    second = _apply_open_item(
        open_item_id,
        second_amount,
        second_date,
        f"{case_id}-FINAL",
    )
    settled = _request_json(
        "GET", f"/api/subledger/open-items/{open_item_id}?as_of={second_date}"
    )
    if (
        Decimal(settled.get("open_balance", "NaN")) != Decimal("0")
        or settled.get("status") != "settled"
    ):
        raise AssertionError(f"{case_id} did not settle exactly: {settled}")

    professional = _request_json(
        "GET",
        f"/api/subledger/open-items/{open_item_id}/professional?as_of={second_date}",
    )
    pro_item = professional.get("open_item", {})
    if (
        Decimal(pro_item.get("open_balance", "NaN")) != Decimal("0")
        or pro_item.get("third_party_id") != party["id"]
    ):
        raise AssertionError(f"{case_id} professional readback differs: {professional}")
    source_operation = professional.get("source_operation", {})
    documents = source_operation.get("documents", [])
    if len(documents) != 1 or documents[0].get("third_party_id") != party["id"]:
        raise AssertionError(f"{case_id} professional source document differs: {professional}")
    if source_operation.get("entry_id") != posted.get("entry_id"):
        raise AssertionError(f"{case_id} professional source ledger differs: {professional}")
    if source_operation.get("audit", {}).get("event_type") != "entry_posted":
        raise AssertionError(f"{case_id} canonical posting audit is missing: {professional}")
    if not professional.get("reconciliation", {}).get("is_reconciled"):
        raise AssertionError(f"{case_id} professional subledger is not reconciled: {professional}")

    reconciliation = _request_json(
        "GET", f"/api/subledger/reconciliation/{kind}?as_of={second_date}"
    )
    if not reconciliation.get("is_reconciled"):
        raise AssertionError(f"{case_id} control account does not reconcile: {reconciliation}")

    return {
        "party_id": party["id"],
        "open_item_id": open_item_id,
        "source_entry_id": posted["entry_id"],
        "partial_entry_id": first["entry_id"],
        "final_entry_id": second["entry_id"],
    }


def _assert_v1_02_and_v1_04_http_flows() -> dict:
    receivable = _assert_credit_journey(
        case_id="V1-02",
        kind="receivable",
        operation_key="sale_credit",
        party_name="Ana Cliente",
        party_type="customer",
        original_amount="200.00",
        first_amount="80.00",
        second_amount="120.00",
        balance_after_first="120.00",
        source_date="2026-01-10",
        due_date="2026-01-30",
        first_date="2026-01-20",
        second_date="2026-01-21",
    )
    payable = _assert_credit_journey(
        case_id="V1-04",
        kind="payable",
        operation_key="utility_credit",
        party_name="Proveedor Servicios",
        party_type="supplier",
        original_amount="1500.00",
        first_amount="500.00",
        second_amount="1000.00",
        balance_after_first="1000.00",
        source_date="2026-02-10",
        due_date="2026-02-28",
        first_date="2026-02-20",
        second_date="2026-02-21",
    )
    return {"V1-02": receivable, "V1-04": payable}


def _decimal(value, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise AssertionError(f"{label} is not exact decimal text: {value!r}") from exc
    if not result.is_finite():
        raise AssertionError(f"{label} is not finite: {value!r}")
    return result


def _bank_line_for_entry(db_path: Path, entry_id: int, ledger_account_id: int) -> dict:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT jl.id,a.code,jl.account_id,jl.debit,jl.credit "
            "FROM journalline jl JOIN account a ON a.id=jl.account_id "
            "WHERE jl.entry_id=? AND jl.account_id=? ORDER BY jl.id",
            (entry_id, ledger_account_id),
        ).fetchall()
    if len(rows) != 1:
        raise AssertionError(
            f"bank entry {entry_id} expected one line for account {ledger_account_id}, got {rows}"
        )
    row = rows[0]
    return {
        "id": row[0],
        "account_code": row[1],
        "account_id": row[2],
        "debit": row[3],
        "credit": row[4],
    }


def _assert_v1_05_and_v1_06_banking(db_path: Path) -> dict:
    case = "V1-05 banking composition"
    initial = _request_json("GET", "/api/onboarding")
    if initial.get("configured") is not False:
        raise AssertionError(f"{case}: banking SQLite was not clean: {initial}")
    configured = _request_json("POST", "/api/onboarding", _onboarding_payload())
    if configured.get("configured") is not True:
        raise AssertionError(f"{case}: onboarding failed: {configured}")

    source = _request_json(
        "POST",
        "/api/banking/accounts",
        {
            "institution_name": "Banco origen V1-05",
            "account_identifier": "V1-05-SOURCE",
            "currency": "MXN",
        },
    )
    destination = _request_json(
        "POST",
        "/api/banking/accounts",
        {
            "institution_name": "Banco destino V1-05",
            "account_identifier": "V1-05-DESTINATION",
            "currency": "MXN",
        },
    )
    if source.get("ledger_account_id") == destination.get("ledger_account_id"):
        raise AssertionError(f"{case}: two BankAccounts share one ledger account: {source}, {destination}")

    listed = _request_json("GET", "/api/banking/accounts")
    by_id = {row["id"]: row for row in listed}
    for bank in (source, destination):
        reopened = by_id.get(bank["id"])
        if reopened is None or reopened.get("ledger_account_id") != bank.get("ledger_account_id"):
            raise AssertionError(f"{case}: BankAccount identity did not survive readback: {bank}, {listed}")

    ledger_ids = (source["ledger_account_id"], destination["ledger_account_id"])
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT child.id,child.code,child.origin,parent.code "
            "FROM account child LEFT JOIN account parent ON parent.id=child.parent_id "
            "WHERE child.id IN (?,?) ORDER BY child.id",
            ledger_ids,
        ).fetchall()
    if len(rows) != 2:
        raise AssertionError(f"{case}: governed bank Account rows missing: {rows}")
    account_truth = {row[0]: {"code": row[1], "origin": row[2], "parent_code": row[3]} for row in rows}
    if set(account_truth) != set(ledger_ids):
        raise AssertionError(f"{case}: ledger account identities changed: {account_truth}")
    codes = []
    for ledger_id in ledger_ids:
        truth = account_truth[ledger_id]
        codes.append(truth["code"])
        if truth["origin"] != "entity" or truth["parent_code"] != "1101":
            raise AssertionError(f"{case}: bank Account is not governed under canonical 1101: {truth}")
    if len(set(codes)) != 2:
        raise AssertionError(f"{case}: governed extensions are not distinct: {codes}")

    def transfer(amount: str, posting_date: str, description: str) -> dict:
        result = _request_json(
            "POST",
            "/api/banking/transfers",
            {
                "source_bank_account_id": source["id"],
                "destination_bank_account_id": destination["id"],
                "amount": amount,
                "posting_date": posting_date,
                "description": description,
            },
        )
        if not result.get("entry_id") or not result.get("audit_event_id"):
            raise AssertionError(f"{case}: transfer lacks canonical identities: {result}")
        return result

    transfer_300 = transfer("300.00", "2026-03-01", "V1-05 transferencia propia 300")
    with sqlite3.connect(db_path) as conn:
        lines = conn.execute(
            "SELECT a.id,a.code,jl.debit,jl.credit "
            "FROM journalline jl JOIN account a ON a.id=jl.account_id "
            "WHERE jl.entry_id=? ORDER BY jl.id",
            (transfer_300["entry_id"],),
        ).fetchall()
        audit_rows = conn.execute(
            "SELECT id,details_json FROM auditevent WHERE event_type='bank_transfer_posted' ORDER BY id"
        ).fetchall()
    expected_lines = [
        (destination["ledger_account_id"], account_truth[destination["ledger_account_id"]]["code"], Decimal("300.00"), Decimal("0")),
        (source["ledger_account_id"], account_truth[source["ledger_account_id"]]["code"], Decimal("0"), Decimal("300.00")),
    ]
    actual_lines = [(row[0], row[1], _decimal(row[2], f"{case} debit"), _decimal(row[3], f"{case} credit")) for row in lines]
    if actual_lines != expected_lines:
        raise AssertionError(f"{case}: canonical transfer lines differ: {actual_lines}")
    matching_audits = []
    for audit_id, details_json in audit_rows:
        details = json.loads(details_json)
        if details.get("entry_id") == transfer_300["entry_id"]:
            matching_audits.append((audit_id, details))
    if len(matching_audits) != 1:
        raise AssertionError(f"{case}: transfer audit is not unique: {matching_audits}")
    audit_id, audit = matching_audits[0]
    if audit_id != transfer_300["audit_event_id"]:
        raise AssertionError(f"{case}: returned audit identity differs from persistence: {audit_id}, {transfer_300}")
    if (
        audit.get("source_bank_account_id") != source["id"]
        or audit.get("destination_bank_account_id") != destination["id"]
        or _decimal(audit.get("amount"), f"{case} audit amount") != Decimal("300.00")
    ):
        raise AssertionError(f"{case}: persisted transfer audit differs: {audit}")

    case = "V1-06 reconciliation"
    transfer_900 = transfer("900.00", "2026-03-02", "V1-06 movimiento conciliable 900")
    transfer_100 = transfer("100.00", "2026-03-03", "V1-06 diferencia explicable 100")
    destination_300 = _bank_line_for_entry(
        db_path, transfer_300["entry_id"], destination["ledger_account_id"]
    )
    destination_900 = _bank_line_for_entry(
        db_path, transfer_900["entry_id"], destination["ledger_account_id"]
    )
    destination_100 = _bank_line_for_entry(
        db_path, transfer_100["entry_id"], destination["ledger_account_id"]
    )
    for label, line, amount in (
        ("300", destination_300, Decimal("300.00")),
        ("900", destination_900, Decimal("900.00")),
        ("100", destination_100, Decimal("100.00")),
    ):
        if line["account_id"] != destination["ledger_account_id"]:
            raise AssertionError(f"{case}: {label} line is outside selected BankAccount: {line}")
        if _decimal(line["debit"], f"{case} {label} debit") != amount or _decimal(
            line["credit"], f"{case} {label} credit"
        ) != Decimal("0"):
            raise AssertionError(f"{case}: unexpected selected-bank line {label}: {line}")

    imported = _request_json(
        "POST",
        "/api/banking/import",
        {
            "bank_account_id": destination["id"],
            "source_name": "V1-06-statement.csv",
            "content": (
                "date,reference,amount,balance\n"
                "2026-03-01,V1-06-300,300.00,300.00\n"
                "2026-03-02,V1-06-900,900.00,1200.00\n"
            ),
        },
    )
    reconciliation = _request_json(
        "POST",
        "/api/banking/reconciliations",
        {
            "bank_account_id": destination["id"],
            "statement_id": imported["statement_id"],
            "as_of": "2026-03-03",
        },
    )
    reconciliation_id = reconciliation["reconciliation_id"]

    with sqlite3.connect(db_path) as conn:
        external_rows = conn.execute(
            "SELECT id,reference,amount,direction,external_balance "
            "FROM banktransaction WHERE statement_id=? ORDER BY id",
            (imported["statement_id"],),
        ).fetchall()
        statement = conn.execute(
            "SELECT bank_account_id,closing_balance FROM bankstatement WHERE id=?",
            (imported["statement_id"],),
        ).fetchone()
    if statement is None or statement[0] != destination["id"] or _decimal(
        statement[1], f"{case} statement balance"
    ) != Decimal("1200.00"):
        raise AssertionError(f"{case}: statement identity/closing balance differs: {statement}")
    if len(external_rows) != 2:
        raise AssertionError(f"{case}: expected exactly two external transactions: {external_rows}")
    transactions = {row[1]: row for row in external_rows}
    if set(transactions) != {"V1-06-300", "V1-06-900"}:
        raise AssertionError(f"{case}: external references differ: {transactions}")
    for reference, expected in (("V1-06-300", Decimal("300.00")), ("V1-06-900", Decimal("900.00"))):
        row = transactions[reference]
        if _decimal(row[2], f"{case} {reference} amount") != expected or row[3] != "credit":
            raise AssertionError(f"{case}: external evidence differs for {reference}: {row}")
    if any(_decimal(row[2], f"{case} external amount") == Decimal("100.00") for row in external_rows):
        raise AssertionError(f"{case}: fabricated external 100.00 transaction exists: {external_rows}")

    for reference, line in (
        ("V1-06-300", destination_300),
        ("V1-06-900", destination_900),
    ):
        matched = _request_json(
            "POST",
            "/api/banking/matches",
            {
                "reconciliation_id": reconciliation_id,
                "bank_transaction_id": transactions[reference][0],
                "journal_line_id": line["id"],
            },
        )
        if not matched.get("match_id"):
            raise AssertionError(f"{case}: match lacks identity for {reference}: {matched}")

    view = _request_json("GET", f"/api/banking/reconciliations/{reconciliation_id}")
    if view.get("bank_account_id") != destination["id"]:
        raise AssertionError(f"{case}: reconciliation changed BankAccount: {view}")
    for field, expected in (
        ("ledger_balance", Decimal("1300.00")),
        ("bank_balance", Decimal("1200.00")),
        ("difference", Decimal("100.00")),
    ):
        if _decimal(view.get(field), f"{case} {field}") != expected:
            raise AssertionError(f"{case}: {field} differs: {view}")
    if view.get("missing_bank_transaction_ids") not in ([], ()):
        raise AssertionError(f"{case}: conciliable external evidence remains unmatched: {view}")
    if view.get("missing_journal_line_ids") != [destination_100["id"]]:
        raise AssertionError(f"{case}: 100.00 ledger line is not the explicit difference: {view}")

    line_by_bank = {row["bank_transaction_id"]: row for row in view.get("lines", [])}
    for reference, expected_line in (
        ("V1-06-300", destination_300),
        ("V1-06-900", destination_900),
    ):
        external_id = transactions[reference][0]
        row = line_by_bank.get(external_id)
        if row is None or row.get("state") != "matched" or row.get("journal_line_id") != expected_line["id"]:
            raise AssertionError(f"{case}: persisted match differs for {reference}: {view}")

    reopened = _request_json("GET", f"/api/banking/reconciliations/{reconciliation_id}")
    if reopened != view:
        raise AssertionError(f"{case}: reconciliation readback changed across sessions: {view} != {reopened}")

    with sqlite3.connect(db_path) as conn:
        entry_count = conn.execute("SELECT COUNT(*) FROM journalentry WHERE state='posted'").fetchone()[0]
        line_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
        external_count = conn.execute(
            "SELECT COUNT(*) FROM banktransaction WHERE statement_id=?",
            (imported["statement_id"],),
        ).fetchone()[0]
        match_rows = conn.execute(
            "SELECT rm.bank_transaction_id,rm.journal_line_id,jl.account_id "
            "FROM reconciliationmatch rm JOIN journalline jl ON jl.id=rm.journal_line_id "
            "WHERE rm.reconciliation_id=? ORDER BY rm.id",
            (reconciliation_id,),
        ).fetchall()
    if entry_count != 3 or line_count != 6:
        raise AssertionError(
            f"{case}: reconciliation invented or lost accounting entries: entries={entry_count}, lines={line_count}"
        )
    if external_count != 2 or len(match_rows) != 2:
        raise AssertionError(
            f"{case}: external evidence/matches are not separate relational truth: external={external_count}, matches={match_rows}"
        )
    if any(row[2] != destination["ledger_account_id"] for row in match_rows):
        raise AssertionError(f"{case}: match points outside BankAccount ledger authority: {match_rows}")

    return {
        "V1-05": {
            "source_bank_account_id": source["id"],
            "destination_bank_account_id": destination["id"],
            "source_account_code": account_truth[source["ledger_account_id"]]["code"],
            "destination_account_code": account_truth[destination["ledger_account_id"]]["code"],
            "entry_id": transfer_300["entry_id"],
        },
        "V1-06": {
            "reconciliation_id": reconciliation_id,
            "ledger_balance": view["ledger_balance"],
            "bank_balance": view["bank_balance"],
            "difference": view["difference"],
            "unmatched_journal_line_id": destination_100["id"],
        },
    }


def _terminate_process(process: subprocess.Popen) -> bool:
    forced_kill = False
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            forced_kill = True
            process.kill()
            process.wait(timeout=5)
    return forced_kill


def _install_and_run(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="aqorath-installed-v1-") as temp:
        root = Path(temp)
        venv_dir = root / "venv"
        workdir = root / "outside-checkout"
        db_path = root / "user-data" / "aqorath.db"
        banking_db_path = root / "banking-data" / "aqorath.db"
        workdir.mkdir()

        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
        bindir = _venv_bin(venv_dir)
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        _run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                str(wheel),
            ]
        )

        console = bindir / ("aqorath.exe" if os.name == "nt" else "aqorath")
        if not console.is_file():
            raise AssertionError(f"console script missing: {console}")

        guard_dir, attempts = _write_offline_guard(root)
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["AQORATH_SMOKE_REPO_ROOT"] = str(REPO_ROOT)
        env["AQORATH_DB"] = str(db_path)
        env["AQORATH_OFFLINE_ATTEMPTS"] = str(attempts)
        env["PYTHONPATH"] = str(guard_dir)

        log_path = root / "aqorath-v1.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [str(console)],
                cwd=workdir,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                integrity = _wait_for_surface(process, log_path)
                if not integrity.get("healthy"):
                    raise AssertionError(f"clean installed integrity failed: {integrity}")
                entry_id = _assert_v1_01_http_flow()
                credit_results = _assert_v1_02_and_v1_04_http_flows()
                post_integrity = _request_json("GET", "/api/system/integrity")
                if not post_integrity.get("healthy"):
                    raise AssertionError(
                        f"post-V1-flow integrity check failed: {post_integrity}"
                    )
                _post_artifact("/api/system/backup")
                _post_artifact("/api/system/portable-export")
                print(f"installed V1-01 entry_id={entry_id}")
                print("installed credit journeys=" + json.dumps(credit_results, sort_keys=True))
            finally:
                forced_kill = _terminate_process(process)
            if forced_kill:
                raise AssertionError("installed Aqorath did not shut down cleanly")

        if not db_path.is_file():
            raise AssertionError(f"installed V1 flow did not create SQLite DB: {db_path}")
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT account_code,debit,credit FROM journalline ORDER BY id"
            ).fetchall()
            entries = conn.execute(
                "SELECT COUNT(*) FROM journalentry WHERE state='posted'"
            ).fetchone()[0]
            open_items = conn.execute("SELECT COUNT(*) FROM openitem").fetchone()[0]
            applications = conn.execute(
                "SELECT COUNT(*) FROM openitemapplication"
            ).fetchone()[0]
        if rows[:2] != [("1102", "200.00", "0"), ("4201", "0", "200.00")]:
            raise AssertionError(f"installed SQLite lost V1-01 truth: {rows[:2]}")
        if entries != 7:
            raise AssertionError(f"expected 7 canonical posted entries, found {entries}")
        if open_items != 2 or applications != 4:
            raise AssertionError(
                "installed subledger relationship counts differ from V1-02/V1-04: "
                f"open_items={open_items}, applications={applications}"
            )

        banking_env = env.copy()
        banking_env["AQORATH_DB"] = str(banking_db_path)
        banking_log_path = root / "aqorath-banking-v1.log"
        with banking_log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [str(console)],
                cwd=workdir,
                env=banking_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                integrity = _wait_for_surface(process, banking_log_path)
                if not integrity.get("healthy"):
                    raise AssertionError(f"V1-05 banking composition: clean integrity failed: {integrity}")
                banking_results = _assert_v1_05_and_v1_06_banking(banking_db_path)
                post_integrity = _request_json("GET", "/api/system/integrity")
                if not post_integrity.get("healthy"):
                    raise AssertionError(
                        f"V1-06 reconciliation: post-flow integrity failed: {post_integrity}"
                    )
                print("installed banking journeys=" + json.dumps(banking_results, sort_keys=True))
            finally:
                forced_kill = _terminate_process(process)
            if forced_kill:
                raise AssertionError("installed banking Aqorath did not shut down cleanly")

        if not banking_db_path.is_file():
            raise AssertionError(
                f"installed banking flow did not create SQLite DB: {banking_db_path}"
            )
        with sqlite3.connect(banking_db_path) as conn:
            if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise AssertionError("installed banking SQLite integrity_check failed")
            if conn.execute("SELECT COUNT(*) FROM bankaccount").fetchone()[0] != 2:
                raise AssertionError("installed banking readback did not preserve two BankAccounts")

        if attempts.exists() and attempts.read_text(encoding="utf-8").strip():
            raise AssertionError(
                "installed V1 flow attempted external network access:\n"
                + attempts.read_text(encoding="utf-8")
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", required=True, type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file():
        raise SystemExit(f"wheel not found: {wheel}")
    _install_and_run(wheel)
    print("AQR-015 installed V1-01/V1-02/V1-04/V1-05/V1-06 smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
