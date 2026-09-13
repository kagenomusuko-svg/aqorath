#!/usr/bin/env python3
"""AQR-015 distribution smoke test.

The source suite is intentionally not enough for this contract. This script is
run after `python -m build`: it installs the built wheel into a fresh virtual
environment, runs from a directory outside the checkout, verifies product
resources/imports, clean bootstrap, historical upgrade, future-schema rejection,
offline-local serving, AQR-014 recovery/export, and clean shutdown.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from urllib.request import Request, urlopen
import venv


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8765


def _run(args, *, cwd=None, env=None, expected_returncode=0):
    completed = subprocess.run(
        [str(item) for item in args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != expected_returncode:
        raise RuntimeError(
            f"command returned {completed.returncode}; expected {expected_returncode}: "
            f"{' '.join(map(str, args))}\n{completed.stdout}"
        )
    return completed.stdout


def _run_must_fail(args, *, cwd=None, env=None):
    completed = subprocess.run(
        [str(item) for item in args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode == 0:
        raise RuntimeError(
            f"command unexpectedly succeeded: {' '.join(map(str, args))}\n"
            f"{completed.stdout}"
        )
    return completed.stdout


def _venv_bin(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _installed_current_schema(python: Path, workdir: Path, env: dict[str, str]) -> int:
    output = _run(
        [
            python,
            "-c",
            "from aqorath.migrations import CURRENT_SCHEMA_VERSION; print(CURRENT_SCHEMA_VERSION)",
        ],
        cwd=workdir,
        env=env,
    )
    return int(output.strip().splitlines()[-1])


def _create_schema6_fixture(db_path: Path) -> tuple:
    ddl = (REPO_ROOT / "tests" / "fixtures" / "schema6.sql").read_text(encoding="utf-8")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(ddl)
        created = "2026-01-15T00:00:00+00:00"
        conn.execute(
            "INSERT INTO account(code,name,nature,vat_flag,origin,parent_id,created_at) "
            "VALUES ('1103','Clientes','DEBIT',0,'canonical',NULL,?)",
            (created,),
        )
        account_id = conn.execute(
            "SELECT id FROM account WHERE code='1103'"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO journalentry(date,concept,doc_ref,period_id,posted_by,state,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (created, "AQR-015 historical sentinel", "HIST-15", None, "fixture", "posted", created),
        )
        entry_id = conn.execute("SELECT max(id) FROM journalentry").fetchone()[0]
        conn.execute(
            "INSERT INTO journalline(entry_id,account_code,account_id,debit,credit,description,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (entry_id, "1103", account_id, "123.45", "0", "historical sentinel", created),
        )
        line_id = conn.execute("SELECT max(id) FROM journalline").fetchone()[0]
        before = conn.execute(
            "SELECT id,entry_id,account_code,account_id,debit,credit,description,created_at "
            "FROM journalline WHERE id=?",
            (line_id,),
        ).fetchone()
        conn.commit()
    return before


def _assert_installed_upgrade(
    python: Path,
    workdir: Path,
    base_env: dict[str, str],
    current_schema: int,
    root: Path,
) -> None:
    db_path = root / "upgrade" / "historical-v6.db"
    before = _create_schema6_fixture(db_path)
    env = base_env.copy()
    env["AQORATH_DB"] = str(db_path)

    _run(
        [
            python,
            "-c",
            "from aqorath.product_bootstrap import bootstrap_local_product; "
            "r=bootstrap_local_product(); print(r.schema_version)",
        ],
        cwd=workdir,
        env=env,
    )

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == current_schema
        after = conn.execute(
            "SELECT id,entry_id,account_code,account_id,debit,credit,description,created_at "
            "FROM journalline WHERE description='historical sentinel'"
        ).fetchone()
        assert after == before
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert conn.execute("SELECT count(*) FROM reportpreset").fetchone()[0] == 0

    backups = sorted((db_path.parent / ".aqorath_backups").glob("*.db"))
    if len(backups) != 1:
        raise AssertionError(f"historical upgrade expected one pre-migration backup, got {backups}")
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        backup_line = conn.execute(
            "SELECT id,entry_id,account_code,account_id,debit,credit,description,created_at "
            "FROM journalline WHERE description='historical sentinel'"
        ).fetchone()
        assert backup_line == before


def _assert_future_schema_fails_closed(
    python: Path,
    workdir: Path,
    base_env: dict[str, str],
    current_schema: int,
    root: Path,
) -> None:
    db_path = root / "future" / "future.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
        conn.execute("INSERT INTO sentinel(value) VALUES ('untouched')")
        conn.execute(f"PRAGMA user_version={current_schema + 1}")
        conn.commit()
    before_hash = _sha256(db_path)

    env = base_env.copy()
    env["AQORATH_DB"] = str(db_path)
    output = _run_must_fail(
        [
            python,
            "-c",
            "from aqorath.product_bootstrap import bootstrap_local_product; bootstrap_local_product()",
        ],
        cwd=workdir,
        env=env,
    )
    if "newer than" not in output or "Refusing downgrade" not in output:
        raise AssertionError(f"future schema did not fail with canonical message:\n{output}")
    if _sha256(db_path) != before_hash:
        raise AssertionError("future-schema bootstrap changed the database bytes")
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == current_schema + 1
        assert conn.execute("SELECT value FROM sentinel").fetchone()[0] == "untouched"
    backup_dir = db_path.parent / ".aqorath_backups"
    if backup_dir.exists() and list(backup_dir.iterdir()):
        raise AssertionError("future-schema rejection must not create a migration backup")


def _write_offline_guard(root: Path) -> tuple[Path, Path]:
    guard_dir = root / "offline-guard"
    guard_dir.mkdir()
    attempts = root / "network-attempts.log"
    code = r'''
import os
import socket
from pathlib import Path

_ALLOWED = {"127.0.0.1", "localhost", "::1"}
_LOG = Path(os.environ["AQORATH_OFFLINE_ATTEMPTS"])
_orig_getaddrinfo = socket.getaddrinfo
_orig_connect = socket.socket.connect
_orig_create_connection = socket.create_connection

def _host(value):
    if isinstance(value, bytes):
        value = value.decode("ascii", "replace")
    return str(value)

def _record(kind, host):
    with _LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{kind}:{host}\n")

def _allowed(host):
    return _host(host) in _ALLOWED

def guarded_getaddrinfo(host, *args, **kwargs):
    if not _allowed(host):
        _record("getaddrinfo", host)
        raise OSError(f"offline guard rejected DNS/network host: {host}")
    return _orig_getaddrinfo(host, *args, **kwargs)

def guarded_connect(sock, address):
    host = address[0] if isinstance(address, tuple) and address else address
    if not _allowed(host):
        _record("connect", host)
        raise OSError(f"offline guard rejected connection host: {host}")
    return _orig_connect(sock, address)

def guarded_create_connection(address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) and address else address
    if not _allowed(host):
        _record("create_connection", host)
        raise OSError(f"offline guard rejected connection host: {host}")
    return _orig_create_connection(address, *args, **kwargs)

socket.getaddrinfo = guarded_getaddrinfo
socket.socket.connect = guarded_connect
socket.create_connection = guarded_create_connection
'''
    (guard_dir / "sitecustomize.py").write_text(code, encoding="utf-8")
    return guard_dir, attempts


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
        except Exception as exc:
            last_error = exc
        time.sleep(0.25)
    log = log_path.read_text(encoding="utf-8", errors="replace")
    raise RuntimeError(f"installed surface did not become ready: {last_error}\n{log}")


def _post_artifact(path: str) -> bytes:
    request = Request(
        f"http://127.0.0.1:{DEFAULT_PORT}{path}",
        data=b"",
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise AssertionError(f"{path} returned {response.status}")
        content = response.read()
        if not content.startswith(b"PK"):
            raise AssertionError(f"{path} did not return a ZIP artifact")
        return content


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

        base_env = os.environ.copy()
        base_env.pop("PYTHONPATH", None)
        base_env["AQORATH_SMOKE_REPO_ROOT"] = str(REPO_ROOT)
        base_env["AQORATH_DB"] = str(db_path)
        _probe_installed_python(python, workdir, base_env)
        current_schema = _installed_current_schema(python, workdir, base_env)

        _assert_installed_upgrade(python, workdir, base_env, current_schema, root)
        _assert_future_schema_fails_closed(python, workdir, base_env, current_schema, root)

        console = bindir / ("aqorath.exe" if os.name == "nt" else "aqorath")
        if not console.is_file():
            raise AssertionError(f"console script missing: {console}")

        guard_dir, attempts = _write_offline_guard(root)
        server_env = base_env.copy()
        server_env["AQORATH_DB"] = str(db_path)
        server_env["AQORATH_OFFLINE_ATTEMPTS"] = str(attempts)
        # PYTHONPATH contains only the temporary offline guard, never the source checkout.
        server_env["PYTHONPATH"] = str(guard_dir)

        log_path = root / "aqorath.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [str(console)],
                cwd=workdir,
                env=server_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            forced_kill = False
            try:
                integrity = _wait_for_surface(process, log_path)
                if not integrity.get("healthy"):
                    raise AssertionError(f"installed integrity check not healthy: {integrity}")
                if integrity.get("schema_version") != current_schema:
                    raise AssertionError(f"unexpected installed schema: {integrity}")
                with urlopen(f"http://127.0.0.1:{DEFAULT_PORT}/", timeout=2) as response:
                    if response.status != 200:
                        raise AssertionError(f"root surface returned {response.status}")
                _post_artifact("/api/system/backup")
                _post_artifact("/api/system/portable-export")
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

        if attempts.exists() and attempts.read_text(encoding="utf-8").strip():
            raise AssertionError(
                "installed offline run attempted external network access:\n"
                + attempts.read_text(encoding="utf-8")
            )
        if not db_path.is_file():
            raise AssertionError(f"installed launcher did not create SQLite DB: {db_path}")
        with sqlite3.connect(db_path) as conn:
            schema = conn.execute("PRAGMA user_version").fetchone()[0]
        if schema != current_schema:
            raise AssertionError(
                f"installed DB has schema {schema}; expected {current_schema}"
            )


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
