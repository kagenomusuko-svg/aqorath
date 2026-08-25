"""
P1-3 REGRESSION TESTS: Governed catalog extensibility.

Model:
  CANONICAL account (from JSON): 1101 Bancos, Deudora
  ENTITY accounts under it:
    - 1101.001 BBVA
    - 1101.002 Banamex
    - 1101.003 Nu
  
  Each entity account:
  - Has real id in Account table
  - Can receive JournalLine
  - Inherits nature from parent
  - Knows its parent_id explicitly
  - Has code like "1101.001" (generated, not user-defined)
  - Does NOT alter catalogo_base.json
  
Schema requirements:
  - origin: "canonical" | "entity"
  - parent_id: None (canonical) | Account.id (entity)

Function contract (not implemented):
  create_entity_account(session, parent_code, name) -> Account
"""

import pytest
from decimal import Decimal
from pathlib import Path
from sqlalchemy import create_engine
from sqlmodel import SQLModel, Session, select
import aqorath.core as core
import aqorath.catalog as catalog
from aqorath.models import Account
from aqorath.money import to_decimal_exact


def require_create_entity_account():
    """
    Get create_entity_account function or fail gracefully.
    Allows tests to reference a future function without ImportError at collection.
    """
    fn = getattr(catalog, "create_entity_account", None)
    if not callable(fn):
        pytest.fail(
            "create_entity_account() not implemented in aqorath.catalog; "
            "P1-3 requires: create_entity_account(session, parent_code, name) -> Account"
        )
    return fn


@pytest.fixture
def isolated_catalog_engine(tmp_path, monkeypatch):
    """
    Isolated SQLite engine for catalog tests.
    Seeds canonical accounts from JSON.
    """
    db_file = tmp_path / "catalog_extensibility_test.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, echo=False)
    SQLModel.metadata.create_all(engine)

    # Seed canonical accounts (1101, 4101) from JSON catalog
    canonical_codes = ["1101", "4101"]
    
    with Session(engine) as session:
        columns = set(Account.__table__.columns.keys())
        
        for code in canonical_codes:
            # Get canonical metadata from JSON
            canonical_meta = catalog.resolve_account_by_code(code)
            if canonical_meta is None:
                continue
            
            # Map JSON keys to Account fields
            account_kwargs = {
                "code": code,
                "name": canonical_meta.get("name_osc") or canonical_meta.get("name_comercial"),
                "nature": canonical_meta.get("naturaleza", ""),
            }
            
            # Add origin/parent_id if schema supports them (future-proof)
            if "origin" in columns:
                account_kwargs["origin"] = "canonical"
            if "parent_id" in columns:
                account_kwargs["parent_id"] = None
            
            # Verify values are not None
            if not account_kwargs["code"]:
                raise RuntimeError(f"Cannot seed account without code: {canonical_meta}")
            if not account_kwargs["name"]:
                raise RuntimeError(f"Cannot seed account without name: {canonical_meta}")
            
            acc = Account(**account_kwargs)
            session.add(acc)
        
        session.commit()

    monkeypatch.setenv("AQORATH_DB", str(db_file))
    
    return engine


# ============================================================
# Schema tests
# ============================================================

def test_account_schema_supports_governed_extensions(isolated_catalog_engine):
    """
    P1-3: Account schema must support origin and parent_id.
    
    CONTRATO FUTURO:
    - origin: "canonical" | "entity"
    - parent_id: None | Account.id
    
    ESTADO ACTUAL: FAIL esperado (campos no existen aún)
    """
    columns = set(Account.__table__.columns.keys())
    
    # Future schema requirements
    assert "origin" in columns, (
        "Account schema must have 'origin' column (canonical|entity)"
    )
    assert "parent_id" in columns, (
        "Account schema must have 'parent_id' column for entity accounts"
    )


# ============================================================
# Entity creation tests
# ============================================================

