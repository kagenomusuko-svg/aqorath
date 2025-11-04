from __future__ import annotations
"""
Utilities para el cierre del ejercicio contable.

Comportamiento principal:
- Crea backup en ~/.local/share/aqorath/ejercicios/YYYYMMDD_HHMMSS/
- Calcula resultado del ejercicio usando trial_balance() + catálogo (accounting_rules).
- Verifica que las cuentas 3103 y 3104 EXISTAN en la tabla account; si faltan, ABORTA el traslado (pero deja el backup).
- Inserta el JournalEntry de traslado usando SQLModel si es posible; si falla, usa inserción sqlite directa.
- Nunca crea cuentas automáticamente.
"""
import json
import os
import shutil
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

import sqlite3

# Import project helpers defensivamente
try:
    from aqorath.storage import get_session
except Exception:
    get_session = None  # fallback a sqlite cuando sea necesario

# Import functions we designed earlier
try:
    from aqorath.core import trial_balance
except Exception:
    trial_balance = None

try:
    from aqorath.accounting_rules import load_catalog, compute_resultado_ejercicio
except Exception:
    load_catalog = None
    compute_resultado_ejercicio = None

# Try ORM models if available
try:
    from aqorath.models import Account, JournalEntry, JournalLine  # type: ignore
except Exception:
    Account = None
    JournalEntry = None
    JournalLine = None

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

DEFAULT_DB_CANDIDATES = [
    os.environ.get("AQORATH_DB"),
    "tests/test.db",
    "datos/aqorath.db",
    "aqorath.db",
    "test.db",
]

OUT_ROOT_DEFAULT = Path.home() / ".local" / "share" / "aqorath" / "ejercicios"


def _find_db_path() -> Optional[Path]:
    for p in DEFAULT_DB_CANDIDATES:
        if not p:
            continue
        pth = Path(p)
        if pth.exists():
            return pth
    return None


def _copy_files(dest: Path, db_path: Optional[Path]):
    dest.mkdir(parents=True, exist_ok=True)
    if db_path and db_path.exists():
        shutil.copy2(db_path, dest / db_path.name)
    # copy catalog if exists
    catalog_path = Path("aqorath") / "data" / "catalogo_base.json"
    if catalog_path.exists():
        shutil.copy2(catalog_path, dest / catalog_path.name)


