"""Installed-wheel V1-14 fiscal acceptance case for the AQR-015 harness.

This module is a domain helper only. It drives the already-installed product over
loopback HTTP and reads SQLite only to prove persistence/reference-data shape.
It owns no fiscal rules, calculations, posting authority or standalone harness.
"""

from decimal import Decimal
import json
import sqlite3

import _installed_v1_core_cases as core


FISCAL_BINDINGS = {
    "professional_services_expense": "5303",
    "vat_pending_credit": "1182",
    "tax_payable": "2080",
    "isr_withholding_payable": "2160",
    "vat_withholding_payable": "2170",
}

EXPECTED_REFERENCE_RULES = {
    (
        "iva.general_rate", "MX", "general", "comercial", "2010-01-01",
        "0.16", "rate", "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1",
    ),
    (
        "iva.zero_rate", "MX", "general", "comercial", "1981-01-01",
        "0.00", "rate", "DOF:1980-12-30:ART8+TRANSITORIO-PRIMERO;LIVA:ART2-A",
    ),
    (
        "iva.exempt.sale.land", "MX", "general", "comercial", "1980-01-01",
        "0", "exempt", "DOF:1978-12-29;LIVA:ART9-I",
    ),
    (
        "iva.freight_transport_retention_rate", "MX", "general", "persona_moral", "2006-12-05",
        "0.04", "rate", "DOF:2006-12-04;LIVA:ART1-A-II-c;RLIVA:ART3-II",
    ),
    (
        "isr.professional_services_retention_rate", "MX", "general", "persona_fisica_profesional", "2014-01-01",
        "0.10", "rate", "DOF:2013-12-11;LISR:ART106",
    ),
    (
        "iva.professional_services_retention_fraction", "MX", "general", "persona_fisica_profesional", "2006-12-05",
        "2", "fraction_2_3_of_transferred_vat", "DOF:2006-12-04;LIVA:ART1-A-II-a;RLIVA:ART3-I-a",
    ),
    (
        "isr.resico_retention_rate", "MX", "resico", "persona_fisica", "2022-01-01",
        "0.0125", "rate", "DOF:2021-11-12;LISR:ART113-J",
    ),
}


def _reference_rules(db_path):
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT rule_key,jurisdiction,regime,entity_type,effective_from,value,unit,source_ref "
            "FROM fiscalruleversion ORDER BY rule_key,jurisdiction,regime,entity_type,effective_from"
        ).fetchall()
    return {
        (rule_key, jurisdiction, regime, entity_type, effective_from, value, unit, source_ref)
        for rule_key, jurisdiction, regime, entity_type, effective_from, value, unit, source_ref in rows
    }


def _fiscal_onboarding_payload():
    payload = core._onboarding_payload()
    payload["name"] = "Negocio fiscal V1-14 instalado"
    payload["bindings"] = {**core.CORE_BINDINGS, **FISCAL_BINDINGS}
    return payload


def _entry_count(db_path):
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0]


def _assert_reference_data(db_path):
    actual = _reference_rules(db_path)
    if actual != EXPECTED_REFERENCE_RULES:
        raise AssertionError(
            "V1-14: clean-wheel curated fiscal reference data differs: "
            f"expected={sorted(EXPECTED_REFERENCE_RULES)}, actual={sorted(actual)}"
        )