def test_entity_can_create_bank_account_under_canonical_1101(isolated_catalog_engine):
    """
    P1-3: Can create an entity account (BBVA) under canonical 1101.
    
    CONTRATO FUTURO:
    - account.name == "BBVA"
    - account.origin == "entity"
    - account.parent_id == parent_1101.id
    - account.nature == parent_1101.nature (inherited)
    - account.code starts with "1101."
    
    ESTADO ACTUAL: FAIL (create_entity_account not implemented)
    """
    create_entity_account = require_create_entity_account()
    
    with core.get_session() as session:
        # Create BBVA under 1101
        bbva = create_entity_account(
            session=session,
            parent_code="1101",
            name="BBVA"
        )
        
        # Verify creation
        assert bbva.id is not None, "BBVA account must have id"
        assert bbva.name == "BBVA"
        
        # Get parent for comparison
        parent_1101 = session.exec(
            select(Account).where(Account.code == "1101")
        ).one_or_none()
        assert parent_1101 is not None, "Parent 1101 must exist"
        
        # Check origin/parent_id if schema supports
        columns = set(Account.__table__.columns.keys())
        if "origin" in columns:
            assert bbva.origin == "entity", "BBVA must be origin=entity"
        if "parent_id" in columns:
            assert bbva.parent_id == parent_1101.id, "BBVA parent_id must reference 1101"
        
        # Check nature inheritance
        assert bbva.nature == parent_1101.nature, (
            f"BBVA nature ({bbva.nature}) must inherit from parent ({parent_1101.nature})"
        )
        
        # Check code format
        assert bbva.code != "1101", "BBVA code must not equal parent code"
        assert bbva.code.startswith("1101."), "BBVA code must be under parent (1101.*)"


def test_entity_account_codes_are_generated_under_parent(isolated_catalog_engine):
    """
    P1-3: Entity account codes are generated, not user-defined.
    
    Creating multiple entities under 1101 generates:
    - 1101.001 (BBVA)
    - 1101.002 (Banamex)
    
    User does NOT pass code parameter.
    Function generates sequentially.
    
    CONTRATO FUTURO:
    - No 'code' parameter in create_entity_account()
    - Codes assigned as parent_code + ".NNN"
    
    ESTADO ACTUAL: FAIL (function not implemented)
    """
    create_entity_account = require_create_entity_account()
    
    with core.get_session() as session:
        # Create first entity
        bbva = create_entity_account(
            session=session,
            parent_code="1101",
            name="BBVA"
        )
        
        # Create second entity
        banamex = create_entity_account(
            session=session,
            parent_code="1101",
            name="Banamex"
        )
        
        # Verify sequential codes
        assert bbva.code == "1101.001", (
            f"First entity under 1101 must be 1101.001, got {bbva.code}"
        )
        assert banamex.code == "1101.002", (
            f"Second entity under 1101 must be 1101.002, got {banamex.code}"
        )


def test_entity_account_inherits_canonical_nature(isolated_catalog_engine):
    """
    P1-3: Entity account inherits nature from parent.
    
    Parent 1101 is Deudora (DEBIT).
    Create BBVA under 1101.
    
    CONTRATO FUTURO:
    - child.nature == parent.nature
    - Function does NOT accept nature parameter
    
    ESTADO ACTUAL: FAIL (function not implemented)
    """
    create_entity_account = require_create_entity_account()
    
    with core.get_session() as session:
        # Get parent canonical
        parent_1101 = session.exec(
            select(Account).where(Account.code == "1101")
        ).one_or_none()
        assert parent_1101 is not None
        parent_nature = parent_1101.nature
        
        # Create entity
        bbva = create_entity_account(
            session=session,
            parent_code="1101",
            name="BBVA"
        )
        
        # Verify inheritance
        assert bbva.nature == parent_nature, (
            f"BBVA nature ({bbva.nature}) must equal parent ({parent_nature})"
        )


# ============================================================
# Validation tests
# ============================================================

