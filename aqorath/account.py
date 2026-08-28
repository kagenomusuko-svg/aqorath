"""Pure immutable accounting account domain value."""

from dataclasses import dataclass


_ACCOUNT_TYPES = frozenset({
    "asset",
    "liability",
    "equity",
    "income",
    "expense",
})
_NATURES = frozenset({"debit", "credit"})


def _require_optional_positive_id(value, field_name):
    if value is None:
        return
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int or None")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_text(value, field_name):
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str")
    if not value or value.strip() != value:
        raise ValueError(
            f"{field_name} must be nonblank without surrounding whitespace"
        )


def _require_optional_text(value, field_name):
    if value is None:
        return
    _require_text(value, field_name)


@dataclass(frozen=True)
class Account:
    """Describe one explicit governed accounting account."""

    id: int | None
    code: str
    name: str
    account_type: str
    subtype: str
    nature: str
    is_canonical: bool = True
    name_osc: str | None = None
    name_comercial: str | None = None

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")
        _require_text(self.code, "code")
        _require_text(self.name, "name")
        _require_text(self.account_type, "account_type")
        _require_text(self.subtype, "subtype")
        _require_text(self.nature, "nature")
        _require_optional_text(self.name_osc, "name_osc")
        _require_optional_text(self.name_comercial, "name_comercial")

        if self.account_type not in _ACCOUNT_TYPES:
            raise ValueError("account_type must be a canonical structure token")
        if self.nature not in _NATURES:
            raise ValueError("nature must be debit or credit")
        if type(self.is_canonical) is not bool:
            raise TypeError("is_canonical must be bool")
