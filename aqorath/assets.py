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

def annual_depreciation_straight(acquisition_cost: float, salvage_value: float, life_years: int):
    if life_years <= 0:
        raise ValueError("life_years debe ser mayor que 0")
    depreciable = max(0.0, acquisition_cost - salvage_value)
    annual = depreciable / float(life_years)
    return round(annual, 2)

def generate_depreciation_entries_for_period(target_year: int, target_month: int = None, posted_by: str = None) -> List[int]:
    """
    Si target_month es None -> genera entries anuales (por year).
    Si target_month es int 1..12 -> genera entries mensuales del mes indicado.
    Retorna lista de JournalEntry ids creados.
    """
    created_ids = []
    from .models import JournalEntry, JournalLine, Account
    from sqlmodel import select as _select
    with get_session() as s:
        assets = s.exec(select(Asset)).all()
        for asset in assets:
            if not asset.active:
                continue
            # decide si generar para este asset según periodicidad
            if asset.depreciation_period == "monthly" and target_month is None:
                continue
            # compute date of posting
            if target_month:
                end_of_month = date(target_year, target_month, calendar.monthrange(target_year, target_month)[1])
                if asset.acquisition_date > end_of_month:
                    continue
                amount = monthly_depreciation_straight(asset.acquisition_cost, asset.salvage_value, asset.life_years)
                post_date = end_of_month
            else:
                # annual
                end_of_year = date(target_year, 12, 31)
                if asset.acquisition_date > end_of_year:
                    continue
                amount = annual_depreciation_straight(asset.acquisition_cost, asset.salvage_value, asset.life_years)
                post_date = end_of_year
            if amount <= 0:
                continue
            # lookup accounts - expects seed '6000' and '1700' or config
            q1 = s.exec(_select(Account).where(Account.code == "6000"))
            acc_exp = q1.one_or_none()
            q2 = s.exec(_select(Account).where(Account.code == "1700"))
            acc_accum = q2.one_or_none()
            expense_acc_id = acc_exp.id if acc_exp else None
            accum_acc_id = acc_accum.id if acc_accum else None
            entry = JournalEntry(date=post_date, concept=f"Depreciación {asset.code} {post_date.isoformat()}",
                                 posted_by=posted_by, state="posted")
            s.add(entry)
            s.commit()
            s.refresh(entry)
            from .models import JournalLine as JL
            jl_d = JL(entry_id=entry.id, account_id=expense_acc_id, debit=amount, credit=0.0,
                       description=f"Depreciación {asset.code}")
            jl_c = JL(entry_id=entry.id, account_id=accum_acc_id, debit=0.0, credit=amount,
                       description=f"Depreciación acumulada {asset.code}")
            s.add(jl_d)
            s.add(jl_c)
            s.commit()
            created_ids.append(entry.id)
    return created_ids