def test_entity_account_rejects_unknown_canonical_parent(isolated_catalog_engine):
    """
    P1-3: Attempting to create entity under non-existent parent fails.
    
    CONTRATO FUTURO:
    - raises ValueError
    - Account not inserted
    
    ESTADO ACTUAL: FAIL (function not implemented, but intended behavior)
    """
    create_entity_account = require_create_entity_account()
    
    with core.get_session() as session:
        # Attempt to create under non-existent parent
        with pytest.raises(ValueError) as exc_info:
            create_entity_account(
                session=session,
                parent_code="9999-NO-EXISTE",
                name="Imposible"
            )
        
        assert "9999-NO-EXISTE" in str(exc_info.value) or "parent" in str(exc_info.value).lower(), (
            "Error must mention non-existent parent"
        )
        
        # Verify not inserted
        impossible = session.exec(
            select(Account).where(Account.name == "Imposible")
        ).one_or_none()
        assert impossible is None, "Impossible account must not exist"


def test_entity_account_cannot_use_entity_account_as_parent(isolated_catalog_engine):
    """
    P1-3: Entity accounts cannot be parents to other entities (one level only).
    
    Hierarchy:
      1101 (canonical)
      ├─ BBVA (entity)
      ├─ Banamex (entity)
      └─ (NOT: BBVA → subcuenta)
    
    CONTRATO FUTURO:
    - creating entity under another entity: ValueError
    
    ESTADO ACTUAL: FAIL (function not implemented)
    """
    create_entity_account = require_create_entity_account()
    
    with core.get_session() as session:
        # Create first entity under canonical
        bbva = create_entity_account(
            session=session,
            parent_code="1101",
            name="BBVA"
        )
        
        # Attempt to create under BBVA (entity, not canonical)
        with pytest.raises(ValueError) as exc_info:
            create_entity_account(
                session=session,
                parent_code=bbva.code,  # Use entity code as parent
                name="Subcuenta rara"
            )
        
        assert "parent" in str(exc_info.value).lower() or "canonical" in str(exc_info.value).lower(), (
            "Error must indicate parent must be canonical"
        )


def test_arbitrary_orphan_account_remains_rejected(isolated_catalog_engine):
    """
    P1-3: P0-4 persists: arbitrary orphan accounts rejected.
    
    Direct insertion of:
    Account(code="9999.001", name="...", origin="entity", parent_id=None)
    must FAIL.
    
    Extensibility does NOT mean "any code works".
    
    CONTRATO FUTURO:
    - raises ValueError, RuntimeError, or listener rejection
    - account NOT inserted
    
    ESTADO ACTUAL: Should PASS because current listener rejects non-JSON codes.
    """
    with core.get_session() as session:
        columns = set(Account.__table__.columns.keys())
        
        # Try to insert orphaned entity account
        kwargs = {
            "code": "9999.001",
            "name": "Cuenta huérfana",
            "nature": "DEBIT",
        }
        
        if "origin" in columns:
            kwargs["origin"] = "entity"
        if "parent_id" in columns:
            kwargs["parent_id"] = None
        
        orphan = Account(**kwargs)
        session.add(orphan)
        
        # CONTRATO: insertion must be rejected
        with pytest.raises((ValueError, RuntimeError)):
            session.commit()
        
        # Verify not inserted
        session.rollback()
        
        orphan_row = session.exec(
            select(Account).where(Account.code == "9999.001")
        ).one_or_none()
        
        assert orphan_row is None, (
            "Orphan account 9999.001 must not exist in DB after rollback"
        )


