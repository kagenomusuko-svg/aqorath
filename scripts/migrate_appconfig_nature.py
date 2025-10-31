# scripts/migrate_appconfig_nature.py
from aqorath.storage import get_session
from aqorath.models import AppConfig
from sqlmodel import select

def map_value(v: str) -> str:
    if not v:
        return v
    lower = v.strip().lower()
    if 'debit' in lower or lower in ('debit','debito','debit0'):
        return 'Deudora'
    if 'credit' in lower or lower in ('credit','credito'):
        return 'Acreedora'
    if 'deud' in lower or 'debe' in lower:
        return 'Deudora'
    if 'acre' in lower:
        return 'Acreedora'
    # fallback: capitalize
    return v.strip().capitalize()

def run():
    with get_session() as s:
        rows = s.exec(select(AppConfig).where(AppConfig.key.like('account.% .naturaleza'))).all()
        # Alternative: some keys may be 'account.<code>.naturaleza' without space; check both:
        rows = s.exec(select(AppConfig).where(AppConfig.key.like('account.%naturaleza'))).all()
        updated = 0
        for r in rows:
            new = map_value(r.value)
            if new != r.value:
                r.value = new
                s.add(r)
                updated += 1
        s.commit()
    print(f"AppConfig updated: {updated}")

if __name__ == '__main__':
    run()