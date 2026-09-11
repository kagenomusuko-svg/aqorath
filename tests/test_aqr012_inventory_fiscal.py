from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from test_aqr012_inventory import _purchase, _setup


def _enable_general_sale_fiscality(engine, entity):
    from aqorath import fiscal_rule_data_mx as data
    from aqorath.account_bindings import set_account_binding
    from aqorath.entity import FiscalProfile
    from aqorath.entity_repository import register_fiscal_profile
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.models import Account

    with Session(engine) as session:
        register_fiscal_profile(
            session,
            FiscalProfile(
                id=None,
                entity_id=entity.id,
                jurisdiction="MX",
                fiscal_regime_code="603",
                tax_characteristics=(),
                effective_from=date(2026, 1, 1),
                effective_to=None,
            ),
        )
        vat = Account(code="2080", name="IVA trasladado", nature="CREDIT")
        session.add(vat)
        session.commit()
        set_account_binding(session, "tax_payable", vat.code)
        install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)
    return engine


def test_supported_fiscal_inventory_sale_is_one_balanced_posting_with_one_truth(tmp_path, monkeypatch):
    from aqorath.inventory import MerchandiseSaleFact
    from aqorath.inventory_operations import (
        confirm_inventory_operation,
        execute_inventory_operation,
        prepare_inventory_sale,
    )
    from aqorath.inventory_surface_application import load_inventory_surface_professional
    from aqorath.models import AuditEventRecord, FiscalPostingAuditRecord, JournalEntry, JournalLine

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    _enable_general_sale_fiscality(engine, entity)
    with Session(engine) as session:
        _prepared, stock = _purchase(
            session, entity, supplier, product, "10", "10", date(2026, 9, 9)
        )
    execute_inventory_operation(stock)

    with Session(engine) as session:
        prepared = prepare_inventory_sale(
            session,
            MerchandiseSaleFact(
                entity.id,
                product.id,
                Decimal("4"),
                Decimal("25"),
                date(2026, 9, 10),
                "cash",
            ),
            fiscal_activity="ordinary_taxable_sale",
        )
        assert prepared.revenue_or_purchase_amount == Decimal("100.00")
        assert prepared.inventory_cost == Decimal("40.00")
        assert prepared.fiscal_prepared is not None
        assert [
            (line.account_role, line.side, line.amount)
            for line in prepared.fiscal_prepared.snapshot.lines
        ] == [
            ("cash", "debit", Decimal("116.00")),
            ("sales_revenue", "credit", Decimal("100.00")),
            ("tax_payable", "credit", Decimal("16.00")),
        ]
        confirmed = confirm_inventory_operation(prepared)

    result = execute_inventory_operation(confirmed)
    with Session(engine) as session:
        entries = session.exec(select(JournalEntry).order_by(JournalEntry.id)).all()
        assert len(entries) == 2  # stock receipt + one sale; never a second fiscal posting.
        lines = session.exec(
            select(JournalLine).where(JournalLine.entry_id == result["entry_id"])
        ).all()
        assert len(lines) == 5
        assert sum((Decimal(line.debit) for line in lines), Decimal("0")) == Decimal("156.00")
        assert sum((Decimal(line.credit) for line in lines), Decimal("0")) == Decimal("156.00")
        assert len(session.exec(
            select(FiscalPostingAuditRecord).where(FiscalPostingAuditRecord.entry_id == result["entry_id"])
        ).all()) == 1
        events = session.exec(
            select(AuditEventRecord).where(AuditEventRecord.entity_id == entity.id)
        ).all()
        event_types = [event.event_type for event in events]
        assert event_types.count("entry_posted") == 1
        assert event_types.count("inventory_operation_posted") == 2

    professional = load_inventory_surface_professional(result["movement_id"])
    assert professional["fiscality"]["coverage_version"] == "mx-fiscal-v1.2026-09-10"
    assert professional["monetary"] == {
        "purchase_amount": None,
        "revenue": "100.00",
        "cost_of_sale": "40.00",
        "margin": "60.00",
    }
    assert professional["fiscality"]["facts"]["activity"] == "ordinary_taxable_sale"
    assert professional["fiscality"]["facts"]["base"] == "100.00"


def test_inventory_does_not_infer_fiscality_and_unsupported_explicit_activity_fails_closed(tmp_path, monkeypatch):
    from aqorath.fiscal_v1_coverage import UnsupportedFiscalV1Case
    from aqorath.inventory import MerchandiseSaleFact
    from aqorath.inventory_operations import (
        confirm_inventory_operation,
        execute_inventory_operation,
        prepare_inventory_sale,
    )
    from aqorath.inventory_surface_application import load_inventory_surface_professional
    from aqorath.models import JournalEntry

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    _enable_general_sale_fiscality(engine, entity)
    with Session(engine) as session:
        _prepared, stock = _purchase(
            session, entity, supplier, product, "10", "10", date(2026, 9, 9)
        )
    execute_inventory_operation(stock)

    with Session(engine) as session:
        plain = prepare_inventory_sale(
            session,
            MerchandiseSaleFact(
                entity.id, product.id, Decimal("1"), Decimal("25"),
                date(2026, 9, 10), "cash",
            ),
        )
        assert plain.fiscal_prepared is None
    plain_result = execute_inventory_operation(confirm_inventory_operation(plain))
    assert load_inventory_surface_professional(plain_result["movement_id"])["fiscality"] is None

    with Session(engine) as session:
        before = len(session.exec(select(JournalEntry)).all())
        with pytest.raises(UnsupportedFiscalV1Case):
            prepare_inventory_sale(
                session,
                MerchandiseSaleFact(
                    entity.id, product.id, Decimal("1"), Decimal("25"),
                    date(2026, 9, 10), "cash",
                ),
                fiscal_activity="land_freight_goods",
            )
        assert len(session.exec(select(JournalEntry)).all()) == before


def test_fiscalized_inventory_sale_requires_supported_settlement_before_posting(tmp_path, monkeypatch):
    from aqorath.fiscal_v1_coverage import UnsupportedFiscalV1Case
    from aqorath.inventory import MerchandiseSaleFact
    from aqorath.inventory_operations import execute_inventory_operation, prepare_inventory_sale
    from aqorath.models import JournalEntry

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    _enable_general_sale_fiscality(engine, entity)
    with Session(engine) as session:
        _prepared, stock = _purchase(
            session, entity, supplier, product, "10", "10", date(2026, 9, 9)
        )
    execute_inventory_operation(stock)

    with Session(engine) as session:
        before = len(session.exec(select(JournalEntry)).all())
        with pytest.raises(UnsupportedFiscalV1Case):
            prepare_inventory_sale(
                session,
                MerchandiseSaleFact(
                    entity.id, product.id, Decimal("1"), Decimal("25"),
                    date(2026, 9, 10), "bank",
                ),
                fiscal_activity="ordinary_taxable_sale",
            )
        assert len(session.exec(select(JournalEntry)).all()) == before