def _assert_common_preview(prepared, party_id):
    token = core._assert_common_preview(prepared, amount="1000.00")
    common = prepared.get("preview", {})
    if common.get("coverage_version") != "mx-fiscal-v1.2026-09-10":
        raise AssertionError(f"V1-14: common coverage version differs: {common}")
    if core._decimal(common.get("base"), "V1-14 common base") != Decimal("1000.00"):
        raise AssertionError(f"V1-14: common base differs: {common}")
    if common.get("counterparty_third_party_id") != party_id or common.get("cfdi_source_id") is not None:
        raise AssertionError(f"V1-14: common factual provenance differs: {common}")
    common_text = json.dumps(common, sort_keys=True, ensure_ascii=False)
    for forbidden in ("account_role", "account_code", '"side"', "Debe", "Haber", "5303", "1182", "2160", "2170"):
        if forbidden in common_text:
            raise AssertionError(f"V1-14: common preview leaked professional accounting data ({forbidden}): {common}")
    treatment_amounts = {
        item.get("name"): core._decimal(item.get("amount"), f"V1-14 common {item.get('name')}")
        for item in common.get("treatments", [])
    }
    expected = {
        "iva.general_rate": Decimal("160.00"),
        "isr.professional_services_retention_rate": Decimal("100.00"),
        "iva.professional_services_retention_fraction": Decimal("106.67"),
    }
    if treatment_amounts != expected:
        raise AssertionError(f"V1-14: common fiscal amounts differ: {treatment_amounts}")
    return token


def _assert_professional_preview(preview, party_id):
    if preview.get("coverage_version") != "mx-fiscal-v1.2026-09-10" or preview.get("third_party_id") != party_id:
        raise AssertionError(f"V1-14: professional preview identity differs: {preview}")
    facts = preview.get("facts", {})
    if (
        facts.get("counterparty_legal_personality") != "persona_fisica"
        or facts.get("counterparty_fiscal_regime") != "general"
        or core._decimal(facts.get("base"), "V1-14 preview base") != Decimal("1000.00")
        or facts.get("effectively_paid") is not True
    ):
        raise AssertionError(f"V1-14: professional preview facts differ: {facts}")
    treatments = preview.get("treatments", [])
    if [item.get("rule_key") for item in treatments] != [
        "iva.general_rate",
        "isr.professional_services_retention_rate",
        "iva.professional_services_retention_fraction",
    ]:
        raise AssertionError(f"V1-14: professional treatment selection differs: {treatments}")
    if [item.get("rule_set_version") for item in treatments] != ["2010.1", "2014.1", "2006.1"]:
        raise AssertionError(f"V1-14: professional rule-set versions differ: {treatments}")
    if any(not item.get("source_ref") for item in treatments):
        raise AssertionError(f"V1-14: professional preview lost fiscal source provenance: {treatments}")
    fraction = treatments[2]
    if fraction.get("formula") != "2/3 × IVA trasladado y efectivamente pagado" or "0.666" in fraction.get("formula", ""):
        raise AssertionError(f"V1-14: two-thirds legal formula was approximated: {fraction}")
    if core._decimal(fraction.get("rounded_amount"), "V1-14 preview retained VAT") != Decimal("106.67"):
        raise AssertionError(f"V1-14: rounded retained VAT differs: {fraction}")
    if core._decimal(fraction.get("exact_amount"), "V1-14 preview exact retained VAT") == Decimal("106.67"):
        raise AssertionError(f"V1-14: exact two-thirds amount was prematurely rounded: {fraction}")

    actual_accounting = [
        (item.get("account_role"), item.get("side"), core._decimal(item.get("amount"), "V1-14 preview accounting amount"))
        for item in preview.get("accounting", [])
    ]
    expected_accounting = [
        ("professional_services_expense", "debit", Decimal("1000.00")),
        ("bank", "credit", Decimal("953.33")),
        ("vat_pending_credit", "debit", Decimal("160.00")),
        ("isr_withholding_payable", "credit", Decimal("100.00")),
        ("vat_withholding_payable", "credit", Decimal("106.67")),
    ]
    if actual_accounting != expected_accounting:
        raise AssertionError(f"V1-14: professional preview accounting differs: {actual_accounting}")
    return treatments


