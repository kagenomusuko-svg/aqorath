"""Phase 5AK.1 — immutable multiple-fiscal-effects contracts, tests only."""

import sqlite3
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select


def _accounting(*, fact_amount="100.00"):
    from aqorath.economic_fact_accounting_provenance import (
        resolve_economic_fact_with_provenance,
    )
    from aqorath.economic_facts import EconomicFact

    return resolve_economic_fact_with_provenance(
        EconomicFact("sale", Decimal(fact_amount), "cash")
    )


def _effect(
    accounting,
    *,
    rule_key,
    rate,
    exact_amount,
    rounded_amount,
    role,
    side,
    source_ref,
    fact_amount=None,
):
    from aqorath.fiscal_accounting_effect import build_fiscal_accounting_effect
    from aqorath.fiscal_accounting_treatment import declare_fiscal_accounting_treatment
    from aqorath.fiscal_monetary_confirmation import (
        ConfirmedFiscalMonetaryAmount,
        FiscalMonetaryConfirmationSnapshot,
    )

    snapshot = FiscalMonetaryConfirmationSnapshot(
        fact_type="sale",
        fact_amount=(
            accounting.fact.amount
            if fact_amount is None
            else Decimal(fact_amount)
        ),
        payment_method="cash",
        effective_date=date(2026, 8, 27),
        jurisdiction="MX",
        regime="general",
        entity_type="commercial",
        rule_key=rule_key,
        base=Decimal("100.00"),
        rate=Decimal(rate),
        unit="rate",
        rule_effective_from=date(2010, 1, 1),
        rule_effective_to=None,
        rule_source_ref=source_ref,
        exact_amount=Decimal(exact_amount),
        rounding_policy_key="two-decimals",
        rounding_quantizer=Decimal("0.01"),
        rounding_mode="ROUND_HALF_UP",
        rounding_source_ref=f"ROUND:{rule_key}",
        rounded_amount=Decimal(rounded_amount),
    )
    confirmed = ConfirmedFiscalMonetaryAmount(snapshot)
    treatment = declare_fiscal_accounting_treatment(confirmed, role, side)
    return build_fiscal_accounting_effect(treatment)


def _effects(accounting):
    return (
        _effect(
            accounting,
            rule_key="iva.general_rate",
            rate="0.16",
            exact_amount="16.0000",
            rounded_amount="16.00",
            role="vat_payable",
            side="credit",
            source_ref="TEST:IVA-TRASLADADO",
        ),
        _effect(
            accounting,
            rule_key="iva.withholding",
            rate="0.10666666",
            exact_amount="10.666666",
            rounded_amount="10.67",
            role="vat_withheld_receivable",
            side="debit",
            source_ref="TEST:IVA-RETENIDO",
        ),
        _effect(
            accounting,
            rule_key="isr.withholding",
            rate="0.0125",
            exact_amount="1.2500",
            rounded_amount="1.25",
            role="isr_withheld_receivable",
            side="debit",
            source_ref="TEST:ISR-RETENIDO",
        ),
    )


def _declaration(
    *,
    fact_amount="100.00",
    basis="net_before_fiscal",
    adjustment_role="cash",
):
    from aqorath.fiscal_economic_composition import (
        declare_fiscal_economic_composition,
    )

    accounting = _accounting(fact_amount=fact_amount)
    effects = _effects(accounting)
    return declare_fiscal_economic_composition(
        accounting,
        effects,
        basis,
        adjustment_role,
    )


def _resolved_multi(monkeypatch):
    import aqorath.catalog as catalog
    from aqorath.fiscalized_account_resolution import (
        resolve_fiscalized_proposal_accounts,
    )
    from aqorath.fiscalized_accounting_proposal import (
        compose_fiscal_economic_accounting,
    )

    declaration = _declaration()
    fiscalized = compose_fiscal_economic_accounting(declaration)
    accounts = {
        "CASH": type("Account", (), {"id": 1, "code": "CASH", "name": "Caja"})(),
        "SALES": type("Account", (), {"id": 2, "code": "SALES", "name": "Ventas"})(),
        "VAT-P": type("Account", (), {"id": 3, "code": "VAT-P", "name": "IVA por pagar"})(),
        "VAT-W": type("Account", (), {"id": 4, "code": "VAT-W", "name": "IVA retenido por cobrar"})(),
        "ISR-W": type("Account", (), {"id": 5, "code": "ISR-W", "name": "ISR retenido por cobrar"})(),
    }
    monkeypatch.setattr(
        catalog,
        "resolve_account_by_code",
        lambda session, code: accounts[code],
    )
    return resolve_fiscalized_proposal_accounts(
        object(),
        fiscalized,
        {
            "cash": "CASH",
            "sales_revenue": "SALES",
            "vat_payable": "VAT-P",
            "vat_withheld_receivable": "VAT-W",
            "isr_withheld_receivable": "ISR-W",
        },
    )