def test_entity_extension_cannot_override_parent_nature(isolated_catalog_engine):
    """
    P1-3: Entity extension cannot override parent nature.
    
    Create BBVA (entity) under 1101 (Deudora).
    Attempt to modify BBVA.nature to Acreedora.
    
    CONTRATO FUTURO:
    - create_entity_account() succeeds
    - nature modification at DB layer REJECTED
    - original nature preserved after rollback
    
    ESTADO ACTUAL: FAIL because create_entity_account not implemented yet.
    Once implemented, the override attempt should fail.
    """
    create_entity_account = require_create_entity_account()
    
    with core.get_session() as session:
        # Create BBVA under 1101
        bbva = create_entity_account(
            session=session,
            parent_code="1101",
            name="BBVA"
        )
        original_nature = bbva.nature
        
        # Verify parent nature matches
        parent_1101 = session.exec(
            select(Account).where(Account.code == "1101")
        ).one_or_none()
        assert original_nature == parent_1101.nature, (
            "Entity nature must inherit from parent initially"
        )
        
        # Calculate wrong nature
        wrong_nature = (
            "Acreedora" if original_nature == "Deudora" else "Deudora"
        )
        
        # Attempt to override nature
        bbva.nature = wrong_nature
        session.add(bbva)
        
        # CONTRATO: modification must be REJECTED by listener
        with pytest.raises((ValueError, RuntimeError)):
            session.commit()
        
        # Verify nature reverted after rollback
        session.rollback()
        session.refresh(bbva)
        
        assert bbva.nature == original_nature, (
            f"BBVA nature must remain {original_nature} after failed override"
        )


# ============================================================
# E2E tests
# ============================================================

def test_post_entry_accepts_registered_entity_extension(isolated_catalog_engine):
    """
    P1-3: A registered entity account can receive JournalLine.
    
    Create BBVA under 1101.
    Post entry with line to BBVA.code.
    Entry persists correctly.
    
    This integrates:
    - extensibility (BBVA exists as Account)
    - P0-4 (account validated and persisted)
    - P1-1 (ORM persistence works)
    
    CONTRATO FUTURO:
    - post_entry accepts entity account codes
    - JournalLine created with account_id/account_code
    
    ESTADO ACTUAL: FAIL (create_entity_account not implemented)
    """
    create_entity_account = require_create_entity_account()
    
    with core.get_session() as session:
        # Create BBVA
        bbva = create_entity_account(
            session=session,
            parent_code="1101",
            name="BBVA"
        )
        session.commit()
        bbva_code = bbva.code
        bbva_id = bbva.id
    
    # Now post entry using BBVA code
    result = core.post_entry({
        "description": "Venta depositada en BBVA",
        "lines": [
            {
                "account_code": bbva_code,
                "debit": Decimal("100"),
                "credit": Decimal("0"),
            },
            {
                "account_code": "4101",
                "debit": Decimal("0"),
                "credit": Decimal("100"),
            },
        ]
    })
    
    # Entry should succeed
    assert result.get("ok") is True, (
        f"post_entry with entity account {bbva_code} failed: {result}"
    )
    
    # Verify JournalLine created correctly
    entry_id = result.get("entry_id")
    assert entry_id is not None
    
    from aqorath.models import JournalLine
    with core.get_session() as session:
        lines = session.exec(
            select(JournalLine).where(JournalLine.entry_id == entry_id)
        ).all()
        
        assert len(lines) >= 1, "JournalLines should exist"
        
        # Find BBVA line
        bbva_line = None
        for line in lines:
            if line.account_code == bbva_code or line.account_id == bbva_id:
                bbva_line = line
                break
        
        assert bbva_line is not None, (
            f"JournalLine for {bbva_code} not found"
        )
        assert bbva_line.account_id == bbva_id, (
            f"JournalLine account_id must be {bbva_id}"
        )
        assert bbva_line.account_code == bbva_code, (
            f"JournalLine account_code must be {bbva_code}"
        )
        assert bbva_line.debit == str(to_decimal_exact(Decimal("100"))), (
            f"JournalLine debit mismatch"
        )


# ============================================================
# Stability tests
# ============================================================

