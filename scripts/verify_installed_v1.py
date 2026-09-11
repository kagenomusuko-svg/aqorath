#!/usr/bin/env python3
"""AQR-015 clean-wheel V1-01 acceptance smoke.

This harness deliberately runs the product from an isolated virtual environment
and a working directory outside the repository.  It drives the canonical
loopback HTTP surface through onboarding, a common V1-01 sale/cash flow, the
professional readback of the same persisted truth, and AQR-014 recovery/export
endpoints while an offline guard rejects any non-loopback network access.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
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
    token = prepared.get("token")
    common = prepared.get("preview", {})
    if not token or common.get("amount") != "200.00":
        raise AssertionError(f"invalid common V1-01 preview: {prepared}")
    if "account_code" in json.dumps(common, sort_keys=True):
        raise AssertionError(f"common preview leaked professional account codes: {common}")

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


def _install_and_run(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="aqorath-installed-v1-") as temp:
        root = Path(temp)
        venv_dir = root / "venv"
        workdir = root / "outside-checkout"
        db_path = root / "user-data" / "aqorath.db"
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
            forced_kill = False
            try:
                integrity = _wait_for_surface(process, log_path)
                if not integrity.get("healthy"):
                    raise AssertionError(f"clean installed integrity failed: {integrity}")
                entry_id = _assert_v1_01_http_flow()
                post_integrity = _request_json("GET", "/api/system/integrity")
                if not post_integrity.get("healthy"):
                    raise AssertionError(
                        f"post-V1-01 integrity check failed: {post_integrity}"
                    )
                _post_artifact("/api/system/backup")
                _post_artifact("/api/system/portable-export")
                print(f"installed V1-01 entry_id={entry_id}")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        forced_kill = True
                        process.kill()
                        process.wait(timeout=5)
            if forced_kill:
                raise AssertionError("installed Aqorath did not shut down cleanly")

        if attempts.exists() and attempts.read_text(encoding="utf-8").strip():
            raise AssertionError(
                "installed V1 flow attempted external network access:\n"
                + attempts.read_text(encoding="utf-8")
            )
        if not db_path.is_file():
            raise AssertionError(f"installed V1 flow did not create SQLite DB: {db_path}")
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT account_code,debit,credit FROM journalline ORDER BY id"
            ).fetchall()
        if rows != [("1102", "200.00", "0"), ("4201", "0", "200.00")]:
            raise AssertionError(f"installed SQLite truth differs from V1-01: {rows}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", required=True, type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file():
        raise SystemExit(f"wheel not found: {wheel}")
    _install_and_run(wheel)
    print("AQR-015 installed V1-01 smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
