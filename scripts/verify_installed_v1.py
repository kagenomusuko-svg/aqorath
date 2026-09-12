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


def _osc_onboarding_payload() -> dict:
    payload = _onboarding_payload()
    payload.update({
        "name": "OSC AQR-015 instalada",
        "legal_form": "A.C.",
        "economic_purpose": "no_lucrativo",
        "special_capabilities": ["osc"],
        "bindings": {
            **CORE_BINDINGS,
            "donation_income": "4104",
            "fixed_asset_computer_equipment": "1202",
        },
    })
    return payload


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
    prepared = _request_json("POST", "/api/operations/prepare", {"operation_key": "sale_cash", "amount": "200.00", "posting_date": "2026-09-10"})
    token = _assert_common_preview(prepared, amount="200.00")
    professional_preview = _request_json("GET", f"/api/operations/{token}/professional-preview")
    preview_lines = professional_preview.get("lines", [])
    if [line.get("account_code") for line in preview_lines] != ["1102", "4201"]:
        raise AssertionError(f"unexpected professional preview accounts: {professional_preview}")
    if [line.get("amount") for line in preview_lines] != ["200.00", "200.00"]:
        raise AssertionError(f"unexpected professional preview amounts: {professional_preview}")
    posted = _request_json("POST", f"/api/operations/{token}/confirm")
    if posted.get("state") != "posted" or not posted.get("entry_id"):
        raise AssertionError(f"V1-01 did not post canonically: {posted}")
    entry_id = int(posted["entry_id"])
    professional = _request_json("GET", f"/api/operations/{entry_id}/professional")
    if professional.get("state") != "posted":
        raise AssertionError(f"professional readback is not posted: {professional}")
    if professional.get("period", {}).get("id") != 202609:
        raise AssertionError(f"unexpected V1-01 period: {professional.get('period')}")
    actual_lines = [(line.get("account_code"), line.get("debit"), line.get("credit")) for line in professional.get("lines", [])]
    expected_lines = [("1102", "200.00", "0"), ("4201", "0", "200.00")]
    if actual_lines != expected_lines:
        raise AssertionError(f"professional truth differs from V1-01 expectation: {actual_lines}")
    consent = professional.get("audit", {}).get("details", {}).get("decision", {}).get("consent")
    if consent != "explicit_confirmation":
        raise AssertionError(f"unexpected persisted consent: {consent}")
    return entry_id


def _create_party(name: str, party_type: str) -> dict:
    party = _request_json("POST", "/api/subledger/third-parties", {"name": name, "party_type": party_type})
    parties = _request_json("GET", "/api/subledger/third-parties")
    if party not in parties:
        raise AssertionError(f"created ThirdParty is not reusable from product surface: {party}")
    return party


def _prepare_credit_origin(*, operation_key: str, amount: str, posting_date: str, party_id: int, due_date: str, document_number: str) -> dict:
    prepared = _request_json("POST", "/api/subledger/origins/prepare", {
        "operation_key": operation_key, "amount": amount, "posting_date": posting_date,
        "third_party_id": party_id, "due_date": due_date, "document_type": "invoice",
        "document_number": document_number, "document_date": posting_date,
    })
    token = _assert_common_preview(prepared, amount=amount)
    professional = _request_json("GET", f"/api/operations/{token}/professional-preview")
    if professional.get("subledger", {}).get("third_party_id") != party_id:
        raise AssertionError(f"professional preview lost ThirdParty provenance: {professional}")
    return prepared


def _apply_open_item(open_item_id: int, amount: str, posting_date: str, document_number: str) -> dict:
    prepared = _request_json("POST", "/api/subledger/applications/batch/prepare", {
        "allocations": [{"open_item_id": open_item_id, "amount": amount}],
        "posting_date": posting_date, "document_type": "payment",
        "document_number": document_number, "document_date": posting_date,
    })
    token = _assert_common_preview(prepared, amount=amount)
    professional = _request_json("GET", f"/api/operations/{token}/professional-preview")
    allocations = professional.get("subledger", {}).get("allocations", [])
    if len(allocations) != 1 or allocations[0].get("open_item_id") != open_item_id:
        raise AssertionError(f"professional preview lost OpenItem allocation: {professional}")
    result = _request_json("POST", f"/api/operations/{token}/confirm")
    if result.get("state") != "posted" or not result.get("entry_id"):
        raise AssertionError(f"subledger application did not post canonically: {result}")
    return result


