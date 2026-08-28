"""Pure immutable definition of one report document capability."""

from dataclasses import dataclass


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


def _require_token_tuple(value, field_name, *, allow_empty=True):
    if type(value) is not tuple:
        raise TypeError(f"{field_name} must be tuple")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must not be empty")

    seen = set()
    for item in value:
        _require_text(item, f"{field_name} item")
        if item in seen:
            raise ValueError(f"{field_name} must not contain duplicates")
        seen.add(item)


@dataclass(frozen=True)
class ReportDefinition:
    """Describe what report document exists without generating it."""

    id: int | None
    name: str
    description: str
    required_data: tuple[str, ...]
    supported_formats: tuple[str, ...]
    requires_capabilities: tuple[str, ...]
    forbidden_capabilities: tuple[str, ...]
    required_fiscal_features: tuple[str, ...]
    renderer_id: str
    query_template_id: str

    def __post_init__(self):
        _require_optional_positive_id(self.id, "id")
        _require_text(self.name, "name")
        _require_text(self.description, "description")
        _require_text(self.renderer_id, "renderer_id")
        _require_text(self.query_template_id, "query_template_id")

        _require_token_tuple(self.required_data, "required_data")
        _require_token_tuple(
            self.supported_formats,
            "supported_formats",
            allow_empty=False,
        )
        _require_token_tuple(self.requires_capabilities, "requires_capabilities")
        _require_token_tuple(self.forbidden_capabilities, "forbidden_capabilities")
        _require_token_tuple(
            self.required_fiscal_features,
            "required_fiscal_features",
        )

        overlap = set(self.requires_capabilities).intersection(
            self.forbidden_capabilities
        )
        if overlap:
            raise ValueError(
                "a capability cannot be both required and forbidden"
            )
