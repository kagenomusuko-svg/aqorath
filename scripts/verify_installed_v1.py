#!/usr/bin/env python3
"""Authoritative AQR-015 installed-product acceptance harness.

One wheel is installed once into one isolated virtualenv. Domain helpers exercise
independent SQLite databases over the real loopback product surface while the
offline guard remains active. This is TECHNICAL_INSTALLED evidence only.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import venv

import _installed_v1_core_cases as core
import installed_v1_assets_periods_case as assets_periods
import installed_v1_cfdi_case as cfdi
import installed_v1_fiscal_case as fiscal


def _integrity(path: Path, label: str):
    if not path.is_file():
        raise AssertionError(f"{label} did not create SQLite DB: {path}")
    with sqlite3.connect(path) as conn:
        if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise AssertionError(f"{label} SQLite integrity_check failed")


def _install_and_run(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="aqorath-installed-v1-") as temp:
        root = Path(temp)
        venv_dir = root / "venv"
        workdir = root / "outside-checkout"
        workdir.mkdir()

        db_path = root / "user-data" / "aqorath.db"
        banking_db_path = root / "banking-data" / "aqorath.db"
        osc_db_path = root / "osc-data" / "aqorath.db"
        correction_db_path = root / "correction-data" / "aqorath.db"
        assets_db_path = root / "assets-data" / "aqorath.db"
        periods_db_path = root / "periods-data" / "aqorath.db"
        reporting_db_path = root / "reporting-data" / "aqorath.db"
        cfdi_db_path = root / "cfdi-data" / "aqorath.db"
        fiscal_db_path = root / "fiscal-data" / "aqorath.db"
        period_backup_root = root / "period-backups"

        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
        bindir = core._venv_bin(venv_dir)
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        core._run([python, "-m", "pip", "install", "--disable-pip-version-check", str(wheel)])
        console = bindir / ("aqorath.exe" if os.name == "nt" else "aqorath")
        if not console.is_file():
            raise AssertionError(f"console script missing: {console}")

        guard_dir, attempts = core._write_offline_guard(root)
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["AQORATH_SMOKE_REPO_ROOT"] = str(core.REPO_ROOT)
        env["AQORATH_DB"] = str(db_path)
        env["AQORATH_OFFLINE_ATTEMPTS"] = str(attempts)
        env["PYTHONPATH"] = str(guard_dir)

        def core_case():
            entry_id = core._assert_v1_01_http_flow()
            credit_results = core._assert_v1_02_and_v1_04_http_flows()
            core._post_artifact("/api/system/backup")
            core._post_artifact("/api/system/portable-export")
            return entry_id, credit_results

        entry_id, credit_results = core._run_server_case(console, workdir, env, root / "aqorath-v1.log", core_case, "V1-01/V1-02/V1-04")
        print(f"installed V1-01 entry_id={entry_id}")
        print("installed credit journeys=" + json.dumps(credit_results, sort_keys=True))
        _integrity(db_path, "installed core flow")
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute("SELECT account_code,debit,credit FROM journalline ORDER BY id").fetchall()
            entries = conn.execute("SELECT COUNT(*) FROM journalentry WHERE state='posted'").fetchone()[0]
            open_items = conn.execute("SELECT COUNT(*) FROM openitem").fetchone()[0]
            applications = conn.execute("SELECT COUNT(*) FROM openitemapplication").fetchone()[0]
        if rows[:2] != [("1102", "200.00", "0"), ("4201", "0", "200.00")] or entries != 7 or open_items != 2 or applications != 4:
            raise AssertionError(f"installed core persistence differs: rows={rows[:2]}, entries={entries}, open_items={open_items}, applications={applications}")

        banking_env = env.copy(); banking_env["AQORATH_DB"] = str(banking_db_path)
        banking_results = core._run_server_case(console, workdir, banking_env, root / "aqorath-banking-v1.log", lambda: core._assert_v1_05_and_v1_06_banking(banking_db_path), "V1-05/V1-06")
        print("installed banking journeys=" + json.dumps(banking_results, sort_keys=True))
        _integrity(banking_db_path, "installed banking flow")
        with sqlite3.connect(banking_db_path) as conn:
            if conn.execute("SELECT COUNT(*) FROM bankaccount").fetchone()[0] != 2:
                raise AssertionError("installed banking persistence differs")

        osc_env = env.copy(); osc_env["AQORATH_DB"] = str(osc_db_path)
        osc_results = core._run_server_case(console, workdir, osc_env, root / "aqorath-osc-v1.log", lambda: core._assert_v1_07_v1_15_v1_22_osc(osc_db_path), "V1-07/V1-15/V1-22")
        print("installed OSC journeys=" + json.dumps(osc_results, sort_keys=True))
        _integrity(osc_db_path, "installed OSC flow")

        correction_env = env.copy(); correction_env["AQORATH_DB"] = str(correction_db_path)
        correction_results = core._run_server_case(console, workdir, correction_env, root / "aqorath-correction-v1.log", lambda: core._assert_v1_03_v1_18_correction(correction_db_path), "V1-03/V1-18")
        print("installed correction journeys=" + json.dumps(correction_results, sort_keys=True))
        _integrity(correction_db_path, "installed correction flow")

        assets_env = env.copy(); assets_env["AQORATH_DB"] = str(assets_db_path)
        asset_results = core._run_server_case(console, workdir, assets_env, root / "aqorath-assets-v1.log", lambda: assets_periods.assert_v1_08_v1_09_assets(assets_db_path), "V1-08/V1-09")
        print("installed assets journeys=" + json.dumps({k: v for k, v in asset_results.items() if k != "book"}, sort_keys=True))
        reopened_assets = core._run_server_case(console, workdir, assets_env, root / "aqorath-assets-reopen-v1.log", lambda: assets_periods.assert_v1_08_v1_09_reopen(assets_db_path, asset_results), "V1-08/V1-09 reopen")
        print("installed assets reopen=" + json.dumps(reopened_assets, sort_keys=True))
        _integrity(assets_db_path, "installed assets flow")

        periods_env = env.copy(); periods_env["AQORATH_DB"] = str(periods_db_path)
        period_results = core._run_server_case(console, workdir, periods_env, root / "aqorath-periods-v1.log", lambda: assets_periods.assert_v1_10_periods(periods_db_path, period_backup_root), "V1-10")
        print("installed V1-10 periods=" + json.dumps({k: v for k, v in period_results.items() if k not in {"period_state", "closing"}}, sort_keys=True))
        reopened_periods = core._run_server_case(console, workdir, periods_env, root / "aqorath-periods-reopen-v1.log", lambda: assets_periods.assert_v1_10_reopen(periods_db_path, period_results), "V1-10 reopen")
        print("installed V1-10 periods reopen=" + json.dumps(reopened_periods, sort_keys=True))
        _integrity(periods_db_path, "installed periods flow")

        reporting_env = env.copy(); reporting_env["AQORATH_DB"] = str(reporting_db_path)
        reporting_results = core._run_server_case(console, workdir, reporting_env, root / "aqorath-reporting-v1.log", lambda: core._assert_v1_11_v1_12_reporting(reporting_db_path), "V1-11/V1-12")
        print("installed reporting journeys=" + json.dumps({key: ({k: value for k, value in item.items() if k != "preset"} if isinstance(item, dict) else item) for key, item in reporting_results.items()}, sort_keys=True))
        preset = reporting_results["V1-12"]["preset"]
        reopened = core._run_server_case(console, workdir, reporting_env, root / "aqorath-reporting-reopen-v1.log", lambda: core._assert_v1_12_reporting_reopen(preset["id"], preset), "V1-12 preset reopen")
        print("installed reporting reopen=" + json.dumps(reopened, sort_keys=True))
        _integrity(reporting_db_path, "installed reporting flow")

        cfdi_env = env.copy(); cfdi_env["AQORATH_DB"] = str(cfdi_db_path)
        cfdi_result = core._run_server_case(console, workdir, cfdi_env, root / "aqorath-cfdi-v1.log", lambda: cfdi.assert_v1_13_cfdi(cfdi_db_path), "V1-13 CFDI")
        print("installed V1-13 CFDI=" + json.dumps({key: value for key, value in cfdi_result.items() if key != "professional"}, sort_keys=True))
        reopened_cfdi = core._run_server_case(console, workdir, cfdi_env, root / "aqorath-cfdi-reopen-v1.log", lambda: cfdi.assert_v1_13_reopen(cfdi_db_path, cfdi_result), "V1-13 CFDI reopen")
        print("installed V1-13 CFDI reopen=" + json.dumps(reopened_cfdi, sort_keys=True))
        _integrity(cfdi_db_path, "installed CFDI flow")

        fiscal_env = env.copy(); fiscal_env["AQORATH_DB"] = str(fiscal_db_path)
        fiscal_result = core._run_server_case(console, workdir, fiscal_env, root / "aqorath-fiscal-v1.log", lambda: fiscal.assert_v1_14_fiscal(fiscal_db_path), "V1-14 fiscal")
        print("installed V1-14 fiscal=" + json.dumps({key: value for key, value in fiscal_result.items() if key != "professional"}, sort_keys=True))
        reopened_fiscal = core._run_server_case(console, workdir, fiscal_env, root / "aqorath-fiscal-reopen-v1.log", lambda: fiscal.assert_v1_14_reopen(fiscal_db_path, fiscal_result), "V1-14 fiscal reopen")
        print("installed V1-14 fiscal reopen=" + json.dumps(reopened_fiscal, sort_keys=True))
        _integrity(fiscal_db_path, "installed fiscal flow")

        if attempts.exists() and attempts.read_text(encoding="utf-8").strip():
            raise AssertionError("installed V1 flow attempted external network access:\n" + attempts.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", required=True, type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file():
        raise SystemExit(f"wheel not found: {wheel}")
    _install_and_run(wheel)
    print(
        "AQR-015 installed V1-01/V1-02/V1-03/V1-04/V1-05/V1-06/V1-07/"
        "V1-08/V1-09/V1-10/V1-11/V1-12/V1-13/V1-14/V1-15/V1-18/V1-22 smoke: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