def _assert_credit_journey(*, case_id: str, kind: str, operation_key: str, party_name: str, party_type: str, original_amount: str, first_amount: str, second_amount: str, balance_after_first: str, source_date: str, due_date: str, first_date: str, second_date: str) -> dict:
    party = _create_party(party_name, party_type)
    cancelled = _prepare_credit_origin(operation_key=operation_key, amount="1.00", posting_date=source_date, party_id=party["id"], due_date=due_date, document_number=f"{case_id}-CANCEL")
    _request_json("DELETE", f"/api/operations/{cancelled['token']}")
    before = _request_json("GET", f"/api/subledger/open-items?kind={kind}&as_of={source_date}")
    if before:
        raise AssertionError(f"{case_id} cancelled preview persisted an OpenItem: {before}")
    origin = _prepare_credit_origin(operation_key=operation_key, amount=original_amount, posting_date=source_date, party_id=party["id"], due_date=due_date, document_number=f"{case_id}-SOURCE")
    posted = _request_json("POST", f"/api/operations/{origin['token']}/confirm")
    if posted.get("state") != "posted" or not posted.get("open_item_id"):
        raise AssertionError(f"{case_id} credit origin did not post: {posted}")
    open_item_id = int(posted["open_item_id"])
    source_view = _request_json("GET", f"/api/subledger/open-items/{open_item_id}?as_of={source_date}")
    if source_view.get("original_amount") != original_amount or source_view.get("third_party_id") != party["id"] or source_view.get("document_number") != f"{case_id}-SOURCE":
        raise AssertionError(f"{case_id} source OpenItem differs: {source_view}")
    first = _apply_open_item(open_item_id, first_amount, first_date, f"{case_id}-PARTIAL")
    partial = _request_json("GET", f"/api/subledger/open-items/{open_item_id}?as_of={first_date}")
    if Decimal(partial.get("open_balance", "NaN")) != Decimal(balance_after_first) or partial.get("status") != "open":
        raise AssertionError(f"{case_id} partial settlement is wrong: {partial}")
    rejected = _request_error("POST", "/api/subledger/applications/batch/prepare", {
        "allocations": [{"open_item_id": open_item_id, "amount": str(Decimal(balance_after_first) + Decimal("1.00"))}],
        "posting_date": second_date, "document_type": "payment", "document_number": f"{case_id}-OVER", "document_date": second_date,
    })
    if "exceeds" not in rejected.get("detail", ""):
        raise AssertionError(f"{case_id} overapplication failed for the wrong reason: {rejected}")
    second = _apply_open_item(open_item_id, second_amount, second_date, f"{case_id}-FINAL")
    settled = _request_json("GET", f"/api/subledger/open-items/{open_item_id}?as_of={second_date}")
    if Decimal(settled.get("open_balance", "NaN")) != Decimal("0") or settled.get("status") != "settled":
        raise AssertionError(f"{case_id} did not settle exactly: {settled}")
    professional = _request_json("GET", f"/api/subledger/open-items/{open_item_id}/professional?as_of={second_date}")
    pro_item = professional.get("open_item", {})
    if Decimal(pro_item.get("open_balance", "NaN")) != Decimal("0") or pro_item.get("third_party_id") != party["id"]:
        raise AssertionError(f"{case_id} professional readback differs: {professional}")
    source_operation = professional.get("source_operation", {})
    documents = source_operation.get("documents", [])
    if len(documents) != 1 or documents[0].get("third_party_id") != party["id"] or source_operation.get("entry_id") != posted.get("entry_id") or source_operation.get("audit", {}).get("event_type") != "entry_posted":
        raise AssertionError(f"{case_id} professional source provenance differs: {professional}")
    if not professional.get("reconciliation", {}).get("is_reconciled"):
        raise AssertionError(f"{case_id} professional subledger is not reconciled: {professional}")
    reconciliation = _request_json("GET", f"/api/subledger/reconciliation/{kind}?as_of={second_date}")
    if not reconciliation.get("is_reconciled"):
        raise AssertionError(f"{case_id} control account does not reconcile: {reconciliation}")
    return {"party_id": party["id"], "open_item_id": open_item_id, "source_entry_id": posted["entry_id"], "partial_entry_id": first["entry_id"], "final_entry_id": second["entry_id"]}


def _assert_v1_02_and_v1_04_http_flows() -> dict:
    receivable = _assert_credit_journey(case_id="V1-02", kind="receivable", operation_key="sale_credit", party_name="Ana Cliente", party_type="customer", original_amount="200.00", first_amount="80.00", second_amount="120.00", balance_after_first="120.00", source_date="2026-01-10", due_date="2026-01-30", first_date="2026-01-20", second_date="2026-01-21")
    payable = _assert_credit_journey(case_id="V1-04", kind="payable", operation_key="utility_credit", party_name="Proveedor Servicios", party_type="supplier", original_amount="1500.00", first_amount="500.00", second_amount="1000.00", balance_after_first="1000.00", source_date="2026-02-10", due_date="2026-02-28", first_date="2026-02-20", second_date="2026-02-21")
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
        rows = conn.execute("SELECT jl.id,a.code,jl.account_id,jl.debit,jl.credit FROM journalline jl JOIN account a ON a.id=jl.account_id WHERE jl.entry_id=? AND jl.account_id=? ORDER BY jl.id", (entry_id, ledger_account_id)).fetchall()
    if len(rows) != 1:
        raise AssertionError(f"bank entry {entry_id} expected one line for account {ledger_account_id}, got {rows}")
    row = rows[0]
    return {"id": row[0], "account_code": row[1], "account_id": row[2], "debit": row[3], "credit": row[4]}


