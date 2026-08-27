"""Curated Mexican fiscal rule manifests backed by explicit official provenance.

Current scope is intentionally narrow. This module contains source data only;
it does not install rules, open sessions, calculate tax, or infer applicability
outside the exact FiscalContext declared by each manifest.
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


CURATED_FISCAL_RULE_SETS = (MX_GENERAL_COMMERCIAL_IVA,)


__all__ = [
    "MX_GENERAL_COMMERCIAL_IVA",
    "CURATED_FISCAL_RULE_SETS",
]
