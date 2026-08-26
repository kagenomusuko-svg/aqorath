"""
Phase 2B.1: Account Role Resolution Contracts (Hardened)

Congelan el contrato de resolución de ROLES DE CUENTA a CUENTAS CONCRETAS.

Arquitectura:
  AccountingProposal (semántica, roles)
    ↓ resolve_proposal_accounts(session, proposal, account_bindings)
    ↓ ResolvedAccountingProposal (con identidades concretas: account_id/code/name)

Separación fundamental:
  - economic_facts resuelve: QUÉ ocurrió (AccountingProposal semántica)
  - account_resolution resuelve: EN QUÉ cuentas concretas cae
  - [posting futuro] persiste: los asientos finales

account_bindings es ENTRADA EXPLÍCITA:
  { "cash": "CODIGO-CAJA", "sales_revenue": "CODIGO-VENTAS" }

NO hardcodear códigos. NO crear cuentas automáticamente. NO persistir.

HARDENING: Contracts are fail-closed. Assertions are strict. No exception swallowing.
"""

from decimal import Decimal
import pytest


def test_account_resolution_module_exists():
    """
    Contract: aqorath.account_resolution module must exist.

    Establece que existe un módulo futuro de resolución de cuentas.
    """
    import aqorath.account_resolution


def test_account_resolution_public_contract_exists():
    """
    Contract: account_resolution expone los tipos y función pública.

    Establece que la API futura contiene:
      - ResolvedProposalLine
      - ResolvedAccountingProposal
      - resolve_proposal_accounts
    """
    import aqorath.account_resolution
    
    assert hasattr(aqorath.account_resolution, "ResolvedProposalLine")
    assert hasattr(aqorath.account_resolution, "ResolvedAccountingProposal")
    assert hasattr(aqorath.account_resolution, "resolve_proposal_accounts")
    assert callable(aqorath.account_resolution.resolve_proposal_accounts)


def test_cash_sale_proposal_accepts_explicit_account_bindings(monkeypatch):
    """
    Contract: resolve_proposal_accounts recibe una propuesta y bindings explícitos.

    Establece que la función acepta:
      - session: sesión SQLite actual
      - proposal: AccountingProposal semántica
      - account_bindings: dict role → account_code configurado
    
    Caso real: venta en efectivo previamente resuelta a nivel semántico.
    HARDENING: Assertions estrictas, sin exception swallowing.
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact
    from aqorath.account_resolution import resolve_proposal_accounts
    import aqorath.catalog
    import types
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)
    
    bindings = {
        "cash": "TEST-CASH-001",
        "sales_revenue": "TEST-SALES-900",
    }
    
    supplied_session = object()
    
    def fake_catalog_resolver(sess, code):
        accounts = {
            "TEST-CASH-001": {
                "id": 101,
                "code": "TEST-CASH-001",
                "name": "Caja principal",
                "origin": "entity",
            },
            "TEST-SALES-900": {
                "id": 902,
                "code": "TEST-SALES-900",
                "name": "Ventas",
                "origin": "entity",
            },
        }
        if code not in accounts:
            return None
        return types.SimpleNamespace(**accounts[code])
    
    monkeypatch.setattr(aqorath.catalog, "resolve_account_by_code", fake_catalog_resolver)
    
    # Sin exception swallowing
    resolved = resolve_proposal_accounts(supplied_session, proposal, bindings)
    
    # Assertions estrictas
    assert resolved is not None
    assert len(resolved.lines) == 2
    assert resolved.lines[0].account_code == "TEST-CASH-001"
    assert resolved.lines[0].account_id == 101
    assert resolved.lines[1].account_code == "TEST-SALES-900"
    assert resolved.lines[1].account_id == 902


def test_account_resolution_uses_catalog_with_supplied_session(monkeypatch):
    """
    Contract: resolve_proposal_accounts usa la sesión suministrada para lookup.

    Establece que:
      1. La sesión recibida es la MISMA que se pasa a catalog (identidad)
      2. Los códigos consultados son exactos (bindings)
      3. El catálogo se invoca exactamente 2 veces (una por línea)
    
    HARDENING: Assertions estrictas sobre calls.
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact
    from aqorath.account_resolution import resolve_proposal_accounts
    import aqorath.catalog
    import types
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)
    
    bindings = {
        "cash": "TEST-CASH-001",
        "sales_revenue": "TEST-SALES-900",
    }
    
    supplied_session = object()
    calls = []
    
    def tracking_catalog_resolver(sess, code):
        calls.append((sess, code))
        accounts = {
            "TEST-CASH-001": types.SimpleNamespace(
                id=101, code="TEST-CASH-001", name="Caja", origin="entity"
            ),
            "TEST-SALES-900": types.SimpleNamespace(
                id=902, code="TEST-SALES-900", name="Ventas", origin="entity"
            ),
        }
        return accounts.get(code)
    
    monkeypatch.setattr(aqorath.catalog, "resolve_account_by_code", tracking_catalog_resolver)
    
    # Sin exception swallowing
    resolved = resolve_proposal_accounts(supplied_session, proposal, bindings)
    
    # Assertions estrictas sobre calls
    assert len(calls) == 2, "catalog resolver debe invocarse exactamente una vez por línea"
    
    # Session identity
    for sess, code in calls:
        assert sess is supplied_session, "sesión debe ser exacta por identidad"
    
    # Códigos exactos en orden
    codes = [code for sess, code in calls]
    assert codes == ["TEST-CASH-001", "TEST-SALES-900"], "códigos deben ser exactamente los de bindings"


