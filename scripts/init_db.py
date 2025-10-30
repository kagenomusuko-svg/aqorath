import datetime
from aqorath.storage import init_db, get_session, DB_PATH
from aqorath.models import Account, Period, AppConfig
from pathlib import Path
from sqlmodel import select

def seed_accounts_comercial(session):
    # códigos de ejemplo; ajusta según tu catálogo
    seed = [
        ("1000", "Bancos", "DEBIT"),
        ("1100", "Clientes / Cuentas por cobrar", "DEBIT"),
        ("2000", "Proveedores / Cuentas por pagar", "CREDIT"),
        ("4000", "Ventas", "CREDIT"),
        ("2100", "IVA trasladado", "CREDIT"),
        ("2200", "IVA acreditable", "DEBIT"),
        ("5000", "Gastos", "DEBIT"),
        ("1700", "Depreciación acumulada", "CREDIT"),
        ("6000", "Depreciación gasto", "DEBIT"),
        ("2300", "ISR retenido", "CREDIT"),
        ("2310", "IMSS obrero (retenido)", "CREDIT"),
        ("2320", "IMSS patronal (por pagar)", "CREDIT"),
        ("2400", "IVA retenido (por pagar)", "CREDIT"),
        ("7000", "Gasto sueldos", "DEBIT"),
        ("7010", "Gasto cargas patronales", "DEBIT"),
    ]
    for code, name, nature in seed:
        a = Account(code=code, name=name, nature=nature)
        session.add(a)
    session.commit()

def seed_appconfig(session):
    # default mapping logical_name -> account_code
    defaults = {
        "bank": "1000",
        "receivable": "1100",
        "payable": "2000",
        "sales": "4000",
        "vat_tr": "2100",
        "vat_ac": "2200",
        "expense": "5000",
        "isr_ret": "2300",
        "imss_obrero_payable": "2310",
        "imss_patronal_payable": "2320",
        "vat_ret": "2400",
        "salary_expense": "7000",
        "employer_social_expense": "7010"
    }
    for logical, code in defaults.items():
        key = f"default_account.{logical}"
        existing = session.exec(select(AppConfig).where(AppConfig.key == key)).first()
        if not existing:
            session.add(AppConfig(key=key, value=code))
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
        has = s.exec(select(Period)).first()
        if not has:
            period = Period(year=year, start_date=start, end_date=end, type="COMERCIAL", is_open=True)
            s.add(period)
            s.commit()
        # seed accounts if not present
        q = s.exec(select(Account)).first()
        if not q:
            seed_accounts_comercial(s)
        # seed appconfig defaults
        seed_appconfig(s)
    print("DB inicializada y datos semilla creados.")

if __name__ == "__main__":
    from sqlmodel import select
    init()