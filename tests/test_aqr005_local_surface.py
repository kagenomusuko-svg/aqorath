"""AQR-005 — two presentation views over the same Application truth."""

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import types

import pytest
from sqlalchemy import text
from sqlmodel import Session

from period_fixtures import seed_engine_calendar


@pytest.fixture
def surface_engine(tmp_path, monkeypatch):
    import aqorath.accounting_operation_persistence as persistence
    import aqorath.storage as storage
    import aqorath.surface_application as surface_application
    from aqorath.account_bindings import set_account_binding
    from aqorath.models import Account

    path = tmp_path / "aqr005.db"
    monkeypatch.setenv("AQORATH_DB", str(path))
    engine = storage.init_db(str(path))
    seed_engine_calendar(engine)

    with Session(engine) as session:
        session.add_all([
            Account(code="1102", name="Caja", nature="DEBIT"),
            Account(code="4201", name="Ventas", nature="CREDIT"),
        ])
        session.commit()
        set_account_binding(session, "cash", "1102")
        set_account_binding(session, "sales_revenue", "4201")

    monkeypatch.setattr(surface_application._storage, "get_session", lambda: Session(engine))
    monkeypatch.setattr(persistence._storage, "get_session", lambda: Session(engine))
    yield engine
    engine.dispose()


