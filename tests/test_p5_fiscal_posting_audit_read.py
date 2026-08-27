"""Phase 5AH.1 — persisted fiscal posting audit read contracts."""

from datetime import date, datetime, timezone
from decimal import Decimal
from inspect import Parameter, signature

import pytest
from sqlmodel import Session


def _assert_signature(fn, names):
    sig = signature(fn)
    assert list(sig.parameters) == names
    for parameter in sig.parameters.values():
        assert parameter.kind is Parameter.POSITIONAL_OR_KEYWORD
        assert parameter.default is Parameter.empty


def _seed(session, *, concept="Venta fiscalizada confirmada", overrides=None):
    from aqorath.models import FiscalPostingAuditRecord, JournalEntry

    entry = JournalEntry(
        date=datetime(2026, 8, 27, tzinfo=timezone.utc),
        concept=concept,
        state="draft",
    )
    session.add(entry)
    session.flush()

    values = {
        "entry_id": entry.id,
        "fact_type": "sale",
        "fact_amount": "100.0000",
        "payment_method": "cash",
        "effective_date": date(2026, 8, 27),
        "jurisdiction": "MX",
        "regime": "general",
        "entity_type": "commercial",
        "rule_key": "iva.general_rate",
        "base": "100.000",
        "rate": "0.1600",
        "unit": "rate",
        "rule_effective_from": date(2010, 1, 1),
        "rule_effective_to": None,
        "rule_source_ref": "CURATED:IVA",
        "exact_fiscal_amount": "16.000",
        "rounding_policy_key": "two-decimals",
        "rounding_quantizer": "0.010",
        "rounding_mode": "ROUND_HALF_UP",
        "rounding_source_ref": "EXPLICIT:5AH",
        "rounded_fiscal_amount": "16.00",
        "amount_basis": "net_before_fiscal",
        "adjustment_role": "cash",
        "fiscal_role": "tax_payable",
        "fiscal_side": "credit",
        "zero_fiscal_line_policy": "reject_zero_fiscal_line",
        "omitted_zero_account_role": None,
        "omitted_zero_account_id": None,
        "omitted_zero_account_code": None,
        "omitted_zero_account_name": None,
        "omitted_zero_side": None,
        "omitted_zero_amount": None,
    }
    if overrides:
        values.update(overrides)
    record = FiscalPostingAuditRecord(**values)
    session.add(record)
    session.commit()
    return entry.id


def _session(tmp_path, monkeypatch, name="audit-read.db"):
    import aqorath.storage as storage

    db = tmp_path / name
    monkeypatch.setenv("AQORATH_DB", str(db))
    engine = storage.init_db(str(db), create_tables=True)
    return engine, Session(engine)


def test_persisted_audit_read_public_contract_and_exact_signature_exist():
    import aqorath.fiscal_posting_audit_read as read

    assert callable(read.load_fiscal_posting_audit_snapshot)
    _assert_signature(read.load_fiscal_posting_audit_snapshot, ["session", "entry_id"])


def test_read_reconstructs_nominal_snapshot_from_exact_entry_and_audit_record(tmp_path, monkeypatch):
    import aqorath.fiscal_posting_audit as audit
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot

    engine, session = _session(tmp_path, monkeypatch)
    try:
        entry_id = _seed(session)
        snapshot = load_fiscal_posting_audit_snapshot(session, entry_id)

        assert isinstance(snapshot, audit.FiscalPostingAuditSnapshot)
        assert snapshot.description == "Venta fiscalizada confirmada"
        assert snapshot.provenance.fact_type == "sale"
        assert snapshot.provenance.payment_method == "cash"
        assert snapshot.provenance.rule_key == "iva.general_rate"
        assert snapshot.provenance.rule_source_ref == "CURATED:IVA"
        assert snapshot.provenance.amount_basis == "net_before_fiscal"
        assert snapshot.provenance.adjustment_role == "cash"
        assert snapshot.provenance.fiscal_role == "tax_payable"
        assert snapshot.provenance.fiscal_side == "credit"
        assert snapshot.zero_fiscal_line_policy == "reject_zero_fiscal_line"
        assert snapshot.omitted_zero_fiscal_line is None
    finally:
        session.close()
        engine.dispose()


