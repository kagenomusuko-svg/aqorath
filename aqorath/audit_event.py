"""Pure append-only general traceability event."""

from dataclasses import dataclass
from datetime import datetime
import math


def _require_positive_id(value, field_name):
    if type(value) is not int:
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_optional_positive_id(value, field_name):
    if value is None:
        return
    _require_positive_id(value, field_name)


def _require_text(value, field_name):
    if type(value) is not str:
        raise TypeError(f"{field_name} must be str")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be nonblank without surrounding whitespace")


def _validate_json_value(value):
    if value is None or type(value) in (str, int, bool):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("details float values must be finite")
        return
    if type(value) is list:
        for item in value:
            _validate_json_value(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            _require_text(key, "details key")
            _validate_json_value(item)
        return
    raise TypeError("details values must be explicit JSON-compatible values")


@dataclass(frozen=True)
class AuditEvent:
    """Immutable explicit traceability metadata owned by one Entity."""

    id: int | None
    entity_id: int
    event_type: str
    timestamp: datetime
    details: dict

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")
        _require_positive_id(self.entity_id, "entity_id")
        _require_text(self.event_type, "event_type")
        if type(self.timestamp) is not datetime:
            raise TypeError("timestamp must be datetime")
        if type(self.details) is not dict:
            raise TypeError("details must be dict")
        _validate_json_value(self.details)