def _account_exists_sqlite(db_path: Path, code: str) -> Optional[int]:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM account WHERE code = ? LIMIT 1", (str(code),))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _insert_transfer_sqlite(db_path: Path, amount: Decimal, id_3103: int, id_3104: int) -> None:
    """
    Inserta entry y journallines directamente en sqlite.
    Asume esquema común (entry table, journalline table). Si nombres distintos puede fallar.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        now = datetime.utcnow().isoformat()
        # Detect entry table name
        entry_table = None
        for candidate in ("entry", "journalentry", "journal_entry"):
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (candidate,))
            if cur.fetchone():
                entry_table = candidate
                break
        if entry_table is None:
            raise RuntimeError("No se encontró tabla de entries en la DB")

        cur.execute(f"INSERT INTO {entry_table} (description, created_at) VALUES (?, ?)", (f"Cierre ejercicio traslado {amount}", now))
        entry_id = cur.lastrowid

        jl_table = None
        for cand in ("journalline", "journal_line", "line", "journalentryline"):
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (cand,))
            if cur.fetchone():
                jl_table = cand
                break
        if jl_table is None:
            raise RuntimeError("No se encontró tabla journalline en la DB")

        if amount > 0:
            d = str(amount)
            # Débito 3103, Crédito 3104
            cur.execute(
                f"INSERT INTO {jl_table} (entry_id, account_id, debit, credit, description, created_at) VALUES (?,?,?,?,?,?)",
                (entry_id, id_3103, d, "0", "Cierre: traslado a 3104", now),
            )
            cur.execute(
                f"INSERT INTO {jl_table} (entry_id, account_id, debit, credit, description, created_at) VALUES (?,?,?,?,?,?)",
                (entry_id, id_3104, "0", d, "Cierre: contrapartida desde 3103", now),
            )
        else:
            amt = str(abs(amount))
            cur.execute(
                f"INSERT INTO {jl_table} (entry_id, account_id, debit, credit, description, created_at) VALUES (?,?,?,?,?,?)",
                (entry_id, id_3104, amt, "0", "Cierre pérdida: traslado a 3104", now),
            )
            cur.execute(
                f"INSERT INTO {jl_table} (entry_id, account_id, debit, credit, description, created_at) VALUES (?,?,?,?,?,?)",
                (entry_id, id_3103, "0", amt, "Cierre pérdida: contrapartida desde 3104", now),
            )

        conn.commit()
    finally:
        conn.close()


def close_exercise(carry_over: bool = True, out_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Realiza backup y, si carry_over True, traslada el resultado del ejercicio de 3103 a 3104.
    No crea cuentas bajo ninguna circunstancia.
    """
    out_root = out_root or OUT_ROOT_DEFAULT
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = out_root / ts
    db_path = _find_db_path()

    # Crear backup primero (si es posible copiar archivos)
    try:
        _copy_files(dest, db_path)
    except Exception as e:
        LOG.exception("Error creando backup: %s", e)
        return {"ok": False, "error": f"Error creando backup: {e}"}

    if not carry_over:
        return {"ok": True, "path": str(dest), "note": "Backup creado, no se realizó traslado de saldos."}

    # Calcular balances y resultado usando rules
    try:
        balances: Dict[str, Decimal] = {}
        if trial_balance is not None:
            balances = trial_balance()
        else:
            LOG.info("trial_balance no disponible; intentando lectura sqlite directa")
            dbp = db_path or _find_db_path()
            if dbp is None:
                return {"ok": False, "path": str(dest), "error": "No se encontró base de datos para calcular saldos."}
            # fallback: simple aggregation implemented inline (account_code or account_id)
            conn = sqlite3.connect(str(dbp))
            try:
                cur = conn.cursor()
                cur.execute("PRAGMA table_info('journalline')")
                cols = [r[1] for r in cur.fetchall()]
                acct_col = next((c for c in cols if "account" in c.lower() or c.endswith("_id")), None)
                debit_col = next((c for c in cols if c.lower() in ("debit", "debe", "cargo")), None)
                credit_col = next((c for c in cols if c.lower() in ("credit", "haber", "abono")), None)
                if not acct_col:
                    return {"ok": False, "path": str(dest), "error": "No se pudo detectar columna de cuenta en journalline."}
                q_debit = debit_col or "0"
                q_credit = credit_col or "0"
                # try join with account to get codes if account_id present
                if acct_col == "account_id":
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='account'")
                    if cur.fetchone():
                        sql = f'''SELECT COALESCE(a.code, CAST(jl.account_id AS TEXT)) as acct_code,
                                       SUM(COALESCE(jl.{q_debit},0) - COALESCE(jl.{q_credit},0)) as saldo
                                 FROM journalline jl
                                 LEFT JOIN account a ON jl.account_id = a.id
                                 GROUP BY acct_code'''
                        cur.execute(sql)
                        rows = cur.fetchall()
                        for acct_code, saldo in rows:
                            balances[str(acct_code)] = Decimal(str(saldo or 0))
                    else:
                        sql = f'''SELECT CAST(account_id AS TEXT) as acct_code,
                                       SUM(COALESCE({q_debit},0) - COALESCE({q_credit},0)) as saldo
                                 FROM journalline GROUP BY acct_code'''
                        cur.execute(sql)
                        rows = cur.fetchall()
                        for acct_code, saldo in rows:
                            balances[str(acct_code)] = Decimal(str(saldo or 0))
                else:
                    sql = f'''SELECT COALESCE({acct_col}, '') as acct_code,
                                   SUM(COALESCE({q_debit},0) - COALESCE({q_credit},0)) as saldo
                             FROM journalline GROUP BY acct_code'''
                    cur.execute(sql)
                    rows = cur.fetchall()
                    for acct_code, saldo in rows:
                        if acct_code is None or acct_code == "":
                            continue
                        balances[str(acct_code)] = Decimal(str(saldo or 0))
            finally:
                conn.close()

        # cargar catálogo
        catalog: Dict[str, dict] = {}
        if load_catalog is not None:
            catalog = load_catalog()
        else:
            # intentar leer JSON directamente (defensivo)
            p = Path("aqorath/data/catalogo_base.json")
            if p.exists():
                try:
                    catalog = json.loads(p.read_text(encoding="utf-8")).get("accounts", {})
                except Exception:
                    catalog = {}

        # calcular resultado del ejercicio (usando catálogo)
        if compute_resultado_ejercicio is not None:
            resultado, totals = compute_resultado_ejercicio(balances, catalog)
        else:
            # fallback: intentar usar saldo de 3103 si existe, sino 0
            resultado = Decimal(0)
            if "3103" in balances:
                resultado = Decimal(str(balances["3103"]))
            else:
                # buscar key cuyo código termine en 3103
                k3103 = next((k for k in balances.keys() if k.endswith("3103")), None)
                if k3103:
                    resultado = Decimal(str(balances[k3103]))

    except Exception as e:
        LOG.exception("Error calculando resultado 3103: %s", e)
        return {"ok": False, "path": str(dest), "error": f"No se pudo calcular resultado: {e}"}

    # Verificar existencia de cuentas 3103 y 3104 (NO crear)
    id_3103: Optional[int] = None
    id_3104: Optional[int] = None
    # Intentar resolver vía ORM si está disponible
    try:
        if Account is not None and get_session is not None:
            with get_session() as s:
                acc_3103 = s.exec(__import__("sqlmodel").sql.select(Account).where(Account.code == "3103")).one_or_none()
                acc_3104 = s.exec(__import__("sqlmodel").sql.select(Account).where(Account.code == "3104")).one_or_none()
                if acc_3103:
                    id_3103 = acc_3103.id
                if acc_3104:
                    id_3104 = acc_3104.id
    except Exception:
        LOG.debug("ORM account lookup failed; will try sqlite direct lookup")

    # Si aún no resueltos, usar sqlite direct
    dbp = db_path or _find_db_path()
    if id_3103 is None or id_3104 is None:
        if dbp is None:
            return {"ok": False, "path": str(dest), "error": "No se encontró DB para verificar cuentas 3103/3104."}
        try:
            id_3103 = id_3103 or _account_exists_sqlite(dbp, "3103")
            id_3104 = id_3104 or _account_exists_sqlite(dbp, "3104")
        except Exception as e:
            return {"ok": False, "path": str(dest), "error": f"Error verificando cuentas: {e}"}

    missing = []
    if not id_3103:
        missing.append("3103")
    if not id_3104:
        missing.append("3104")
    if missing:
        # Backup ya creado; abortar traslado y devolver mensaje claro
        return {
            "ok": False,
            "path": str(dest),
            "error": f"Cuentas necesarias para cierre faltan en DB: {', '.join(missing)}. El sistema no creará cuentas automáticamente."
        }

    # Si resultado == 0 no transferir
    if resultado == Decimal(0):
        return {"ok": True, "path": str(dest), "note": "No hay saldo en 3103 para trasladar."}

    # Intentar insertar asiento: prefer ORM/SQLModel
    try:
        if JournalEntry is not None and JournalLine is not None and get_session is not None:
            with get_session() as s:
                je = JournalEntry(description=f"Cierre ejercicio: traslado {resultado}", created_at=datetime.utcnow())
                s.add(je)
                s.commit()
                s.refresh(je)
                if resultado > 0:
                    jl1 = JournalLine(entry_id=je.id, account_id=int(id_3103), debit=float(resultado), credit=0.0, description="Cierre débito 3103")
                    jl2 = JournalLine(entry_id=je.id, account_id=int(id_3104), debit=0.0, credit=float(resultado), description="Cierre crédito 3104")
                else:
                    amt = abs(resultado)
                    jl1 = JournalLine(entry_id=je.id, account_id=int(id_3104), debit=float(amt), credit=0.0, description="Cierre débito 3104")
                    jl2 = JournalLine(entry_id=je.id, account_id=int(id_3103), debit=0.0, credit=float(amt), description="Cierre crédito 3103")
                s.add(jl1); s.add(jl2)
                s.commit()
            return {"ok": True, "path": str(dest), "transferred": str(resultado)}
    except Exception as e:
        LOG.exception("ORM insert failed; falling back to sqlite direct insert: %s", e)

    # SQLite fallback insertion
    try:
        _insert_transfer_sqlite(dbp, resultado, int(id_3103), int(id_3104))
        return {"ok": True, "path": str(dest), "transferred": str(resultado)}
    except Exception as e:
        LOG.exception("Fallback sqlite insert failed: %s", e)
        return {"ok": False, "path": str(dest), "error": f"No se pudo insertar asiento: {e}"}