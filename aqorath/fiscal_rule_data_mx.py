"""Curated Mexican fiscal rule manifests backed by explicit official provenance.

This module contains reviewable source data only. It does not install rules,
open sessions, calculate tax, infer applicability, choose accounts, or post.
Each manifest is scoped to one exact FiscalContext and authored effective date.
"""

from datetime import date
from decimal import Decimal

from .fiscal_rule_set import FiscalRuleSetEntry, FiscalRuleSetManifest
from .fiscal_rules import FiscalContext


_MX_GENERAL_COMMERCIAL_CONTEXT = FiscalContext(
    jurisdiction="MX",
    regime="general",
    entity_type="comercial",
)

_MX_GENERAL_PERSONA_MORAL_CONTEXT = FiscalContext(
    jurisdiction="MX",
    regime="general",
    entity_type="persona_moral",
)

_MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_CONTEXT = FiscalContext(
    jurisdiction="MX",
    regime="general",
    entity_type="persona_fisica_profesional",
)

_MX_RESICO_PERSONA_FISICA_CONTEXT = FiscalContext(
    jurisdiction="MX",
    regime="resico",
    entity_type="persona_fisica",
)


MX_GENERAL_COMMERCIAL_IVA = FiscalRuleSetManifest(
    set_key="mx.general.comercial.iva-general",
    version="2010.1",
    context=_MX_GENERAL_COMMERCIAL_CONTEXT,
    entries=(
        FiscalRuleSetEntry(
            rule_key="iva.general_rate",
            effective_from=date(2010, 1, 1),
            value=Decimal("0.16"),
            unit="rate",
            source_ref="DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1",
        ),
    ),
)


MX_GENERAL_COMMERCIAL_IVA_ZERO = FiscalRuleSetManifest(
    set_key="mx.general.comercial.iva-zero",
    version="1981.1",
    context=_MX_GENERAL_COMMERCIAL_CONTEXT,
    entries=(
        FiscalRuleSetEntry(
            rule_key="iva.zero_rate",
            effective_from=date(1981, 1, 1),
            value=Decimal("0.00"),
            unit="rate",
            source_ref="DOF:1980-12-30:ART8+TRANSITORIO-PRIMERO;LIVA:ART2-A",
        ),
    ),
)


MX_GENERAL_COMMERCIAL_IVA_EXEMPT_LAND = FiscalRuleSetManifest(
    set_key="mx.general.comercial.iva-exempt-land",
    version="1980.1",
    context=_MX_GENERAL_COMMERCIAL_CONTEXT,
    entries=(
        FiscalRuleSetEntry(
            rule_key="iva.exempt.sale.land",
            effective_from=date(1980, 1, 1),
            value=Decimal("0"),
            unit="exempt",
            source_ref="DOF:1978-12-29;LIVA:ART9-I",
        ),
    ),
)


MX_GENERAL_PERSONA_MORAL_IVA_FREIGHT_RETENTION = FiscalRuleSetManifest(
    set_key="mx.general.persona-moral.iva-freight-retention",
    version="2006.1",
    context=_MX_GENERAL_PERSONA_MORAL_CONTEXT,
    entries=(
        FiscalRuleSetEntry(
            rule_key="iva.freight_transport_retention_rate",
            effective_from=date(2006, 12, 5),
            value=Decimal("0.04"),
            unit="rate",
            source_ref="DOF:2006-12-04;LIVA:ART1-A-II-c;RLIVA:ART3-II",
        ),
    ),
)


MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_ISR_RETENTION = FiscalRuleSetManifest(
    set_key="mx.general.persona-fisica-profesional.isr-retention",
    version="2014.1",
    context=_MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_CONTEXT,
    entries=(
        FiscalRuleSetEntry(
            rule_key="isr.professional_services_retention_rate",
            effective_from=date(2014, 1, 1),
            value=Decimal("0.10"),
            unit="rate",
            source_ref="DOF:2013-12-11;LISR:ART106",
        ),
    ),
)


MX_RESICO_PERSONA_FISICA_ISR_RETENTION = FiscalRuleSetManifest(
    set_key="mx.resico.persona-fisica.isr-retention",
    version="2022.1",
    context=_MX_RESICO_PERSONA_FISICA_CONTEXT,
    entries=(
        FiscalRuleSetEntry(
            rule_key="isr.resico_retention_rate",
            effective_from=date(2022, 1, 1),
            value=Decimal("0.0125"),
            unit="rate",
            source_ref="DOF:2021-11-12;LISR:ART113-J",
        ),
    ),
)


# Historical Phase 5E public aggregate is frozen and intentionally unchanged.
CURATED_FISCAL_RULE_SETS = (MX_GENERAL_COMMERCIAL_IVA,)

# Current expanded Mexican curated coverage. Applicability remains explicit;
# membership here does not make any rule automatic for an EconomicFact.
CURATED_MX_FISCAL_RULE_SETS = (
    MX_GENERAL_COMMERCIAL_IVA,
    MX_GENERAL_COMMERCIAL_IVA_ZERO,
    MX_GENERAL_COMMERCIAL_IVA_EXEMPT_LAND,
    MX_GENERAL_PERSONA_MORAL_IVA_FREIGHT_RETENTION,
    MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_ISR_RETENTION,
    MX_RESICO_PERSONA_FISICA_ISR_RETENTION,
)


__all__ = [
    "MX_GENERAL_COMMERCIAL_IVA",
    "MX_GENERAL_COMMERCIAL_IVA_ZERO",
    "MX_GENERAL_COMMERCIAL_IVA_EXEMPT_LAND",
    "MX_GENERAL_PERSONA_MORAL_IVA_FREIGHT_RETENTION",
    "MX_GENERAL_PERSONA_FISICA_PROFESSIONAL_ISR_RETENTION",
    "MX_RESICO_PERSONA_FISICA_ISR_RETENTION",
    "CURATED_FISCAL_RULE_SETS",
    "CURATED_MX_FISCAL_RULE_SETS",
]
