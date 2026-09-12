"""Installed-wheel technical acceptance for V1-16 recovery and V1-17 portability.

The product is driven only through its loopback HTTP surface. Portable-export
inspection intentionally uses only Python's standard library and never imports an
Aqorath persistence or domain authority.
"""

from __future__ import annotations

import base64
from decimal import Decimal
import io
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

import _installed_v1_core_cases as core


BACKUP_FORMAT = "aqorath-backup-v1"
PORTABLE_FORMAT = "aqorath-portable-export-v1"
RESTORE_HEADER = "X-Aqorath-Confirm-Restore"


def _raw_request(method: str, path: str, *, body: bytes | None = None, headers=None):
    request = Request(
        f"http://127.0.0.1:{core.DEFAULT_PORT}{path}",
        data=body,
        headers=dict(headers or {}),
        method=method,
    )
    with urlopen(request, timeout=15) as response:
        return response.status, dict(response.headers.items()), response.read()


def _raw_error(
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers=None,
    expected_status: int,
):
    try:
        _raw_request(method, path, body=body, headers=headers)
    except HTTPError as exc:
        payload = exc.read()
        if exc.code != expected_status:
            raise AssertionError(
                f"{method} {path} returned {exc.code}, expected {expected_status}: "
                f"{payload.decode('utf-8', 'replace')}"
            ) from exc
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"detail": payload.decode("utf-8", "replace")}
    raise AssertionError(f"{method} {path} unexpectedly succeeded")


def _json_from_raw(method: str, path: str, *, body=None, headers=None):
    status, response_headers, payload = _raw_request(
        method, path, body=body, headers=headers
    )
    if status != 200:
        raise AssertionError(f"{method} {path} returned {status}")
    return json.loads(payload.decode("utf-8")), response_headers


def _post_common(operation_key: str, amount: str, posting_date: str) -> dict:
    prepared = core._request_json(
        "POST",
        "/api/operations/prepare",
        {
            "operation_key": operation_key,
            "amount": amount,
            "posting_date": posting_date,
        },
    )
    token = core._assert_common_preview(prepared, amount=amount)
    posted = core._request_json("POST", f"/api/operations/{token}/confirm")
    if posted.get("state") != "posted" or not posted.get("entry_id"):
        raise AssertionError(f"V1-16 fixture did not post canonically: {posted}")
    return posted


def _healthy_integrity(label: str) -> dict:
    value = core._request_json("GET", "/api/system/integrity")
    if (
        value.get("healthy") is not True
        or value.get("sqlite_integrity") is not True
        or value.get("schema_current") is not True
        or value.get("foreign_key_violations") != []
        or value.get("errors") != []
    ):
        raise AssertionError(f"{label}: installation integrity is not healthy: {value}")
    return value


def _assert_missing_entry(entry_id: int, label: str):
    missing = core._request_error(
        "GET", f"/api/operations/{entry_id}/professional", expected_status=404
    )
    if not missing.get("detail"):
        raise AssertionError(f"{label}: missing operation did not explain absence: {missing}")


def assert_v1_16_restore_http(db_path: Path) -> dict:
    """Backup, mutate, reject unconfirmed restore, restore, and read back in-process."""
    initial = core._request_json("GET", "/api/onboarding")
    if initial.get("configured") is not False:
        raise AssertionError(f"V1-16: recovery database was not clean: {initial}")
    configured = core._request_json("POST", "/api/onboarding", core._onboarding_payload())
    if configured.get("configured") is not True:
        raise AssertionError(f"V1-16: onboarding failed: {configured}")

    baseline_posted = _post_common("sale_cash", "200.00", "2026-03-10")
    baseline_id = int(baseline_posted["entry_id"])
    baseline = core._request_json(
        "GET", f"/api/operations/{baseline_id}/professional"
    )
    before_integrity = _healthy_integrity("V1-16 before backup")

    status, backup_headers, backup_bytes = _raw_request("POST", "/api/system/backup")
    if status != 200 or not backup_bytes.startswith(b"PK"):
        raise AssertionError("V1-16: HTTP backup was not a non-empty ZIP response")
    if "application/zip" not in backup_headers.get("Content-Type", ""):
        raise AssertionError(f"V1-16: backup media type differs: {backup_headers}")
    if not backup_headers.get("X-Aqorath-Artifact-Sha256"):
        raise AssertionError("V1-16: backup HTTP response lacks artifact digest")
    try:
        with ZipFile(io.BytesIO(backup_bytes), "r") as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise AssertionError("V1-16: HTTP backup is not independently readable") from exc
    if manifest.get("format") != BACKUP_FORMAT:
        raise AssertionError(f"V1-16: unexpected backup format: {manifest}")

    mutation_posted = _post_common("utility_bank", "75.00", "2026-03-11")
    mutation_id = int(mutation_posted["entry_id"])
    mutation = core._request_json(
        "GET", f"/api/operations/{mutation_id}/professional"
    )

    rejected = _raw_error(
        "POST",
        "/api/system/restore",
        body=backup_bytes,
        headers={"Content-Type": "application/zip"},
        expected_status=400,
    )
    if "confirmation" not in rejected.get("detail", "").lower():
        raise AssertionError(
            f"V1-16: restore without explicit header failed for wrong reason: {rejected}"
        )
    after_rejection = core._request_json(
        "GET", f"/api/operations/{mutation_id}/professional"
    )
    if after_rejection != mutation:
        raise AssertionError(
            "V1-16: rejected unconfirmed restore changed the later mutation"
        )
    _healthy_integrity("V1-16 after rejected restore")

    restored, _ = _json_from_raw(
        "POST",
        "/api/system/restore",
        body=backup_bytes,
        headers={
            "Content-Type": "application/zip",
            RESTORE_HEADER: "RESTORE",
        },
    )
    if (
        restored.get("restored") is not True
        or not restored.get("package_id")
        or not restored.get("pre_restore_backup_path")
        or restored.get("preserved_corrupt_path") is not None
    ):
        raise AssertionError(f"V1-16: explicit restore result differs: {restored}")

    same_process = core._request_json(
        "GET", f"/api/operations/{baseline_id}/professional"
    )
    if same_process != baseline:
        raise AssertionError(
            "V1-16: restored baseline readback differs in the same server process"
        )
    _assert_missing_entry(mutation_id, "V1-16 same-process restore")
    after_restore_integrity = _healthy_integrity("V1-16 after explicit restore")

    return {
        "baseline_entry_id": baseline_id,
        "mutation_entry_id": mutation_id,
        "baseline": baseline,
        "backup_package_id": manifest["package_id"],
        "pre_restore_backup_path": restored["pre_restore_backup_path"],
        "schema_version": after_restore_integrity["schema_version"],
        "integrity_before": before_integrity["healthy"],
    }


