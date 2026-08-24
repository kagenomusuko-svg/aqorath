"""
P0-2 TEST: Base nueva almacena dinero como STRING, no FLOAT

Verifica que una base SQLite creada con los modelos actuales
almacena debit/credit como TEXT no REAL/FLOAT.

También valida round-trip físico exacto.
"""

import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path
from aqorath.models import Account, JournalEntry, JournalLine
from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel


def test_new_database_monetary_schema():
    """
    Crea una base NEW con SQLModel.
    Verifica que debit/credit se almacenen como TEXT (no FLOAT).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_new_schema.db"
        db_url = f"sqlite:///{db_path}"
        
        # Crear engine y schema
        engine = create_engine(db_url)
        SQLModel.metadata.create_all(engine)
        
        # Verificar PRAGMA de tabla journalline
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("PRAGMA table_info('journalline')")
        columns = cur.fetchall()
        
        # Buscar tipos de debit y credit
        debit_type = None
        credit_type = None
        for cid, name, type_, notnull, dflt_val, pk in columns:
            if name == "debit":
                debit_type = type_
            elif name == "credit":
                credit_type = type_
        
        conn.close()
        
        # Verificación: debit/credit NO deben ser REAL ni FLOAT
        assert debit_type is not None, "Columna 'debit' no encontrada"
        assert credit_type is not None, "Columna 'credit' no encontrada"
        
        # Para SQLModel String, SQLite crea TEXT
        assert "REAL" not in (debit_type or "").upper(), (
            f"debit tipo es {debit_type}, debe ser TEXT no REAL"
        )
        assert "FLOAT" not in (debit_type or "").upper(), (
            f"debit tipo es {debit_type}, debe ser TEXT no FLOAT"
        )
        assert "REAL" not in (credit_type or "").upper(), (
            f"credit tipo es {credit_type}, debe ser TEXT no REAL"
        )
        assert "FLOAT" not in (credit_type or "").upper(), (
            f"credit tipo es {credit_type}, debe ser TEXT no FLOAT"
        )


def test_round_trip_monetary_exact():
    """
    Round-trip físico exacto:
    Persistir valores Decimal exactos → leer → verificar igualdad.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_roundtrip.db"
        db_url = f"sqlite:///{db_path}"
        
        engine = create_engine(db_url)
        SQLModel.metadata.create_all(engine)
        
        test_values = [
            Decimal("0.10"),
            Decimal("0.20"),
            Decimal("0.30"),
            Decimal("123456789.01"),
        ]
        
        # Escribir con Session
        with Session(engine) as session:
            acc1 = Account(code="1101", name="Bancos", nature="DEBIT")
            acc2 = Account(code="4101", name="Ingresos", nature="CREDIT")
            session.add(acc1)
            session.add(acc2)
            session.flush()
            
            for val in test_values:
                entry = JournalEntry(date=__import__('datetime').datetime.now())
                session.add(entry)
                session.flush()
                
                line1 = JournalLine(
                    entry_id=entry.id,
                    account_id=acc1.id,
                    debit=str(val),
                    credit="0"
                )
                line2 = JournalLine(
                    entry_id=entry.id,
                    account_id=acc2.id,
                    debit="0",
                    credit=str(val)
                )
                session.add(line1)
                session.add(line2)
            
            session.commit()
        
        # Leer directamente con SQL
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT debit, credit FROM journalline WHERE debit != '0' OR credit != '0'")
        rows = cur.fetchall()
        conn.close()
        
        # Verificar valores exactos
        recovered_values = set()
        for debit, credit in rows:
            if debit and debit != "0":
                recovered_values.add(Decimal(debit))
            if credit and credit != "0":
                recovered_values.add(Decimal(credit))
        
        for val in test_values:
            assert val in recovered_values, (
                f"Valor {val} no recuperado. Recuperados: {recovered_values}"
            )
