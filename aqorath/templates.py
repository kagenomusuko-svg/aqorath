"""Retired legacy operation-template compatibility tombstone.

Aqorath V1 no longer exposes an OperationTemplate accounting authority.  The
canonical paths are EconomicFact/AQR-004, AQR-006 subledgers, AQR-011 fiscal
composition, and the explicit vertical authorities covered by PRODUCT_ACCEPTANCE_V1.

This module remains importable temporarily so architecture tests that assert
modern fiscal code does *not* depend on the legacy module can still monkeypatch
``get_template``.  It contains no registry, calculations, account selection, or
posting semantics.
"""

_RETIRED = (
    "Legacy OperationTemplate authority is retired; use Aqorath's canonical "
    "fact/application authorities."
)


def get_template(*args, **kwargs):
    raise RuntimeError(_RETIRED)


def register_template(*args, **kwargs):
    raise RuntimeError(_RETIRED)


def list_templates():
    """Return no executable legacy templates.

    Returning an empty immutable result intentionally prevents ``core`` from
    falling back to filesystem templates while keeping import-only compatibility.
    """
    return ()


__all__ = ["get_template", "register_template", "list_templates"]