def _assert_professional_readback(professional, party_id, preview_treatments):
    if (
        professional.get("coverage_version") != "mx-fiscal-v1.2026-09-10"
        or professional.get("entry_state") != "posted"
        or professional.get("posting_date") != "2026-09-10"
        or professional.get("counterparty", {}).get("third_party_id") != party_id
        or professional.get("counterparty", {}).get("rfc") != "COSC8001137NA"
        or professional.get("cfdi_source") is not None
    ):
        raise AssertionError(f"V1-14: professional persisted identity differs: {professional}")

    facts = professional.get("facts", {})
    if (
        facts.get("type") != "professional_services_expense"
        or facts.get("payment_method") != "bank"
        or facts.get("counterparty_legal_personality") != "persona_fisica"
        or facts.get("counterparty_fiscal_regime") != "general"
        or core._decimal(facts.get("base"), "V1-14 persisted base") != Decimal("1000.00")
        or facts.get("effectively_paid") is not True
    ):
        raise AssertionError(f"V1-14: persisted fiscal facts differ: {facts}")

    treatments = professional.get("treatments", [])
    if [item.get("rule_key") for item in treatments] != [item.get("rule_key") for item in preview_treatments]:
        raise AssertionError(f"V1-14: persisted treatment order differs: {treatments}")
    preview_by_key = {item["rule_key"]: item for item in preview_treatments}
    expected_meta = {
        "iva.general_rate": ("2010.1", "2010-01-01", "DOF:2009-12-07:ART7+TRANSITORIO-UNICO;LIVA:ART1", Decimal("1000.00"), Decimal("0.16"), "rate", Decimal("160.00")),
        "isr.professional_services_retention_rate": ("2014.1", "2014-01-01", "DOF:2013-12-11;LISR:ART106", Decimal("1000.00"), Decimal("0.10"), "rate", Decimal("100.00")),
        "iva.professional_services_retention_fraction": ("2006.1", "2006-12-05", "DOF:2006-12-04;LIVA:ART1-A-II-a;RLIVA:ART3-I-a", Decimal("160.00"), Decimal("2"), "fraction_2_3_of_transferred_vat", Decimal("106.67")),
    }
    for item in treatments:
        key = item.get("rule_key")
        if key not in expected_meta:
            raise AssertionError(f"V1-14: unexpected persisted treatment: {item}")
        version, effective_from, source_ref, base, rule_value, unit, rounded = expected_meta[key]
        if (
            item.get("rule_set_version") != version
            or item.get("effective_from") != effective_from
            or item.get("effective_to") is not None
            or item.get("source_ref") != source_ref
            or item.get("jurisdiction") != "MX"
            or core._decimal(item.get("base"), f"V1-14 {key} base") != base
            or core._decimal(item.get("rule_value"), f"V1-14 {key} rule value") != rule_value
            or item.get("unit") != unit
            or item.get("rounding_policy_key") != "mx-fiscal-v1.mxn-two-decimals-half-up"
            or core._decimal(item.get("rounding_quantizer"), f"V1-14 {key} quantizer") != Decimal("0.01")
            or item.get("rounding_mode") != "ROUND_HALF_UP"
            or not item.get("rounding_source_ref")
            or core._decimal(item.get("rounded_amount"), f"V1-14 {key} rounded") != rounded
        ):
            raise AssertionError(f"V1-14: persisted rule provenance differs for {key}: {item}")
        if item.get("exact_amount") != preview_by_key[key].get("exact_amount"):
            raise AssertionError(f"V1-14: exact amount changed after posting for {key}: {item}")

    fraction = next(item for item in treatments if item.get("rule_key") == "iva.professional_services_retention_fraction")
    if fraction.get("formula") != "2/3 × IVA trasladado y efectivamente pagado" or "0.666" in fraction.get("formula", ""):
        raise AssertionError(f"V1-14: persisted two-thirds formula differs: {fraction}")
    if core._decimal(fraction.get("exact_amount"), "V1-14 persisted exact fraction") == core._decimal(fraction.get("rounded_amount"), "V1-14 persisted rounded fraction"):
        raise AssertionError(f"V1-14: persisted exact fraction lost pre-rounding truth: {fraction}")

    actual_lines = [
        (line.get("account_code"), core._decimal(line.get("debit"), "V1-14 persisted debit"), core._decimal(line.get("credit"), "V1-14 persisted credit"))
        for line in professional.get("accounting_lines", [])
    ]
    expected_lines = [
        ("5303", Decimal("1000.00"), Decimal("0")),
        ("1101", Decimal("0"), Decimal("953.33")),
        ("1182", Decimal("160.00"), Decimal("0")),
        ("2160", Decimal("0"), Decimal("100.00")),
        ("2170", Decimal("0"), Decimal("106.67")),
    ]
    if actual_lines != expected_lines:
        raise AssertionError(f"V1-14: canonical fiscal JournalLines differ: {actual_lines}")
    if sum((d for _, d, _ in actual_lines), Decimal("0")) != sum((c for _, _, c in actual_lines), Decimal("0")):
        raise AssertionError(f"V1-14: canonical fiscal policy is unbalanced: {actual_lines}")
    fiscal_audit = professional.get("fiscal_audit", {})
    if fiscal_audit.get("effect_count") != 3 or fiscal_audit.get("amount_basis") != "base_before_fiscal_settlement":
        raise AssertionError(f"V1-14: fiscal posting audit differs: {fiscal_audit}")


