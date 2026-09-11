from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select


def _setup(tmp_path, monkeypatch):
    from aqorath import inventory_models  # noqa: F401 - register schema
    from aqorath import storage
    from aqorath.account_bindings import set_account_binding
    from aqorath.entity import Entity, EntityProfile
    from aqorath.entity_repository import create_entity
    from aqorath.inventory import Product
    from aqorath.inventory_repository import create_product
    from aqorath.models import Account
    from aqorath.third_party import ThirdParty
    from aqorath.third_party_repository import create_third_party
    from period_fixtures import seed_engine_calendar

    path = tmp_path / "aqr012.db"
    monkeypatch.setenv("AQORATH_DB", str(path))
    engine = storage.init_db(str(path), create_tables=True)
    with Session(engine) as session:
        entity = create_entity(
            session,
            Entity(
                None,
                "Comercial AQR-012",
                "AAA010101AAA",
                "persona_moral",
                "sociedad mercantil",
                EntityProfile(
                    "lucrativo",
                    False,
                    ("inventory_control",),
                    ("inventory",),
                ),
                True,
            ),
        )
    seed_engine_calendar(engine)
    with Session(engine) as session:
        supplier = create_third_party(
            session,
            ThirdParty(None, entity.id, "Proveedor", "BBB010101BBB", None, None, "supplier", None, None, None, True),
        )
        customer = create_third_party(
            session,
            ThirdParty(None, entity.id, "Cliente", "CCC010101CCC", None, None, "customer", None, None, None, True),
        )
        accounts = [
            Account(code="1101", name="Bancos", nature="DEBIT"),
            Account(code="1102", name="Caja", nature="DEBIT"),
            Account(code="1103", name="Clientes", nature="DEBIT"),
            Account(code="1104", name="Inventario", nature="DEBIT"),
            Account(code="2101", name="Proveedores", nature="CREDIT"),
            Account(code="4201", name="Ventas", nature="CREDIT"),
            Account(code="5101", name="Costo de ventas", nature="DEBIT"),
        ]
        session.add_all(accounts)
        session.commit()
        for role, code in {
            "bank": "1101",
            "cash": "1102",
            "accounts_receivable": "1103",
            "inventory": "1104",
            "accounts_payable": "2101",
            "sales_revenue": "4201",
            "cost_of_goods_sold": "5101",
        }.items():
            set_account_binding(session, role, code)
        product = create_product(session, Product(None, entity.id, "SKU-X", "Producto X", "unidad"))
        other = create_product(session, Product(None, entity.id, "SKU-Y", "Producto Y", "unidad"))
    return engine, entity, supplier, customer, product, other


def _purchase(session, entity, supplier, product, qty, price, day=date(2026, 9, 10)):
    from aqorath.inventory import MerchandisePurchaseFact
    from aqorath.inventory_operations import prepare_inventory_purchase, confirm_inventory_operation
    prepared = prepare_inventory_purchase(
        session,
        MerchandisePurchaseFact(entity.id, product.id, Decimal(qty), Decimal(price), day, supplier.id, "bank"),
    )
    return prepared, confirm_inventory_operation(prepared)


def _sale(session, entity, product, qty, price, day=date(2026, 9, 10)):
    from aqorath.inventory import MerchandiseSaleFact
    from aqorath.inventory_operations import prepare_inventory_sale, confirm_inventory_operation
    prepared = prepare_inventory_sale(
        session,
        MerchandiseSaleFact(entity.id, product.id, Decimal(qty), Decimal(price), day, "cash"),
    )
    return prepared, confirm_inventory_operation(prepared)


