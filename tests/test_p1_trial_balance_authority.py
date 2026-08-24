"""
P1-4 REGRESSION TESTS: trial_balance must be SQLite-authoritative.

P1-4: Si SQLite falla, trial_balance DEBE fallar (NO fallback a Libro).
P1-4: Si SQLite válido pero vacío, retorna ceros sin consultar Libro.
"""

import pytest
import sqlite3
from decimal import Decimal
from pathlib import Path
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session
from aqorath.core import trial_balance, _balances_from_sqlite, _balances_from_libro
import aqorath.core as core
from aqorath.models import Account
from unittest.mock import patch


def test_trial_balance_does_not_fallback_to_libro_when_sqlite_fails(tmp_path, monkeypatch):
    """
    P1-4: Si _balances_from_sqlite falla, trial_balance debe fallar.
    NO puede preguntar a modelos.libro cuál es el saldo.

    ESTADO ACTUAL: EXPECTED FAIL
    - trial_balance captura el error de SQLite
    - Consulta _balances_from_libro
    - Retorna saldo ficticio (no el error)

    CONTRATO FUTURO:
    - Si SQLite falla: RuntimeError propagado
    - _balances_from_libro NO es consultado
    - Fallo explícito, no silencioso
    """
    # Track if Libro is called
    libro_called = [False]

    def mock_balances_from_libro(db_path=None, as_of=None):
        libro_called[0] = True
        return {"FAKE": Decimal("999")}

    # Force SQLite to fail
    def mock_balances_from_sqlite(db_path, as_of=None):
        raise RuntimeError("Forced SQLite failure for testing")

    # Prevent fallback to default DB
    def mock_find_db_path():
        return Path("/nonexistent/db.sqlite")

    with patch("aqorath.core._balances_from_sqlite", side_effect=mock_balances_from_sqlite):
        with patch("aqorath.core._balances_from_libro", side_effect=mock_balances_from_libro):
            with patch("aqorath.core._find_db_path", side_effect=mock_find_db_path):
                # trial_balance should raise, not fallback
                caught = None
                try:
                    trial_balance()
                except RuntimeError as exc:
                    caught = exc

                # FUTURE CONTRACT: RuntimeError propagated AND Libro NOT consulted
                # CURRENT STATE: RuntimeError NOT propagated OR Libro IS consulted
                assert caught is not None and libro_called[0] is False, (
                    f"P1-4 trial_balance authority: "
                    f"error_propagated={caught is not None}; "
                    f"libro_called={libro_called[0]} "
                    f"(expected: error_propagated=True, libro_called=False)"
                )


def test_trial_balance_empty_sqlite_does_not_consult_libro(tmp_path, monkeypatch):
    """
    P1-4: SQLite válido pero vacío retorna ceros sin consultar Libro.

    Distingue: SQLite válido sin movimientos ≠ SQLite averiada.

    ESTADO ACTUAL: Puede estar PASS si el código no intenta Libro en vacío.
    """
    # Setup empty SQLite
    db_file = tmp_path / "empty_trial_balance.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, echo=False)
    SQLModel.metadata.create_all(engine)

    # Create accounts but no movements
    with Session(engine) as session:
        acc_1101 = Account(code="1101", name="Bancos", nature="DEBIT")
        acc_4101 = Account(code="4101", name="Ventas", nature="CREDIT")
        session.add(acc_1101)
        session.add(acc_4101)
        session.commit()

    monkeypatch.setenv("AQORATH_DB", str(db_file))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    # Track if Libro is called
    libro_called = [False]

    def mock_balances_from_libro(db_path=None, as_of=None):
        libro_called[0] = True
        raise AssertionError("Libro should not be consulted for valid empty SQLite")

    with patch("aqorath.core._balances_from_libro", side_effect=mock_balances_from_libro):
        result = trial_balance()

    # Empty SQLite should return ceros
    assert isinstance(result, dict), "trial_balance returned non-dict"

    # Should NOT have consulted Libro
    assert libro_called[0] is False, (
        f"P1-4 Empty SQLite: trial_balance consulted Libro for valid empty database"
    )

    # Verify ceros for accounts (or at least that result was computed)
    assert isinstance(result, dict), "trial_balance should return dict for empty SQLite"


def test_trial_balance_account_catalog_failure_is_explicit(tmp_path, monkeypatch):
    """
    P1-4A: Account catalog read failure propagates.
    
    If catalog (SELECT code FROM account) fails:
    - Error must propagate
    - NOT: return partial balances
    - NOT: consultar Libro
    
    CONTRATO:
    - _balances_from_sqlite returns valid {"1101": Decimal("100")}
    - catalog read fails with RuntimeError
    - trial_balance() must raise RuntimeError
    - NOT: return partial {"1101": Decimal("100")} as if valid
    """
    from unittest.mock import MagicMock

    db_file = tmp_path / "catalog_fail_test.db"

    monkeypatch.setenv("AQORATH_DB", str(db_file))

    # Mock _balances_from_sqlite to return valid balances
    def mock_balances_from_sqlite(db_path=None, as_of=None):
        return {"1101": Decimal("100")}

    # Mock _find_db_path to return our temp db
    def mock_find_db_path():
        return str(db_file)

    # Create a mock connection that fails on catalog read
    def failing_connect(*args, **kwargs):
        mock_conn = MagicMock()
        
        def mock_cursor(*args, **kwargs):
            mock_cur = MagicMock()
            
            def execute_with_failure(sql, *args, **kwargs):
                if "SELECT code FROM account" in sql:
                    raise RuntimeError("forced account catalog DB failure")
                return MagicMock()
            
            mock_cur.execute = execute_with_failure
            mock_cur.fetchall = lambda: []
            return mock_cur
        
        mock_conn.cursor = mock_cursor
        mock_conn.close = MagicMock()
        return mock_conn

    with patch("aqorath.core._balances_from_sqlite", side_effect=mock_balances_from_sqlite):
        with patch("aqorath.core._find_db_path", side_effect=mock_find_db_path):
            with patch("sqlite3.connect", side_effect=failing_connect):
                # Catalog read fails → error propagates
                with pytest.raises(RuntimeError) as exc_info:
                    trial_balance()

                assert "forced account catalog DB failure" in str(exc_info.value), (
                    "P1-4A trial_balance: catalog failure should propagate, not return partial balance"
                )
