from .storage import get_session
from .models import Account, AppConfig
from sqlmodel import select

def get_account_display_name(code: str, project_type: str = "comercial") -> str:
    # project_type: "comercial" or "osc"
    with get_session() as s:
        acc = s.exec(select(Account).where(Account.code == code)).one_or_none()
        if not acc:
            return code
    # Buscar metadatos en AppConfig
    meta_key = f"account.{code}.name_comercial" if project_type == "comercial" else f"account.{code}.name_osc"
    with get_session() as s:
        cfg = s.exec(select(AppConfig).where(AppConfig.key == meta_key)).one_or_none()
    if cfg and cfg.value:
        return cfg.value
    return acc.name if acc else code