def _assert_v1_05_and_v1_06_banking(db_path: Path) -> dict:
    case = "V1-05 banking composition"
    initial = _request_json("GET", "/api/onboarding")
    if initial.get("configured") is not False:
        raise AssertionError(f"{case}: banking SQLite was not clean: {initial}")
    configured = _request_json("POST", "/api/onboarding", _onboarding_payload())
    if configured.get("configured") is not True:
        raise AssertionError(f"{case}: onboarding failed: {configured}")
    source = _request_json("POST", "/api/banking/accounts", {"institution_name": "Banco origen V1-05", "account_identifier": "V1-05-SOURCE", "currency": "MXN"})
    destination = _request_json("POST", "/api/banking/accounts", {"institution_name": "Banco destino V1-05", "account_identifier": "V1-05-DESTINATION", "currency": "MXN"})
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
        rows = conn.execute("SELECT child.id,child.code,child.origin,parent.code FROM account child LEFT JOIN account parent ON parent.id=child.parent_id WHERE child.id IN (?,?) ORDER BY child.id", ledger_ids).fetchall()
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
        result = _request_json("POST", "/api/banking/transfers", {"source_bank_account_id": source["id"], "destination_bank_account_id": destination["id"], "amount": amount, "posting_date": posting_date, "description": description})
        if not result.get("entry_id") or not result.get("audit_event_id"):
            raise AssertionError(f"{case}: transfer lacks canonical identities: {result}")
        return result
    transfer_300 = transfer("300.00", "2026-03-01", "V1-05 transferencia propia 300")
    with sqlite3.connect(db_path) as conn:
        lines = conn.execute("SELECT a.id,a.code,jl.debit,jl.credit FROM journalline jl JOIN account a ON a.id=jl.account_id WHERE jl.entry_id=? ORDER BY jl.id", (transfer_300["entry_id"],)).fetchall()
        audit_rows = conn.execute("SELECT id,details_json FROM auditevent WHERE event_type='bank_transfer_posted' ORDER BY id").fetchall()
    expected_lines = [(destination["ledger_account_id"], account_truth[destination["ledger_account_id"]]["code"], Decimal("300.00"), Decimal("0")), (source["ledger_account_id"], account_truth[source["ledger_account_id"]]["code"], Decimal("0"), Decimal("300.00"))]
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
    if audit_id != transfer_300["audit_event_id"] or audit.get("source_bank_account_id") != source["id"] or audit.get("destination_bank_account_id") != destination["id"] or _decimal(audit.get("amount"), f"{case} audit amount") != Decimal("300.00"):
        raise AssertionError(f"{case}: persisted transfer audit differs: {audit}")
    case = "V1-06 reconciliation"
    transfer_900 = transfer("900.00", "2026-03-02", "V1-06 movimiento conciliable 900")
    transfer_100 = transfer("100.00", "2026-03-03", "V1-06 diferencia explicable 100")
    destination_300 = _bank_line_for_entry(db_path, transfer_300["entry_id"], destination["ledger_account_id"])
    destination_900 = _bank_line_for_entry(db_path, transfer_900["entry_id"], destination["ledger_account_id"])
    destination_100 = _bank_line_for_entry(db_path, transfer_100["entry_id"], destination["ledger_account_id"])
    for label, line, amount in (("300", destination_300, Decimal("300.00")), ("900", destination_900, Decimal("900.00")), ("100", destination_100, Decimal("100.00"))):
        if line["account_id"] != destination["ledger_account_id"] or _decimal(line["debit"], f"{case} {label} debit") != amount or _decimal(line["credit"], f"{case} {label} credit") != Decimal("0"):
            raise AssertionError(f"{case}: unexpected selected-bank line {label}: {line}")
    imported = _request_json("POST", "/api/banking/import", {"bank_account_id": destination["id"], "source_name": "V1-06-statement.csv", "content": "date,reference,amount,balance\n2026-03-01,V1-06-300,300.00,300.00\n2026-03-02,V1-06-900,900.00,1200.00\n"})
    reconciliation = _request_json("POST", "/api/banking/reconciliations", {"bank_account_id": destination["id"], "statement_id": imported["statement_id"], "as_of": "2026-03-03"})
    reconciliation_id = reconciliation["reconciliation_id"]
    with sqlite3.connect(db_path) as conn:
        external_rows = conn.execute("SELECT id,reference,amount,direction,external_balance FROM banktransaction WHERE statement_id=? ORDER BY id", (imported["statement_id"],)).fetchall()
        statement = conn.execute("SELECT bank_account_id,closing_balance FROM bankstatement WHERE id=?", (imported["statement_id"],)).fetchone()
    if statement is None or statement[0] != destination["id"] or _decimal(statement[1], f"{case} statement balance") != Decimal("1200.00") or len(external_rows) != 2:
        raise AssertionError(f"{case}: statement/external evidence differs: {statement}, {external_rows}")
    transactions = {row[1]: row for row in external_rows}
    if set(transactions) != {"V1-06-300", "V1-06-900"}:
        raise AssertionError(f"{case}: external references differ: {transactions}")
    for reference, expected in (("V1-06-300", Decimal("300.00")), ("V1-06-900", Decimal("900.00"))):
        row = transactions[reference]
        if _decimal(row[2], f"{case} {reference} amount") != expected or row[3] != "credit":
            raise AssertionError(f"{case}: external evidence differs for {reference}: {row}")
    if any(_decimal(row[2], f"{case} external amount") == Decimal("100.00") for row in external_rows):
        raise AssertionError(f"{case}: fabricated external 100.00 transaction exists: {external_rows}")
    for reference, line in (("V1-06-300", destination_300), ("V1-06-900", destination_900)):
        matched = _request_json("POST", "/api/banking/matches", {"reconciliation_id": reconciliation_id, "bank_transaction_id": transactions[reference][0], "journal_line_id": line["id"]})
        if not matched.get("match_id"):
            raise AssertionError(f"{case}: match lacks identity for {reference}: {matched}")
    view = _request_json("GET", f"/api/banking/reconciliations/{reconciliation_id}")
    if view.get("bank_account_id") != destination["id"]:
        raise AssertionError(f"{case}: reconciliation changed BankAccount: {view}")
    for field, expected in (("ledger_balance", Decimal("1300.00")), ("bank_balance", Decimal("1200.00")), ("difference", Decimal("100.00"))):
        if _decimal(view.get(field), f"{case} {field}") != expected:
            raise AssertionError(f"{case}: {field} differs: {view}")
    if view.get("missing_bank_transaction_ids") not in ([], ()) or view.get("missing_journal_line_ids") != [destination_100["id"]]:
        raise AssertionError(f"{case}: explicit unmatched evidence differs: {view}")
    line_by_bank = {row["bank_transaction_id"]: row for row in view.get("lines", [])}
    for reference, expected_line in (("V1-06-300", destination_300), ("V1-06-900", destination_900)):
        row = line_by_bank.get(transactions[reference][0])
        if row is None or row.get("state") != "matched" or row.get("journal_line_id") != expected_line["id"]:
            raise AssertionError(f"{case}: persisted match differs for {reference}: {view}")
    reopened = _request_json("GET", f"/api/banking/reconciliations/{reconciliation_id}")
    if reopened != view:
        raise AssertionError(f"{case}: reconciliation readback changed across sessions: {view} != {reopened}")
    with sqlite3.connect(db_path) as conn:
        entry_count = conn.execute("SELECT COUNT(*) FROM journalentry WHERE state='posted'").fetchone()[0]
        line_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
        external_count = conn.execute("SELECT COUNT(*) FROM banktransaction WHERE statement_id=?", (imported["statement_id"],)).fetchone()[0]
        match_rows = conn.execute("SELECT rm.bank_transaction_id,rm.journal_line_id,jl.account_id FROM reconciliationmatch rm JOIN journalline jl ON jl.id=rm.journal_line_id WHERE rm.reconciliation_id=? ORDER BY rm.id", (reconciliation_id,)).fetchall()
    if entry_count != 3 or line_count != 6 or external_count != 2 or len(match_rows) != 2 or any(row[2] != destination["ledger_account_id"] for row in match_rows):
        raise AssertionError(f"{case}: reconciliation persistence differs: entries={entry_count}, lines={line_count}, external={external_count}, matches={match_rows}")
    return {"V1-05": {"source_bank_account_id": source["id"], "destination_bank_account_id": destination["id"], "source_account_code": account_truth[source["ledger_account_id"]]["code"], "destination_account_code": account_truth[destination["ledger_account_id"]]["code"], "entry_id": transfer_300["entry_id"]}, "V1-06": {"reconciliation_id": reconciliation_id, "ledger_balance": view["ledger_balance"], "bank_balance": view["bank_balance"], "difference": view["difference"], "unmatched_journal_line_id": destination_100["id"]}}