def _confirmed_multi(monkeypatch):
    from aqorath.fiscalized_confirmation import (
        confirm_fiscalized_snapshot,
        create_fiscalized_confirmation_snapshot,
    )

    snapshot = create_fiscalized_confirmation_snapshot(_resolved_multi(monkeypatch))
    return snapshot, confirm_fiscalized_snapshot(snapshot)


def test_composition_accepts_ordered_immutable_effect_tuple_without_breaking_single_effect_contract():
    from aqorath.fiscal_economic_composition import (
        FiscalEconomicCompositionDeclaration,
        declare_fiscal_economic_composition,
    )

    accounting = _accounting()
    effects = _effects(accounting)
    declaration = declare_fiscal_economic_composition(
        accounting,
        effects,
        "net_before_fiscal",
        "cash",
    )

    assert isinstance(declaration, FiscalEconomicCompositionDeclaration)
    assert declaration.accounting_resolution is accounting
    assert declaration.fiscal_effects is effects
    assert declaration.fiscal_effect == effects
    assert tuple(effect.line.account_role for effect in declaration.fiscal_effects) == (
        "vat_payable",
        "vat_withheld_receivable",
        "isr_withheld_receivable",
    )
    with pytest.raises(TypeError):
        declaration.fiscal_effects[0] = declaration.fiscal_effects[1]
    with pytest.raises(FrozenInstanceError):
        declaration.fiscal_effect = effects[:1]


def test_composition_rejects_mutable_empty_malformed_or_cross_fact_effect_collections():
    from aqorath.fiscal_economic_composition import declare_fiscal_economic_composition

    accounting = _accounting()
    effects = _effects(accounting)

    for invalid in ([], (), (effects[0], object())):
        with pytest.raises((TypeError, ValueError)):
            declare_fiscal_economic_composition(
                accounting,
                invalid,
                "net_before_fiscal",
                "cash",
            )

    mismatched = _effect(
        accounting,
        rule_key="isr.withholding",
        rate="0.0125",
        exact_amount="1.2500",
        rounded_amount="1.25",
        role="isr_withheld_receivable",
        side="debit",
        source_ref="TEST:MISMATCH",
        fact_amount="99.00",
    )
    with pytest.raises(ValueError, match="fact_amount|economic|fiscal"):
        declare_fiscal_economic_composition(
            accounting,
            (effects[0], effects[1], mismatched),
            "net_before_fiscal",
            "cash",
        )


def test_net_before_fiscal_composes_iva_and_two_withholdings_as_exact_balanced_five_line_truth():
    from aqorath.fiscalized_accounting_proposal import (
        compose_fiscal_economic_accounting,
    )

    proposal = compose_fiscal_economic_accounting(_declaration())
    assert tuple((line.account_role, line.side, line.amount) for line in proposal.lines) == (
        ("cash", "debit", Decimal("104.08")),
        ("sales_revenue", "credit", Decimal("100.00")),
        ("vat_payable", "credit", Decimal("16.00")),
        ("vat_withheld_receivable", "debit", Decimal("10.67")),
        ("isr_withheld_receivable", "debit", Decimal("1.25")),
    )
    total_debit = sum(
        (line.amount for line in proposal.lines if line.side == "debit"),
        Decimal("0"),
    )
    total_credit = sum(
        (line.amount for line in proposal.lines if line.side == "credit"),
        Decimal("0"),
    )
    assert total_debit == total_credit == Decimal("116.00")
    assert "fiscal_effects=[" in proposal.explanation


def test_gross_including_fiscal_uses_aggregate_effect_direction_and_reaches_same_truth():
    from aqorath.fiscalized_accounting_proposal import (
        compose_fiscal_economic_accounting,
    )

    proposal = compose_fiscal_economic_accounting(
        _declaration(
            fact_amount="104.08",
            basis="gross_including_fiscal",
            adjustment_role="sales_revenue",
        )
    )
    assert tuple((line.account_role, line.side, line.amount) for line in proposal.lines) == (
        ("cash", "debit", Decimal("104.08")),
        ("sales_revenue", "credit", Decimal("100.00")),
        ("vat_payable", "credit", Decimal("16.00")),
        ("vat_withheld_receivable", "debit", Decimal("10.67")),
        ("isr_withheld_receivable", "debit", Decimal("1.25")),
    )