def test_v1_21_moving_average_purchase_purchase_sale_e2e(tmp_path, monkeypatch):
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.inventory_repository import inventory_state
    from aqorath.models import JournalEntry, JournalLine
    from aqorath.inventory_models import InventoryMovementRecord

    engine, entity, supplier, _, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as s:
        p1, c1 = _purchase(s, entity, supplier, product, "10", "10")
        assert p1.before.quantity == Decimal("0")
        assert p1.after.quantity == Decimal("10")
        assert p1.after.value == Decimal("100.00")
        assert p1.after.average == Decimal("10.000000000000")
    r1 = execute_inventory_operation(c1)

    with Session(engine) as s:
        p2, c2 = _purchase(s, entity, supplier, product, "10", "20")
        assert p2.before.quantity == Decimal("10")
        assert p2.after.quantity == Decimal("20")
        assert p2.after.value == Decimal("300.00")
        assert p2.after.average == Decimal("15.000000000000")
    r2 = execute_inventory_operation(c2)

    with Session(engine) as s:
        sale, cs = _sale(s, entity, product, "4", "25")
        assert sale.revenue_or_purchase_amount == Decimal("100.00")
        assert sale.inventory_cost == Decimal("60.00")
        assert sale.before.quantity == Decimal("20")
        assert sale.after.quantity == Decimal("16")
        assert sale.after.value == Decimal("240.00")
        assert sale.revenue_or_purchase_amount - sale.inventory_cost == Decimal("40.00")
    rs = execute_inventory_operation(cs)

    with Session(engine) as s:
        state = inventory_state(s, entity.id, product.id)
        assert state.quantity == Decimal("16")
        assert state.value == Decimal("240.00")
        assert state.average == Decimal("15.000000000000")
        movements = s.exec(select(InventoryMovementRecord).order_by(InventoryMovementRecord.id)).all()
        assert [Decimal(m.quantity_delta) for m in movements] == [Decimal("10"), Decimal("10"), Decimal("-4")]
        assert [Decimal(m.value_delta) for m in movements] == [Decimal("100.00"), Decimal("200.00"), Decimal("-60.00")]
        assert len(s.exec(select(JournalEntry)).all()) == 3
        sale_lines = s.exec(select(JournalLine).where(JournalLine.entry_id == rs["entry_id"])).all()
        assert len(sale_lines) == 4
        by_code = {line.account_code: (Decimal(line.debit), Decimal(line.credit)) for line in sale_lines}
        assert by_code["1102"] == (Decimal("100.00"), Decimal("0"))
        assert by_code["4201"] == (Decimal("0"), Decimal("100.00"))
        assert by_code["5101"] == (Decimal("60.00"), Decimal("0"))
        assert by_code["1104"] == (Decimal("0",), Decimal("60.00"))
        assert r1["entry_id"] != r2["entry_id"] != rs["entry_id"]


def test_prepare_and_negative_stock_write_nothing(tmp_path, monkeypatch):
    from aqorath.inventory import MerchandiseSaleFact
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.inventory_operations import prepare_inventory_sale
    from aqorath.models import JournalEntry

    engine, entity, _, _, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as s:
        before_entries = len(s.exec(select(JournalEntry)).all())
        before_moves = len(s.exec(select(InventoryMovementRecord)).all())
        with pytest.raises(ValueError, match="insufficient inventory"):
            prepare_inventory_sale(
                s,
                MerchandiseSaleFact(entity.id, product.id, Decimal("1"), Decimal("25"), date(2026, 9, 10), "cash"),
            )
        assert len(s.exec(select(JournalEntry)).all()) == before_entries
        assert len(s.exec(select(InventoryMovementRecord)).all()) == before_moves


def test_idempotent_confirmation_does_not_duplicate_units_or_entry(tmp_path, monkeypatch):
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.models import JournalEntry

    engine, entity, supplier, _, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as s:
        _, confirmed = _purchase(s, entity, supplier, product, "10", "10")
    first = execute_inventory_operation(confirmed)
    second = execute_inventory_operation(confirmed)
    assert second["idempotent"] is True
    assert first["entry_id"] == second["entry_id"]
    with Session(engine) as s:
        assert len(s.exec(select(InventoryMovementRecord)).all()) == 1
        assert len(s.exec(select(JournalEntry)).all()) == 1