def _assert_v1_07_v1_15_v1_22_osc(db_path: Path) -> dict:
    case = "V1-07 monetary donation"
    initial = _request_json("GET", "/api/onboarding")
    if initial.get("configured") is not False:
        raise AssertionError(f"{case}: OSC SQLite was not clean: {initial}")
    configured = _request_json("POST", "/api/onboarding", _osc_onboarding_payload())
    if configured.get("configured") is not True:
        raise AssertionError(f"{case}: OSC onboarding failed: {configured}")
    program = _request_json("POST", "/api/osc/programs", {"name": "Educación", "description": "Programa educativo", "budget": "50000.00"})
    programs = _request_json("GET", "/api/osc/programs")
    if len(programs) != 1 or programs[0].get("id") != program.get("id") or _decimal(program.get("budget"), f"{case} program budget") != Decimal("50000.00"):
        raise AssertionError(f"{case}: Program readback differs: {programs}")
    with sqlite3.connect(db_path) as conn:
        if conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0] != 0:
            raise AssertionError(f"{case}: Program creation wrote ledger truth")
    donor = _request_json("POST", "/api/subledger/third-parties", {"name": "Donante principal", "party_type": "other"})
    bank = _request_json("POST", "/api/banking/accounts", {"institution_name": "Banco OSC", "account_identifier": "OSC-001", "currency": "MXN"})
    fund = _request_json("POST", "/api/osc/funds", {"code": "EDU", "name": "Educación", "restriction": "restricted", "purpose": "Programa educativo", "program_id": program["id"]})
    source = _request_json("POST", "/api/osc/funding-sources", {"name": "Convenio principal", "donor_third_party_id": donor["id"], "external_reference": "CONV-001"})
    if fund.get("program_id") != program["id"]:
        raise AssertionError(f"{case}: Fund did not retain Program identity: {fund}")
    with sqlite3.connect(db_path) as conn:
        account_truth = conn.execute("SELECT child.code,child.origin,parent.code FROM account child LEFT JOIN account parent ON parent.id=child.parent_id WHERE child.id=?", (bank["ledger_account_id"],)).fetchone()
    if account_truth is None or account_truth[1] != "entity" or account_truth[2] != "1101" or account_truth[0] == "1101":
        raise AssertionError(f"{case}: selected bank is not a governed 1101 extension: {account_truth}")
    bank_code = account_truth[0]
    monetary = _request_json("POST", "/api/osc/donations/prepare", {"donor_name": donor["name"], "amount": "1000.00", "date": "2026-02-01", "bank_account_identifier": bank["account_identifier"], "document_type": "acta", "document_number": "DON-001", "document_date": "2026-02-01", "fund_name": fund["name"], "funding_source_name": source["name"], "program_name": program["name"], "restriction": "restricted", "purpose": "Programa educativo"})
    token = _assert_common_preview(monetary, amount="1000.00")
    common_json = json.dumps(monetary["preview"], sort_keys=True)
    if "Debe" in common_json or "Haber" in common_json or bank_code in common_json:
        raise AssertionError(f"{case}: common preview leaked accounting internals: {monetary['preview']}")
    professional_preview = _request_json("GET", f"/api/operations/{token}/professional-preview")
    bank_lines = [line for line in professional_preview.get("lines", []) if line.get("account_id") == bank["ledger_account_id"]]
    if len(bank_lines) != 1:
        raise AssertionError(f"{case}: professional preview lost selected bank: {professional_preview}")
    bank_preview = bank_lines[0]
    if bank_preview.get("account_code") != bank_code or bank_preview.get("side") != "debit" or _decimal(bank_preview.get("amount"), f"{case} professional bank amount") != Decimal("1000.00"):
        raise AssertionError(f"{case}: professional preview did not freeze specific bank truth: {bank_preview}")
    monetary_result = _request_json("POST", f"/api/operations/{token}/confirm")
    donation_id = monetary_result.get("donation_id"); receipt_id = monetary_result.get("fund_receipt_id")
    if not donation_id or not receipt_id or not monetary_result.get("entry_id"):
        raise AssertionError(f"{case}: confirmed donation lacks canonical identities: {monetary_result}")
    monetary_professional = _request_json("GET", f"/api/osc/donations/{donation_id}/professional")
    if monetary_professional.get("program", {}).get("id") != program["id"] or monetary_professional.get("fund", {}).get("id") != fund["id"] or monetary_professional.get("funding_source", {}).get("id") != source["id"] or monetary_professional.get("donor", {}).get("id") != donor["id"] or monetary_professional.get("document", {}).get("document_number") != "DON-001":
        raise AssertionError(f"{case}: professional readback lost OSC provenance: {monetary_professional}")
    ledger = monetary_professional.get("ledger", {})
    if ledger.get("entry_id") != monetary_result["entry_id"] or ledger.get("state") != "posted":
        raise AssertionError(f"{case}: donation ledger identity differs: {monetary_professional}")
    posted_bank_lines = [line for line in ledger.get("lines", []) if line.get("account_id") == bank["ledger_account_id"]]
    if len(posted_bank_lines) != 1 or _decimal(posted_bank_lines[0].get("debit"), f"{case} posted bank debit") != Decimal("1000.00") or monetary_professional.get("audit", {}).get("event_type") != "entry_posted":
        raise AssertionError(f"{case}: posted ledger/audit differs: {monetary_professional}")
    case = "V1-15 OSC traceability"
    expense = _request_json("POST", "/api/operations/prepare", {"operation_key": "utility_bank", "amount": "300.00", "posting_date": "2026-02-03"})
    expense_token = _assert_common_preview(expense, amount="300.00")
    expense_result = _request_json("POST", f"/api/operations/{expense_token}/confirm")
    candidates = _request_json("GET", "/api/osc/fund-candidates?kind=application")
    candidate = next((item for item in candidates if item.get("entry_id") == expense_result.get("entry_id")), None)
    if candidate is None:
        raise AssertionError(f"{case}: expense did not become an application candidate: {candidates}")
    application = _request_json("POST", "/api/osc/fund-applications", {"fund_id": fund["id"], "program_id": program["id"], "journal_line_id": candidate["journal_line_id"], "amount": "300.00", "receipt_id": receipt_id, "purpose": "Servicios del programa"})
    if application.get("program_id") != program["id"] or application.get("fund_id") != fund["id"]:
        raise AssertionError(f"{case}: FundApplication collapsed OSC identities: {application}")
    balance_path = f"/api/osc/funds/{fund['id']}/balance?as_of=2026-02-03"; trace_path = f"/api/osc/funds/{fund['id']}/traceability?as_of=2026-02-03"
    balance = _request_json("GET", balance_path)
    for field, expected in (("received", Decimal("1000.00")), ("applied", Decimal("300.00")), ("available", Decimal("700.00"))):
        if _decimal(balance.get(field), f"{case} {field}") != expected:
            raise AssertionError(f"{case}: balance {field} differs: {balance}")
    if balance.get("program_id") != program["id"]:
        raise AssertionError(f"{case}: balance lost Program identity: {balance}")
    trace = _request_json("GET", trace_path)
    receipts = trace.get("receipts", []); applications = trace.get("applications", [])
    if trace.get("fund", {}).get("program_id") != program["id"] or len(receipts) != 1 or receipts[0].get("source", {}).get("id") != source["id"] or len(applications) != 1 or applications[0].get("program_id") != program["id"] or _decimal(trace.get("received"), f"{case} trace received") != Decimal("1000.00") or _decimal(trace.get("applied"), f"{case} trace applied") != Decimal("300.00") or _decimal(trace.get("available"), f"{case} trace available") != Decimal("700.00"):
        raise AssertionError(f"{case}: traceability differs: {trace}")
    if _request_json("GET", balance_path) != balance or _request_json("GET", trace_path) != trace:
        raise AssertionError(f"{case}: balance/traceability changed across persisted readback")
    case = "V1-22 in-kind donation"
    inkind = _request_json("POST", "/api/osc/in-kind-donations/prepare", {"donor_name": donor["name"], "description": "Computadora donada", "quantity": "1", "date": "2026-02-02", "valuation_amount": "12000.00", "valuation_method": "avaluo", "valuation_evidence": "Avalúo firmado IK-001", "document_type": "constancia", "document_number": "IK-001", "document_date": "2026-02-02", "fund_name": fund["name"], "program_name": program["name"], "asset_code": "AF-IK-001", "asset_name": "Computadora donada", "useful_life_months": 36})
    inkind_token = _assert_common_preview(inkind, amount="12000.00")
    inkind_common = inkind.get("preview", {}); inkind_common_json = json.dumps(inkind_common, sort_keys=True)
    if "account_code" in inkind_common_json or "Debe" in inkind_common_json or "Haber" in inkind_common_json or inkind_common.get("cash_or_bank") != "Sin efectivo ni banco" or _decimal(inkind_common.get("amount"), f"{case} valuation") != Decimal("12000.00"):
        raise AssertionError(f"{case}: common preview differs: {inkind_common}")
    inkind_result = _request_json("POST", f"/api/operations/{inkind_token}/confirm"); inkind_id = inkind_result.get("inkind_donation_id")
    if not inkind_id or not inkind_result.get("entry_id"):
        raise AssertionError(f"{case}: confirmation lacks canonical identities: {inkind_result}")
    inkind_professional = _request_json("GET", f"/api/osc/in-kind-donations/{inkind_id}/professional")
    valuation = inkind_professional.get("valuation", {})
    if inkind_professional.get("donor", {}).get("id") != donor["id"] or inkind_professional.get("document", {}).get("document_number") != "IK-001" or inkind_professional.get("program", {}).get("id") != program["id"] or inkind_professional.get("fund", {}).get("id") != fund["id"] or _decimal(valuation.get("amount"), f"{case} professional valuation") != Decimal("12000.00") or valuation.get("method") != "avaluo" or valuation.get("evidence") != "Avalúo firmado IK-001" or inkind_professional.get("fixed_asset", {}).get("code") != "AF-IK-001" or inkind_professional.get("cash_or_bank") != [] or inkind_professional.get("ledger", {}).get("cash_or_bank_lines", []) != [] or inkind_professional.get("ledger", {}).get("entry_id") != inkind_result["entry_id"] or inkind_professional.get("fiscality", {}).get("supported") is not False:
        raise AssertionError(f"{case}: professional reconstruction differs: {inkind_professional}")
    reopened_programs = _request_json("GET", "/api/osc/programs")
    if len(reopened_programs) != 1 or reopened_programs[0].get("id") != program["id"]:
        raise AssertionError(f"{case}: Program identity changed after OSC journeys: {reopened_programs}")
    with sqlite3.connect(db_path) as conn:
        entry_count = conn.execute("SELECT COUNT(*) FROM journalentry WHERE state='posted'").fetchone()[0]
        counts = tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("donation", "inkinddonation", "fund", "program", "fundingsource"))
    if entry_count != 3 or counts != (1, 1, 1, 1, 1):
        raise AssertionError(f"V1-07/V1-15/V1-22 persistence differs: entries={entry_count}, counts={counts}")
    return {"V1-07": {"donation_id": donation_id, "entry_id": monetary_result["entry_id"], "bank_account_id": bank["id"], "bank_account_code": bank_code}, "V1-15": {"fund_id": fund["id"], "program_id": program["id"], "funding_source_id": source["id"], "received": balance["received"], "applied": balance["applied"], "available": balance["available"]}, "V1-22": {"inkind_donation_id": inkind_id, "entry_id": inkind_result["entry_id"], "program_id": program["id"]}}