def test_resolved_lines_preserve_semantics_and_add_account_identity(monkeypatch):
    """
    Contract: ResolvedProposalLine preserva semántica y agrega identidad concreta.

    Establece que:
      - account_role se conserva
      - side se conserva
      - amount se conserva exactamente (Decimal)
      - account_id, account_code, account_name se agregan
      - NO es JournalLine (sin entry_id, debit, credit)
    
    HARDENING: Assertions de tipo, sin try/except, verificación de ausencia de campos.
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact
    from aqorath.account_resolution import resolve_proposal_accounts, ResolvedProposalLine
    import aqorath.catalog
    import types
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)
    
    bindings = {
        "cash": "TEST-CASH-001",
        "sales_revenue": "TEST-SALES-900",
    }
    
    def fake_resolver(sess, code):
        accounts = {
            "TEST-CASH-001": types.SimpleNamespace(
                id=101, code="TEST-CASH-001", name="Caja principal", origin="entity"
            ),
            "TEST-SALES-900": types.SimpleNamespace(
                id=902, code="TEST-SALES-900", name="Ingresos por ventas", origin="entity"
            ),
        }
        return accounts.get(code)
    
    monkeypatch.setattr(aqorath.catalog, "resolve_account_by_code", fake_resolver)
    
    # Sin exception swallowing
    resolved = resolve_proposal_accounts(object(), proposal, bindings)
    
    # Type check
    assert len(resolved.lines) == 2
    for line in resolved.lines:
        assert isinstance(line, ResolvedProposalLine)
    
    # Cash line
    cash_line = resolved.lines[0]
    assert cash_line.account_role == "cash"
    assert cash_line.account_id == 101
    assert cash_line.account_code == "TEST-CASH-001"
    assert cash_line.account_name == "Caja principal"
    assert cash_line.side == "debit"
    assert cash_line.amount == Decimal("200.00")
    
    # Sales line
    sales_line = resolved.lines[1]
    assert sales_line.account_role == "sales_revenue"
    assert sales_line.account_id == 902
    assert sales_line.account_code == "TEST-SALES-900"
    assert sales_line.account_name == "Ingresos por ventas"
    assert sales_line.side == "credit"
    assert sales_line.amount == Decimal("200.00")
    
    # NO JournalLine fields
    assert not hasattr(cash_line, "entry_id")
    assert not hasattr(cash_line, "debit")
    assert not hasattr(cash_line, "credit")
    assert not hasattr(sales_line, "entry_id")
    assert not hasattr(sales_line, "debit")
    assert not hasattr(sales_line, "credit")


def test_resolved_proposal_preserves_decimal_balance_order_and_explanation(monkeypatch):
    """
    Contract: ResolvedAccountingProposal preserva balance, orden y explanation exactos.

    Establece que:
      - total_debit == total_credit == Decimal("200.00")
      - Líneas en mismo orden
      - explanation es idéntica, sin reescritura
    
    HARDENING: Sin try/except, type check, assertions estrictas.
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact
    from aqorath.account_resolution import resolve_proposal_accounts, ResolvedAccountingProposal
    import aqorath.catalog
    import types
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)
    original_explanation = proposal.explanation
    
    bindings = {
        "cash": "TEST-CASH-001",
        "sales_revenue": "TEST-SALES-900",
    }
    
    def fake_resolver(sess, code):
        accounts = {
            "TEST-CASH-001": types.SimpleNamespace(
                id=101, code="TEST-CASH-001", name="Caja", origin="entity"
            ),
            "TEST-SALES-900": types.SimpleNamespace(
                id=902, code="TEST-SALES-900", name="Ventas", origin="entity"
            ),
        }
        return accounts.get(code)
    
    monkeypatch.setattr(aqorath.catalog, "resolve_account_by_code", fake_resolver)
    
    # Sin exception swallowing
    resolved = resolve_proposal_accounts(object(), proposal, bindings)
    
    # Type check
    assert isinstance(resolved, ResolvedAccountingProposal)
    
    # Balance
    total_debit = sum(
        (l.amount for l in resolved.lines if l.side == "debit"),
        Decimal("0"),
    )
    total_credit = sum(
        (l.amount for l in resolved.lines if l.side == "credit"),
        Decimal("0"),
    )
    assert total_debit == Decimal("200.00")
    assert total_credit == Decimal("200.00")
    
    # Orden
    assert resolved.lines[0].account_role == "cash"
    assert resolved.lines[1].account_role == "sales_revenue"
    
    # Explanation idéntica
    assert resolved.explanation == original_explanation