def assert_v1_16_reopen(expected: dict) -> dict:
    """Prove the restored readback survives a real server restart."""
    onboarding = core._request_json("GET", "/api/onboarding")
    if onboarding.get("configured") is not True:
        raise AssertionError(f"V1-16 reopen: restored onboarding disappeared: {onboarding}")
    baseline = core._request_json(
        "GET", f"/api/operations/{expected['baseline_entry_id']}/professional"
    )
    if baseline != expected["baseline"]:
        raise AssertionError("V1-16 reopen: baseline readback changed after restart")
    _assert_missing_entry(expected["mutation_entry_id"], "V1-16 reopen")
    integrity = _healthy_integrity("V1-16 reopen")
    if integrity.get("schema_version") != expected["schema_version"]:
        raise AssertionError(
            f"V1-16 reopen: schema changed across restart: {integrity}"
        )
    return {
        "baseline_entry_id": expected["baseline_entry_id"],
        "mutation_absent": True,
        "healthy": True,
        "schema_version": integrity["schema_version"],
    }


def _decode_cell(cell: dict):
    kind = cell.get("type")
    value = cell.get("value")
    if kind == "null":
        if value is not None:
            raise AssertionError(f"V1-17: invalid null cell: {cell}")
        return None
    if kind == "integer":
        return int(value)
    if kind == "real":
        return value
    if kind == "text":
        return value
    if kind == "blob-base64":
        return base64.b64decode(value, validate=True)
    raise AssertionError(f"V1-17: unknown portable cell type: {cell}")


def _read_table(archive: ZipFile, table: str):
    payload = json.loads(archive.read(f"data/{table}.json").decode("utf-8"))
    if payload.get("table") != table:
        raise AssertionError(f"V1-17: table payload identity differs for {table}")
    columns = payload.get("columns")
    rows = payload.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise AssertionError(f"V1-17: malformed table payload for {table}")
    decoded = [dict(zip(columns, (_decode_cell(cell) for cell in row))) for row in rows]
    return columns, rows, decoded


def _assert_relational_archive(archive: ZipFile, manifest: dict, schema: dict):
    table_names = set(manifest.get("tables", []))
    schema_tables = schema.get("tables", {})
    if table_names != set(schema_tables):
        raise AssertionError("V1-17: manifest and schema table sets differ")

    decoded = {}
    typed = {}
    for table in sorted(table_names):
        member = f"data/{table}.json"
        if member not in archive.namelist():
            raise AssertionError(f"V1-17: missing portable member {member}")
        _, typed_rows, decoded_rows = _read_table(archive, table)
        typed[table] = typed_rows
        decoded[table] = decoded_rows
        if manifest.get("row_counts", {}).get(table) != len(decoded_rows):
            raise AssertionError(f"V1-17: row count differs for {table}")

    for table, table_schema in schema_tables.items():
        pk_columns = [
            column["name"]
            for column in sorted(
                table_schema.get("columns", []),
                key=lambda value: value.get("primary_key_position", 0),
            )
            if column.get("primary_key_position", 0)
        ]
        if pk_columns:
            keys = [tuple(row[name] for name in pk_columns) for row in decoded[table]]
            if any(any(value is None for value in key) for key in keys):
                raise AssertionError(f"V1-17: null primary key in {table}")
            if len(keys) != len(set(keys)):
                raise AssertionError(f"V1-17: duplicate primary key in {table}")

        for fk in table_schema.get("foreign_keys", []):
            target_table = fk["table"]
            source_column = fk["from"]
            target_column = fk["to"]
            if target_table not in decoded:
                raise AssertionError(
                    f"V1-17: FK target {target_table} is absent from portable data"
                )
            target_values = {row[target_column] for row in decoded[target_table]}
            for row in decoded[table]:
                value = row[source_column]
                if value is not None and value not in target_values:
                    raise AssertionError(
                        f"V1-17: broken FK {table}.{source_column} -> "
                        f"{target_table}.{target_column}: {value}"
                    )
    return typed, decoded