def _assert_v1_03_v1_18_correction(db_path: Path) -> dict:
    case = "V1-03 cash purchase/expense"
    if _request_json("GET", "/api/onboarding").get("configured") is not False:
        raise AssertionError(f"{case}: correction SQLite was not clean")
    _request_json("POST", "/api/onboarding", _onboarding_payload())
    prepared = _request_json("POST", "/api/operations/prepare", {"operation_key": "utility_bank", "amount": "150.00", "posting_date": "2026-04-01"})
    token = _assert_common_preview(prepared, amount="150.00")
    common_json = json.dumps(prepared.get("preview", {}), sort_keys=True)
    if "Debe" in common_json or "Haber" in common_json:
        raise AssertionError(f"{case}: common preview leaked debit/credit language: {prepared}")
    professional_preview = _request_json("GET", f"/api/operations/{token}/professional-preview")
    preview_lines = professional_preview.get("lines", [])
    by_code = {line.get("account_code"): line for line in preview_lines}
    if set(by_code) != {"5102", "1101"}:
        raise AssertionError(f"{case}: professional preview accounts differ: {professional_preview}")
    if by_code["5102"].get("side") != "debit" or _decimal(by_code["5102"].get("amount"), f"{case} expense") != Decimal("150.00") or by_code["1101"].get("side") != "credit" or _decimal(by_code["1101"].get("amount"), f"{case} bank") != Decimal("150.00"):
        raise AssertionError(f"{case}: professional preview amounts/sides differ: {professional_preview}")
    original = _request_json("POST", f"/api/operations/{token}/confirm")
    original_id = original.get("entry_id")
    if not original_id or original.get("state") != "posted":
        raise AssertionError(f"{case}: expense did not post canonically: {original}")
    original_professional = _request_json("GET", f"/api/operations/{original_id}/professional")
    if original_professional.get("state") != "posted" or original_professional.get("audit", {}).get("event_type") != "entry_posted":
        raise AssertionError(f"{case}: professional readback differs: {original_professional}")
    with sqlite3.connect(db_path) as conn:
        original_lines_before = conn.execute("SELECT id,account_code,debit,credit,description FROM journalline WHERE entry_id=? ORDER BY id", (original_id,)).fetchall()
    if len(original_lines_before) != 2:
        raise AssertionError(f"{case}: original persisted lines differ: {original_lines_before}")

    case = "V1-18 correction by reversal"
    reversed_result = _request_json("POST", f"/api/operations/{original_id}/reverse", {"reason": "Importe capturado incorrectamente: 150 debía ser 120", "reversal_date": "2026-04-02"})
    reversal_id = reversed_result.get("reversal_entry_id")
    if reversed_result.get("original_entry_id") != original_id or not reversal_id or reversed_result.get("reason") != "Importe capturado incorrectamente: 150 debía ser 120" or not reversed_result.get("audit_event_id"):
        raise AssertionError(f"{case}: reversal result lacks canonical provenance: {reversed_result}")
    original_after = _request_json("GET", f"/api/operations/{original_id}/professional")
    reversal_view = original_after.get("reversal", {})
    if original_after.get("state") != "reversed" or reversal_view.get("original_entry_id") != original_id or reversal_view.get("reversal_entry_id") != reversal_id or reversal_view.get("reason") != reversed_result["reason"]:
        raise AssertionError(f"{case}: original professional history differs: {original_after}")

    replacement_prepared = _request_json("POST", "/api/operations/prepare", {"operation_key": "utility_bank", "amount": "120.00", "posting_date": "2026-04-02"})
    replacement_token = _assert_common_preview(replacement_prepared, amount="120.00")
    replacement = _request_json("POST", f"/api/operations/{replacement_token}/confirm")
    replacement_id = replacement.get("entry_id")
    if not replacement_id or replacement.get("state") != "posted" or replacement_id in (original_id, reversal_id):
        raise AssertionError(f"{case}: replacement identity/state differs: {replacement}")
    replacement_professional = _request_json("GET", f"/api/operations/{replacement_id}/professional")
    if replacement_professional.get("state") != "posted" or replacement_professional.get("reversal") is not None:
        raise AssertionError(f"{case}: replacement professional state differs: {replacement_professional}")

    with sqlite3.connect(db_path) as conn:
        original_lines_after = conn.execute("SELECT id,account_code,debit,credit,description FROM journalline WHERE entry_id=? ORDER BY id", (original_id,)).fetchall()
        relation = conn.execute("SELECT original_entry_id,reversal_entry_id,reason FROM journalentryreversal WHERE original_entry_id=?", (original_id,)).fetchone()
        states = conn.execute("SELECT id,state FROM journalentry ORDER BY id").fetchall()
        net_rows = conn.execute("SELECT account_code,debit,credit FROM journalline ORDER BY id").fetchall()
        reversal_audits = conn.execute("SELECT id,details_json FROM auditevent WHERE event_type='entry_reversed' ORDER BY id").fetchall()
    if original_lines_after != original_lines_before:
        raise AssertionError(f"{case}: reversal mutated original JournalLines: before={original_lines_before}, after={original_lines_after}")
    if relation != (original_id, reversal_id, reversed_result["reason"]):
        raise AssertionError(f"{case}: durable reversal relation differs: {relation}")
    if len(states) != 3 or dict(states).get(original_id) != "reversed" or dict(states).get(reversal_id) != "posted" or dict(states).get(replacement_id) != "posted":
        raise AssertionError(f"{case}: original/reversal/replacement states differ: {states}")
    net = {}
    for code, debit, credit in net_rows:
        net[code] = net.get(code, Decimal("0")) + _decimal(debit, f"{case} {code} debit") - _decimal(credit, f"{case} {code} credit")
    if net.get("5102") != Decimal("120.00") or net.get("1101") != Decimal("-120.00"):
        raise AssertionError(f"{case}: corrected net truth is not 120: {net}")
    matching_audits = []
    for audit_id, details_json in reversal_audits:
        details = json.loads(details_json)
        if details.get("original_entry_id") == original_id:
            matching_audits.append((audit_id, details))
    if len(matching_audits) != 1 or matching_audits[0][0] != reversed_result["audit_event_id"] or matching_audits[0][1].get("reversal_entry_id") != reversal_id or matching_audits[0][1].get("reason") != reversed_result["reason"]:
        raise AssertionError(f"{case}: reversal audit differs: {matching_audits}")
    if _request_json("GET", f"/api/operations/{original_id}/professional") != original_after:
        raise AssertionError(f"{case}: original history changed across readback")
    return {"V1-03": {"entry_id": original_id, "amount": "150.00", "expense_account": "5102", "bank_account": "1101"}, "V1-18": {"original_entry_id": original_id, "reversal_entry_id": reversal_id, "replacement_entry_id": replacement_id, "net_expense": str(net["5102"]), "reason": reversed_result["reason"]}}


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


