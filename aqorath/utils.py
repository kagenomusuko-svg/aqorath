from typing import Optional

def nature_to_side(nature: Optional[str]) -> str:
    if not nature:
        return "debit"
    v = str(nature).strip().lower()
    if any(x in v for x in ("deud", "debe", "debit", "debito")):
        return "debit"
    if any(x in v for x in ("acre", "acreedor", "credit", "credito")):
        return "credit"
    return "debit"

def side_to_nature(side: Optional[str]) -> str:
    if not side:
        return "Deudora"
    s = str(side).strip().lower()
    if s == "debit":
        return "Deudora"
    if s == "credit":
        return "Acreedora"
    return "Deudora"
