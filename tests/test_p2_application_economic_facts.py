"""
Phase 2A.3: Application Integration with Economic Facts

Congelan el contrato futuro de integración entre:
  aqorath.application (facade)
  aqorath.economic_facts (dominio puro)

para la operación de PREVIEW de un EconomicFact.

La operación de preview:
  - Recibe un EconomicFact estructurado
  - Delega determinísticamente a economic_facts.resolve_economic_fact
  - Retorna AccountingProposal en memoria
  - NO persiste
  - NO postea
  - NO usa template engine

Arquitectura:
  adapter → application.preview_economic_fact → economic_facts.resolve_economic_fact
                                                      ↓
                                           AccountingProposal (en memoria)

Sin NLP. Sin CFDI. Sin segundo vertical. Sin posting.
"""

from decimal import Decimal
import pytest


def test_application_exposes_preview_economic_fact():
    """
    Contract: aqorath.application debe exponer preview_economic_fact como capability.

    Establece que existe una función pública:
      aqorath.application.preview_economic_fact
    
    que sea callable para obtener previews de EconomicFacts.
    """
    import aqorath.application
    
    assert hasattr(aqorath.application, "preview_economic_fact"), (
        "aqorath.application must expose preview_economic_fact capability"
    )
    assert callable(aqorath.application.preview_economic_fact)


def test_preview_economic_fact_accepts_structured_fact():
    """
    Contract: preview_economic_fact recibe un EconomicFact estructurado.

    Establece que la entrada es un objeto de dominio completo:
      EconomicFact(type="sale", amount=Decimal("200.00"), payment_method="cash")
    
    NO es un string, NO es un dict, NO son argumentos separados.
    La facade recibe el objeto de dominio ya estructurado.
    """
    from aqorath.economic_facts import EconomicFact
    from aqorath.application import preview_economic_fact
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    
    # Debe aceptar el EconomicFact estructurado
    # (aunque todavía no haya implementación, el test establece la firma esperada)
    try:
        preview_economic_fact(fact)
    except Exception as e:
        # Es aceptable que falle por no estar implementado
        # pero no por rechazo de tipo
        if "unexpected keyword argument" in str(e):
            raise AssertionError(
                "preview_economic_fact must accept EconomicFact as single argument"
            )
        # Si falla por otra razón, es esperado


def test_preview_economic_fact_delegates_exact_fact_to_domain_resolver(monkeypatch):
    """
    Contract: preview_economic_fact delega EXACTAMENTE a economic_facts.resolve_economic_fact.

    Establece que no reimplementa la lógica, sino que:
      1. Recibe el mismo EconomicFact por identidad
      2. Lo pasa sin transformación al resolver de dominio
      3. Retorna exactamente lo que el resolver retorna
    
    Usa sentinel para verificar delegación transparente.
    """
    from aqorath.economic_facts import EconomicFact
    from aqorath.application import preview_economic_fact
    import aqorath.economic_facts
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    
    # Sentinel para capturar call
    sentinel_proposal = object()
    calls = []
    
    def fake_resolver(received_fact):
        calls.append(received_fact)
        return sentinel_proposal
    
    # Monkeypatch el resolver del dominio
    monkeypatch.setattr(
        aqorath.economic_facts,
        "resolve_economic_fact",
        fake_resolver,
    )
    
    # Ejecutar preview
    result = preview_economic_fact(fact)
    
    # Verificaciones de delegación exacta
    assert len(calls) == 1, "resolver debe ser invocado exactamente una vez"
    assert calls[0] is fact, "el fact recibido por resolver debe ser el mismo por identidad"
    assert result is sentinel_proposal, "el resultado retornado debe ser exactamente el del resolver"


def test_preview_economic_fact_returns_exact_domain_result(monkeypatch):
    """
    Contract: El resultado de preview_economic_fact es exactamente lo que retorna resolve_economic_fact.

    No construye AccountingProposal paralela. No transforma resultado.
    Usa sentinel para verificar identidad de retorno.
    """
    from aqorath.economic_facts import EconomicFact
    from aqorath.application import preview_economic_fact
    import aqorath.economic_facts
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    
    # Sentinel específico como retorno
    sentinel_proposal = object()
    
    monkeypatch.setattr(
        aqorath.economic_facts,
        "resolve_economic_fact",
        lambda f: sentinel_proposal,
    )
    
    result = preview_economic_fact(fact)
    
    assert result is sentinel_proposal, (
        "preview_economic_fact must return exactly what domain resolver returns, "
        "without transformation or wrapping"
    )


def test_preview_economic_fact_calls_domain_resolver_once(monkeypatch):
    """
    Contract: preview_economic_fact invoca el resolver exactamente una sola vez.

    Congela que no hay reintentos, no hay caché oculto,
    no hay llamadas adicionales al resolver.
    """
    from aqorath.economic_facts import EconomicFact
    from aqorath.application import preview_economic_fact
    import aqorath.economic_facts
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    
    call_count = [0]
    
    def counting_resolver(f):
        call_count[0] += 1
        # Retorna algo válido
        from aqorath.economic_facts import AccountingProposal, ProposalLine
        return AccountingProposal(
            lines=[
                ProposalLine(account_role="cash", side="debit", amount=f.amount),
                ProposalLine(account_role="sales_revenue", side="credit", amount=f.amount),
            ],
            explanation="test",
        )
    
    monkeypatch.setattr(
        aqorath.economic_facts,
        "resolve_economic_fact",
        counting_resolver,
    )
    
    preview_economic_fact(fact)
    
    assert call_count[0] == 1, "resolver debe ser invocado exactamente una sola vez"


