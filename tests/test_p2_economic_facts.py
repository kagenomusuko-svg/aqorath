"""
Phase 2A.1: Economic Fact Application Layer Contracts

Congelan el contrato mínimo del primer vertical de producto:
"Vendí un pantalón por $200 en efectivo."

Representa un HECHO ECONÓMICO estruturado:
  - type: "sale"
  - amount: Decimal("200.00")
  - payment_method: "cash"

Que se resuelve determinísticamente a una PROPUESTA CONTABLE sin persistencia:
  - Dos líneas: cash (debit) y sales_revenue (credit)
  - Balanceada exactamente en Decimal
  - Explicación humana legible
  - Pura: sin DB, sin LLM, sin llamadas externas

Phase 2A.1 define únicamente contratos. La implementación pertenece a Phase 2A.2.
"""

from decimal import Decimal
import ast
import pytest


# ============================================================================
# TEST-ONLY HELPERS: AST-based import detection
# ============================================================================
# These helpers are used only within test_economic_fact_resolution_does_not_persist
# to verify that economic_facts module doesn't import prohibited families.
# They handle:
#   - ast.Import: import X, import X.Y, import X as Z
#   - ast.ImportFrom: from X import Y, from X import Y as Z
#   - Relative: from . import X, from .X import Y, from .. import X
# ============================================================================


def _parse_imports_from_source(source: str) -> tuple:
    """
    Parse Python source and extract all imports.
    
    Returns:
        (absolute_imports, from_imports)
        
        absolute_imports: Set of module names from 'import X'
        from_imports: Set of tuples (level, module, name) from 'from X import Y'
                      - level: 0 for absolute, 1+ for relative
                      - module: module name or empty string for "from . import X"
                      - name: the imported name (not the alias)
    """
    tree = ast.parse(source)
    
    absolute_imports = set()
    from_imports = set()
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute_imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                from_imports.add((node.level, node.module or "", alias.name))
    
    return absolute_imports, from_imports


def _detects_forbidden_domain_import(
    absolute_imports: set,
    from_imports: set
) -> bool:
    """
    Check if imports contain prohibited families.
    
    Prohibited families:
      - aqorath.core (and submodules)
      - aqorath.storage (and submodules)
      - sqlite3
      - sqlalchemy
      - sqlmodel
    
    Args:
        absolute_imports: Set of 'import X' module names
        from_imports: Set of (level, module, name) tuples from 'from X import Y'
    
    Returns:
        True if any prohibited import is detected, False otherwise.
    """
    prohibited_families = [
        "sqlite3",
        "sqlalchemy",
        "sqlmodel",
        "aqorath.core",
        "aqorath.storage",
    ]
    
    # Check absolute imports: import X or import X.Y
    for module_name in absolute_imports:
        for prohibited in prohibited_families:
            if module_name == prohibited or module_name.startswith(prohibited + "."):
                return True
    
    # Check from imports
    for level, module, name in from_imports:
        if level == 0:
            # Absolute: from X import Y or from X.Y import Z
            if module:
                # Check the module part
                for prohibited in prohibited_families:
                    if module == prohibited or module.startswith(prohibited + "."):
                        return True
                
                # Special case: from aqorath import core or storage
                if module == "aqorath" and name in ("core", "storage"):
                    return True
            else:
                # from something import Y (shouldn't happen for absolute without module)
                pass
        else:
            # Relative: from . import X or from .X import Y or from .. import X
            if module:
                # from .X import Y - check if X is a prohibited relative module
                for prohibited in prohibited_families:
                    prohibited_relative = prohibited.split(".")[-1]  # "core" or "storage"
                    if module == prohibited_relative or module.startswith(prohibited_relative + "."):
                        return True
            else:
                # from . import X or from .. import X
                # Check the imported name directly
                for prohibited in prohibited_families:
                    prohibited_relative = prohibited.split(".")[-1]  # "core" or "storage"
                    if name == prohibited_relative:
                        return True
    
    return False


def test_economic_fact_module_exists():
    """
    Contract: The economic_facts module must exist in aqorath.

    Establece que aqorath.economic_facts es un módulo importable.
    """
    import aqorath.economic_facts  # noqa: F401


