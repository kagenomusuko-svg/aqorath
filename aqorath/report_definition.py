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


def _require_optional_text(value, field_name):
    if value is None:
        return
    _require_text(value, field_name)


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
    """Describe what report document exists without generating it.

    AQR-013 extends the frozen foundation with optional product-governance metadata.
    Legacy/foundation values may omit the new fields, while definitions exposed by the
    product catalog must provide them and are validated by the catalog/application
    authorities. No balances or generated results live here.
    """

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
    key: str | None = None
    report_type: str | None = None
    allowed_parameters: tuple[str, ...] = ()
    allowed_dimensions: tuple[str, ...] = ()
    period_mode: str | None = None
    version: str | None = None

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
        _require_optional_text(self.key, "key")
        _require_optional_text(self.report_type, "report_type")
        _require_token_tuple(self.allowed_parameters, "allowed_parameters")
        _require_token_tuple(self.allowed_dimensions, "allowed_dimensions")
        _require_optional_text(self.period_mode, "period_mode")
        _require_optional_text(self.version, "version")

        overlap = set(self.requires_capabilities).intersection(
            self.forbidden_capabilities
        )
        if overlap:
            raise ValueError(
                "a capability cannot be both required and forbidden"
            )