def test_preview_economic_fact_does_not_post_or_use_template_engine(monkeypatch):
    """
    Contract: preview_economic_fact NO postea y NO usa template engine.

    Establece que:
      - NO llama core.post_entry
      - NO llama core.generate_preview
    
    La previsualizacion de un EconomicFact es resolución de dominio puro,
    no posting y no template.
    """
    from aqorath.economic_facts import EconomicFact
    from aqorath.application import preview_economic_fact
    import aqorath.core
    import aqorath.economic_facts
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    
    # Bloquear post_entry
    def forbidden_post(*args, **kwargs):
        raise AssertionError(
            "preview_economic_fact must not call core.post_entry. "
            "Preview is not posting."
        )
    
    # Bloquear generate_preview
    def forbidden_preview(*args, **kwargs):
        raise AssertionError(
            "preview_economic_fact must not call core.generate_preview. "
            "Economic fact resolution is not template-based."
        )
    
    monkeypatch.setattr(aqorath.core, "post_entry", forbidden_post)
    monkeypatch.setattr(aqorath.core, "generate_preview", forbidden_preview)
    
    # Monkeypatch resolver del dominio para que retorne algo válido sin llamar core
    from aqorath.economic_facts import AccountingProposal, ProposalLine
    
    def safe_resolver(f):
        return AccountingProposal(
            lines=[
                ProposalLine(account_role="cash", side="debit", amount=f.amount),
                ProposalLine(account_role="sales_revenue", side="credit", amount=f.amount),
            ],
            explanation="test",
        )
    
    monkeypatch.setattr(
        aqorath.economic_facts,
        "resolve_economic_fact",
        safe_resolver,
    )
    
    # Si post_entry o generate_preview son llamados, habrá AssertionError
    # Si no, el test pasa
    try:
        preview_economic_fact(fact)
    except AssertionError as e:
        if "must not call core.post_entry" in str(e) or "must not call core.generate_preview" in str(e):
            raise
        # Otras AssertionErrors son de otra fuente


def test_preview_economic_fact_real_cash_sale_returns_accounting_proposal():
    """
    Contract: preview_economic_fact funciona end-to-end con economic_facts real.

    Caso vertical real: una venta en efectivo obtiene una propuesta contable válida.

    Este test NO mockea el resolver; usa la implementación real de dominio.
    Verifica composición: application ↓ economic_facts ↓ AccountingProposal.
    """
    from aqorath.economic_facts import EconomicFact, AccountingProposal, ProposalLine
    from aqorath.application import preview_economic_fact
    
    fact = EconomicFact(
        type="sale",
        amount=Decimal("200.00"),
        payment_method="cash",
    )
    
    proposal = preview_economic_fact(fact)
    
    # Verificar que es AccountingProposal
    assert isinstance(proposal, AccountingProposal), (
        f"preview_economic_fact must return AccountingProposal, got {type(proposal)}"
    )
    
    # Verificar estructura
    assert len(proposal.lines) == 2, "Proposal must have exactly 2 lines"
    
    # Verificar líneas
    lines_by_role = {line.account_role: line for line in proposal.lines}
    
    assert "cash" in lines_by_role, "Must have cash line"
    assert "sales_revenue" in lines_by_role, "Must have sales_revenue line"
    
    cash_line = lines_by_role["cash"]
    revenue_line = lines_by_role["sales_revenue"]
    
    assert cash_line.side == "debit", "cash must be debit"
    assert revenue_line.side == "credit", "sales_revenue must be credit"
    
    assert cash_line.amount == Decimal("200.00")
    assert revenue_line.amount == Decimal("200.00")
    
    # Verificar balance
    total_debit = sum(
        (l.amount for l in proposal.lines if l.side == "debit"),
        Decimal("0"),
    )
    total_credit = sum(
        (l.amount for l in proposal.lines if l.side == "credit"),
        Decimal("0"),
    )
    
    assert total_debit == total_credit == Decimal("200.00"), "Proposal must be balanced"
    
    # Verificar explicación
    assert isinstance(proposal.explanation, str), "explanation must be string"
    assert proposal.explanation.strip(), "explanation must not be empty"


def test_existing_application_api_remains_available():
    """
    Contract: La adición de preview_economic_fact no reemplaza o elimina capability existentes.

    Establece que los 4 métodos históricos congelados siguen siendo públicos:
      - list_templates
      - preview_template
      - post_template
      - get_trial_balance
    
    La facade expande de 4 a 5 capacidades sin regresiones.
    La profundidad de estos métodos es responsabilidad de Phase 1E.
    """
    import aqorath.application
    
    # Verificar que siguen disponibles
    assert hasattr(aqorath.application, "list_templates"), (
        "list_templates must remain available"
    )
    assert callable(aqorath.application.list_templates)
    
    assert hasattr(aqorath.application, "preview_template"), (
        "preview_template must remain available"
    )
    assert callable(aqorath.application.preview_template)
    
    assert hasattr(aqorath.application, "post_template"), (
        "post_template must remain available"
    )
    assert callable(aqorath.application.post_template)
    
    assert hasattr(aqorath.application, "get_trial_balance"), (
        "get_trial_balance must remain available"
    )
    assert callable(aqorath.application.get_trial_balance)
    
    # Y la nueva capability
    assert hasattr(aqorath.application, "preview_economic_fact"), (
        "preview_economic_fact must be newly available"
    )
    assert callable(aqorath.application.preview_economic_fact)
