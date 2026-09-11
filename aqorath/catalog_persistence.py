"""Persistence composition for the governed canonical account catalog.

The embedded JSON remains the catalog authority. This module only ensures that its
canonical identities exist in SQLite so normal Application authorities can bind and
post against persistent Account rows. It never commits: the caller owns transaction
boundaries.
"""

from sqlmodel import select

from .catalog import load_catalog
from .models import Account


def ensure_canonical_accounts(session, economic_purpose: str) -> tuple[str, ...]:
    if economic_purpose not in {"lucrativo", "no_lucrativo"}:
        raise ValueError("economic_purpose must be 'lucrativo' or 'no_lucrativo'")

    document = load_catalog()
    accounts = document.get("accounts") if isinstance(document, dict) else None
    if not isinstance(accounts, dict) or not accounts:
        raise RuntimeError("governed account catalog contains no accounts")

    existing = {
        str(item.code): item
        for item in session.exec(select(Account).order_by(Account.code)).all()
    }
    inserted = []
    preferred_name = "name_osc" if economic_purpose == "no_lucrativo" else "name_comercial"
    alternate_name = "name_comercial" if preferred_name == "name_osc" else "name_osc"

    for raw_code in sorted(accounts, key=str):
        code = str(raw_code).strip()
        metadata = accounts[raw_code]
        if not code or not isinstance(metadata, dict):
            raise RuntimeError("governed account catalog contains invalid metadata")
        if code in existing:
            if existing[code].origin != "canonical":
                raise RuntimeError(
                    f"governed canonical code {code} is occupied by a non-canonical account"
                )
            continue

        name = metadata.get(preferred_name) or metadata.get(alternate_name)
        nature = metadata.get("naturaleza")
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError(f"catalog account {code} has no usable name")
        if not isinstance(nature, str) or not nature.strip():
            raise RuntimeError(f"catalog account {code} has no usable nature")

        session.add(
            Account(
                code=code,
                name=name.strip(),
                nature=nature.strip(),
                origin="canonical",
                parent_id=None,
            )
        )
        inserted.append(code)

    session.flush()
    return tuple(inserted)


__all__ = ["ensure_canonical_accounts"]
