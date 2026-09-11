from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from test_aqr012_inventory import _purchase, _setup


def _foreign_entity(session):
    from aqorath.entity import Entity, EntityProfile
    from aqorath.entity_repository import create_entity

    return create_entity(
        session,
        Entity(
            None,
            "Entidad ajena",
            "ZZZ010101ZZZ",
            "persona_moral",
            "sociedad mercantil",
            EntityProfile("lucrativo", False, ("inventory_control",), ("inventory",)),
            False,
        ),
    )


def test_foreign_product_third_party_and_bank_account_fail_before_posting(tmp_path, monkeypatch):
    from aqorath.bank_repository import create_bank_account
    from aqorath.banking import BankAccount
    from aqorath.inventory import MerchandisePurchaseFact, MerchandiseSaleFact
    from aqorath.inventory_models import ProductRecord
    from aqorath.inventory_operations import prepare_inventory_purchase, prepare_inventory_sale
    from aqorath.models import Account, JournalEntry, ThirdPartyRecord

    engine, entity, _supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        foreign = _foreign_entity(session)
        foreign_product = ProductRecord(
            entity_id=foreign.id, sku="FOREIGN", name="Producto ajeno", unit="unidad", is_active=True
        )
        foreign_party = ThirdPartyRecord(
            entity_id=foreign.id,
            name="Tercero ajeno",
            rfc="YYY010101YYY",
            party_type="supplier",
            is_active=True,
        )
        session.add_all([foreign_product, foreign_party])
        session.commit()
        bank_ledger = session.exec(select(Account).where(Account.code == "1101")).one()
        foreign_bank = create_bank_account(
            session,
            BankAccount(None, foreign.id, bank_ledger.id, "Banco ajeno", "FOREIGN-1", "MXN"),
        )
        before = len(session.exec(select(JournalEntry)).all())

        with pytest.raises(LookupError, match="product does not belong"):
            prepare_inventory_sale(
                session,
                MerchandiseSaleFact(
                    entity.id, foreign_product.id, Decimal("1"), Decimal("10"),
                    date(2026, 9, 10), "cash",
                ),
            )
        with pytest.raises(LookupError, match="supplier ThirdParty"):
            prepare_inventory_purchase(
                session,
                MerchandisePurchaseFact(
                    entity.id, product.id, Decimal("1"), Decimal("10"),
                    date(2026, 9, 10), foreign_party.id, "bank",
                ),
            )
        with pytest.raises(LookupError, match="bank account does not belong"):
            prepare_inventory_purchase(
                session,
                MerchandisePurchaseFact(
                    entity.id, product.id, Decimal("1"), Decimal("10"),
                    date(2026, 9, 10), _supplier.id, "bank",
                ),
                bank_account_id=foreign_bank.id,
            )
        assert len(session.exec(select(JournalEntry)).all()) == before


def test_owned_bank_account_selects_its_canonical_ledger_account(tmp_path, monkeypatch):
    from aqorath.bank_repository import create_bank_account
    from aqorath.banking import BankAccount
    from aqorath.inventory import MerchandisePurchaseFact
    from aqorath.inventory_operations import (
        confirm_inventory_operation,
        execute_inventory_operation,
        prepare_inventory_purchase,
    )
    from aqorath.models import Account, JournalLine

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        selected_ledger = Account(code="1105", name="Anticipos a proveedores", nature="DEBIT")
        session.add(selected_ledger)
        session.commit()
        bank = create_bank_account(
            session,
            BankAccount(None, entity.id, selected_ledger.id, "Banco propio", "OWN-1", "MXN"),
        )
        selected_ledger_id = selected_ledger.id
        prepared = prepare_inventory_purchase(
            session,
            MerchandisePurchaseFact(
                entity.id, product.id, Decimal("10"), Decimal("10"),
                date(2026, 9, 10), supplier.id, "bank",
            ),
            bank_account_id=bank.id,
        )
    result = execute_inventory_operation(confirm_inventory_operation(prepared))
    with Session(engine) as session:
        lines = session.exec(select(JournalLine).where(JournalLine.entry_id == result["entry_id"])).all()
        settlement = next(line for line in lines if Decimal(line.credit) == Decimal("100.00"))
        assert settlement.account_id == selected_ledger_id
        assert settlement.account_code == "1105"