def assert_v1_17_portable_http(expected: dict) -> dict:
    """Download through HTTP and inspect with stdlib only, outside Aqorath."""
    status, headers, content = _raw_request("POST", "/api/system/portable-export")
    if status != 200 or not content.startswith(b"PK"):
        raise AssertionError("V1-17: portable export was not a ZIP response")
    if "application/zip" not in headers.get("Content-Type", ""):
        raise AssertionError(f"V1-17: portable media type differs: {headers}")
    if not headers.get("X-Aqorath-Artifact-Sha256"):
        raise AssertionError("V1-17: portable response lacks artifact digest")

    try:
        archive = ZipFile(io.BytesIO(content), "r")
    except BadZipFile as exc:
        raise AssertionError("V1-17: portable HTTP body is not a readable ZIP") from exc

    with archive:
        names = set(archive.namelist())
        required = {"manifest.json", "schema.json", "reconciliation.json"}
        if not required <= names:
            raise AssertionError(f"V1-17: portable archive lacks {required - names}")
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        schema = json.loads(archive.read("schema.json").decode("utf-8"))
        reconciliation = json.loads(
            archive.read("reconciliation.json").decode("utf-8")
        )
        if manifest.get("format") != PORTABLE_FORMAT:
            raise AssertionError(f"V1-17: portable format differs: {manifest}")
        if not any(name.startswith("data/") and name.endswith(".json") for name in names):
            raise AssertionError("V1-17: portable archive has no data/*.json members")
        if not manifest.get("encoding", {}).get("blob-base64", "").startswith("RFC 4648"):
            raise AssertionError(f"V1-17: BLOB encoding contract differs: {manifest}")

        typed, decoded = _assert_relational_archive(archive, manifest, schema)
        if not {"journalentry", "journalline"} <= set(decoded):
            raise AssertionError("V1-17: journal relational truth is absent")

        entries = decoded["journalentry"]
        lines = decoded["journalline"]
        entry_ids = {row["id"] for row in entries}
        if expected["baseline_entry_id"] not in entry_ids:
            raise AssertionError("V1-17: restored baseline JournalEntry is absent")
        if expected["mutation_entry_id"] in entry_ids:
            raise AssertionError("V1-17: post-backup mutation leaked into restored export")
        if any(line["entry_id"] not in entry_ids for line in lines):
            raise AssertionError("V1-17: JournalLine -> JournalEntry relation is broken")

        journal_columns = json.loads(
            archive.read("data/journalline.json").decode("utf-8")
        )["columns"]
        debit_index = journal_columns.index("debit")
        credit_index = journal_columns.index("credit")
        baseline_typed = [
            row
            for row, decoded_row in zip(typed["journalline"], lines)
            if decoded_row["entry_id"] == expected["baseline_entry_id"]
        ]
        if len(baseline_typed) != 2:
            raise AssertionError(f"V1-17: baseline line cardinality differs: {baseline_typed}")
        money_cells = [
            row[debit_index] for row in baseline_typed if row[debit_index]["value"] != "0"
        ] + [
            row[credit_index] for row in baseline_typed if row[credit_index]["value"] != "0"
        ]
        if money_cells != [
            {"type": "text", "value": "200.00"},
            {"type": "text", "value": "200.00"},
        ]:
            raise AssertionError(
                f"V1-17: exact monetary text representation differs: {money_cells}"
            )

        debit_total = sum((Decimal(str(row["debit"])) for row in lines), Decimal("0"))
        credit_total = sum((Decimal(str(row["credit"])) for row in lines), Decimal("0"))
        if debit_total != Decimal("200.00") or credit_total != Decimal("200.00"):
            raise AssertionError(
                f"V1-17: exact decoded totals differ: {debit_total}/{credit_total}"
            )
        if reconciliation != {
            "available": True,
            "entry_count": 1,
            "line_count": 2,
            "debit_total": "200.00",
            "credit_total": "200.00",
            "balanced": True,
        }:
            raise AssertionError(
                f"V1-17: reconciliation does not match restored ledger: {reconciliation}"
            )

    return {
        "format": manifest["format"],
        "table_count": len(manifest["tables"]),
        "entry_count": reconciliation["entry_count"],
        "line_count": reconciliation["line_count"],
        "debit_total": reconciliation["debit_total"],
        "credit_total": reconciliation["credit_total"],
        "balanced": reconciliation["balanced"],
    }


__all__ = [
    "assert_v1_16_restore_http",
    "assert_v1_16_reopen",
    "assert_v1_17_portable_http",
]
