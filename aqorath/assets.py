from datetime import date, datetime
from .models import Asset
from .storage import get_session
from sqlmodel import select
from typing import List
import calendar

def monthly_depreciation_straight(acquisition_cost: float, salvage_value: float, life_years: int):
    if life_years <= 0:
        raise ValueError("life_years debe ser mayor que 0")
    depreciable = max(0.0, acquisition_cost - salvage_value)
    annual = depreciable / float(life_years)
    monthly = annual / 12.0
    return round(monthly, 2)

def generate_monthly_depreciation_entries(target_year: int, target_month: int, posted_by: str = None) -> List[int]:
    created_ids = []
    with get_session() as s:
        assets = s.exec(select(Asset)).all()
        for asset in assets:
            if not asset.active:
                continue
            end_of_month = date(target_year, target_month, calendar.monthrange(target_year, target_month)[1])
            if asset.acquisition_date > end_of_month:
                continue
            monthly = monthly_depreciation_straight(asset.acquisition_cost, asset.salvage_value, asset.life_years)
            if monthly <= 0:
                continue
            # Crear entry y líneas; NOTA: asumimos que existen cuentas seed '6000' y '1700'
            from .models import JournalEntry, JournalLine
            from .models import Account  # usado sólo para comprobación abajo (si quieres más seguridad)
            from sqlmodel import select as _select
            entry = JournalEntry(date=end_of_month, concept=f"Depreciación {asset.code} {end_of_month.isoformat()}",
                                 posted_by=posted_by, state="posted")
            s.add(entry)
            s.commit()
            s.refresh(entry)
            q1 = s.exec(_select(Account).where(Account.code == "6000"))
            acc_exp = q1.one_or_none()
            q2 = s.exec(_select(Account).where(Account.code == "1700"))
            acc_accum = q2.one_or_none()
            expense_acc_id = acc_exp.id if acc_exp else None
            accum_acc_id = acc_accum.id if acc_accum else None
            from .models import JournalLine as JL
            jl_d = JL(entry_id=entry.id, account_id=expense_acc_id, debit=monthly, credit=0.0,
                       description=f"Depreciación mensual {asset.code}")
            jl_c = JL(entry_id=entry.id, account_id=accum_acc_id, debit=0.0, credit=monthly,
                       description=f"Depreciación acumulada {asset.code}")
            s.add(jl_d)
            s.add(jl_c)
            s.commit()
            created_ids.append(entry.id)
    return created_ids