def test_confirmation_preserves_all_effect_provenance_in_order_and_matches_trailing_fiscal_lines(monkeypatch):
    from aqorath.fiscalized_confirmation import create_fiscalized_confirmation_snapshot

    snapshot = create_fiscalized_confirmation_snapshot(_resolved_multi(monkeypatch))
    effects = snapshot.provenance.fiscal_effects

    assert isinstance(effects, tuple)
    assert len(effects) == 3
    assert tuple(effect.rule_key for effect in effects) == (
        "iva.general_rate",
        "iva.withholding",
        "isr.withholding",
    )
    assert tuple(effect.fiscal_role for effect in effects) == (
        "vat_payable",
        "vat_withheld_receivable",
        "isr_withheld_receivable",
    )
    assert effects[0].exact_fiscal_amount.as_tuple() == Decimal("16.0000").as_tuple()
    assert effects[1].exact_fiscal_amount.as_tuple() == Decimal("10.666666").as_tuple()
    assert effects[1].rounded_fiscal_amount.as_tuple() == Decimal("10.67").as_tuple()
    assert effects[2].exact_fiscal_amount.as_tuple() == Decimal("1.2500").as_tuple()
    assert snapshot.provenance.rule_key == effects[0].rule_key
    assert snapshot.provenance.fiscal_role == effects[0].fiscal_role

    trailing = snapshot.lines[-len(effects):]
    assert tuple((line.account_role, line.side, line.amount) for line in trailing) == tuple(
        (effect.fiscal_role, effect.fiscal_side, effect.rounded_fiscal_amount)
        for effect in effects
    )


def test_multi_effect_posting_instruction_preserves_all_confirmed_positive_lines_and_balance(monkeypatch):
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    snapshot, confirmed = _confirmed_multi(monkeypatch)
    instruction = create_fiscalized_posting_instruction(
        confirmed,
        "reject_zero_fiscal_line",
    )

    assert instruction.confirmed_proposal is confirmed
    assert instruction.description == snapshot.explanation
    assert len(instruction.lines) == 5
    assert tuple(line.account_role for line in instruction.lines) == (
        "cash",
        "sales_revenue",
        "vat_payable",
        "vat_withheld_receivable",
        "isr_withheld_receivable",
    )
    assert sum((line.debit for line in instruction.lines), Decimal("0")) == Decimal("116.00")
    assert sum((line.credit for line in instruction.lines), Decimal("0")) == Decimal("116.00")
    assert instruction.omitted_zero_fiscal_line is None


def test_audit_snapshot_deep_copies_complete_multi_effect_provenance_without_recalculation(monkeypatch):
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_posting_audit as audit
    import aqorath.fiscal_rounding as rounding
    from aqorath.fiscalized_posting import create_fiscalized_posting_instruction

    snapshot, confirmed = _confirmed_multi(monkeypatch)
    instruction = create_fiscalized_posting_instruction(
        confirmed,
        "reject_zero_fiscal_line",
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("multi-effect audit must copy confirmed truth, never recalculate")

    monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", forbidden)
    monkeypatch.setattr(rounding, "round_confirmed_fiscal_amount", forbidden)

    result = audit.create_fiscal_posting_audit_snapshot(instruction)
    assert result.provenance == snapshot.provenance
    assert result.provenance is not snapshot.provenance
    assert result.provenance.fiscal_effects == snapshot.provenance.fiscal_effects
    assert all(
        copied is not source
        for copied, source in zip(
            result.provenance.fiscal_effects,
            snapshot.provenance.fiscal_effects,
        )
    )


def test_schema_additively_ensures_ordered_additional_effect_records_without_bumping_frozen_v4(tmp_path):
    from aqorath import migrations

    db = tmp_path / "multi-effects-additive.db"
    migrations.migrate_database(db)
    assert migrations.CURRENT_SCHEMA_VERSION == 5
    assert migrations.get_schema_version(db) == 5

    conn = sqlite3.connect(str(db))
    try:
        conn.execute("DROP TABLE IF EXISTS fiscalpostingauditeffectrecord")
        conn.commit()
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fiscalpostingauditeffectrecord'"
        ).fetchone() is None
    finally:
        conn.close()

    result = migrations.migrate_database(db)
    assert result["to_version"] == 5
    assert migrations.get_schema_version(db) == 5

    conn = sqlite3.connect(str(db))
    try:
        columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(fiscalpostingauditeffectrecord)")
        }
        assert columns
        assert "audit_record_id" in columns
        assert "position" in columns
        assert "rule_key" in columns
        assert "exact_fiscal_amount" in columns
        assert "rounded_fiscal_amount" in columns
        assert "fiscal_role" in columns
        assert "fiscal_side" in columns
        for name in (
            "base",
            "rate",
            "exact_fiscal_amount",
            "rounding_quantizer",
            "rounded_fiscal_amount",
        ):
            assert "REAL" not in columns[name].upper()
            assert "FLOAT" not in columns[name].upper()
    finally:
        conn.close()


