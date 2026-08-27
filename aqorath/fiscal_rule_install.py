"""Atomic installation boundary for reviewed fiscal rule-set manifests."""

from . import fiscal_rule_registry as _registry
from . import fiscal_rule_set as _rule_set


def install_fiscal_rule_set(session, manifest):
    """Materialize one manifest and install all registrations atomically."""
    registrations = _rule_set.materialize_fiscal_rule_set(manifest)
    return _registry.register_fiscal_rule_versions(session, registrations)


__all__ = ["install_fiscal_rule_set"]
