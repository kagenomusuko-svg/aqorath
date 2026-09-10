from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

from sqlalchemy import create_engine
from sqlmodel import Session


def test_schema10_adds_inkind_evidence_without_backfill(tmp_path):
    from aqorath.migrations import migrate_database
    path = tmp_path / "donations.db"
    migrate_database(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
        assert {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} >= {"donation", "inkinddonation"}
        assert conn.execute("SELECT count(*) FROM inkinddonation").fetchone()[0] == 0


def test_inkind_donation_persists_exact_valuation_and_never_posts(tmp_path):
    from aqorath.entity import Entity, EntityProfile
    from aqorath.entity_repository import create_entity
    from aqorath.inkind_donation import InKindDonation
    from aqorath.inkind_donation_repository import create_inkind_donation
    path = tmp_path / "donations.db"
    from aqorath.migrations import migrate_database
    migrate_database(path)
    engine = create_engine(f"sqlite:///{path}")
    with Session(engine) as session:
        entity = create_entity(session, Entity(id=None, name="OSC", rfc=None, legal_personality="persona_moral", legal_form="A.C.", profile=EntityProfile("no_lucrativo", False, ("osc",), ("banking",)), is_active=True))
        item = create_inkind_donation(session, InKindDonation(None, entity.id, None, None, None, None, None, datetime(2026, 1, 2, tzinfo=timezone.utc), "Computadoras", Decimal("2"), Decimal("1500.00"), "MXN", "appraisal", "Avalúo firmado", "IK-001"))
        assert item.valuation_amount == Decimal("1500.00")
        assert session.exec(__import__("sqlmodel").select(__import__("aqorath.models", fromlist=["InKindDonationRecord"]).InKindDonationRecord)).one().valuation_amount == "1500.00"