def test_account_resolution_uses_bindings_not_hardcoded_codes(monkeypatch):
    """
    Contract: La resolución usa bindings suministrados, NO códigos hardcodeados.

    Congelado: Si la MISMA propuesta se resuelve con bindings DISTINTOS,
    produce resultados DISTINTOS.
    
    HARDENING TOTAL (Phase 2B.1B):
    - Registra TODOS los lookups al catálogo
    - Verifica exactamente 4 lookups (2 por resolución)
    - Verifica identidad de sesión (session_a is, session_b is)
    - Verifica códigos exactos en orden: CASH-A, SALES-A, CASH-B, SALES-B
    - Verifica que account_id/code/name vienen de Account retornado
    - Verifica que role/side/amount se preservan en ambas resoluciones
    - Sin exception swallowing
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact
    from aqorath.account_resolution import resolve_proposal_accounts
    import aqorath.catalog
    import types
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)
    
    bindings_a = {
        "cash": "CASH-A",
        "sales_revenue": "SALES-A",
    }
    
    bindings_b = {
        "cash": "CASH-B",
        "sales_revenue": "SALES-B",
    }
    
    # Accounts deliberadamente distintos en TODOS los campos
    accounts_db = {
        "CASH-A": types.SimpleNamespace(
            id=101, code="CASH-A", name="Caja A", origin="entity"
        ),
        "SALES-A": types.SimpleNamespace(
            id=201, code="SALES-A", name="Ventas A", origin="canonical"
        ),
        "CASH-B": types.SimpleNamespace(
            id=102, code="CASH-B", name="Caja B", origin="canonical"
        ),
        "SALES-B": types.SimpleNamespace(
            id=202, code="SALES-B", name="Ventas B", origin="entity"
        ),
    }
    
    # Registrar TODOS los lookups
    calls = []
    
    def tracking_resolver(sess, code):
        calls.append((sess, code))
        return accounts_db.get(code)
    
    monkeypatch.setattr(aqorath.catalog, "resolve_account_by_code", tracking_resolver)
    
    # Dos sesiones distintas
    session_a = object()
    session_b = object()
    
    # Sin exception swallowing
    resolved_a = resolve_proposal_accounts(session_a, proposal, bindings_a)
    resolved_b = resolve_proposal_accounts(session_b, proposal, bindings_b)
    
    # ===== VERIFY EXACT LOOKUPS =====
    # Exactamente 4 calls (2 líneas × 2 resoluciones)
    assert len(calls) == 4, f"Expected 4 catalog lookups, got {len(calls)}"
    
    # Códigos exactos en orden
    codes = [code for _, code in calls]
    assert codes == ["CASH-A", "SALES-A", "CASH-B", "SALES-B"], (
        f"Expected exact codes [CASH-A, SALES-A, CASH-B, SALES-B], got {codes}"
    )
    
    # Session identity
    assert calls[0][0] is session_a, "First lookup must use session_a"
    assert calls[1][0] is session_a, "Second lookup must use session_a"
    assert calls[2][0] is session_b, "Third lookup must use session_b"
    assert calls[3][0] is session_b, "Fourth lookup must use session_b"
    
    # ===== VERIFY FULL OUTPUT IDENTITY — RESOLUTION A =====
    # Cash line A
    assert resolved_a.lines[0].account_role == "cash"
    assert resolved_a.lines[0].account_id == 101, "Cash A id must be 101"
    assert resolved_a.lines[0].account_code == "CASH-A", "Cash A code must be CASH-A"
    assert resolved_a.lines[0].account_name == "Caja A", "Cash A name must be Caja A"
    assert resolved_a.lines[0].side == "debit"
    assert resolved_a.lines[0].amount == Decimal("200.00")
    
    # Sales line A
    assert resolved_a.lines[1].account_role == "sales_revenue"
    assert resolved_a.lines[1].account_id == 201, "Sales A id must be 201"
    assert resolved_a.lines[1].account_code == "SALES-A", "Sales A code must be SALES-A"
    assert resolved_a.lines[1].account_name == "Ventas A", "Sales A name must be Ventas A"
    assert resolved_a.lines[1].side == "credit"
    assert resolved_a.lines[1].amount == Decimal("200.00")
    
    # ===== VERIFY FULL OUTPUT IDENTITY — RESOLUTION B =====
    # Cash line B
    assert resolved_b.lines[0].account_role == "cash"
    assert resolved_b.lines[0].account_id == 102, "Cash B id must be 102"
    assert resolved_b.lines[0].account_code == "CASH-B", "Cash B code must be CASH-B"
    assert resolved_b.lines[0].account_name == "Caja B", "Cash B name must be Caja B"
    assert resolved_b.lines[0].side == "debit"
    assert resolved_b.lines[0].amount == Decimal("200.00")
    
    # Sales line B
    assert resolved_b.lines[1].account_role == "sales_revenue"
    assert resolved_b.lines[1].account_id == 202, "Sales B id must be 202"
    assert resolved_b.lines[1].account_code == "SALES-B", "Sales B code must be SALES-B"
    assert resolved_b.lines[1].account_name == "Ventas B", "Sales B name must be Ventas B"
    assert resolved_b.lines[1].side == "credit"
    assert resolved_b.lines[1].amount == Decimal("200.00")
    
    # ===== VERIFY DISTINCTNESS =====
    # A and B must be completely distinct
    assert resolved_a.lines[0].account_id != resolved_b.lines[0].account_id
    assert resolved_a.lines[0].account_code != resolved_b.lines[0].account_code
    assert resolved_a.lines[0].account_name != resolved_b.lines[0].account_name
    
    assert resolved_a.lines[1].account_id != resolved_b.lines[1].account_id
    assert resolved_a.lines[1].account_code != resolved_b.lines[1].account_code
    assert resolved_a.lines[1].account_name != resolved_b.lines[1].account_name


def test_account_resolution_rejects_missing_role_binding(monkeypatch):
    """
    Contract: Si un role no tiene binding, la resolución falla explícitamente.

    Establece ALL-OR-NOTHING: no output parcial.
    
    HARDENING: Bindings incompletos, error esperado restringido a KeyError/ValueError.
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact
    from aqorath.account_resolution import resolve_proposal_accounts
    import aqorath.catalog
    import types
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)
    
    # Bindings incompletos: cash OK, sales_revenue falta
    bindings = {
        "cash": "TEST-CASH-001",
    }
    
    def fake_resolver(sess, code):
        # Cash es válido, sales_revenue no existe
        if code == "TEST-CASH-001":
            return types.SimpleNamespace(
                id=101, code="TEST-CASH-001", name="Caja", origin="entity"
            )
        return None
    
    monkeypatch.setattr(aqorath.catalog, "resolve_account_by_code", fake_resolver)
    
    # Debe fallar con KeyError o ValueError (no AttributeError, no TypeError)
    with pytest.raises((KeyError, ValueError)):
        resolve_proposal_accounts(object(), proposal, bindings)


