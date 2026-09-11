#!/usr/bin/env python3
"""AQR-015 distribution smoke test.

The source suite is intentionally not enough for this contract. This script is
run after `python -m build`: it installs the built wheel into a fresh virtual
environment, runs from a directory outside the checkout, verifies product
resources/imports, starts the installed console script, checks the local
surface and SQLite bootstrap, and shuts the installed process down.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.request import urlopen
import venv


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8765


def _run(args, *, cwd=None, env=None):
    completed = subprocess.run(
        [str(item) for item in args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(map(str, args))}\n"
            f"{completed.stdout}"
        )
    return completed.stdout


def _venv_bin(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin")


def _assert_sdist_contains_runtime_resource(sdist: Path) -> None:
    with tarfile.open(sdist, "r:gz") as archive:
        names = set(archive.getnames())
    required_suffixes = (
        "/aqorath/data/catalogo_base.json",
        "/setup.cfg",
        "/pyproject.toml",
    )
    for suffix in required_suffixes:
        if not any(name.endswith(suffix) for name in names):
            raise AssertionError(f"sdist missing required member suffix: {suffix}")


def _probe_installed_python(python: Path, workdir: Path, env: dict[str, str]) -> None:
    code = r'''
import importlib.metadata
from pathlib import Path
import aqorath
from aqorath.catalog import get_catalog_path, load_catalog
from aqorath.accounting_rules import load_catalog as load_rules_catalog
from aqorath.local_server import LOCAL_HOST
import aqorath.cfdi_source
import aqorath.financial_statements_pdf
import aqorath.reporting_xlsx
import aqorath.storage
import aqorath.web_surface

repo_root = Path(__import__("os").environ["AQORATH_SMOKE_REPO_ROOT"]).resolve()
package_path = Path(aqorath.__file__).resolve()
try:
    package_path.relative_to(repo_root)
except ValueError:
    pass
else:
    raise AssertionError(f"installed import leaked to source checkout: {package_path}")

catalog_path = get_catalog_path().resolve()
assert catalog_path.is_file(), catalog_path
assert load_catalog().get("accounts")
assert load_rules_catalog()
assert LOCAL_HOST == "127.0.0.1"
assert importlib.metadata.version("aqorath") == aqorath.__version__
print(package_path)
print(catalog_path)
'''
    _run([python, "-c", code], cwd=workdir, env=env)


def _wait_for_surface(process: subprocess.Popen, log_path: Path) -> dict:
    deadline = time.monotonic() + 30
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            log = log_path.read_text(encoding="utf-8", errors="replace")
            raise RuntimeError(
                f"installed aqorath exited before smoke request ({process.returncode})\n{log}"
            )
        try:
            with urlopen(
                f"http://127.0.0.1:{DEFAULT_PORT}/api/system/integrity",
                timeout=1,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if response.status == 200:
                    return payload
        except Exception as exc:  # server may still be starting
            last_error = exc
        time.sleep(0.25)
    log = log_path.read_text(encoding="utf-8", errors="replace")
    raise RuntimeError(f"installed surface did not become ready: {last_error}\n{log}")


def _install_and_smoke_wheel(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="aqorath-dist-smoke-") as temp:
        root = Path(temp)
        venv_dir = root / "venv"
        workdir = root / "outside-checkout"
        data_dir = root / "user-data"
        db_path = data_dir / "aqorath.db"
        workdir.mkdir()

        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
        bindir = _venv_bin(venv_dir)
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        pip = [python, "-m", "pip"]

        _run([*pip, "install", "--disable-pip-version-check", str(wheel)])

        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["AQORATH_DB"] = str(db_path)
        env["AQORATH_SMOKE_REPO_ROOT"] = str(REPO_ROOT)
        _probe_installed_python(python, workdir, env)

        console = bindir / ("aqorath.exe" if os.name == "nt" else "aqorath")
        if not console.is_file():
            raise AssertionError(f"console script missing: {console}")

        log_path = root / "aqorath.log"
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
                    raise AssertionError(f"installed integrity check not healthy: {integrity}")
                with urlopen(f"http://127.0.0.1:{DEFAULT_PORT}/", timeout=2) as response:
                    if response.status != 200:
                        raise AssertionError(f"root surface returned {response.status}")
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
                raise AssertionError("installed Aqorath did not shut down after termination request")

        if not db_path.is_file():
            raise AssertionError(f"installed launcher did not create SQLite DB: {db_path}")
        with sqlite3.connect(db_path) as conn:
            schema = conn.execute("PRAGMA user_version").fetchone()[0]
        if schema <= 0:
            raise AssertionError(f"installed DB has invalid schema version: {schema}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--sdist", required=True, type=Path)
    args = parser.parse_args()

    wheel = args.wheel.resolve()
    sdist = args.sdist.resolve()
    if not wheel.is_file():
        raise SystemExit(f"wheel not found: {wheel}")
    if not sdist.is_file():
        raise SystemExit(f"sdist not found: {sdist}")

    _assert_sdist_contains_runtime_resource(sdist)
    _install_and_smoke_wheel(wheel)
    print("AQR-015 distribution smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
