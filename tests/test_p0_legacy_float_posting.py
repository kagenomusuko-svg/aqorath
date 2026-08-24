"""
P0-2 TEST: Legacy float input conversion via entry_dict posting.

Verifica que float legacy (0.1, 0.2) se conviertan exactamente:
  float → to_decimal_exact() → Decimal(str(float)) → exacto en SQLite
"""

from decimal import Decimal
from pathlib import Path
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session
from aqorath.core import post_entry, trial_balance
from aqorath.models import Account


def test_legacy_float_entry_dict_exact(tmp_path, monkeypatch):
    """
    Post two legacy entry dicts with float 0.1 and 0.2.
    
    Esperado: trial_balance suma exactamente a 0.30, no 0.30000000...
    """
    # Setup isolated database
    db_file = tmp_path / "legacy_float.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, echo=False)
    SQLModel.metadata.create_all(engine)
    
    # Create accounts
    with Session(engine) as session:
        acc_1101 = Account(code="1101", name="Bancos", nature="DEBIT")
        acc_4101 = Account(code="4101", name="Ingresos", nature="CREDIT")
        session.add(acc_1101)
        session.add(acc_4101)
        session.commit()
    
    monkeypatch.setenv("AQORATH_DB", str(db_file))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    
    # Entry 1 with float 0.1
    entry_dict_1 = {
        "description": "Legacy float 0.1",
        "lines": [
            {
                "account_code": "1101",
                "debit": 0.1,  # float legacy
                "credit": 0,
                "description": "Test debit"
            },
            {
                "account_code": "4101",
                "debit": 0,
                "credit": 0.1,  # float legacy
                "description": "Test credit"
            }
        ]
    }
    result_1 = post_entry(entry_dict_1, user="test")
    # post_entry returns dict for entry_dict input
    assert isinstance(result_1, dict) and result_1.get("ok"), f"Entry 1 failed: {result_1}"
    entry_id_1 = result_1["entry_id"]
    
    # Entry 2 with float 0.2
    entry_dict_2 = {
        "description": "Legacy float 0.2",
        "lines": [
            {
                "account_code": "1101",
                "debit": 0.2,  # float legacy
                "credit": 0,
                "description": "Test debit"
            },
            {
                "account_code": "4101",
                "debit": 0,
                "credit": 0.2,  # float legacy
                "description": "Test credit"
            }
        ]
    }
    result_2 = post_entry(entry_dict_2, user="test")
    assert isinstance(result_2, dict) and result_2.get("ok"), f"Entry 2 failed: {result_2}"
    entry_id_2 = result_2["entry_id"]
    
    # Trial balance
    balances = trial_balance()
    saldo_1101 = balances.get("1101", Decimal("0"))
    saldo_4101 = balances.get("4101", Decimal("0"))
    
    # 0.1 + 0.2 = 0.3 exactly
    assert saldo_1101 == Decimal("0.30"), (
        f"1101: esperado 0.30, actual {saldo_1101} (float legacy failed)"
    )
    assert saldo_4101 == Decimal("-0.30"), (
        f"4101: esperado -0.30, actual {saldo_4101}"
    )
    
    # Exactness check (no binary float artifacts)
    # Decimal("0.3") stringifies to "0.3", not "0.30"
    # The important check is that it equals Decimal("0.30") exactly
    assert str(saldo_1101) == "0.3"
    assert str(saldo_4101) == "-0.3"
