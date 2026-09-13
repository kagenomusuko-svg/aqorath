"""Installed-wheel V1-13 CFDI source-document acceptance case.

This helper is invoked only by ``scripts/verify_installed_v1.py``. It uses the
AQR-010 fixture as external input, drives only product HTTP surfaces for writes,
and uses SQLite reads solely to prove durable identity/cardinality/rollback.
"""

from __future__ import annotations

import base64
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

import _installed_v1_core_cases as core


FIXTURE = core.REPO_ROOT / "tests" / "fixtures" / "cfdi40_ingreso.xml"
EXPECTED_UUID = "123E4567-E89B-12D3-A456-426614174000"
EXPECTED_TOTAL = Decimal("1160.00")
EXPECTED_TAX = Decimal("160.00")


def _payload():
    payload = core._onboarding_payload()
    payload.update({
        "name": "Meriadock A.C. CFDI V1-13",
        "rfc": "MER260101AB1",
        "legal_form": "A.C.",
        "economic_purpose": "no_lucrativo",
        "special_capabilities": ["osc"],
    })
    return payload


def _counts(db_path: Path):
    with sqlite3.connect(db_path) as conn:
        return {
            "sources": conn.execute("SELECT COUNT(*) FROM cfdisource").fetchone()[0],
            "tax_evidence": conn.execute("SELECT COUNT(*) FROM cfditaxevidence").fetchone()[0],
            "third_parties": conn.execute("SELECT COUNT(*) FROM thirdparty").fetchone()[0],
            "links": conn.execute("SELECT COUNT(*) FROM cfdisourcelink").fetchone()[0],
            "documents": conn.execute("SELECT COUNT(*) FROM documentreference").fetchone()[0],
            "metadata": conn.execute("SELECT COUNT(*) FROM cfdiimportmetadata").fetchone()[0],
            "entries": conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0],
            "lines": conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0],
            "import_audits": conn.execute("SELECT COUNT(*) FROM auditevent WHERE event_type='cfdi_source_imported'").fetchone()[0],
            "posting_audits": conn.execute("SELECT COUNT(*) FROM auditevent WHERE event_type='entry_posted'").fetchone()[0],
            "link_audits": conn.execute("SELECT COUNT(*) FROM auditevent WHERE event_type='cfdi_source_linked'").fetchone()[0],
        }


def _source_truth(db_path: Path, source_id: int):
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT id,third_party_id,document_position,uuid,file_hash,total,total_transferred,total_withheld,xml_bytes "
            "FROM cfdisource WHERE id=?",
            (source_id,),
        ).fetchone()
        taxes = conn.execute(
            "SELECT direction,base,tax_code,factor_type,rate_or_quota,amount "
            "FROM cfditaxevidence WHERE cfdi_source_id=? ORDER BY position",
            (source_id,),
        ).fetchall()
    if row is None:
        raise AssertionError(f"V1-13: CfdiSource {source_id} disappeared")
    return row, taxes


def _assert_imported_unposted(professional, imported):
    source = imported["source"]
    read_source = professional.get("source", {})
    for key in ("id", "uuid", "document_number", "document_position", "file_hash", "total", "total_transferred", "total_withheld"):
        if read_source.get(key) != source.get(key):
            raise AssertionError(f"V1-13: imported professional source changed {key}: {professional}")
    if professional.get("status") != "imported_unposted":
        raise AssertionError(f"V1-13: imported source is not explicitly unposted: {professional}")
    if professional.get("document_reference_id") is not None or professional.get("accounting") is not None:
        raise AssertionError(f"V1-13: importing external evidence created accounting truth: {professional}")
    if professional.get("evidence_vs_accounting", {}).get("document_amount") != "1160.00":
        raise AssertionError(f"V1-13: imported document amount differs: {professional}")
    if professional.get("evidence_vs_accounting", {}).get("ledger_amount") is not None:
        raise AssertionError(f"V1-13: unposted source already exposes ledger amount: {professional}")
    fiscality = professional.get("fiscality", {})
    if fiscality.get("supported") is not False or "no determina" not in fiscality.get("limitation", ""):
        raise AssertionError(f"V1-13: XML was treated as fiscal determination: {fiscality}")


