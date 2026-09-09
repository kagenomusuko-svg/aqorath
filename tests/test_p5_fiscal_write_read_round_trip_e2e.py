"""Phase 5AJ.1 — full fiscal write/read round-trip acceptance contract."""

from dataclasses import fields
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlmodel import Session, select


def _initialize_canonical_db(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.models import Account

    db_path = tmp_path / "fiscal-write-read-round-trip.db"
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

    return engine


def _assert_exact_provenance_round_trip(expected, loaded):
    for field in fields(expected):
        expected_value = getattr(expected, field.name)
        loaded_value = getattr(loaded, field.name)
        if isinstance(expected_value, Decimal):
            assert isinstance(loaded_value, Decimal)
            assert loaded_value.as_tuple() == expected_value.as_tuple(), field.name
        else:
            assert loaded_value == expected_value, field.name


def test_economic_fact_round_trips_through_atomic_audited_sqlite_and_read_restores_confirmed_fiscal_truth_without_recalculation(
    tmp_path,
    monkeypatch,
):
    import aqorath.application as application
    import aqorath.fiscal_calculation as fiscal_calculation
    import aqorath.fiscal_posting_audit as fiscal_posting_audit
    import aqorath.fiscal_rounding as fiscal_rounding
    import aqorath.fiscal_rule_data_mx as data
    import aqorath.fiscalized_account_resolution as fiscalized_account_resolution
    from aqorath.economic_facts import EconomicFact
    from aqorath.fiscal_rounding import FiscalRoundingPolicy
    from aqorath.fiscal_rule_install import install_fiscal_rule_set
    from aqorath.models import FiscalPostingAuditRecord, JournalEntry, JournalLine

    engine = _initialize_canonical_db(tmp_path, monkeypatch)
    try:
        with Session(engine) as session:
            install_fiscal_rule_set(session, data.MX_GENERAL_COMMERCIAL_IVA)

            fact = EconomicFact("sale", Decimal("100.00"), "cash")
            accounting_resolution = application.resolve_economic_fact_with_provenance(fact)
            applicability = application.declare_fiscal_rate_applicability(
                fact,
                date(2026, 8, 27),
                data.MX_GENERAL_COMMERCIAL_IVA.context,
                "iva.general_rate",
                Decimal("100.00"),
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
                    "EXPLICIT:5AJ-E2E",
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
                "net_before_fiscal",
                "cash",
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
            confirmation_snapshot = application.prepare_fiscalized_confirmation(resolved)
            confirmed = application.confirm_fiscalized_snapshot(confirmation_snapshot)
            instruction = application.create_fiscalized_posting_instruction(
                confirmed,
                "reject_zero_fiscal_line",
            )

        result = application.execute_fiscalized_posting_with_audit(instruction)
        assert result == {"ok": True, "entry_id": result["entry_id"]}
        assert isinstance(result["entry_id"], int)

        with Session(engine) as session:
            entries = session.exec(select(JournalEntry)).all()
            lines = session.exec(select(JournalLine)).all()
            audits = session.exec(select(FiscalPostingAuditRecord)).all()

            assert len(entries) == 1
            assert len(lines) == 3
            assert len(audits) == 1
            assert entries[0].id == result["entry_id"]
            assert audits[0].entry_id == result["entry_id"]

            by_code = {line.account_code: line for line in lines}
            assert set(by_code) == {"1102", "4201", "2103"}
            assert (by_code["1102"].debit, by_code["1102"].credit) == ("116.00", "0")
            assert (by_code["4201"].debit, by_code["4201"].credit) == ("0", "100.00")
            assert (by_code["2103"].debit, by_code["2103"].credit) == ("0", "16.00")

            def forbidden_reconstruction(*args, **kwargs):
                raise AssertionError(
                    "persisted fiscal audit read must not recalculate, reround, "
                    "re-resolve accounts, or rebuild audit truth"
                )

            monkeypatch.setattr(
                fiscal_calculation,
                "calculate_fiscal_rate_amount",
                forbidden_reconstruction,
            )
            monkeypatch.setattr(
                fiscal_rounding,
                "round_confirmed_fiscal_amount",
                forbidden_reconstruction,
            )
            monkeypatch.setattr(
                fiscalized_account_resolution,
                "resolve_fiscalized_proposal_accounts",
                forbidden_reconstruction,
            )
            monkeypatch.setattr(
                fiscal_posting_audit,
                "create_fiscal_posting_audit_snapshot",
                forbidden_reconstruction,
            )

            loaded = application.load_fiscal_posting_audit_snapshot(
                session,
                result["entry_id"],
            )

        assert loaded.description == confirmation_snapshot.explanation
        assert loaded.zero_fiscal_line_policy == "reject_zero_fiscal_line"
        assert loaded.omitted_zero_fiscal_line is None
        _assert_exact_provenance_round_trip(
            confirmation_snapshot.provenance,
            loaded.provenance,
        )

        assert loaded.provenance.fact_amount.as_tuple() == Decimal("100.00").as_tuple()
        assert loaded.provenance.base.as_tuple() == Decimal("100.00").as_tuple()
        assert loaded.provenance.rate.as_tuple() == Decimal("0.16").as_tuple()
        assert loaded.provenance.exact_fiscal_amount.as_tuple() == Decimal("16.0000").as_tuple()
        assert loaded.provenance.rounding_quantizer.as_tuple() == Decimal("0.01").as_tuple()
        assert loaded.provenance.rounded_fiscal_amount.as_tuple() == Decimal("16.00").as_tuple()
    finally:
        engine.dispose()