def _run_server_case(console, workdir, env, log_path, assertion, label):
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(console)], cwd=workdir, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
        try:
            integrity = _wait_for_surface(process, log_path)
            if not integrity.get("healthy"):
                raise AssertionError(f"{label}: clean integrity failed: {integrity}")
            result = assertion()
            post_integrity = _request_json("GET", "/api/system/integrity")
            if not post_integrity.get("healthy"):
                raise AssertionError(f"{label}: post-flow integrity failed: {post_integrity}")
            return result
        finally:
            forced_kill = _terminate_process(process)
            if forced_kill:
                raise AssertionError(f"{label}: Aqorath did not shut down cleanly")


def _install_and_run(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="aqorath-installed-v1-") as temp:
        root = Path(temp); venv_dir = root / "venv"; workdir = root / "outside-checkout"; workdir.mkdir()
        db_path = root / "user-data" / "aqorath.db"; banking_db_path = root / "banking-data" / "aqorath.db"; osc_db_path = root / "osc-data" / "aqorath.db"; correction_db_path = root / "correction-data" / "aqorath.db"
        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
        bindir = _venv_bin(venv_dir); python = bindir / ("python.exe" if os.name == "nt" else "python")
        _run([python, "-m", "pip", "install", "--disable-pip-version-check", str(wheel)])
        console = bindir / ("aqorath.exe" if os.name == "nt" else "aqorath")
        if not console.is_file():
            raise AssertionError(f"console script missing: {console}")
        guard_dir, attempts = _write_offline_guard(root)
        env = os.environ.copy(); env.pop("PYTHONPATH", None); env["AQORATH_SMOKE_REPO_ROOT"] = str(REPO_ROOT); env["AQORATH_DB"] = str(db_path); env["AQORATH_OFFLINE_ATTEMPTS"] = str(attempts); env["PYTHONPATH"] = str(guard_dir)

        def core_case():
            entry_id = _assert_v1_01_http_flow(); credit_results = _assert_v1_02_and_v1_04_http_flows(); _post_artifact("/api/system/backup"); _post_artifact("/api/system/portable-export")
            return entry_id, credit_results
        entry_id, credit_results = _run_server_case(console, workdir, env, root / "aqorath-v1.log", core_case, "V1-01/V1-02/V1-04")
        print(f"installed V1-01 entry_id={entry_id}"); print("installed credit journeys=" + json.dumps(credit_results, sort_keys=True))
        if not db_path.is_file(): raise AssertionError(f"installed V1 flow did not create SQLite DB: {db_path}")
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT account_code,debit,credit FROM journalline ORDER BY id").fetchall(); entries = conn.execute("SELECT COUNT(*) FROM journalentry WHERE state='posted'").fetchone()[0]; open_items = conn.execute("SELECT COUNT(*) FROM openitem").fetchone()[0]; applications = conn.execute("SELECT COUNT(*) FROM openitemapplication").fetchone()[0]
        if rows[:2] != [("1102", "200.00", "0"), ("4201", "0", "200.00")] or entries != 7 or open_items != 2 or applications != 4:
            raise AssertionError(f"installed core persistence differs: rows={rows[:2]}, entries={entries}, open_items={open_items}, applications={applications}")

        banking_env = env.copy(); banking_env["AQORATH_DB"] = str(banking_db_path)
        banking_results = _run_server_case(console, workdir, banking_env, root / "aqorath-banking-v1.log", lambda: _assert_v1_05_and_v1_06_banking(banking_db_path), "V1-05/V1-06")
        print("installed banking journeys=" + json.dumps(banking_results, sort_keys=True))
        if not banking_db_path.is_file(): raise AssertionError(f"installed banking flow did not create SQLite DB: {banking_db_path}")
        with sqlite3.connect(banking_db_path) as conn:
            if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or conn.execute("SELECT COUNT(*) FROM bankaccount").fetchone()[0] != 2:
                raise AssertionError("installed banking persistence/integrity differs")

        osc_env = env.copy(); osc_env["AQORATH_DB"] = str(osc_db_path)
        osc_results = _run_server_case(console, workdir, osc_env, root / "aqorath-osc-v1.log", lambda: _assert_v1_07_v1_15_v1_22_osc(osc_db_path), "V1-07/V1-15/V1-22")
        print("installed OSC journeys=" + json.dumps(osc_results, sort_keys=True))
        if not osc_db_path.is_file(): raise AssertionError(f"installed OSC flow did not create SQLite DB: {osc_db_path}")
        with sqlite3.connect(osc_db_path) as conn:
            if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]: raise AssertionError("installed OSC SQLite integrity_check failed")

        correction_env = env.copy(); correction_env["AQORATH_DB"] = str(correction_db_path)
        correction_results = _run_server_case(console, workdir, correction_env, root / "aqorath-correction-v1.log", lambda: _assert_v1_03_v1_18_correction(correction_db_path), "V1-03/V1-18")
        print("installed correction journeys=" + json.dumps(correction_results, sort_keys=True))
        if not correction_db_path.is_file(): raise AssertionError(f"installed correction flow did not create SQLite DB: {correction_db_path}")
        with sqlite3.connect(correction_db_path) as conn:
            if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]: raise AssertionError("installed correction SQLite integrity_check failed")

        if attempts.exists() and attempts.read_text(encoding="utf-8").strip():
            raise AssertionError("installed V1 flow attempted external network access:\n" + attempts.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--wheel", required=True, type=Path); args = parser.parse_args(); wheel = args.wheel.resolve()
    if not wheel.is_file(): raise SystemExit(f"wheel not found: {wheel}")
    _install_and_run(wheel)
    print("AQR-015 installed V1-01/V1-02/V1-03/V1-04/V1-05/V1-06/V1-07/V1-15/V1-18/V1-22 smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