def test_surface_architecture_is_framework_isolated_from_accounting_authorities():
    import aqorath.web_surface as web_surface

    source = Path(web_surface.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = (
        "aqorath.models",
        "aqorath.storage",
        "aqorath.core",
        "aqorath.accounting_period",
        "aqorath.accounting_period_repository",
        "aqorath.reversal",
        "aqorath.fiscal_runtime",
        "sqlmodel",
        "sqlalchemy",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imported
        for prefix in forbidden
    )
    assert "presentation_controller" in source


def test_web_surface_has_only_local_product_routes_and_no_generated_api_docs():
    from aqorath.web_surface import app

    paths = {route.path for route in app.routes}
    assert {
        "/",
        "/api/capabilities",
        "/api/operations/prepare",
        "/api/operations/{token}/professional-preview",
        "/api/operations/{token}/confirm",
        "/api/operations/{token}",
        "/api/professional/operations",
        "/api/operations/{entry_id}/professional",
        "/api/trial-balance",
    } <= paths
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_local_launcher_cannot_be_reconfigured_to_remote_host(monkeypatch):
    import aqorath.local_server as local_server

    sentinel_app = object()
    calls = []
    fake = types.SimpleNamespace(run=lambda target, **kwargs: calls.append((target, kwargs)))
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    monkeypatch.setattr(local_server, "load_local_app", lambda: sentinel_app)

    local_server.run_local_surface(8899)

    assert local_server.LOCAL_HOST == "127.0.0.1"
    assert calls == [
        (
            sentinel_app,
            {"host": "127.0.0.1", "port": 8899, "log_level": "info"},
        )
    ]


def test_common_shell_never_asks_for_accounting_internals():
    from aqorath.web_assets import APP_HTML

    common = APP_HTML.split('<section id="professional"', 1)[0]
    assert "Debe" not in common
    assert "Haber" not in common
    assert "account_code" not in str(common)
    assert "Código contable" not in common
    assert 'id="operation"' in common
    assert 'id="amount"' in common
    assert 'id="postingDate"' in common


def test_declared_common_operations_are_real_domain_facts():
    from aqorath.economic_facts import EconomicFact
    from aqorath.surface_application import list_common_operation_kinds

    for item in list_common_operation_kinds():
        fact = EconomicFact(item.fact_type, Decimal("1"), item.payment_method)
        assert fact.type == item.fact_type
        assert fact.payment_method == item.payment_method


def test_prepare_and_cancel_are_non_persistent_and_common_preview_has_no_codes(surface_engine):
    from aqorath.presentation_controller import LocalPresentationController

    controller = LocalPresentationController()
    prepared = controller.prepare("sale_cash", "200.00", date.today().isoformat())

    assert controller.pending_count == 1
    common = prepared["preview"]
    assert common["amount"] == "200.00"
    assert "account_code" not in str(common)

    with Session(surface_engine) as session:
        assert session.execute(text("SELECT COUNT(*) FROM journalentry")).scalar_one() == 0
        assert session.execute(text("SELECT COUNT(*) FROM auditevent")).scalar_one() == 0

    assert controller.cancel(prepared["token"]) == {"cancelled": True}
    assert controller.pending_count == 0
    with Session(surface_engine) as session:
        assert session.execute(text("SELECT COUNT(*) FROM journalentry")).scalar_one() == 0


def test_common_and_professional_preview_are_two_views_of_exact_same_decision(surface_engine):
    from aqorath.presentation_controller import LocalPresentationController

    controller = LocalPresentationController()
    prepared = controller.prepare("sale_cash", "200.00", date.today().isoformat())
    common = prepared["preview"]
    professional = controller.professional_preview(prepared["token"])

    assert common["amount"] == "200.00"
    assert common["posting_date"] == professional["posting_date"]
    assert common["explanation"] == professional["explanation"]
    assert professional["rule_id"] == "economic_fact:sale:cash"
    assert [line["account_code"] for line in professional["lines"]] == ["1102", "4201"]
    assert [line["side"] for line in professional["lines"]] == ["debit", "credit"]
    assert [line["amount"] for line in professional["lines"]] == ["200.00", "200.00"]


def test_confirm_posts_once_and_professional_view_reads_same_ledger_period_and_audit(surface_engine):
    from aqorath.presentation_controller import LocalPresentationController

    controller = LocalPresentationController()
    prepared = controller.prepare("sale_cash", "200.00", date.today().isoformat())
    expected = controller.professional_preview(prepared["token"])
    result = controller.confirm(prepared["token"])

    assert result["state"] == "posted"
    assert controller.pending_count == 0
    recent = controller.recent_professional_operations()
    assert [row["entry_id"] for row in recent] == [result["entry_id"]]
    assert recent[0]["state"] == "posted"

    view = controller.professional_operation(result["entry_id"])
    assert view["entry_id"] == result["entry_id"]
    assert view["state"] == "posted"
    assert view["posting_date"] == expected["posting_date"]
    assert view["concept"] == expected["explanation"]
    assert view["period"]["id"] == date.today().year * 100 + date.today().month
    assert view["period"]["state"] == "open"
    assert [(line["account_code"], line["debit"], line["credit"]) for line in view["lines"]] == [
        ("1102", "200.00", "0"),
        ("4201", "0", "200.00"),
    ]
    assert view["audit"]["id"] == result["audit_event_id"]
    assert view["audit"]["event_type"] == "entry_posted"
    assert view["audit"]["details"]["decision"]["consent"] == "explicit_confirmation"
    assert view["documents"] == []
    assert view["fiscal_audit"] is None
    assert view["reversal"] is None


def test_recent_professional_index_is_ledger_backed_and_newest_first(surface_engine):
    from aqorath.presentation_controller import LocalPresentationController

    controller = LocalPresentationController()
    first = controller.prepare("sale_cash", "10.00", date.today().isoformat())
    first_result = controller.confirm(first["token"])
    second = controller.prepare("sale_cash", "20.00", date.today().isoformat())
    second_result = controller.confirm(second["token"])

    rows = controller.recent_professional_operations(limit=10)
    assert [row["entry_id"] for row in rows] == [second_result["entry_id"], first_result["entry_id"]]
    with Session(surface_engine) as session:
        persisted = session.execute(text("SELECT id FROM journalentry ORDER BY id DESC")).scalars().all()
    assert [row["entry_id"] for row in rows] == list(persisted)


def test_closed_period_failure_is_inherited_from_aqr002_not_reimplemented_in_ui(surface_engine):
    from aqorath.accounting_operation_persistence import AccountingOperationPersistenceError
    from aqorath.accounting_period_repository import close_period, require_open_period
    from aqorath.presentation_controller import LocalPresentationController

    controller = LocalPresentationController()
    prepared = controller.prepare("sale_cash", "200.00", date.today().isoformat())

    with Session(surface_engine) as session:
        period = require_open_period(session, date.today())
        close_period(session, period.id)
        session.commit()

    with pytest.raises(AccountingOperationPersistenceError, match="closed"):
        controller.confirm(prepared["token"])
    assert controller.pending_count == 1
    with Session(surface_engine) as session:
        assert session.execute(text("SELECT COUNT(*) FROM journalentry")).scalar_one() == 0
        assert session.execute(text("SELECT COUNT(*) FROM auditevent")).scalar_one() == 0


def test_http_functions_are_thin_delegates_without_framework_test_client(monkeypatch):
    import aqorath.web_surface as web_surface

    calls = []

    class FakeController:
        def prepare(self, operation_key, amount, posting_date):
            calls.append(("prepare", operation_key, amount, posting_date))
            return {"token": "x", "preview": {"amount": amount}}

        def confirm(self, token):
            calls.append(("confirm", token))
            return {"entry_id": 9, "audit_event_id": 4, "state": "posted"}

        def recent_professional_operations(self, limit):
            calls.append(("recent", limit))
            return [{"entry_id": 9}]

    fake = FakeController()
    monkeypatch.setattr(web_surface, "controller", fake)

    assert web_surface.prepare_operation(
        {"operation_key": "sale_cash", "amount": "10.50", "posting_date": "2026-09-09"}
    )["token"] == "x"
    assert web_surface.confirm_operation("x")["entry_id"] == 9
    assert web_surface.recent_professional_operations(25) == [{"entry_id": 9}]
    assert calls == [
        ("prepare", "sale_cash", "10.50", "2026-09-09"),
        ("confirm", "x"),
        ("recent", 25),
    ]