def test_economic_fact_public_contract_exists():
    """
    Contract: The module exposes the three core public types.

    Establece que aqorath.economic_facts expone:
      - EconomicFact
      - AccountingProposal
      - ProposalLine
      - resolve_economic_fact
    """
    from aqorath.economic_facts import (
        EconomicFact,
        AccountingProposal,
        ProposalLine,
        resolve_economic_fact,
    )
    assert EconomicFact is not None
    assert AccountingProposal is not None
    assert ProposalLine is not None
    assert callable(resolve_economic_fact)


def test_sale_cash_fact_accepts_decimal_amount():
    """
    Contract: EconomicFact accepts type, amount (Decimal), payment_method.

    Establece que EconomicFact debe aceptar el caso obligatorio:
      type="sale"
      amount=Decimal("200.00")
      payment_method="cash"

    Decimal es la autoridad monetaria. Float rechazado.
    
    También congelará que EconomicFact NO es una póliza contable:
    no debe exponer campos de persistencia/contabilidad como:
      - debit, credit
      - account_id, account_code
      - journal_lines
      - entry_id, db_path, session, sqlite_connection
    
    EconomicFact = HECHO ECONÓMICO, no instrucción contable.
    
    Tampoco debe ACEPTAR silenciosamente kwargs contables:
      - debit=..., credit=..., account_id=..., etc.
    """
    from aqorath.economic_facts import EconomicFact

    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    assert fact.type == "sale"
    assert fact.amount == Decimal("200.00")
    assert fact.payment_method == "cash"

    # EconomicFact NO es una póliza contable
    # No debe exponer campos contables/de persistencia
    prohibited_accounting_fields = [
        "debit",
        "credit",
        "account_id",
        "account_code",
        "journal_lines",
        "entry_id",
        "db_path",
        "session",
        "sqlite_connection",
    ]

    for field in prohibited_accounting_fields:
        assert not hasattr(fact, field), (
            f"EconomicFact must not expose '{field}' (accounting/persistence field). "
            "EconomicFact represents WHAT HAPPENED, not how to record it."
        )

    # Tampoco debe ACEPTAR silenciosamente kwargs contables
    # Si se pasa debit=..., account_id=..., etc. como argumentos, debe fallar
    for field in prohibited_accounting_fields:
        with pytest.raises((TypeError, ValueError, AttributeError)):
            EconomicFact(
                type="sale",
                amount=Decimal("200.00"),
                payment_method="cash",
                **{field: "some_value"}  # Pasar como kwarg prohibido
            )


def test_sale_cash_resolves_to_accounting_proposal():
    """
    Contract: resolve_economic_fact returns an AccountingProposal.

    Establece que llamar resolve_economic_fact sobre un sale + cash
    retorna un objeto de tipo AccountingProposal, no un dict.
    """
    from aqorath.economic_facts import (
        EconomicFact,
        AccountingProposal,
        resolve_economic_fact,
    )

    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)
    assert isinstance(proposal, AccountingProposal)


def test_sale_cash_proposal_has_exactly_two_lines():
    """
    Contract: The proposal for sale+cash has exactly 2 lines.

    Establece que la propuesta contiene exactamente:
      - 1 línea de debito (cash)
      - 1 línea de crédito (sales_revenue)
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)
    assert len(proposal.lines) == 2


def test_sale_cash_debits_cash_and_credits_sales_revenue():
    """
    Contract: Proposal lines specify semantic account roles and sides.

    Establece que la propuesta contiene:
      - Línea 1: account_role="cash", side="debit", amount=Decimal("200.00")
      - Línea 2: account_role="sales_revenue", side="credit", amount=Decimal("200.00")

    NO hardcodear account IDs o SAT numbers. Usar roles semánticos.
    
    También congelará que ProposalLine NO expone account_id/account_code concretos.
    La traducción role → account_code pertenece a una frontera posterior.
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)

    # Buscar líneas por role y side
    cash_line = next(
        (l for l in proposal.lines if l.account_role == "cash" and l.side == "debit"),
        None,
    )
    revenue_line = next(
        (l for l in proposal.lines
         if l.account_role == "sales_revenue" and l.side == "credit"),
        None,
    )

    assert cash_line is not None, "Missing cash debit line"
    assert revenue_line is not None, "Missing sales_revenue credit line"
    assert cash_line.amount == Decimal("200.00")
    assert revenue_line.amount == Decimal("200.00")

    # ProposalLine debe ser semántico: role/side/amount
    # NO debe exponer account_id o account_code concretos
    # (eso pertenece a later mapping: role → account_code)
    prohibited_concrete_fields = [
        "account_id",
        "account_code",
        "account_name",
        "sat_code",
        "db_id",
    ]

    for line in proposal.lines:
        for field in prohibited_concrete_fields:
            assert not hasattr(line, field), (
                f"ProposalLine must not expose '{field}' (concrete account mapping). "
                "Roles are semantic; account translation is delegated to later stage."
            )