def test_read_preserves_exact_decimal_scale_without_float_conversion(tmp_path, monkeypatch):
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot

    engine, session = _session(tmp_path, monkeypatch, "scale.db")
    try:
        entry_id = _seed(session)
        p = load_fiscal_posting_audit_snapshot(session, entry_id).provenance
        assert p.fact_amount.as_tuple() == Decimal("100.0000").as_tuple()
        assert p.base.as_tuple() == Decimal("100.000").as_tuple()
        assert p.rate.as_tuple() == Decimal("0.1600").as_tuple()
        assert p.exact_fiscal_amount.as_tuple() == Decimal("16.000").as_tuple()
        assert p.rounding_quantizer.as_tuple() == Decimal("0.010").as_tuple()
        assert p.rounded_fiscal_amount.as_tuple() == Decimal("16.00").as_tuple()
    finally:
        session.close()
        engine.dispose()


def test_read_reconstructs_explicit_omitted_zero_fiscal_line(tmp_path, monkeypatch):
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot

    engine, session = _session(tmp_path, monkeypatch, "zero.db")
    try:
        entry_id = _seed(
            session,
            overrides={
                "rate": "0.0000",
                "exact_fiscal_amount": "0.000",
                "rounded_fiscal_amount": "0.00",
                "zero_fiscal_line_policy": "omit_confirmed_zero_fiscal_line",
                "omitted_zero_account_role": "tax_payable",
                "omitted_zero_account_id": 33,
                "omitted_zero_account_code": "2103",
                "omitted_zero_account_name": "Impuestos por pagar",
                "omitted_zero_side": "credit",
                "omitted_zero_amount": "0.00",
            },
        )
        snapshot = load_fiscal_posting_audit_snapshot(session, entry_id)
        omitted = snapshot.omitted_zero_fiscal_line
        assert omitted is not None
        assert omitted.account_role == "tax_payable"
        assert omitted.account_id == 33
        assert omitted.account_code == "2103"
        assert omitted.account_name == "Impuestos por pagar"
        assert omitted.side == "credit"
        assert omitted.amount.as_tuple() == Decimal("0.00").as_tuple()
    finally:
        session.close()
        engine.dispose()


def test_read_uses_only_supplied_session_and_never_opens_hidden_database(tmp_path, monkeypatch):
    import aqorath.storage as storage
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot

    engine, session = _session(tmp_path, monkeypatch, "supplied.db")
    try:
        entry_id = _seed(session)
        monkeypatch.setattr(
            storage,
            "get_session",
            lambda: (_ for _ in ()).throw(AssertionError("must use supplied session")),
        )
        assert load_fiscal_posting_audit_snapshot(session, entry_id).description == "Venta fiscalizada confirmada"
    finally:
        session.close()
        engine.dispose()


def test_read_is_read_only_and_never_commits_adds_deletes_or_rolls_back(tmp_path, monkeypatch):
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot

    engine, session = _session(tmp_path, monkeypatch, "readonly.db")
    try:
        entry_id = _seed(session)

        def forbidden(*args, **kwargs):
            raise AssertionError("audit read must be read-only")

        monkeypatch.setattr(session, "add", forbidden)
        monkeypatch.setattr(session, "delete", forbidden)
        monkeypatch.setattr(session, "commit", forbidden)
        monkeypatch.setattr(session, "rollback", forbidden)
        assert load_fiscal_posting_audit_snapshot(session, entry_id).provenance.rate == Decimal("0.1600")
    finally:
        session.close()
        engine.dispose()