def _assert_prepare(prepared, party):
    token = core._assert_common_preview(prepared, amount="1160.00")
    preview = prepared.get("preview", {})
    if preview.get("operation") != "Compra de servicios pagada por banco":
        raise AssertionError(f"V1-13: operation label differs: {preview}")
    if preview.get("uuid") != EXPECTED_UUID or preview.get("document_number") != "A-123":
        raise AssertionError(f"V1-13: common document identity differs: {preview}")
    if preview.get("counterparty") != party["name"]:
        raise AssertionError(f"V1-13: common counterparty differs: {preview}")
    if preview.get("posting_date") != "2026-09-10":
        raise AssertionError(f"V1-13: common posting date differs: {preview}")
    if core._decimal(preview.get("amount"), "V1-13 common amount") != EXPECTED_TOTAL or core._decimal(preview.get("document_total"), "V1-13 document total") != EXPECTED_TOTAL:
        raise AssertionError(f"V1-13: common amount/document total differs: {preview}")
    if core._decimal(preview.get("tax_from_document"), "V1-13 document tax") != EXPECTED_TAX:
        raise AssertionError(f"V1-13: extracted document tax differs: {preview}")
    if "Importar no contabiliza" not in preview.get("warning", "") or preview.get("requires_confirmation") is not True:
        raise AssertionError(f"V1-13: common preview lost consent warning: {preview}")
    if "pendiente/no cubierto" not in preview.get("fiscality", ""):
        raise AssertionError(f"V1-13: common preview inferred fiscal treatment from XML: {preview}")
    serialized = json.dumps(preview, ensure_ascii=False, sort_keys=True)
    if "account_code" in serialized or "Debe" in serialized or "Haber" in serialized:
        raise AssertionError(f"V1-13: common preview leaked professional accounting fields: {preview}")
    return token


def _assert_professional_preview(preview):
    decision = preview.get("decision", {})
    if decision.get("operation_key") != "purchase_utility_bank" or decision.get("posting_date") != "2026-09-10":
        raise AssertionError(f"V1-13: professional decision identity differs: {preview}")
    lines = decision.get("lines", [])
    actual = [(line.get("account_code"), line.get("side"), core._decimal(line.get("amount"), "V1-13 preview line")) for line in lines]
    expected = [("5102", "debit", EXPECTED_TOTAL), ("1101", "credit", EXPECTED_TOTAL)]
    if actual != expected:
        raise AssertionError(f"V1-13: professional proposal differs from AQR-010 authority: {actual}")
    if core._decimal(preview.get("tax_from_document"), "V1-13 professional document tax") != EXPECTED_TAX:
        raise AssertionError(f"V1-13: professional preview lost XML tax evidence: {preview}")


def _assert_single_chain(db_path: Path, expected):
    counts = _counts(db_path)
    expected_counts = {
        "sources": 1,
        "tax_evidence": 1,
        "third_parties": 1,
        "links": 1,
        "documents": 1,
        "metadata": 1,
        "entries": 1,
        "lines": 2,
        "import_audits": 1,
        "posting_audits": 1,
        "link_audits": 1,
    }
    if counts != expected_counts:
        raise AssertionError(f"V1-13: durable cardinality differs: {counts}")
    with sqlite3.connect(db_path) as conn:
        chain = conn.execute(
            "SELECT s.id,l.id,l.document_reference_id,d.id,d.entry_id,e.id,d.third_party_id,d.file_hash "
            "FROM cfdisource s JOIN cfdisourcelink l ON l.cfdi_source_id=s.id "
            "JOIN documentreference d ON d.id=l.document_reference_id "
            "JOIN journalentry e ON e.id=d.entry_id"
        ).fetchone()
        metadata = conn.execute(
            "SELECT document_reference_id,cfdi_version,uuid,issuer_rfc,receiver_rfc "
            "FROM cfdiimportmetadata"
        ).fetchone()
        lines = conn.execute(
            "SELECT account_code,debit,credit FROM journalline WHERE entry_id=? ORDER BY id",
            (expected["entry_id"],),
        ).fetchall()
    if chain is None:
        raise AssertionError("V1-13: source→link→document→entry chain is missing")
    source_id, link_id, link_document_id, document_id, entry_id, joined_entry_id, party_id, file_hash = chain
    if (
        source_id != expected["source_id"]
        or link_id != expected["link_id"]
        or link_document_id != expected["document_id"]
        or document_id != expected["document_id"]
        or entry_id != expected["entry_id"]
        or joined_entry_id != expected["entry_id"]
        or party_id != expected["party_id"]
        or file_hash != expected["file_hash"]
    ):
        raise AssertionError(f"V1-13: durable source chain changed: {chain}")
    if metadata != (
        expected["document_id"],
        "4.0",
        EXPECTED_UUID,
        "AAA010101AAA",
        "MER260101AB1",
    ):
        raise AssertionError(f"V1-13: CFDI metadata does not reuse the canonical document/provenance: {metadata}")
    actual_lines = [(code, core._decimal(debit, "V1-13 debit"), core._decimal(credit, "V1-13 credit")) for code, debit, credit in lines]
    if actual_lines != [("5102", EXPECTED_TOTAL, Decimal("0")), ("1101", Decimal("0"), EXPECTED_TOTAL)]:
        raise AssertionError(f"V1-13: posted canonical lines differ: {actual_lines}")
    return counts