def test_sale_cash_proposal_is_decimal_exact_and_balanced():
    """
    Contract: Proposal is exactly balanced using Decimal arithmetic.

    Establece que:
      - total_debit == Decimal("200.00")
      - total_credit == Decimal("200.00")
      - ambos usan Decimal, no float
      - igualdad exacta, sin tolerancia
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)

    total_debit = sum(
        (l.amount for l in proposal.lines if l.side == "debit"),
        Decimal("0"),
    )
    total_credit = sum(
        (l.amount for l in proposal.lines if l.side == "credit"),
        Decimal("0"),
    )

    assert isinstance(total_debit, Decimal)
    assert isinstance(total_credit, Decimal)
    assert total_debit == total_credit == Decimal("200.00")


def test_economic_fact_resolution_is_deterministic():
    """
    Contract: The same fact resolves identically every time.

    Establece que llamar resolve_economic_fact dos veces sobre el mismo
    EconomicFact produce propuestas semánticamente iguales:
      - mismo número de líneas;
      - mismos roles;
      - mismos sides;
      - mismos amounts;
      - misma explicación.

    Sin IDs aleatorios. Sin timestamps. Sin UUID. Sin LLM.
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )

    proposal1 = resolve_economic_fact(fact)
    proposal2 = resolve_economic_fact(fact)

    # Verificar que ambas propuestas tienen la misma estructura
    assert len(proposal1.lines) == len(proposal2.lines)

    # Verificar que las líneas coinciden en role, side, amount
    for line1, line2 in zip(proposal1.lines, proposal2.lines):
        assert line1.account_role == line2.account_role
        assert line1.side == line2.side
        assert line1.amount == line2.amount

    # Verificar que la explicación es idéntica
    assert proposal1.explanation == proposal2.explanation


def test_accounting_proposal_contains_human_explanation():
    """
    Contract: Proposal includes a human-readable explanation.

    Establece que AccountingProposal.explanation comunica semánticamente:
      1. hubo una venta;
      2. se recibió/entró/aumentó efectivo;
      3. se reconoce ingreso/revenue por ventas.

    NO exigir oración literal exacta. Probar contenido semántico suficiente.
    NO generado por LLM. Determinista. Sin dependencias externas.
    NO una mera lista de keywords: "sale cash revenue" no es suficiente.
    Debe ser un texto coherente que comunique el hecho económico.
    """
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    proposal = resolve_economic_fact(fact)

    explanation = proposal.explanation
    
    # Básico: no vacío y es string
    assert isinstance(explanation, str), "explanation must be a string"
    assert explanation.strip(), "explanation must not be empty"

    explanation_lower = explanation.lower()

    # SEMÁNTICA 1: Venta / Sale
    has_sale_semantic = (
        "sale" in explanation_lower
        or "venta" in explanation_lower
        or "sold" in explanation_lower
        or "vendió" in explanation_lower
    )
    assert has_sale_semantic, (
        "explanation must communicate 'sale' semantic "
        "(use 'sale', 'venta', 'sold', 'vendió', etc.)"
    )

    # SEMÁNTICA 2: Entrada/Aumento de efectivo
    # Familia semántica de "recibió/entró/aumentó" en contexto de efectivo
    has_cash_received = (
        "cash" in explanation_lower
        or "efectivo" in explanation_lower
        or "caja" in explanation_lower
    )
    has_receipt_verb = (
        "receiv" in explanation_lower  # received, receive
        or "recib" in explanation_lower  # recibió, recibir
        or "came in" in explanation_lower
        or "came" in explanation_lower
        or "entr" in explanation_lower  # entró, entrada
        or "increas" in explanation_lower  # increased, increases
        or "increment" in explanation_lower
        or "augment" in explanation_lower
    )
    assert has_cash_received, (
        "explanation must mention cash/efectivo/caja"
    )
    assert has_receipt_verb, (
        "explanation must indicate receipt/entry of cash "
        "(use 'received', 'recibió', 'came in', 'entró', 'increased', etc.)"
    )

    # SEMÁNTICA 3: Reconocimiento de ingreso/revenue
    has_revenue_semantic = (
        "revenue" in explanation_lower
        or "sales revenue" in explanation_lower
        or "ingresos" in explanation_lower
        or "ingreso" in explanation_lower
        or "recogniz" in explanation_lower  # recognized, recognize
        or "reconocer" in explanation_lower
        or "reconoce" in explanation_lower
        or "reconoció" in explanation_lower
    )
    assert has_revenue_semantic, (
        "explanation must communicate revenue/income recognition semantic "
        "(use 'revenue', 'ingresos', 'recogniz-', 'reconocer', etc.)"
    )