def assert_v1_14_fiscal(db_path):
    case = "V1-14 installed fiscal coverage"
    initial = core._request_json("GET", "/api/onboarding")
    if initial.get("configured") is not False:
        raise AssertionError(f"{case}: fiscal SQLite was not clean: {initial}")
    _assert_reference_data(db_path)

    configured = core._request_json("POST", "/api/onboarding", _fiscal_onboarding_payload())
    expected_bindings = {**core.CORE_BINDINGS, **FISCAL_BINDINGS}
    if configured.get("configured") is not True or configured.get("bindings") != expected_bindings:
        raise AssertionError(f"{case}: governed fiscal onboarding differs: {configured}")

    capabilities = core._request_json("GET", "/api/capabilities")
    if "professional_service_paid" not in {item.get("key") for item in capabilities.get("fiscal_v1_operations", [])}:
        raise AssertionError(f"{case}: professional-service fiscal capability missing: {capabilities}")

    party = core._request_json(
        "POST",
        "/api/subledger/third-parties",
        {"name": "Proveedor PF honorarios", "party_type": "supplier", "rfc": "COSC8001137NA"},
    )
    parties = core._request_json("GET", "/api/subledger/third-parties")
    if party not in parties or party.get("rfc") != "COSC8001137NA":
        raise AssertionError(f"{case}: persisted ThirdParty is not reusable: {party}, {parties}")

    outside = core._request_error(
        "POST",
        "/api/fiscal-v1/prepare",
        {"operation_key": "sale_general_paid", "amount": "10.00", "operation_date": "2026-09-11"},
    )
    if "no tiene una regla fiscal V1 declarada" not in json.dumps(outside, ensure_ascii=False):
        raise AssertionError(f"{case}: out-of-window case did not fail closed: {outside}")

    insufficient = core._request_error(
        "POST",
        "/api/fiscal-v1/prepare",
        {
            "operation_key": "professional_service_paid",
            "amount": "1000.00",
            "operation_date": "2026-09-10",
            "counterparty_fiscal_regime": "general",
        },
    )
    if "ThirdParty" not in json.dumps(insufficient, ensure_ascii=False):
        raise AssertionError(f"{case}: insufficient factual evidence did not fail closed: {insufficient}")
    if _entry_count(db_path) != 0:
        raise AssertionError(f"{case}: rejected preparation wrote JournalEntry truth")

    payload = {
        "operation_key": "professional_service_paid",
        "amount": "1000.00",
        "operation_date": "2026-09-10",
        "third_party_id": party["id"],
        "counterparty_fiscal_regime": "general",
    }
    cancelled = core._request_json("POST", "/api/fiscal-v1/prepare", payload)
    cancelled_token = _assert_common_preview(cancelled, party["id"])
    cancelled_preview = core._request_json("GET", f"/api/operations/{cancelled_token}/professional-preview")
    _assert_professional_preview(cancelled_preview, party["id"])
    if _entry_count(db_path) != 0:
        raise AssertionError(f"{case}: preparation wrote accounting truth before consent")
    cancelled_result = core._request_json("DELETE", f"/api/operations/{cancelled_token}")
    if cancelled_result != {"cancelled": True} or _entry_count(db_path) != 0:
        raise AssertionError(f"{case}: cancellation persisted accounting truth: {cancelled_result}")

    prepared = core._request_json("POST", "/api/fiscal-v1/prepare", payload)
    token = _assert_common_preview(prepared, party["id"])
    professional_preview = core._request_json("GET", f"/api/operations/{token}/professional-preview")
    preview_treatments = _assert_professional_preview(professional_preview, party["id"])
    result = core._request_json("POST", f"/api/operations/{token}/confirm")
    entry_id = result.get("entry_id")
    if (
        result.get("state") != "posted"
        or result.get("coverage_version") != "mx-fiscal-v1.2026-09-10"
        or not entry_id
        or not result.get("audit_event_id")
        or result.get("cfdi_source_link_id") is not None
        or result.get("document_reference_id") is not None
    ):
        raise AssertionError(f"{case}: confirmed fiscal identities differ: {result}")

    with sqlite3.connect(db_path) as conn:
        entries = conn.execute("SELECT id,state FROM journalentry ORDER BY id").fetchall()
        lines = conn.execute("SELECT COUNT(*) FROM journalline WHERE entry_id=?", (entry_id,)).fetchone()[0]
    if entries != [(entry_id, "posted")] or lines != 5:
        raise AssertionError(f"{case}: expected one canonical policy/five lines, got entries={entries}, lines={lines}")
    _assert_reference_data(db_path)

    professional = core._request_json("GET", f"/api/fiscal-v1/operations/{entry_id}/professional")
    _assert_professional_readback(professional, party["id"], preview_treatments)
    if professional.get("audit_event_id") != result.get("audit_event_id"):
        raise AssertionError(f"{case}: fiscal audit identity diverged: {professional}, {result}")

    generic = core._request_json("GET", f"/api/operations/{entry_id}/professional")
    if generic.get("entry_id") != entry_id or generic.get("state") != "posted" or generic.get("fiscal_audit") is None:
        raise AssertionError(f"{case}: generic professional policy did not expose same canonical fiscal truth: {generic}")

    return {
        "entry_id": entry_id,
        "party_id": party["id"],
        "audit_event_id": result["audit_event_id"],
        "professional": professional,
    }


