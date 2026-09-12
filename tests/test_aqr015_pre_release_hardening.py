"""Architectural regression for AQR-015 pre-release legacy hardening (#56)."""

import importlib.util

import pytest

from aqorath import application, config, core, templates


def test_legacy_asset_posting_module_is_removed():
    assert importlib.util.find_spec("aqorath.assets") is None


def test_operation_template_authority_is_fail_closed():
    assert templates.list_templates() == ()
    with pytest.raises(RuntimeError, match="retired"):
        templates.get_template("ingreso_venta")
    with pytest.raises(RuntimeError, match="retired"):
        templates.register_template(object())

    # core/application may retain compatibility names while callers migrate, but
    # no template key can resolve to accounting semantics anymore.
    assert core.list_templates() == ()
    assert application.list_templates() == ()
    with pytest.raises(RuntimeError, match="retired"):
        core.generate_preview("ingreso_venta", 100)
    with pytest.raises(RuntimeError, match="retired"):
        core.post_entry("ingreso_venta", amount=100)
    with pytest.raises(RuntimeError, match="retired"):
        application.preview_template("ingreso_venta", 100)
    with pytest.raises(RuntimeError, match="retired"):
        application.post_template("ingreso_venta", amount=100)


def test_binary_accounting_model_authority_is_fail_closed():
    for call in (
        config.get_accounting_model,
        config.is_accounting_model_set,
    ):
        with pytest.raises(RuntimeError, match="retired"):
            call()
    with pytest.raises(RuntimeError, match="retired"):
        config.set_accounting_model("comercial")
    with pytest.raises(RuntimeError, match="retired"):
        config.set_accounting_model("sin_fines")


def test_historical_accounting_model_row_is_not_reinterpreted_here():
    # The tombstone intentionally exposes no fallback path, DB key, filesystem
    # config path, or value enumeration. Historical AppConfig rows may survive as
    # inert history, but this package surface cannot interpret them as identity.
    assert not hasattr(config, "DB_KEY")
    assert not hasattr(config, "FALLBACK_PATH")