def test_read_missing_journal_entry_fails_closed(tmp_path, monkeypatch):
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot

    engine, session = _session(tmp_path, monkeypatch, "missing-entry.db")
    try:
        with pytest.raises(LookupError, match="JournalEntry|entry"):
            load_fiscal_posting_audit_snapshot(session, 999)
    finally:
        session.close()
        engine.dispose()


def test_read_existing_entry_without_fiscal_audit_fails_closed(tmp_path, monkeypatch):
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot
    from aqorath.models import JournalEntry

    engine, session = _session(tmp_path, monkeypatch, "missing-audit.db")
    try:
        entry = JournalEntry(date=datetime.now(timezone.utc), concept="Histórico", state="draft")
        session.add(entry)
        session.commit()
        with pytest.raises(LookupError, match="audit|fiscal"):
            load_fiscal_posting_audit_snapshot(session, entry.id)
    finally:
        session.close()
        engine.dispose()


def test_read_validates_entry_id_nominally_before_query(tmp_path, monkeypatch):
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot

    engine, session = _session(tmp_path, monkeypatch, "identity.db")
    try:
        for invalid in (True, 0, -1, "1", None):
            with pytest.raises((TypeError, ValueError)):
                load_fiscal_posting_audit_snapshot(session, invalid)
    finally:
        session.close()
        engine.dispose()


def test_read_corrupt_decimal_text_fails_closed_without_coercion(tmp_path, monkeypatch):
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot

    engine, session = _session(tmp_path, monkeypatch, "corrupt-decimal.db")
    try:
        entry_id = _seed(session, overrides={"rate": "not-a-decimal"})
        with pytest.raises((ValueError, ArithmeticError)):
            load_fiscal_posting_audit_snapshot(session, entry_id)
    finally:
        session.close()
        engine.dispose()


def test_read_partial_zero_omission_metadata_fails_closed(tmp_path, monkeypatch):
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot

    engine, session = _session(tmp_path, monkeypatch, "partial-zero.db")
    try:
        entry_id = _seed(
            session,
            overrides={
                "rate": "0.00",
                "exact_fiscal_amount": "0.00",
                "rounded_fiscal_amount": "0.00",
                "zero_fiscal_line_policy": "omit_confirmed_zero_fiscal_line",
                "omitted_zero_account_role": "tax_payable",
            },
        )
        with pytest.raises((ValueError, TypeError)):
            load_fiscal_posting_audit_snapshot(session, entry_id)
    finally:
        session.close()
        engine.dispose()


def test_read_rejects_missing_confirmed_description_instead_of_inventing_one(tmp_path, monkeypatch):
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot

    engine, session = _session(tmp_path, monkeypatch, "description.db")
    try:
        entry_id = _seed(session, concept="")
        with pytest.raises(ValueError, match="description|concept"):
            load_fiscal_posting_audit_snapshot(session, entry_id)
    finally:
        session.close()
        engine.dispose()


def test_read_never_recalculates_rerounds_resolves_accounts_or_posts(tmp_path, monkeypatch):
    import aqorath.core as core
    import aqorath.fiscal_calculation as calculation
    import aqorath.fiscal_rounding as rounding
    import aqorath.fiscalized_account_resolution as resolution
    from aqorath.fiscal_posting_audit_read import load_fiscal_posting_audit_snapshot

    engine, session = _session(tmp_path, monkeypatch, "authority.db")
    try:
        entry_id = _seed(session)

        def forbidden(*args, **kwargs):
            raise AssertionError("persisted audit read cannot recalculate, resolve, or post")

        monkeypatch.setattr(calculation, "calculate_fiscal_rate_amount", forbidden)
        monkeypatch.setattr(rounding, "round_confirmed_fiscal_amount", forbidden)
        monkeypatch.setattr(resolution, "resolve_fiscalized_proposal_accounts", forbidden)
        monkeypatch.setattr(core, "post_entry", forbidden)

        snapshot = load_fiscal_posting_audit_snapshot(session, entry_id)
        assert snapshot.provenance.rounded_fiscal_amount == Decimal("16.00")
    finally:
        session.close()
        engine.dispose()