def _assert_linked_professional(professional, expected):
    source = professional.get("source", {})
    if source.get("id") != expected["source_id"] or source.get("uuid") != EXPECTED_UUID or source.get("file_hash") != expected["file_hash"]:
        raise AssertionError(f"V1-13: linked professional source identity differs: {professional}")
    if professional.get("document_reference_id") != expected["document_id"]:
        raise AssertionError(f"V1-13: professional readback changed DocumentReference: {professional}")
    accounting = professional.get("accounting", {})
    if accounting.get("entry_id") != expected["entry_id"] or accounting.get("state") != "posted":
        raise AssertionError(f"V1-13: professional readback changed JournalEntry: {professional}")
    if accounting.get("audit", {}).get("event_type") != "entry_posted":
        raise AssertionError(f"V1-13: canonical posting audit missing: {professional}")
    documents = accounting.get("documents", [])
    if len(documents) != 1 or documents[0].get("id") != expected["document_id"] or documents[0].get("third_party_id") != expected["party_id"] or documents[0].get("file_hash") != expected["file_hash"]:
        raise AssertionError(f"V1-13: accounting does not reuse one canonical CFDI document: {documents}")
    evidence = professional.get("evidence_vs_accounting", {})
    if core._decimal(evidence.get("document_amount"), "V1-13 document amount") != EXPECTED_TOTAL or core._decimal(evidence.get("ledger_amount"), "V1-13 ledger amount") != EXPECTED_TOTAL:
        raise AssertionError(f"V1-13: evidence/accounting amount correspondence differs: {evidence}")
    if professional.get("status") != "linked_to_posted_accounting":
        raise AssertionError(f"V1-13: linked status differs: {professional}")
    if "evidencia externa" not in professional.get("distinction", "") or "autoridad contable" not in professional.get("distinction", ""):
        raise AssertionError(f"V1-13: XML/ledger distinction disappeared: {professional}")
    fiscality = professional.get("fiscality", {})
    if fiscality.get("supported") is not False or "no determina" not in fiscality.get("limitation", ""):
        raise AssertionError(f"V1-13: professional readback inferred fiscal treatment: {fiscality}")
    taxes = fiscality.get("declared_xml_taxes", [])
    if len(taxes) != 1 or core._decimal(taxes[0].get("base"), "V1-13 tax base") != Decimal("1000.00") or core._decimal(taxes[0].get("rate_or_quota"), "V1-13 tax rate evidence") != Decimal("0.160000") or core._decimal(taxes[0].get("amount"), "V1-13 tax amount evidence") != EXPECTED_TAX:
        raise AssertionError(f"V1-13: XML tax evidence changed: {taxes}")


