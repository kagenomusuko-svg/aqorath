"""Pure capability applicability for one report definition and entity profile."""

from .entity import EntityProfile
from .report_definition import ReportDefinition


def is_report_definition_capability_applicable(definition, entity_profile):
    """Return whether explicit special capabilities satisfy the definition."""
    if not isinstance(definition, ReportDefinition):
        raise TypeError("definition must be ReportDefinition")
    if not isinstance(entity_profile, EntityProfile):
        raise TypeError("entity_profile must be EntityProfile")

    present = set(entity_profile.special_capabilities)
    if not set(definition.requires_capabilities).issubset(present):
        return False
    if set(definition.forbidden_capabilities).intersection(present):
        return False
    return True
