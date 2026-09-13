"""Atomic installation boundary for reviewed fiscal rule-set manifests."""

from . import fiscal_rule_registry as _registry
from . import fiscal_rule_set as _rule_set


def install_fiscal_rule_set(session, manifest):
    """Materialize one manifest and install all registrations atomically."""
    registrations = _rule_set.materialize_fiscal_rule_set(manifest)
    return _registry.register_fiscal_rule_versions(session, registrations)


def _matches_curated_registration(resolved, registration):
    return (
        resolved.rule_key == registration.rule_key
        and resolved.jurisdiction == registration.context.jurisdiction
        and resolved.regime == registration.context.regime
        and resolved.entity_type == registration.context.entity_type
        and resolved.effective_from == registration.effective_from
        and resolved.value == registration.value
        and resolved.unit == registration.unit
        and resolved.source_ref == registration.source_ref
    )


def ensure_curated_fiscal_rules(session, manifests):
    """Ensure reviewed reference-data manifests exist exactly once.

    This is product composition over the existing fiscal registry, not another
    fiscal authority. Exact persisted versions are reused; a same-date mismatch
    or a missing historical version behind newer persisted history fails closed.
    Missing appendable versions are staged through the registry's existing
    validator and all changes are committed atomically.

    Installing reference data does not select applicability for an economic
    fact. AQR-011 coverage remains the sole authority for that decision.
    """
    if not isinstance(manifests, tuple):
        raise TypeError("manifests must be a tuple")
    if not manifests:
        raise ValueError("manifests must not be empty")

    registrations = []
    for manifest in manifests:
        registrations.extend(_rule_set.materialize_fiscal_rule_set(manifest))

    ensured = []
    try:
        for registration in registrations:
            history = _registry.get_fiscal_rule_history(
                session,
                registration.rule_key,
                registration.context,
            )
            exact = next(
                (
                    item
                    for item in history
                    if item.effective_from == registration.effective_from
                ),
                None,
            )
            if exact is not None:
                if not _matches_curated_registration(exact, registration):
                    raise ValueError(
                        "Curated fiscal rule conflicts with persisted history: "
                        f"{registration.rule_key} "
                        f"{registration.context.jurisdiction}/"
                        f"{registration.context.regime}/"
                        f"{registration.context.entity_type} "
                        f"from {registration.effective_from.isoformat()}"
                    )
                ensured.append(exact)
                continue

            if history and registration.effective_from < history[-1].effective_from:
                raise ValueError(
                    "Curated fiscal rule is missing behind newer persisted history: "
                    f"{registration.rule_key} "
                    f"{registration.context.jurisdiction}/"
                    f"{registration.context.regime}/"
                    f"{registration.context.entity_type} "
                    f"from {registration.effective_from.isoformat()}"
                )

            _registry._stage_validated_fiscal_rule_version(session, registration)
            session.flush()
            refreshed = _registry.get_fiscal_rule_history(
                session,
                registration.rule_key,
                registration.context,
            )
            exact = next(
                item
                for item in refreshed
                if item.effective_from == registration.effective_from
            )
            ensured.append(exact)

        session.commit()
    except Exception:
        session.rollback()
        raise

    return tuple(ensured)


__all__ = ["install_fiscal_rule_set", "ensure_curated_fiscal_rules"]
