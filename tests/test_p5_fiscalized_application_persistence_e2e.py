"""Phase 5AC — fiscalized application pipeline persists exact confirmed truth to SQLite."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlmodel import Session, select


def _initialize_canonical_db(tmp_path, monkeypatch, filename):
    import aqorath.storage as storage
    from aqorath.models import Account

    db_path = tmp_path / filename
    monkeypatch.setenv("AQORATH_DB", str(db_path))
    engine = storage.init_db(str(db_path), create_tables=True)
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)

    with Session(engine) as session:
        accounts = (
            Account(code="1102", name="Caja chica", nature="DEBIT"),
            Account(
                code="4201",
                name="Venta de productos elaborados",
                nature="CREDIT",
            ),
            Account(code="2103", name="Impuestos por pagar", nature="CREDIT"),
        )
        session.add_all(accounts)
        session.commit()
        for account in accounts:
            session.refresh(account)

    return engine


def _build_confirmed_instruction(
    session,
    *,
    fact_amount,
    fiscal_base,
    amount_basis,
    adjustment_role,
):
    import aqorath.application as application
    import aqorath.fiscal_rule_data_mx as data
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_rounding import FiscalRoundingPolicy
    from aqorath.fiscal_rule_install import install_fiscal_rule_set

    install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)

    fact = EconomicFact("sale", Decimal(fact_amount), "cash")
    accounting_resolution = application.resolve_economic_fact_with_provenance(fact)

    applicability = application.declare_fiscal_rate_applicability(
        fact,
        date(2026, 8, 27),
        data.MX_GENERAL_COMMERCIAL_IVA.context,
        "iva.general_rate",
        Decimal(fiscal_base),
    )
    calculated = application.calculate_declared_fiscal_rate(session, applicability)
    fiscal_snapshot = application.prepare_fiscal_confirmation(calculated)
    confirmed_fiscal = application.confirm_fiscal_treatment(fiscal_snapshot)

    rounded = application.round_confirmed_fiscal_amount(
        confirmed_fiscal,
        FiscalRoundingPolicy(
            "two-decimals",
            Decimal("0.01"),
            ROUND_HALF_UP,
            "EXPLICIT:5AC-E2E",
        ),
    )
    monetary_snapshot = application.prepare_fiscal_monetary_confirmation(rounded)
    confirmed_monetary = application.confirm_fiscal_monetary_amount(monetary_snapshot)

    treatment = application.declare_fiscal_accounting_treatment(
        confirmed_monetary,
        "tax_payable",
        "credit",
    )
    effect = application.build_fiscal_accounting_effect(treatment)

    composition = application.declare_fiscal_economic_composition(
        accounting_resolution,
        effect,
        amount_basis,
        adjustment_role,
    )
    fiscalized = application.compose_fiscal_economic_accounting(composition)
    resolved = application.resolve_fiscalized_proposal_accounts(
        session,
        fiscalized,
        {
            "cash": "1102",
            "sales_revenue": "4201",
            "tax_payable": "2103",
        },
    )
    snapshot = application.prepare_fiscalized_confirmation(resolved)
    confirmed = application.confirm_fiscalized_snapshot(snapshot)
    instruction = application.create_fiscalized_posting_instruction(
        confirmed,
        "reject_zero_fiscal_line",
    )
    return snapshot, instruction


def _assert_persisted_sale(engine, snapshot, result):
    from aqorath.models import JournalEntry, JournalLine

    assert isinstance(result, dict)
    assert result.get("ok") is True
    assert isinstance(result.get("entry_id"), int)

    with Session(engine) as session:
        entries = session.exec(select(JournalEntry)).all()
        lines = session.exec(select(JournalLine)).all()

        assert len(entries) == 1
        assert len(lines) == 3
        entry = entries[0]
        assert entry.id == result["entry_id"]
        assert entry.concept == snapshot.explanation
        assert all(line.entry_id == entry.id for line in lines)

        by_code = {line.account_code: line for line in lines}
        assert set(by_code) == {"1102", "4201", "2103"}

        cash = by_code["1102"]
        assert Decimal(str(cash.debit)) == Decimal("116.00")
        assert Decimal(str(cash.credit)) == Decimal("0")

        sales = by_code["4201"]
        assert Decimal(str(sales.debit)) == Decimal("0")
        assert Decimal(str(sales.credit)) == Decimal("100.00")

        tax = by_code["2103"]
        assert Decimal(str(tax.debit)) == Decimal("0")
        assert Decimal(str(tax.credit)) == Decimal("16.00")


def test_net_before_fiscal_application_pipeline_persists_exact_three_line_sale_to_canonical_sqlite(
    tmp_path,
    monkeypatch,
):
    import aqorath.application as application

    engine = _initialize_canonical_db(tmp_path, monkeypatch, "fiscalized-net-e2e.db")
    try:
        with Session(engine) as session:
            snapshot, instruction = _build_confirmed_instruction(
                session,
                fact_amount="100.00",
                fiscal_base="100.00",
                amount_basis="net_before_fiscal",
                adjustment_role="cash",
            )

        assert snapshot.provenance.amount_basis == "net_before_fiscal"
        assert snapshot.provenance.fact_amount.as_tuple() == Decimal("100.00").as_tuple()
        assert snapshot.provenance.rounded_fiscal_amount.as_tuple() == Decimal("16.00").as_tuple()
        assert [(line.account_code, line.side, line.amount) for line in snapshot.lines] == [
            ("1102", "debit", Decimal("116.00")),
            ("4201", "credit", Decimal("100.00")),
            ("2103", "credit", Decimal("16.00")),
        ]

        result = application.execute_fiscalized_posting_instruction(instruction)
        _assert_persisted_sale(engine, snapshot, result)
    finally:
        engine.dispose()


def test_gross_including_fiscal_application_pipeline_persists_same_professional_truth_to_canonical_sqlite(
    tmp_path,
    monkeypatch,
):
    import aqorath.application as application

    engine = _initialize_canonical_db(tmp_path, monkeypatch, "fiscalized-gross-e2e.db")
    try:
        with Session(engine) as session:
            snapshot, instruction = _build_confirmed_instruction(
                session,
                fact_amount="116.00",
                fiscal_base="100.00",
                amount_basis="gross_including_fiscal",
                adjustment_role="sales_revenue",
            )

        assert snapshot.provenance.amount_basis == "gross_including_fiscal"
        assert snapshot.provenance.fact_amount.as_tuple() == Decimal("116.00").as_tuple()
        assert snapshot.provenance.base.as_tuple() == Decimal("100.00").as_tuple()
        assert snapshot.provenance.rounded_fiscal_amount.as_tuple() == Decimal("16.00").as_tuple()
        assert [(line.account_code, line.side, line.amount) for line in snapshot.lines] == [
            ("1102", "debit", Decimal("116.00")),
            ("4201", "credit", Decimal("100.00")),
            ("2103", "credit", Decimal("16.00")),
        ]

        result = application.execute_fiscalized_posting_instruction(instruction)
        _assert_persisted_sale(engine, snapshot, result)
    finally:
        engine.dispose()
