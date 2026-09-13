#!/usr/bin/env python3
"""Verify #56 against the built wheel, outside the source checkout.

This is intentionally structural: it proves the distribution no longer contains
Aqorath's second fixed-asset posting module and that retained compatibility
imports for templates/accounting_model are fail-closed tombstones rather than
business authorities.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def _assert_wheel_members(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        forbidden = {
            "aqorath/assets.py",
            "aqorath/template_utils.py",
        }
        present = sorted(forbidden & names)
        if present:
            raise AssertionError(f"legacy executable modules remain in wheel: {present}")

        required_tombstones = {
            "aqorath/templates.py",
            "aqorath/config.py",
        }
        missing = sorted(required_tombstones - names)
        if missing:
            raise AssertionError(f"expected compatibility tombstones missing from wheel: {missing}")

        templates_source = archive.read("aqorath/templates.py").decode("utf-8")
        config_source = archive.read("aqorath/config.py").decode("utf-8")
        for forbidden_text in ("class OperationTemplate", "_TEMPLATES", "LineSpec"):
            if forbidden_text in templates_source:
                raise AssertionError(
                    f"legacy template authority survived in wheel: {forbidden_text}"
                )
        for forbidden_text in ("DB_KEY", "FALLBACK_PATH", "_read_db", "_write_db"):
            if forbidden_text in config_source:
                raise AssertionError(
                    f"legacy accounting_model persistence survived in wheel: {forbidden_text}"
                )


def _assert_wheel_runtime(wheel: Path) -> None:
    code = r'''
import importlib.util

assert importlib.util.find_spec("aqorath.assets") is None
assert importlib.util.find_spec("aqorath.template_utils") is None

from aqorath import application, config, core, templates

assert templates.list_templates() == ()
assert core.list_templates() == ()
assert application.list_templates() == ()

for fn, args in (
    (templates.get_template, ("ingreso_venta",)),
    (templates.register_template, (object(),)),
    (core.generate_preview, ("ingreso_venta", 100)),
    (core.post_entry, ("ingreso_venta", 100)),
    (application.preview_template, ("ingreso_venta", 100)),
    (application.post_template, ("ingreso_venta", 100)),
    (config.get_accounting_model, ()),
    (config.is_accounting_model_set, ()),
    (config.set_accounting_model, ("comercial",)),
):
    try:
        fn(*args)
    except RuntimeError as exc:
        assert "retired" in str(exc).lower(), (fn, exc)
    else:
        raise AssertionError(f"legacy authority did not fail closed: {fn}")

assert not hasattr(config, "DB_KEY")
assert not hasattr(config, "FALLBACK_PATH")
print("AQR-015 #56 built-wheel hardening: OK")
'''
    with tempfile.TemporaryDirectory(prefix="aqorath-hardening-wheel-") as temp:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONPATH"] = str(wheel)
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=temp,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if completed.returncode != 0:
            raise AssertionError(
                "built-wheel legacy hardening probe failed:\n" + completed.stdout
            )
        print(completed.stdout, end="")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", required=True, type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file():
        raise SystemExit(f"wheel not found: {wheel}")
    _assert_wheel_members(wheel)
    _assert_wheel_runtime(wheel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