def assert_v1_13_cfdi(db_path: Path):
    case = "V1-13 installed CFDI source document"
    if core._request_json("GET", "/api/onboarding").get("configured") is not False:
        raise AssertionError(f"{case}: CFDI SQLite was not clean")
    configured = core._request_json("POST", "/api/onboarding", _payload())
    if configured.get("configured") is not True or configured.get("entity", {}).get("rfc") != "MER260101AB1":
        raise AssertionError(f"{case}: onboarding identity differs: {configured}")

    party = core._request_json(
        "POST",
        "/api/subledger/third-parties",
        {"name": "Proveedor Ejemplo SA de CV", "party_type": "supplier", "rfc": "AAA010101AAA"},
    )
    if party.get("rfc") != "AAA010101AAA":
        raise AssertionError(f"{case}: product ThirdParty RFC differs: {party}")

    xml_bytes = FIXTURE.read_bytes()
    expected_hash = hashlib.sha256(xml_bytes).hexdigest()
    encoded = base64.b64encode(xml_bytes).decode("ascii")
    first = core._request_json("POST", "/api/cfdi/import", {"xml_base64": encoded})
    source = first.get("source", {})
    if first.get("duplicate") is not False:
        raise AssertionError(f"{case}: first import was not material: {first}")
    if (
        source.get("uuid") != EXPECTED_UUID
        or source.get("file_hash") != expected_hash
        or source.get("document_position") != "receiver"
        or core._decimal(source.get("total"), "V1-13 source total") != EXPECTED_TOTAL
        or core._decimal(source.get("total_transferred"), "V1-13 source transferred") != EXPECTED_TAX
        or core._decimal(source.get("total_withheld"), "V1-13 source withheld") != Decimal("0")
    ):
        raise AssertionError(f"{case}: imported source truth differs: {source}")
    taxes = source.get("taxes", [])
    if len(taxes) != 1 or taxes[0].get("direction") != "transfer" or taxes[0].get("tax_code") != "002" or core._decimal(taxes[0].get("amount"), "V1-13 source tax") != EXPECTED_TAX:
        raise AssertionError(f"{case}: imported tax evidence differs: {source}")

    source_id = source.get("id")
    if not source_id:
        raise AssertionError(f"{case}: imported source lacks identity: {first}")
    row, persisted_taxes = _source_truth(db_path, source_id)
    if row[1] != party["id"] or row[2] != "receiver" or row[3] != EXPECTED_UUID or row[4] != expected_hash or core._decimal(row[5], "V1-13 persisted total") != EXPECTED_TOTAL or row[8] != xml_bytes:
        raise AssertionError(f"{case}: persisted source differs from product import: {row}")
    if persisted_taxes != [("transfer", "1000.00", "002", "Tasa", "0.160000", "160.00")]:
        raise AssertionError(f"{case}: persisted tax evidence differs: {persisted_taxes}")

    unposted = core._request_json("GET", f"/api/cfdi/{EXPECTED_UUID}/professional")
    _assert_imported_unposted(unposted, first)
    initial_counts = _counts(db_path)
    if initial_counts != {
        "sources": 1, "tax_evidence": 1, "third_parties": 1,
        "links": 0, "documents": 0, "metadata": 0, "entries": 0, "lines": 0,
        "import_audits": 1, "posting_audits": 0, "link_audits": 0,
    }:
        raise AssertionError(f"{case}: first import wrote unexpected durable truth: {initial_counts}")

    second = core._request_json("POST", "/api/cfdi/import", {"xml_base64": encoded})
    if second.get("duplicate") is not True:
        raise AssertionError(f"{case}: identical reimport was not idempotent: {second}")
    for key in ("id", "uuid", "file_hash", "document_position", "total", "total_transferred", "total_withheld"):
        if second.get("source", {}).get(key) != source.get(key):
            raise AssertionError(f"{case}: reimport resolved a different source for {key}: {second}")
    if _counts(db_path) != initial_counts:
        raise AssertionError(f"{case}: identical reimport duplicated durable evidence: {_counts(db_path)}")

    prepare_payload = {"uuid": EXPECTED_UUID, "operation_kind": "purchase_utility_bank"}
    cancelled = core._request_json("POST", "/api/cfdi/prepare", prepare_payload)
    cancelled_token = _assert_prepare(cancelled, party)
    cancelled_professional = core._request_json("GET", f"/api/operations/{cancelled_token}/professional-preview")
    _assert_professional_preview(cancelled_professional)
    if _counts(db_path) != initial_counts:
        raise AssertionError(f"{case}: preparation wrote accounting truth")
    cancelled_result = core._request_json("DELETE", f"/api/operations/{cancelled_token}")
    if cancelled_result != {"cancelled": True}:
        raise AssertionError(f"{case}: cancellation result differs: {cancelled_result}")
    cancelled_reuse = core._request_error(
        "POST", f"/api/operations/{cancelled_token}/confirm", expected_status=404
    )
    if "prepared accounting decision not found" not in cancelled_reuse.get("detail", ""):
        raise AssertionError(f"{case}: cancelled token failed for wrong reason: {cancelled_reuse}")
    if _counts(db_path) != initial_counts or core._request_json("GET", f"/api/cfdi/{EXPECTED_UUID}/professional") != unposted:
        raise AssertionError(f"{case}: cancellation changed external evidence")

    prepared = core._request_json("POST", "/api/cfdi/prepare", prepare_payload)
    token = _assert_prepare(prepared, party)
    if token == cancelled_token:
        raise AssertionError(f"{case}: new preparation reused cancelled ephemeral token")
    professional_preview = core._request_json("GET", f"/api/operations/{token}/professional-preview")
    _assert_professional_preview(professional_preview)
    result = core._request_json("POST", f"/api/operations/{token}/confirm")
    required_ids = ("entry_id", "audit_event_id", "cfdi_source_id", "cfdi_source_link_id", "document_reference_id")
    if any(not result.get(key) for key in required_ids):
        raise AssertionError(f"{case}: confirmation lacks canonical identities: {result}")
    if result.get("cfdi_source_id") != source_id:
        raise AssertionError(f"{case}: confirmation changed CfdiSource identity: {result}")
    expected = {
        "source_id": source_id,
        "party_id": party["id"],
        "file_hash": expected_hash,
        "entry_id": result["entry_id"],
        "link_id": result["cfdi_source_link_id"],
        "document_id": result["document_reference_id"],
    }
    _assert_single_chain(db_path, expected)
    linked = core._request_json("GET", f"/api/cfdi/{EXPECTED_UUID}/professional")
    _assert_linked_professional(linked, expected)

    confirmed_reuse = core._request_error(
        "POST", f"/api/operations/{token}/confirm", expected_status=404
    )
    if "prepared accounting decision not found" not in confirmed_reuse.get("detail", ""):
        raise AssertionError(f"{case}: confirmed token failed for wrong reason: {confirmed_reuse}")
    _assert_single_chain(db_path, expected)

    retry = core._request_json("POST", "/api/cfdi/prepare", prepare_payload)
    retry_token = _assert_prepare(retry, party)
    if retry_token in {token, cancelled_token}:
        raise AssertionError(f"{case}: fresh retry did not receive a fresh ephemeral token")
    retry_error = core._request_error("POST", f"/api/operations/{retry_token}/confirm")
    if "CFDI source is already linked to another operation" not in retry_error.get("detail", ""):
        raise AssertionError(f"{case}: second durable use failed for wrong reason: {retry_error}")
    _assert_single_chain(db_path, expected)
    if core._request_json("GET", f"/api/cfdi/{EXPECTED_UUID}/professional") != linked:
        raise AssertionError(f"{case}: rejected second operation modified first durable truth")

    return {
        **expected,
        "uuid": EXPECTED_UUID,
        "document_total": "1160.00",
        "tax_evidence": "160.00",
        "professional": linked,
    }


def assert_v1_13_reopen(db_path: Path, expected):
    case = "V1-13 CFDI reopen"
    professional = core._request_json("GET", f"/api/cfdi/{expected['uuid']}/professional")
    if professional != expected["professional"]:
        raise AssertionError(f"{case}: durable CFDI reconstruction changed after restart")
    _assert_linked_professional(professional, expected)
    _assert_single_chain(db_path, expected)
    sources = core._request_json("GET", "/api/cfdi/sources")
    if len(sources) != 1 or sources[0].get("id") != expected["source_id"] or sources[0].get("uuid") != expected["uuid"] or sources[0].get("file_hash") != expected["file_hash"]:
        raise AssertionError(f"{case}: source list changed after restart: {sources}")
    return {
        "source_id": expected["source_id"],
        "document_reference_id": expected["document_id"],
        "entry_id": expected["entry_id"],
        "uuid": expected["uuid"],
    }


__all__ = ["assert_v1_13_cfdi", "assert_v1_13_reopen"]
