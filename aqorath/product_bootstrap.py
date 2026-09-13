"""Product bootstrap for an installed local Aqorath distribution.

This module is deliberately small: it owns no schema DDL, migration logic or
fiscal applicability. It prepares the writable local directory, delegates
creation/upgrades to the canonical storage/migration authorities, then ensures
reviewed fiscal reference data through the existing fiscal registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .migrations import CURRENT_SCHEMA_VERSION, get_schema_version
from . import storage
from .fiscal_rule_data_mx import CURATED_MX_FISCAL_RULE_SETS
from .fiscal_rule_install import ensure_curated_fiscal_rules


@dataclass(frozen=True)
class ProductBootstrapResult:
    db_path: str
    schema_version: int


def bootstrap_local_product(db_path: str | Path | None = None) -> ProductBootstrapResult:
    """Prepare the installed product DB and return its canonical schema state.

    Parent-directory creation is a product/bootstrap responsibility. Schema
    creation, migration, backup-before-migration and future-schema rejection
    remain exclusively in ``migrations.py`` through ``storage.init_db``.

    Once the current schema exists, reviewed Mexican fiscal manifests are
    ensured as reference data. Their presence never selects a treatment;
    AQR-011 factual coverage remains fail-closed and authoritative.
    """

    resolved = Path(db_path or storage.get_db_path()).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    engine = storage.init_db(str(resolved))
    # Ensure initial creation/migration completed while the canonical engine is alive.
    if engine is None:
        raise RuntimeError("Aqorath storage initialization did not return an engine")

    schema_version = get_schema_version(str(resolved))
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Aqorath bootstrap expected schema {CURRENT_SCHEMA_VERSION}, got {schema_version}"
        )

    with storage.get_session() as session:
        ensure_curated_fiscal_rules(session, CURATED_MX_FISCAL_RULE_SETS)

    return ProductBootstrapResult(
        db_path=str(resolved),
        schema_version=schema_version,
    )


__all__ = ["ProductBootstrapResult", "bootstrap_local_product"]
