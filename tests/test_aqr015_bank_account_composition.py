"""AQR-015 V1-05 product composition over governed bank subaccounts."""

import json
from decimal import Decimal

import pytest
from sqlmodel import Session, select


def _configured_bank_surface(tmp_path, monkeypatch, name):
    from test_aqr015_onboarding import _fresh_db, _payload
    from aqorath.onboarding_surface_application import configure_surface_onboarding
    from aqorath.presentation_controller import LocalPresentationController

    _db, engine = _fresh_db(tmp_path, monkeypatch, name)
    configure_surface_onboarding(_payload())
    return engine, LocalPresentationController()


def test_v1_05_two_product_bank_accounts_use_distinct_governed_accounts_and_one_transfer(tmp_path, monkeypatch):
    from aqorath.account_bindings import get_account_binding
    from aqorath.banking_models import BankAccountRecord
    from aqorath.models import Account, AuditEventRecord, JournalEntry, JournalLine

    engine, controller = _configured_bank_surface(tmp_path, monkeypatch, "v1-05.db")

    source = controller.create_bank_account({
        "institution_name": "Banco Origen",
        "account_identifier": "ORIGEN-001",
        "currency": "MXN",
    })
    destination = controller.create_bank_account({
        "institution_name": "Banco Destino",
        "account_identifier": "DESTINO-001",
        "currency": "MXN",
    })

    assert source["ledger_account_id"] != destination["ledger_account_id"]

    with Session(engine) as session:
        parent = session.exec(select(Account).where(Account.code == "1101")).one()
        children = session.exec(
            select(Account)
            .where(Account.parent_id == parent.id, Account.origin == "entity")
            .order_by(Account.code)
        ).all()
        assert [item.code for item in children] == ["1101.001", "1101.002"]
        assert all(item.nature == parent.nature for item in children)
        assert [item.id for item in children] == [
            source["ledger_account_id"],
            destination["ledger_account_id"],
        ]
        persisted_banks = session.exec(
            select(BankAccountRecord).order_by(BankAccountRecord.id)
        ).all()
        assert [item.ledger_account_id for item in persisted_banks] == [
            source["ledger_account_id"],
            destination["ledger_account_id"],
        ]
        # The generic/default bank binding remains governed independently.
        assert get_account_binding(session, "bank") == "1101"

    result = controller.bank_transfer({
        "source_bank_account_id": source["id"],
        "destination_bank_account_id": destination["id"],
        "amount": "300.00",
        "posting_date": "2026-09-10",
        "description": "Transferencia entre cuentas propias V1-05",
    })

    professional = controller.professional_operation(result["entry_id"])
    assert professional["state"] == "posted"
    assert professional["period"]["id"] == 202609
    assert [
        (line["account_id"], Decimal(line["debit"]), Decimal(line["credit"]))
        for line in professional["lines"]
    ] == [
        (destination["ledger_account_id"], Decimal("300.00"), Decimal("0")),
        (source["ledger_account_id"], Decimal("0"), Decimal("300.00")),
    ]

    with Session(engine) as session:
        assert session.exec(select(JournalEntry)).all().__len__() == 1
        lines = session.exec(
            select(JournalLine)
            .where(JournalLine.entry_id == result["entry_id"])
            .order_by(JournalLine.id)
        ).all()
        assert [(line.account_id, Decimal(line.debit), Decimal(line.credit)) for line in lines] == [
            (destination["ledger_account_id"], Decimal("300.00"), Decimal("0")),
            (source["ledger_account_id"], Decimal("0"), Decimal("300.00")),
        ]
        audit = session.get(AuditEventRecord, result["audit_event_id"])
        assert audit.event_type == "bank_transfer_posted"
        details = json.loads(audit.details_json)
        assert details["entry_id"] == result["entry_id"]
        assert details["source_bank_account_id"] == source["id"]
        assert details["destination_bank_account_id"] == destination["id"]
        assert Decimal(details["amount"]) == Decimal("300.00")

    # A new session sees the same bank -> governed Account identities.
    with Session(engine) as session:
        reopened_source = session.get(BankAccountRecord, source["id"])
        reopened_destination = session.get(BankAccountRecord, destination["id"])
        assert reopened_source.ledger_account_id == source["ledger_account_id"]
        assert reopened_destination.ledger_account_id == destination["ledger_account_id"]

        entries_before = len(session.exec(select(JournalEntry)).all())
        audits_before = len(session.exec(select(AuditEventRecord)).all())

    with pytest.raises(ValueError, match="must differ"):
        controller.bank_transfer({
            "source_bank_account_id": source["id"],
            "destination_bank_account_id": source["id"],
            "amount": "1.00",
            "posting_date": "2026-09-10",
            "description": "No debe persistir",
        })

    with Session(engine) as session:
        assert len(session.exec(select(JournalEntry)).all()) == entries_before
        assert len(session.exec(select(AuditEventRecord)).all()) == audits_before


def test_v1_05_product_bank_account_creation_rolls_back_governed_extension_on_late_failure_and_retries_cleanly(tmp_path, monkeypatch):
    import aqorath.surface_application as surface
    from aqorath.banking_models import BankAccountRecord
    from aqorath.models import Account

    engine, controller = _configured_bank_surface(tmp_path, monkeypatch, "v1-05-rollback.db")
    original = surface._banks._stage_bank_account

    def fail_after_account_extension(*args, **kwargs):
        raise RuntimeError("simulated BankAccount staging failure")

    monkeypatch.setattr(surface._banks, "_stage_bank_account", fail_after_account_extension)

    with pytest.raises(RuntimeError, match="simulated BankAccount staging failure"):
        controller.create_bank_account({
            "institution_name": "Banco Fallido",
            "account_identifier": "FAIL-001",
            "currency": "MXN",
        })

    with Session(engine) as session:
        parent = session.exec(select(Account).where(Account.code == "1101")).one()
        assert session.exec(
            select(Account).where(Account.parent_id == parent.id, Account.origin == "entity")
        ).all() == []
        assert session.exec(select(BankAccountRecord)).all() == []

    monkeypatch.setattr(surface._banks, "_stage_bank_account", original)
    recovered = controller.create_bank_account({
        "institution_name": "Banco Recuperado",
        "account_identifier": "RECOVER-001",
        "currency": "MXN",
    })

    with Session(engine) as session:
        ledger = session.get(Account, recovered["ledger_account_id"])
        bank = session.get(BankAccountRecord, recovered["id"])
        assert ledger.code == "1101.001"
        assert ledger.origin == "entity"
        assert bank.ledger_account_id == ledger.id