def test_canonical_accounts_unchanged_by_extensions(isolated_catalog_engine):
    """
    P1-3: Creating entity accounts does NOT modify canonical.
    
    Canonical 1101 remains:
    - code: "1101"
    - nature: "DEBIT" (unchanged)
    - name: "Bancos" (unchanged)
    
    catalogo_base.json not written (byte-for-byte unchanged).
    
    CONTRATO FUTURO:
    - Extensions do not pollute canonical
    - Runtime operations do NOT touch JSON file
    """
    create_entity_account = require_create_entity_account()
    
    # Original state
    with core.get_session() as session:
        original_1101 = session.exec(
            select(Account).where(Account.code == "1101")
        ).one_or_none()
        original_nature = original_1101.nature
        original_name = original_1101.name
    
    # Capture JSON state BEFORE extensions
    catalog_file = Path(__file__).parent.parent / "aqorath" / "data" / "catalogo_base.json"
    before_bytes = None
    if catalog_file.exists():
        before_bytes = catalog_file.read_bytes()
    
    # Create extensions
    with core.get_session() as session:
        for name in ["BBVA", "Banamex", "Nu"]:
            create_entity_account(
                session=session,
                parent_code="1101",
                name=name
            )
    
    # Verify canonical DB row unchanged
    with core.get_session() as session:
        final_1101 = session.exec(
            select(Account).where(Account.code == "1101")
        ).one_or_none()
        
        assert final_1101.code == "1101", "Canonical code unchanged"
        assert final_1101.nature == original_nature, "Canonical nature unchanged"
        assert final_1101.name == original_name, "Canonical name unchanged"
    
    # CONTRATO FUTURO: JSON file byte-for-byte unchanged
    if before_bytes is not None:
        after_bytes = catalog_file.read_bytes()
        assert after_bytes == before_bytes, (
            "catalogo_base.json must not be modified by runtime operations"
        )
    
    # Also verify extensions not in JSON content
    if catalog_file.exists():
        import json
        with open(catalog_file) as f:
            data = json.load(f)
        assert "1101.001" not in str(data), (
            "catalogo_base.json must not contain extensions"
        )


# ============================================================
# Reporting classification tests
# ============================================================

def test_entity_account_inherits_canonical_reporting_classification(isolated_catalog_engine):
    """
    P1-3: Entity accounts inherit reporting classification from parent.
    
    Entity 1101.001 (under Bancos):
    - Should classify as Activo (like 1101)
    - Should use Deudora nature from parent
    
    Entity 4101.001 (under Ventas):
    - Should classify as Ingreso (like 4101)
    - Should use Acreedora nature from parent
    
    Test using real accounting_rules and catalog.
    """
    from aqorath.accounting_rules import compute_totals_by_tipo
    from aqorath.catalog import load_catalog, create_entity_account
    from decimal import Decimal
    
    # Create entities within a session context
    with core.get_session() as session:
        bbva = create_entity_account(
            session=session,
            parent_code="1101",
            name="BBVA"
        )
        bbva_code = bbva.code
        
        ventas_empresa = create_entity_account(
            session=session,
            parent_code="4101",
            name="Empresa A"
        )
        ventas_code = ventas_empresa.code
    
    # Simulate balances with entity accounts
    balances = {
        bbva_code: Decimal("100"),       # Entity 1101.NNN: +100 (activo deudor)
        ventas_code: Decimal("-100"),    # Entity 4101.NNN: -100 (ingreso acreedor)
    }
    
    # Load real catalog
    catalog_data = load_catalog()
    catalog_accounts = catalog_data.get("accounts", {})
    
    # Compute totals using real function
    totals = compute_totals_by_tipo(balances, catalog_accounts)
    
    # Verify classification inheritance
    assert totals.get("Activo") == Decimal("100"), (
        f"Entity {bbva_code} must inherit Activo classification. Got: {totals}"
    )
    
    assert totals.get("Ingreso") == Decimal("100"), (
        f"Entity {ventas_code} must inherit Ingreso classification. Got: {totals}"
    )
    
    assert totals.get("otros") == Decimal("0"), (
        f"No unclassified balance expected. Got: {totals}"
    )
