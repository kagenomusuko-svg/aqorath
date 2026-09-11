def test_inventory_browser_route_and_common_language_contract():
    import aqorath.web_surface as web
    from aqorath.inventory_web_assets import INVENTORY_HTML

    response = web.inventory_index()
    body = response.body.decode("utf-8")
    assert body == INVENTORY_HTML
    for marker in (
        "Compré mercancía",
        "Vendí mercancía",
        "Cantidad",
        "Precio unitario",
        "Existencia",
        "Promedio",
        "Costo previsto",
        "Contraparte",
        "CFDI importado",
        "Venta ordinaria gravada",
        "Confirmar",
        "Cancelar",
        "Ver reconstrucción profesional",
        "/api/inventory/prepare",
        "/api/inventory/movements/",
    ):
        assert marker in body
    lowered = body.lower()
    for forbidden_input in (
        'id="account_code"',
        'id="cogs_account"',
        'id="inventory_account"',
        'id="rule_key"',
    ):
        assert forbidden_input not in lowered


def test_inventory_surface_forwards_bank_and_business_fiscal_facts(monkeypatch):
    import aqorath.inventory_surface_application as surface

    class Entity:
        id = 7

    class Product:
        id = 11
        sku = "SKU-X"
        name = "Producto X"
        unit = "unidad"

    class Party:
        id = 13
        name = "Cliente"
        rfc = "AAA010101AAA"
        party_type = "customer"

    class Session:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def get(self, _model, identity):
            return Party() if identity == 13 else None

    class Ctx:
        def __enter__(self): return Session()
        def __exit__(self, *_args): return False

    captured = {}
    monkeypatch.setattr(surface._storage, "get_session", lambda: Ctx())
    monkeypatch.setattr(surface._inventory, "require_inventory_entity", lambda _session: Entity())
    monkeypatch.setattr(surface._inventory, "load_product", lambda _session, _entity_id, _product_id: Product())

    from aqorath.inventory import InventoryState
    from decimal import Decimal
    from types import SimpleNamespace

    fiscal = SimpleNamespace(
        treatments=(SimpleNamespace(
            coverage_version="mx-fiscal-v1.2026-09-10",
            treatment_key="iva.general_rate",
            explanation="IVA general",
        ),),
        facts=SimpleNamespace(activity="ordinary_taxable_sale"),
        snapshot=SimpleNamespace(provenance=SimpleNamespace(fiscal_effects=(SimpleNamespace(rounded_fiscal_amount=Decimal("16.00")),))),
        limitations=("limitada",),
    )
    prepared = SimpleNamespace(
        fact=None,
        before=InventoryState(Decimal("10"), Decimal("100.00"), Decimal("10.000000000000")),
        after=InventoryState(Decimal("9"), Decimal("90.00"), Decimal("10.000000000000")),
        revenue_or_purchase_amount=Decimal("25.00"),
        inventory_cost=Decimal("10.00"),
        document=None,
        cfdi_source_id=None,
        explanation="venta",
        bank_account_id=17,
        fiscal_prepared=fiscal,
    )

    def fake_prepare(_session, fact, **kwargs):
        captured["fact"] = fact
        captured.update(kwargs)
        prepared.fact = fact
        return prepared

    monkeypatch.setattr(surface._operations, "prepare_inventory_sale", fake_prepare)
    result = surface.prepare_inventory_surface_operation({
        "operation_kind": "sale",
        "product_id": 11,
        "quantity": "1",
        "unit_price": "25",
        "operation_date": "2026-09-10",
        "settlement_method": "bank",
        "third_party_id": 13,
        "bank_account_id": 17,
        "fiscal_activity": "ordinary_taxable_sale",
    })
    assert captured["bank_account_id"] == 17
    assert captured["fiscal_activity"] == "ordinary_taxable_sale"
    assert result.preview["bank_account_id"] == 17
    assert result.preview["fiscality"]["activity"] == "ordinary_taxable_sale"
    assert result.preview["fiscality"]["treatments"][0]["amount"] == "16.00"