def test_economic_fact_rejects_invalid_amounts():
    """
    Contract: EconomicFact validates amount constraints and required fields.

    Establece que EconomicFact rechaza explícitamente:
      1. amount == Decimal("0")
      2. amount < 0
      3. amount como float (no Decimal)
      4. type faltante (campos obligatorios sin defaults)
      5. amount faltante
      6. payment_method faltante

    Sin fallbacks silenciosos. Campos requeridos son realmente obligatorios.
    """
    from aqorath.economic_facts import EconomicFact

    # Zero amount debe fallar
    with pytest.raises((ValueError, TypeError, AttributeError)):
        EconomicFact(
            type="sale",
            amount=Decimal("0"),
            payment_method="cash",
        )

    # Negative amount debe fallar
    with pytest.raises((ValueError, TypeError, AttributeError)):
        EconomicFact(
            type="sale",
            amount=Decimal("-100.00"),
            payment_method="cash",
        )

    # Float como amount debe fallar o ser prevenido
    with pytest.raises((ValueError, TypeError, AttributeError)):
        EconomicFact(
            type="sale",
            amount=200.00,  # float, not Decimal
            payment_method="cash",
        )

    # CAMPOS OBLIGATORIOS: type, amount, payment_method no tienen defaults
    # Si falta type, debe fallar
    with pytest.raises((TypeError, AttributeError, ValueError)):
        EconomicFact(
            amount=Decimal("200.00"),
            payment_method="cash",
        )

    # Si falta amount, debe fallar
    with pytest.raises((TypeError, AttributeError, ValueError)):
        EconomicFact(
            type="sale",
            payment_method="cash",
        )

    # Si falta payment_method, debe fallar
    with pytest.raises((TypeError, AttributeError, ValueError)):
        EconomicFact(
            type="sale",
            amount=Decimal("200.00"),
        )


def test_economic_fact_rejects_unknown_type_and_payment_method():
    """
    Contract: EconomicFact rejects unknown type and payment_method.

    Establece que:
      1. type desconocido produce error explícito
      2. payment_method desconocido produce error explícito

    Sin fallback a "sale" o "cash" automáticamente.
    """
    from aqorath.economic_facts import EconomicFact

    # Unknown type
    with pytest.raises((ValueError, TypeError, KeyError)):
        EconomicFact(
            type="spaceship_sale",
            amount=Decimal("200.00"),
            payment_method="cash",
        )

    # Unknown payment method
    with pytest.raises((ValueError, TypeError, KeyError)):
        EconomicFact(
            type="sale",
            amount=Decimal("200.00"),
            payment_method="telepathy",
        )


