"""
P0-2 TEST: End-to-end template mode posting with real Decimal exactness.

Verifica que post_entry(template_mode, Decimal) complete:
  Decimal → post_entry → templates.py → generate_preview → _persist_entry → SQLite → trial_balance
"""

from decimal import Decimal
from pathlib import Path
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session
from aqorath.core import post_entry, trial_balance
from aqorath.models import Account


def test_pago_proveedor_decimal_exact_e2e(tmp_path, monkeypatch):
    """
    Real end-to-end: Two pago_proveedor operations with Decimal input.
    
    Operación 1: post_entry("pago_proveedor", Decimal("0.10"))
    Operación 2: post_entry("pago_proveedor", Decimal("0.20"))
    
    Esperado: Saldo exacto 0.30 (sin float artifacts).
    """
    # Setup isolated database
    db_file = tmp_path / "template_e2e.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, echo=False)
    SQLModel.metadata.create_all(engine)
    
    # Create canonical accounts
    with Session(engine) as session:
        acc_1101 = Account(code="1101", name="Bancos", nature="DEBIT")
        acc_2101 = Account(code="2101", name="Proveedores", nature="CREDIT")
        session.add(acc_1101)
        session.add(acc_2101)
        session.commit()
    
    # Point environment to this DB
    monkeypatch.setenv("AQORATH_DB", str(db_file))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    
    # Operation 1: Decimal("0.10")
    entry_id_1 = post_entry(
        "pago_proveedor",
        Decimal("0.10"),
        ctx={
            "account_codes": {"bank": "1101", "payable": "2101"},
            "desc": "Pago 1"
        },
        user="test"
    )
    assert isinstance(entry_id_1, int), "Entry 1 failed"
    
    # Operation 2: Decimal("0.20")
    entry_id_2 = post_entry(
        "pago_proveedor",
        Decimal("0.20"),
        ctx={
            "account_codes": {"bank": "1101", "payable": "2101"},
            "desc": "Pago 2"
        },
        user="test"
    )
    assert isinstance(entry_id_2, int), "Entry 2 failed"
    
    # Get trial balance
    balances = trial_balance()
    
    saldo_2101 = balances.get("2101", Decimal("0"))
    saldo_1101 = balances.get("1101", Decimal("0"))
    
    # pago_proveedor: 2101 DEBIT, 1101 CREDIT
    # Expected: 0.10 + 0.20 = 0.30 exactly
    assert saldo_2101 == Decimal("0.30"), (
        f"Proveedores (2101): esperado 0.30, actual {saldo_2101}"
    )
    assert saldo_1101 == Decimal("-0.30"), (
        f"Bancos (1101): esperado -0.30, actual {saldo_1101}"
    )
    
    # Verify exactness (no 0.30000000...)
    assert str(saldo_2101) == "0.30"
    assert str(saldo_1101) == "-0.30"