def test_atomic_persistence_and_read_round_trip_three_effects_exactly_without_recalculation(
    tmp_path,
    monkeypatch,
):
    import aqorath.application as application
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_rounding as rounding
    import aqorath.storage as storage
    from aqorath.fiscalized_account_resolution import resolve_fiscalized_proposal_accounts
    from aqorath.fiscalized_accounting_proposal import compose_fiscal_economic_accounting
    from aqorath.models import (
        Account,
        FiscalPostingAuditEffectRecord,
        FiscalPostingAuditRecord,
        JournalEntry,
        JournalLine,
    )

    db = tmp_path / "multi-effects-round-trip.db"
    monkeypatch.setenv("AQORATH_DB", str(db))
    engine = storage.init_db(str(db), create_tables=True)
    from period_fixtures import seed_engine_calendar
    seed_engine_calendar(engine)
    try:
        with Session(engine) as session:
            accounts = (
                Account(code="1102", name="Caja chica", nature="DEBIT"),
                Account(code="4201", name="Venta de productos elaborados", nature="CREDIT"),
                Account(code="2103", name="Impuestos por pagar", nature="CREDIT"),
                Account(code="1103", name="Clientes", nature="DEBIT"),
                Account(code="1105", name="Anticipos a proveedores", nature="DEBIT"),
            )
            session.add_all(accounts)
            session.commit()

            declaration = _declaration()
            fiscalized = compose_fiscal_economic_accounting(declaration)
            resolved = resolve_fiscalized_proposal_accounts(
                session,
                fiscalized,
                {
                    "cash": "1102",
                    "sales_revenue": "4201",
                    "vat_payable": "2103",
                    "vat_withheld_receivable": "1103",
                    "isr_withheld_receivable": "1105",
                },
            )
            confirmation = application.prepare_fiscalized_confirmation(resolved)
            confirmed = application.confirm_fiscalized_snapshot(confirmation)
            instruction = application.create_fiscalized_posting_instruction(
                confirmed,
                "reject_zero_fiscal_line",
            )

        result = application.execute_fiscalized_posting_with_audit(instruction)
        assert result["ok"] is True

        with Session(engine) as session:
            entries = session.exec(select(JournalEntry)).all()
            lines = session.exec(select(JournalLine)).all()
            audits = session.exec(select(FiscalPostingAuditRecord)).all()
            additional = session.exec(
                select(FiscalPostingAuditEffectRecord).order_by(
                    FiscalPostingAuditEffectRecord.position
                )
            ).all()

            assert len(entries) == 1
            assert len(lines) == 5
            assert len(audits) == 1
            assert len(additional) == 2
            assert [record.position for record in additional] == [1, 2]
            assert [record.rule_key for record in additional] == [
                "iva.withholding",
                "isr.withholding",
            ]
            assert additional[0].exact_fiscal_amount == "10.666666"
            assert additional[0].rounded_fiscal_amount == "10.67"
            assert additional[1].exact_fiscal_amount == "1.2500"
            assert additional[1].rounded_fiscal_amount == "1.25"

            def forbidden(*args, **kwargs):
                raise AssertionError("persisted multi-effect read cannot recalculate")

            monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", forbidden)
            monkeypatch.setattr(rounding, "round_confirmed_fiscal_amount", forbidden)
            loaded = application.load_fiscal_posting_audit_snapshot(
                session,
                result["entry_id"],
            )

        expected = confirmation.provenance.fiscal_effects
        actual = loaded.provenance.fiscal_effects
        assert len(actual) == 3
        assert tuple(effect.rule_key for effect in actual) == tuple(
            effect.rule_key for effect in expected
        )
        for left, right in zip(actual, expected):
            assert left.fiscal_role == right.fiscal_role
            assert left.fiscal_side == right.fiscal_side
            assert left.base.as_tuple() == right.base.as_tuple()
            assert left.rate.as_tuple() == right.rate.as_tuple()
            assert left.exact_fiscal_amount.as_tuple() == right.exact_fiscal_amount.as_tuple()
            assert left.rounding_quantizer.as_tuple() == right.rounding_quantizer.as_tuple()
            assert left.rounded_fiscal_amount.as_tuple() == right.rounded_fiscal_amount.as_tuple()
    finally:
        engine.dispose()