def test_noninteger_cost_policy_is_decimal_and_reconciles_carrying_value(tmp_path, monkeypatch):
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.inventory_repository import inventory_state

    engine, entity, supplier, _, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as s:
        _, c1 = _purchase(s, entity, supplier, product, "3", "10.01")
    execute_inventory_operation(c1)
    with Session(engine) as s:
        _, cs = _sale(s, entity, product, "1", "20")
    result = execute_inventory_operation(cs)
    with Session(engine) as s:
        state = inventory_state(s, entity.id, product.id)
        assert state.quantity == Decimal("2")
        assert state.value == Decimal("20.02")
        assert state.average == Decimal("10.010000000000")
        assert result["value_after"] == "20.02"


def test_products_do_not_mix_average_and_as_of_reconstructs_history(tmp_path, monkeypatch):
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.inventory_repository import inventory_state

    engine, entity, supplier, _, product, other = _setup(tmp_path, monkeypatch)
    with Session(engine) as s:
        _, c1 = _purchase(s, entity, supplier, product, "10", "10", date(2026, 9, 9))
    execute_inventory_operation(c1)
    with Session(engine) as s:
        _, c2 = _purchase(s, entity, supplier, other, "5", "99", date(2026, 9, 10))
    execute_inventory_operation(c2)
    with Session(engine) as s:
        assert inventory_state(s, entity.id, product.id, date(2026, 9, 9)).value == Decimal("100.00")
        assert inventory_state(s, entity.id, other.id).average == Decimal("99.000000000000")
        assert inventory_state(s, entity.id, product.id).average == Decimal("10.000000000000")


def test_inventory_requires_entity_profile_capability(tmp_path):
    from sqlalchemy import create_engine
    from sqlmodel import SQLModel
    from aqorath import inventory_models  # noqa
    from aqorath.entity import Entity, EntityProfile
    from aqorath.entity_repository import create_entity
    from aqorath.inventory import Product
    from aqorath.inventory_repository import create_product

    engine = create_engine(f"sqlite:///{tmp_path / 'disabled.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        entity = create_entity(s, Entity(None, "No inventory", None, "persona_moral", "AC", EntityProfile("no_lucrativo", False, (), ()), True))
        with pytest.raises(ValueError, match="inventory_control"):
            create_product(s, Product(None, entity.id, "X", "X", "unit"))
    engine.dispose()


def test_inventory_http_routes_delegate_and_present_errors_explicitly(monkeypatch):
    import aqorath.web_surface as web

    calls = []
    monkeypatch.setattr(web.controller, "inventory_products", lambda: [{"sku": "SKU-X"}])
    monkeypatch.setattr(web.controller, "create_inventory_product", lambda payload: calls.append(("product", payload)) or {"id": 1})
    monkeypatch.setattr(web.controller, "prepare_inventory", lambda payload: calls.append(("prepare", payload)) or {"token": "T"})
    monkeypatch.setattr(web.controller, "professional_inventory", lambda movement_id: {"movement_id": movement_id})
    monkeypatch.setattr(web.controller, "reverse_inventory", lambda movement_id, payload: calls.append(("reverse", movement_id, payload)) or {"idempotent": False})

    assert web.inventory_products() == [{"sku": "SKU-X"}]
    assert web.create_inventory_product({"sku": "SKU-X"}) == {"id": 1}
    assert web.prepare_inventory({"operation_kind": "purchase"}) == {"token": "T"}
    assert web.professional_inventory(7) == {"movement_id": 7}
    assert web.reverse_inventory(7, {"reason": "cancel"}) == {"idempotent": False}
    assert calls == [
        ("product", {"sku": "SKU-X"}),
        ("prepare", {"operation_kind": "purchase"}),
        ("reverse", 7, {"reason": "cancel"}),
    ]

    monkeypatch.setattr(web.controller, "prepare_inventory", lambda _payload: (_ for _ in ()).throw(ValueError("bad inventory")))
    error = web.prepare_inventory({"operation_kind": "sale"})
    assert error.status_code == 400
    assert error.detail == "bad inventory"