def test_account_resolution_rejects_missing_account_without_creating_one(monkeypatch):
    """
    Contract: Si una Account no existe, falla sin crearla automáticamente.

    Congelado: missing Account ≠ automatic account creation
    
    HARDENING: Error esperado no incluye AttributeError/TypeError.
    create_entity_account bomb permanece activa.
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact
    from aqorath.account_resolution import resolve_proposal_accounts
    import aqorath.catalog
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)
    
    bindings = {
        "cash": "DOES-NOT-EXIST",
        "sales_revenue": "ALSO-MISSING",
    }
    
    # Resolver devuelve None (cuenta no encontrada)
    def fake_resolver(sess, code):
        return None
    
    # Bomba: create_entity_account
    def forbidden_create(*args, **kwargs):
        raise AssertionError(
            "account_resolution must not automatically create accounts"
        )
    
    monkeypatch.setattr(aqorath.catalog, "resolve_account_by_code", fake_resolver)
    monkeypatch.setattr(aqorath.catalog, "create_entity_account", forbidden_create)
    
    # Debe fallar con ValueError o LookupError (no AttributeError, no TypeError)
    with pytest.raises((ValueError, LookupError)):
        resolve_proposal_accounts(object(), proposal, bindings)


def test_account_resolution_does_not_persist_or_post(monkeypatch):
    """
    Contract: Resolución NO persiste, NO postea, NO usa persistencia.

    Congelado: resolution ≠ persistence ≠ posting
    
    HARDENING: Happy-path sin exception swallowing. Write/post/create bombs.
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact
    from aqorath.account_resolution import resolve_proposal_accounts, ResolvedAccountingProposal
    import aqorath.catalog
    import aqorath.core
    import aqorath.storage
    import types
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)
    
    bindings = {
        "cash": "TEST-CASH-001",
        "sales_revenue": "TEST-SALES-900",
    }
    
    # Session que explota en writes
    class WriteBombSession:
        def add(self, *args, **kwargs):
            raise AssertionError("must not write to session")
        def commit(self):
            raise AssertionError("must not commit")
        def rollback(self):
            raise AssertionError("must not rollback")
        def flush(self):
            raise AssertionError("must not flush")
    
    session = WriteBombSession()
    
    # Resolver normal
    def fake_resolver(sess, code):
        return types.SimpleNamespace(
            id=100,
            code=code,
            name=f"Account {code}",
            origin="entity",
        )
    
    # Bombas
    def forbidden_post(*args, **kwargs):
        raise AssertionError("must not call core.post_entry")
    
    def forbidden_create(*args, **kwargs):
        raise AssertionError("must not create accounts")
    
    def forbidden_get_session():
        raise AssertionError("must not call get_session")
    
    monkeypatch.setattr(aqorath.catalog, "resolve_account_by_code", fake_resolver)
    monkeypatch.setattr(aqorath.core, "post_entry", forbidden_post)
    monkeypatch.setattr(aqorath.catalog, "create_entity_account", forbidden_create)
    monkeypatch.setattr(aqorath.storage, "get_session", forbidden_get_session)
    
    # Sin exception swallowing: happy-path debe completar
    result = resolve_proposal_accounts(session, proposal, bindings)
    
    # Happy-path: resultado es ResolvedAccountingProposal
    assert result is not None
    assert isinstance(result, ResolvedAccountingProposal)
    assert len(result.lines) == 2
