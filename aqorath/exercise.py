from __future__ import annotations
"""Canonical, atomic year-end closing over the existing ledger authorities."""
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from aqorath.accounting_rules import compute_resultado_ejercicio, load_catalog, resolve_catalog_entry_for_account_code
from aqorath.storage import get_db_path, get_session

OUT_ROOT_DEFAULT = Path.home() / ".local" / "share" / "aqorath" / "ejercicios"


def close_exercise(
    carry_over: bool = True,
    out_root: Optional[Path] = None,
    *,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """Close an explicit fiscal year atomically through canonical staging.

    December must remain open until annual closing. Closed months never receive
    new postings, including closing adjustments. No implicit reopening occurs.
    """
    from datetime import date, timedelta
    from sqlalchemy import text
    from .accounting_period_repository import load_fiscal_year, load_periods, require_open_period
    from .accounting_period import PeriodError
    from .account_balance import _exact_decimal_sum
    from .core import _stage_entry_in_session, _balances_from_sqlite
    from .migrations import create_database_backup

    root = out_root or OUT_ROOT_DEFAULT
    db_path = Path(get_db_path())
    try:
        backup = create_database_backup(str(db_path), backup_dir=str(root))
    except Exception as exc:
        return {"ok": False, "error": f"Error creando backup: {exc}"}
    backup_path = backup["backup_path"]
    if not carry_over:
        return {"ok": True, "path": backup_path, "note": "Backup creado, sin cierre contable."}
    if type(year) is not int:
        return {"ok": False, "path": backup_path, "error": "Seleccione explícitamente el ejercicio a cerrar."}
    try:
        with get_session() as session:
            # Acquire SQLite's writer reservation before reading closing balances.
            session.execute(text('UPDATE fiscalyear SET state=state WHERE year=:year'), {'year': year})
            fy = load_fiscal_year(session, year)
            stored = session.execute(text('SELECT closing_entry_id FROM fiscalyear WHERE year=:y'), {'y': year}).scalar()
            if fy.state == 'closed':
                return {"ok": True, "path": backup_path, "entry_id": stored, "already_closed": True}
            periods = load_periods(session, fy)
            if len(periods) != len(fy.periods()):
                raise PeriodError('Fiscal year has missing periods')
            require_open_period(session, fy.end)
            after = _balances_from_sqlite(db_path, fy.end.isoformat())
            before = {} if fy.start == date.min else _balances_from_sqlite(db_path, (fy.start - timedelta(days=1)).isoformat())
            movement = {code: _exact_decimal_sum([after.get(code, Decimal(0)), before.get(code, Decimal(0)).copy_negate()]) for code in after.keys() | before.keys()}
            from .catalog import get_catalog_path
            catalog = load_catalog(get_catalog_path())
            if not catalog:
                raise PeriodError("Canonical catalog is unavailable")
            resultado, _ = compute_resultado_ejercicio(movement, catalog)
            lines = []
            for code, balance in movement.items():
                if (resolve_catalog_entry_for_account_code(code, catalog) or {}).get('tipo') not in ('Ingreso', 'Gasto', 'Costo') or not balance:
                    continue
                lines.append({'account_code': code, 'debit': str(balance.copy_negate() if balance < 0 else Decimal(0)),
                              'credit': str(balance if balance > 0 else Decimal(0))})
            net = _exact_decimal_sum([value for line in lines for value in (Decimal(line['debit']), Decimal(line['credit']).copy_negate())])
            if net != resultado:
                raise PeriodError('Closing result contradicts canonical financial result')
            if net:
                lines.append({'account_code': '3104', 'debit': str(net.copy_negate() if net < 0 else Decimal(0)),
                              'credit': str(net if net > 0 else Decimal(0))})
            entry_id = None
            if lines:
                entry, error = _stage_entry_in_session(session, {
                    'date': fy.end, 'description': f'Cierre del ejercicio {year}',
                    'state': 'posted', 'lines': lines,
                })
                if error:
                    raise PeriodError(error)
                session.flush()
                entry_id = entry.id
                session.info["_aqorath_annual_closing"] = entry_id
            session.execute(text("UPDATE fiscalyear SET state='closed',closing_entry_id=:id WHERE year=:y"), {'id': entry_id, 'y': year})
            session.execute(text("UPDATE accountingperiod SET state='closed' WHERE year=:y"), {'y': year})
            session.commit()
            return {'ok': True, 'path': backup_path, 'entry_id': entry_id, 'transferred': str(resultado)}
    except Exception as exc:
        return {'ok': False, 'path': backup_path, 'error': str(exc)}