def test_foreign_cfdi_source_fails_before_inventory_truth_is_created(tmp_path, monkeypatch):
    from aqorath.cfdi_models import CfdiSourceRecord
    from aqorath.cfdi_source_repository import import_cfdi_source
    from aqorath.inventory import MerchandiseSaleFact
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.inventory_operations import execute_inventory_operation, prepare_inventory_sale
    from aqorath.models import JournalEntry
    from aqorath.third_party import ThirdParty
    from aqorath.third_party_repository import create_third_party
    from test_aqr010_cfdi_source import _xml

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        foreign = _foreign_entity(session)
        customer = create_third_party(
            session,
            ThirdParty(None, entity.id, "Receptor CFDI", "MER260101AB1", None, None, "customer", None, None, None, True),
        )
        source = import_cfdi_source(session, _xml()).source
        row = session.get(CfdiSourceRecord, source.id)
        row.entity_id = foreign.id
        session.add(row)
        session.commit()
        source_id = source.id
        customer_id = customer.id
        _prepared, stock = _purchase(
            session, entity, supplier, product, "10", "100", date(2026, 9, 9)
        )
    execute_inventory_operation(stock)

    with Session(engine) as session:
        before_entries = len(session.exec(select(JournalEntry)).all())
        before_moves = len(session.exec(select(InventoryMovementRecord)).all())
        with pytest.raises((LookupError, ValueError), match="CFDI|Entity|source"):
            prepare_inventory_sale(
                session,
                MerchandiseSaleFact(
                    entity.id, product.id, Decimal("4"), Decimal("290"),
                    date(2026, 9, 10), "cash", customer_id,
                ),
                cfdi_source_id=source_id,
            )
        assert len(session.exec(select(JournalEntry)).all()) == before_entries
        assert len(session.exec(select(InventoryMovementRecord)).all()) == before_moves


def test_professional_readback_rejects_foreign_document_or_open_item_relationship(tmp_path, monkeypatch):
    from aqorath.inventory import MerchandisePurchaseFact
    from aqorath.inventory_operations import (
        InventoryDocumentInput,
        confirm_inventory_operation,
        execute_inventory_operation,
        prepare_inventory_purchase,
    )
    from aqorath.inventory_surface_application import load_inventory_surface_professional
    from aqorath.models import DocumentReferenceRecord, ThirdPartyRecord
    from aqorath.open_item_models import OpenItemRecord

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        foreign = _foreign_entity(session)
        foreign_party = ThirdPartyRecord(
            entity_id=foreign.id,
            name="Proveedor ajeno",
            rfc="XXX010101XXX",
            party_type="supplier",
            is_active=True,
        )
        session.add(foreign_party)
        session.flush()
        foreign_entity_id = foreign.id
        foreign_party_id = foreign_party.id
        session.commit()
        prepared = prepare_inventory_purchase(
            session,
            MerchandisePurchaseFact(
                entity.id, product.id, Decimal("10"), Decimal("10"),
                date(2026, 9, 10), supplier.id, "credit",
            ),
            document=InventoryDocumentInput("invoice", "OWN-DOC", date(2026, 9, 10), supplier.name),
            due_date=date(2026, 10, 10),
        )
    result = execute_inventory_operation(confirm_inventory_operation(prepared))

    with Session(engine) as session:
        document = session.get(DocumentReferenceRecord, result["document_reference_id"])
        document.third_party_id = foreign_party_id
        session.add(document)
        session.commit()
    with pytest.raises(RuntimeError, match="DocumentReference counterparty"):
        load_inventory_surface_professional(result["movement_id"])

    with Session(engine) as session:
        document = session.get(DocumentReferenceRecord, result["document_reference_id"])
        document.third_party_id = supplier.id
        item = session.exec(select(OpenItemRecord).where(OpenItemRecord.source_entry_id == result["entry_id"])).one()
        item.entity_id = foreign_entity_id
        session.add_all([document, item])
        session.commit()
    with pytest.raises(RuntimeError, match="OpenItem belongs to a different Entity"):
        load_inventory_surface_professional(result["movement_id"])


def test_prepared_inventory_operation_rejects_active_entity_context_switch(tmp_path, monkeypatch):
    from aqorath.inventory_models import InventoryMovementRecord
    from aqorath.inventory_operations import execute_inventory_operation
    from aqorath.models import EntityRecord, JournalEntry

    engine, entity, supplier, _customer, product, _ = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        foreign = _foreign_entity(session)
        _prepared, confirmed = _purchase(
            session, entity, supplier, product, "10", "10", date(2026, 9, 10)
        )
        active = session.get(EntityRecord, entity.id)
        other = session.get(EntityRecord, foreign.id)
        active.is_active = False
        other.is_active = True
        session.add_all([active, other])
        session.commit()

    with pytest.raises(ValueError, match="active Entity"):
        execute_inventory_operation(confirmed)
    with Session(engine) as session:
        assert session.exec(select(InventoryMovementRecord)).all() == []
        assert session.exec(select(JournalEntry)).all() == []
