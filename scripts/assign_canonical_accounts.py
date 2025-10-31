#!/usr/bin/env python3
"""
Asigna account.<code>.canonical_id.comercial y account.<code>.canonical_id.osc en AppConfig.
No borra nada; solo escribe metadatos para que el sistema sepa cuál fila usar por modo.
"""
from pathlib import Path
from aqorath.catalog import load_catalog
from aqorath.storage import get_session
from aqorath.models import AppConfig, Account
from sqlmodel import select

def main(catalog_path: Path = None):
    catalog = load_catalog(catalog_path)
    with get_session() as s:
        written = 0
        for code, meta in catalog.items():
            rows = s.exec(select(Account).where(Account.code == code)).all()
            if not rows:
                continue
            # elegir por comercial y por osc por separado
            chosen_com = None
            chosen_osc = None
            name_com = meta.get("name_comercial", "").strip().lower()
            name_osc = meta.get("name_osc", "").strip().lower()
            for r in rows:
                if name_com and r.name and r.name.strip().lower() == name_com:
                    chosen_com = r
                    break
            for r in rows:
                if name_osc and r.name and r.name.strip().lower() == name_osc:
                    chosen_osc = r
                    break
            if not chosen_com:
                chosen_com = rows[0]
            if not chosen_osc:
                chosen_osc = rows[0]
            # escribir AppConfig keys específicas
            key_com = f"account.{code}.canonical_id.comercial"
            key_osc = f"account.{code}.canonical_id.osc"
            existing_com = s.exec(select(AppConfig).where(AppConfig.key == key_com)).one_or_none()
            existing_osc = s.exec(select(AppConfig).where(AppConfig.key == key_osc)).one_or_none()
            if existing_com:
                existing_com.value = str(chosen_com.id)
                s.add(existing_com)
            else:
                s.add(AppConfig(key=key_com, value=str(chosen_com.id)))
            if existing_osc:
                existing_osc.value = str(chosen_osc.id)
                s.add(existing_osc)
            else:
                s.add(AppConfig(key=key_osc, value=str(chosen_osc.id)))
            written += 1
        s.commit()
    print("Canonical (per-mode) mappings written:", written)

if __name__ == "__main__":
    main()