def test_economic_fact_resolution_does_not_persist(monkeypatch):
    """
    Contract: resolve_economic_fact is pure—no dependencies on core/storage/persistence.

    Establece que resolver un EconomicFact:
      - NO importa aqorath.core
      - NO importa aqorath.storage
      - NO importa sqlite3, sqlalchemy, sqlmodel
      - NO abre SQLite
      - NO llama a core.post_entry

    Se demuestra:
      1. Mediante regresiones AST sobre snippets de código (ANTES de import).
      2. Dinámicamente bloqueando core.post_entry via monkeypatch.
      3. Inspección AST del módulo productivo cuando exista.
    """

    # ========================================================================
    # REGRESIONES AST: Probar detector sobre fuentes reales
    # Estos casos se ejecutan PRIMERO, ANTES de intentar importar el módulo
    # que no existe, así que verificamos que el detector funciona.
    # ========================================================================

    # CORE: Detectar imports de aqorath.core
    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "import aqorath.core"
    )), "REGRESSION: import aqorath.core debe detectarse"

    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from aqorath import core as c"
    )), "REGRESSION: from aqorath import core as c debe detectarse"

    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from aqorath.core import post_entry"
    )), "REGRESSION: from aqorath.core import post_entry debe detectarse"

    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from . import core as c"
    )), "REGRESSION: from . import core as c debe detectarse"

    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from .core import post_entry"
    )), "REGRESSION: from .core import post_entry debe detectarse"

    assert not _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from aqorath import core_helpers"
    )), "REGRESSION: from aqorath import core_helpers NO debe detectarse"

    # STORAGE: Detectar imports de aqorath.storage
    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "import aqorath.storage"
    )), "REGRESSION: import aqorath.storage debe detectarse"

    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from aqorath import storage as s"
    )), "REGRESSION: from aqorath import storage as s debe detectarse"

    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from aqorath.storage import get_session"
    )), "REGRESSION: from aqorath.storage import get_session debe detectarse"

    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from . import storage"
    )), "REGRESSION: from . import storage debe detectarse"

    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from .storage import get_session"
    )), "REGRESSION: from .storage import get_session debe detectarse"

    assert not _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from aqorath import storage_utils"
    )), "REGRESSION: from aqorath import storage_utils NO debe detectarse"

    # PERSISTENCE LIBRARIES
    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "import sqlite3"
    )), "REGRESSION: import sqlite3 debe detectarse"

    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from sqlite3 import connect"
    )), "REGRESSION: from sqlite3 import connect debe detectarse"

    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "import sqlalchemy.orm"
    )), "REGRESSION: import sqlalchemy.orm debe detectarse"

    assert _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from sqlmodel import Session"
    )), "REGRESSION: from sqlmodel import Session debe detectarse"

    # ALLOWED: No deben detectarse
    assert not _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from decimal import Decimal"
    )), "REGRESSION: from decimal import Decimal NO debe detectarse"

    assert not _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from aqorath import money"
    )), "REGRESSION: from aqorath import money NO debe detectarse"

    assert not _detects_forbidden_domain_import(*_parse_imports_from_source(
        "from .money import to_decimal_exact"
    )), "REGRESSION: from .money import to_decimal_exact NO debe detectarse"

    # ========================================================================
    # FIN DE REGRESIONES: Todas pasaron. Ahora intentar importar módulo real.
    # ========================================================================

    import aqorath.core
    from aqorath.economic_facts import EconomicFact, resolve_economic_fact

    # Bloquear core.post_entry dinámicamente
    def forbidden_post_entry(*args, **kwargs):
        raise AssertionError(
            "resolve_economic_fact must not call core.post_entry. "
            "Economic fact resolution is pure domain logic (no persistence)."
        )

    monkeypatch.setattr(aqorath.core, "post_entry", forbidden_post_entry)

    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )

    # Resolver el hecho. Si intenta persistir o usar core, fallará.
    proposal = resolve_economic_fact(fact)

    # La propuesta es un objeto en memoria, no una entrada persistida.
    assert proposal is not None
    assert isinstance(proposal.lines, (list, tuple))
    assert len(proposal.lines) == 2

    # ========================================================================
    # AST-based verification: economic_facts must not import prohibited families
    # ========================================================================

    import aqorath.economic_facts as ef_module
    from pathlib import Path

    # Obtener ruta y fuente del módulo
    try:
        ef_file = Path(ef_module.__file__)
        module_source = ef_file.read_text()
    except (AttributeError, OSError) as e:
        raise AssertionError(
            f"Cannot read economic_facts module source for AST inspection: {e}. "
            "Modules must be inspectable."
        )

    # Parsear AST
    try:
        tree = ast.parse(module_source)
    except SyntaxError as e:
        raise AssertionError(
            f"economic_facts module has syntax errors: {e}. "
            "Cannot verify import contracts."
        )

    # Usar el mismo detector que probamos arriba
    abs_imports, from_imports = _parse_imports_from_source(module_source)

    assert not _detects_forbidden_domain_import(abs_imports, from_imports), (
        "economic_facts module must not import prohibited families "
        "(aqorath.core, aqorath.storage, sqlite3, sqlalchemy, sqlmodel). "
        "Resolution is pure domain logic."
    )
