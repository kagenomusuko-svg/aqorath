"""Installed-wheel technical acceptance for V1-21 inventory and cost.

The harness drives only Aqorath's loopback HTTP surface. Expected figures are the
V1-21 fixture contract; moving-average and cost calculations remain owned by AQR-012.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import _installed_v1_core_cases as core


EXPECTED_AVERAGE = "15.000000000000"


def _onboarding_payload() -> dict:
    payload = core._onboarding_payload()
    payload["special_capabilities"] = ["inventory_control"]
    payload["modules_enabled"] = ["inventory"]
    payload["bindings"] = {
        **payload["bindings"],
        "inventory": "1104",
        "cost_of_goods_sold": "5101",
    }
    return payload


def _prepare_and_confirm(
    *,
    operation_kind: str,
    product_id: int,
    quantity: str,
    unit_price: str,
    operation_date: str,
    settlement_method: str,
    third_party_id: int,
    document_number: str,
    issuer_name: str,
):
    prepared = core._request_json(
        "POST",
        "/api/inventory/prepare",
        {
            "operation_kind": operation_kind,
            "product_id": product_id,
            "quantity": quantity,
            "unit_price": unit_price,
            "operation_date": operation_date,
            "settlement_method": settlement_method,
            "third_party_id": third_party_id,
            "document_type": "invoice",
            "document_number": document_number,
            "document_date": operation_date,
            "issuer_name": issuer_name,
        },
    )
    core._assert_common_preview(prepared)
    token = prepared["token"]
    professional_preview = core._request_json(
        "GET", f"/api/operations/{token}/professional-preview"
    )
    if professional_preview.get("physical_effect") is None:
        raise AssertionError(
            f"V1-21: professional preview lacks AQR-012 physical effect: {professional_preview}"
        )
    confirmed = core._request_json("POST", f"/api/operations/{token}/confirm")
    if not confirmed.get("entry_id") or not confirmed.get("movement_id"):
        raise AssertionError(f"V1-21: confirmation lacks durable identities: {confirmed}")
    professional = core._request_json(
        "GET",
        f"/api/inventory/movements/{confirmed['movement_id']}/professional",
    )
    return prepared["preview"], professional_preview, confirmed, professional


def _decimal_lines(professional: dict) -> dict[str, tuple[Decimal, Decimal]]:
    lines = professional.get("ledger", {}).get("lines", [])
    return {
        line["account_code"]: (Decimal(str(line["debit"])), Decimal(str(line["credit"])))
        for line in lines
    }


def _assert_posted_reconciled(professional: dict, *, party_id: int, document_number: str):
    ledger = professional.get("ledger", {})
    if ledger.get("state") != "posted" or not ledger.get("entry_id"):
        raise AssertionError(f"V1-21: inventory JournalEntry is not posted: {professional}")
    if professional.get("reconciled") is not True:
        raise AssertionError(f"V1-21: inventory movement is not reconciled: {professional}")
    party = professional.get("third_party") or {}
    if party.get("id") != party_id:
        raise AssertionError(f"V1-21: ThirdParty identity diverged: {professional}")
    document = professional.get("document") or {}
    if document.get("number") != document_number:
        raise AssertionError(f"V1-21: document provenance diverged: {professional}")
    if not any(
        event.get("event_type") == "inventory_operation_posted"
        for event in professional.get("audit", [])
    ):
        raise AssertionError(f"V1-21: inventory posting audit is absent: {professional}")


def _valuation(product_id: int, as_of_date: str) -> dict:
    report = core._request_json(
        "POST",
        "/api/reports/inventory-valuation/professional",
        {"as_of_date": as_of_date, "format": "json"},
    )
    authorities = set(report.get("source_authorities", []))
    if not {"AQR-012.inventory_state", "InventoryMovementRecord", "JournalLine"} <= authorities:
        raise AssertionError(f"V1-21: valuation does not declare canonical authorities: {report}")
    required_data = set(report.get("definition", {}).get("required_data", []))
    if not {"inventory_products", "inventory_movements", "journal_lines"} <= required_data:
        raise AssertionError(f"V1-21: valuation definition lost required data contract: {report}")
    restrictions = set(report.get("governance", {}).get("restrictions", []))
    if "no-cost-recalculation" not in restrictions:
        raise AssertionError(f"V1-21: valuation no longer declares no-cost-recalculation: {report}")
    content = report.get("content", {})
    lines = [line for line in content.get("lines", []) if line.get("product_id") == product_id]
    if len(lines) != 1:
        raise AssertionError(f"V1-21: valuation lacks unique product line: {report}")
    line = lines[0]
    if (
        Decimal(str(line.get("quantity"))) != Decimal("16")
        or Decimal(str(line.get("carrying_value"))) != Decimal("240.00")
        or Decimal(str(line.get("moving_average"))) != Decimal("15.000000000000")
        or Decimal(str(content.get("total_carrying_value"))) != Decimal("240.00")
    ):
        raise AssertionError(f"V1-21: as-of valuation differs from canonical fixture: {report}")
    return report


def assert_v1_21_inventory_http(db_path: Path) -> dict:
    initial = core._request_json("GET", "/api/onboarding")
    if initial.get("configured") is not False:
        raise AssertionError(f"V1-21: inventory database was not clean: {initial}")
    configured = core._request_json("POST", "/api/onboarding", _onboarding_payload())
    if configured.get("configured") is not True:
        raise AssertionError(f"V1-21: onboarding failed: {configured}")
    bindings = configured.get("bindings", {})
    if bindings.get("inventory") != "1104" or bindings.get("cost_of_goods_sold") != "5101":
        raise AssertionError(f"V1-21: governed inventory bindings differ: {configured}")

    product = core._request_json(
        "POST",
        "/api/inventory/products",
        {"sku": "SKU-V1-21", "name": "Mercancía V1-21", "unit": "unidad"},
    )
    if not product.get("id"):
        raise AssertionError(f"V1-21: Product identity was not created: {product}")
    product_id = int(product["id"])

    supplier = core._create_party("Proveedor V1-21", "supplier")
    customer = core._create_party("Cliente V1-21", "customer")

    first_preview, _first_prof_preview, first_result, first = _prepare_and_confirm(
        operation_kind="purchase",
        product_id=product_id,
        quantity="10",
        unit_price="10.00",
        operation_date="2026-04-10",
        settlement_method="bank",
        third_party_id=int(supplier["id"]),
        document_number="P-V1-21-001",
        issuer_name=supplier["name"],
    )
    if (
        Decimal(first_preview.get("stock_before")) != Decimal("0")
        or Decimal(first_preview.get("stock_after")) != Decimal("10")
        or Decimal(first_preview.get("inventory_value_after")) != Decimal("100.00")
        or Decimal(first_preview.get("moving_average_after")) != Decimal("10.000000000000")
        or Decimal(first_preview.get("purchase_amount")) != Decimal("100.00")
    ):
        raise AssertionError(f"V1-21: first purchase preview differs: {first_preview}")
    _assert_posted_reconciled(
        first, party_id=int(supplier["id"]), document_number="P-V1-21-001"
    )
    if _decimal_lines(first) != {
        "1104": (Decimal("100.00"), Decimal("0")),
        "1101": (Decimal("0"), Decimal("100.00")),
    }:
        raise AssertionError(f"V1-21: first purchase ledger differs: {first}")

    second_preview, _second_prof_preview, second_result, second = _prepare_and_confirm(
        operation_kind="purchase",
        product_id=product_id,
        quantity="10",
        unit_price="20.00",
        operation_date="2026-04-11",
        settlement_method="bank",
        third_party_id=int(supplier["id"]),
        document_number="P-V1-21-002",
        issuer_name=supplier["name"],
    )
    if (
        Decimal(second_preview.get("stock_after")) != Decimal("20")
        or Decimal(second_preview.get("inventory_value_after")) != Decimal("300.00")
        or second_preview.get("moving_average_after") != EXPECTED_AVERAGE
        or Decimal(second_preview.get("purchase_amount")) != Decimal("200.00")
    ):
        raise AssertionError(f"V1-21: second purchase preview differs: {second_preview}")
    _assert_posted_reconciled(
        second, party_id=int(supplier["id"]), document_number="P-V1-21-002"
    )
    if (first.get("third_party") or {}).get("id") != (second.get("third_party") or {}).get("id"):
        raise AssertionError("V1-21: two purchases did not reuse the same supplier identity")
    if _decimal_lines(second) != {
        "1104": (Decimal("200.00"), Decimal("0")),
        "1101": (Decimal("0"), Decimal("200.00")),
    }:
        raise AssertionError(f"V1-21: second purchase ledger differs: {second}")

    sale_preview, sale_prof_preview, sale_result, sale = _prepare_and_confirm(
        operation_kind="sale",
        product_id=product_id,
        quantity="4",
        unit_price="25.00",
        operation_date="2026-04-12",
        settlement_method="cash",
        third_party_id=int(customer["id"]),
        document_number="S-V1-21-001",
        issuer_name=configured.get("entity", {}).get("name", "Negocio AQR-015 instalado"),
    )
    if (
        Decimal(sale_preview.get("stock_before")) != Decimal("20")
        or Decimal(sale_preview.get("stock_after")) != Decimal("16")
        or Decimal(sale_preview.get("inventory_value_after")) != Decimal("240.00")
        or sale_preview.get("moving_average_after") != EXPECTED_AVERAGE
        or Decimal(sale_preview.get("revenue")) != Decimal("100.00")
        or Decimal(sale_preview.get("estimated_cost_of_sale")) != Decimal("60.00")
        or Decimal(sale_preview.get("margin_before_tax")) != Decimal("40.00")
    ):
        raise AssertionError(f"V1-21: sale preview differs: {sale_preview}")
    physical = sale_prof_preview.get("physical_effect", {})
    if Decimal(str(physical.get("cost_release"))) != Decimal("60.00"):
        raise AssertionError(f"V1-21: professional preview cost release differs: {sale_prof_preview}")
    _assert_posted_reconciled(
        sale, party_id=int(customer["id"]), document_number="S-V1-21-001"
    )
    movement = sale.get("movement", {})
    monetary = sale.get("monetary", {})
    if (
        Decimal(str(movement.get("quantity_delta"))) != Decimal("-4")
        or Decimal(str(movement.get("value_delta"))) != Decimal("-60.00")
        or Decimal(str(movement.get("quantity_after"))) != Decimal("16")
        or Decimal(str(movement.get("value_after"))) != Decimal("240.00")
        or movement.get("moving_average_after") != EXPECTED_AVERAGE
        or Decimal(str(monetary.get("revenue"))) != Decimal("100.00")
        or Decimal(str(monetary.get("cost_of_sale"))) != Decimal("60.00")
        or Decimal(str(monetary.get("margin"))) != Decimal("40.00")
    ):
        raise AssertionError(f"V1-21: professional sale readback differs: {sale}")
    sale_lines = _decimal_lines(sale)
    if sale_lines != {
        "1102": (Decimal("100.00"), Decimal("0")),
        "4201": (Decimal("0"), Decimal("100.00")),
        "5101": (Decimal("60.00"), Decimal("0")),
        "1104": (Decimal("0"), Decimal("60.00")),
    }:
        raise AssertionError(f"V1-21: sale ledger differs: {sale}")
    total_debit = sum((value[0] for value in sale_lines.values()), Decimal("0"))
    total_credit = sum((value[1] for value in sale_lines.values()), Decimal("0"))
    if total_debit != total_credit or total_debit != Decimal("160.00"):
        raise AssertionError(f"V1-21: sale JournalLines do not reconcile: {sale_lines}")

    valuation = _valuation(product_id, "2026-04-12")
    return {
        "product": product,
        "supplier": supplier,
        "customer": customer,
        "movement_ids": [
            int(first_result["movement_id"]),
            int(second_result["movement_id"]),
            int(sale_result["movement_id"]),
        ],
        "entry_ids": [
            int(first_result["entry_id"]),
            int(second_result["entry_id"]),
            int(sale_result["entry_id"]),
        ],
        "professionals": [first, second, sale],
        "valuation": valuation,
    }


def assert_v1_21_reopen(expected: dict) -> dict:
    onboarding = core._request_json("GET", "/api/onboarding")
    if onboarding.get("configured") is not True:
        raise AssertionError(f"V1-21 reopen: onboarding disappeared: {onboarding}")
    products = core._request_json("GET", "/api/inventory/products")
    if expected["product"] not in products:
        raise AssertionError(f"V1-21 reopen: Product identity changed: {products}")
    parties = core._request_json("GET", "/api/subledger/third-parties")
    party_ids = {item.get("id") for item in parties}
    if expected["supplier"]["id"] not in party_ids or expected["customer"]["id"] not in party_ids:
        raise AssertionError(f"V1-21 reopen: reusable ThirdParty identities changed: {parties}")

    recovered = []
    for movement_id, prior in zip(expected["movement_ids"], expected["professionals"]):
        current = core._request_json(
            "GET", f"/api/inventory/movements/{movement_id}/professional"
        )
        if current != prior:
            raise AssertionError(
                f"V1-21 reopen: durable movement {movement_id} changed across restart"
            )
        recovered.append(current)

    sale = recovered[-1]
    movement = sale["movement"]
    if (
        Decimal(str(movement["quantity_after"])) != Decimal("16")
        or Decimal(str(movement["value_after"])) != Decimal("240.00")
        or movement["moving_average_after"] != EXPECTED_AVERAGE
    ):
        raise AssertionError(f"V1-21 reopen: final inventory truth differs: {sale}")
    valuation = _valuation(int(expected["product"]["id"]), "2026-04-12")
    return {
        "product_id": expected["product"]["id"],
        "supplier_id": expected["supplier"]["id"],
        "customer_id": expected["customer"]["id"],
        "quantity": movement["quantity_after"],
        "inventory_value": movement["value_after"],
        "moving_average": movement["moving_average_after"],
        "valuation_total": valuation["content"]["total_carrying_value"],
    }


__all__ = ["assert_v1_21_inventory_http", "assert_v1_21_reopen"]