def assert_v1_14_reopen(db_path, expected):
    case = "V1-14 fiscal reopen"
    _assert_reference_data(db_path)
    onboarding = core._request_json("GET", "/api/onboarding")
    for role, code in FISCAL_BINDINGS.items():
        if onboarding.get("bindings", {}).get(role) != code:
            raise AssertionError(f"{case}: fiscal binding {role} changed after restart: {onboarding}")
    professional = core._request_json(
        "GET", f"/api/fiscal-v1/operations/{expected['entry_id']}/professional"
    )
    if professional != expected["professional"]:
        raise AssertionError(f"{case}: persisted fiscal truth changed after restart")
    if professional.get("audit_event_id") != expected["audit_event_id"] or professional.get("counterparty", {}).get("third_party_id") != expected["party_id"]:
        raise AssertionError(f"{case}: persisted fiscal identities changed after restart: {professional}")
    with sqlite3.connect(db_path) as conn:
        if conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0] != 1:
            raise AssertionError(f"{case}: restart duplicated canonical accounting truth")
        if conn.execute("SELECT COUNT(*) FROM fiscalruleversion").fetchone()[0] != len(EXPECTED_REFERENCE_RULES):
            raise AssertionError(f"{case}: restart duplicated curated fiscal reference data")
    return {"entry_id": expected["entry_id"], "audit_event_id": expected["audit_event_id"], "reference_rules": len(EXPECTED_REFERENCE_RULES)}


__all__ = ["assert_v1_14_fiscal", "assert_v1_14_reopen"]
