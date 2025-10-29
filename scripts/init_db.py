import datetime
from aqorath.storage import init_db, get_session, DB_PATH
from aqorath.models import Account, Period
from pathlib import Path

def seed_accounts_comercial(session):
    # códigos de ejemplo; ajusta según tu catálogo
    seed = [
        ("1000", "Bancos", "DEBIT"),
        ("4000", "Ventas", "CREDIT"),
        ("2100", "IVA trasladado", "CREDIT"),
        ("2200", "IVA acreditable", "DEBIT"),
        ("5000", "Gastos", "DEBIT"),
        ("1700", "Depreciación acumulada", "CREDIT"),
        ("6000", "Depreciación gasto", "DEBIT"),
        ("2300", "ISR retenido", "CREDIT"),
    ]
    for code, name, nature in seed:
        a = Account(code=code, name=name, nature=nature)
        session.add(a)
    session.commit()

def init():
    print("Inicializando DB en:", DB_PATH)
    init_db()
    with get_session() as s:
        # seed one open period (current year)
        today = datetime.date.today()
        year = today.year
        start = datetime.date(year, 1, 1)
        end = datetime.date(year, 12, 31)
        p = s.exec(select(Period)).first() if False else None  # dummy to avoid import collision
        # create period if none exists
        from sqlmodel import select
        has = s.exec(select(Period)).first()
        if not has:
            period = Period(year=year, start_date=start, end_date=end, type="COMERCIAL", is_open=True)
            s.add(period)
            s.commit()
        # seed accounts if not present
        q = s.exec(select(Account)).first()
        if not q:
            seed_accounts_comercial(s)
    print("DB inicializada y datos semilla creados.")

if __name__ == "__main__":
    # Import here to avoid circulars at module import time
    from sqlmodel import select
    init()