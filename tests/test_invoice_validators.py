"""
Tests for invoice field validators.
Verifies that invoice/fiscal validators enforce required fields.
"""
from datetime import date
from decimal import Decimal
from modelos.registro import Registro, validate_invoice_fields


def test_invoice_validator_not_required_when_no_flag():
    """Test that invoice validation is skipped when has_invoice/has_cfdi are not set."""
    registro = Registro.create(
        fecha="2024-01-01",
        cuenta="4000",
        cantidad=1000.0,
        descripcion="Normal sale without invoice"
    )
    
    ok, msgs = validate_invoice_fields(registro)
    assert ok is True
    assert len(msgs) == 0


def test_invoice_validator_fails_missing_emitter_rfc():
    """Test that validator fails when emitter_rfc is missing."""
    registro = Registro.create(
        fecha="2024-01-01",
        cuenta="4000",
        cantidad=1000.0,
        descripcion="Sale with invoice"
    )
    registro.extra["has_invoice"] = True
    # Missing emitter_rfc
    registro.extra["receiver_rfc"] = "XAXX010101000"
    registro.extra["folio"] = "A123"
    registro.extra["subtotal"] = 1000.0
    registro.extra["total"] = 1160.0
    registro.extra["tax_breakdown"] = {"IVA": 160.0}
    
    ok, msgs = validate_invoice_fields(registro)
    assert ok is False
    assert any("emitter_rfc" in msg or "emisor_rfc" in msg for msg in msgs)


def test_invoice_validator_fails_missing_receiver_rfc():
    """Test that validator fails when receiver_rfc is missing."""
    registro = Registro.create(
        fecha="2024-01-01",
        cuenta="4000",
        cantidad=1000.0,
        descripcion="Sale with invoice"
    )
    registro.extra["has_invoice"] = True
    registro.extra["emitter_rfc"] = "AAA010101AAA"
    # Missing receiver_rfc
    registro.extra["folio"] = "A123"
    registro.extra["subtotal"] = 1000.0
    registro.extra["total"] = 1160.0
    registro.extra["tax_breakdown"] = {"IVA": 160.0}
    
    ok, msgs = validate_invoice_fields(registro)
    assert ok is False
    assert any("receiver_rfc" in msg or "receptor_rfc" in msg for msg in msgs)


def test_invoice_validator_fails_missing_folio_and_serie():
    """Test that validator fails when both folio and serie are missing."""
    registro = Registro.create(
        fecha="2024-01-01",
        cuenta="4000",
        cantidad=1000.0,
        descripcion="Sale with invoice"
    )
    registro.extra["has_cfdi"] = True
    registro.extra["emitter_rfc"] = "AAA010101AAA"
    registro.extra["receiver_rfc"] = "XAXX010101000"
    # Missing folio and serie
    registro.extra["subtotal"] = 1000.0
    registro.extra["total"] = 1160.0
    registro.extra["tax_breakdown"] = {"IVA": 160.0}
    
    ok, msgs = validate_invoice_fields(registro)
    assert ok is False
    assert any("folio" in msg.lower() or "serie" in msg.lower() for msg in msgs)


def test_invoice_validator_fails_missing_subtotal():
    """Test that validator fails when subtotal is missing."""
    registro = Registro.create(
        fecha="2024-01-01",
        cuenta="4000",
        cantidad=1000.0,
        descripcion="Sale with invoice"
    )
    registro.extra["has_invoice"] = True
    registro.extra["emitter_rfc"] = "AAA010101AAA"
    registro.extra["receiver_rfc"] = "XAXX010101000"
    registro.extra["folio"] = "A123"
    # Missing subtotal
    registro.extra["total"] = 1160.0
    registro.extra["tax_breakdown"] = {"IVA": 160.0}
    
    ok, msgs = validate_invoice_fields(registro)
    assert ok is False
    assert any("subtotal" in msg.lower() for msg in msgs)


def test_invoice_validator_fails_missing_total():
    """Test that validator fails when total is missing."""
    registro = Registro.create(
        fecha="2024-01-01",
        cuenta="4000",
        cantidad=1000.0,
        descripcion="Sale with invoice"
    )
    registro.extra["has_invoice"] = True
    registro.extra["emitter_rfc"] = "AAA010101AAA"
    registro.extra["receiver_rfc"] = "XAXX010101000"
    registro.extra["folio"] = "A123"
    registro.extra["subtotal"] = 1000.0
    # Missing total
    registro.extra["tax_breakdown"] = {"IVA": 160.0}
    
    ok, msgs = validate_invoice_fields(registro)
    assert ok is False
    assert any("total" in msg.lower() for msg in msgs)


def test_invoice_validator_fails_missing_tax_breakdown():
    """Test that validator fails when tax_breakdown is missing."""
    registro = Registro.create(
        fecha="2024-01-01",
        cuenta="4000",
        cantidad=1000.0,
        descripcion="Sale with invoice"
    )
    registro.extra["has_invoice"] = True
    registro.extra["emitter_rfc"] = "AAA010101AAA"
    registro.extra["receiver_rfc"] = "XAXX010101000"
    registro.extra["folio"] = "A123"
    registro.extra["subtotal"] = 1000.0
    registro.extra["total"] = 1160.0
    # Missing tax_breakdown
    
    ok, msgs = validate_invoice_fields(registro)
    assert ok is False
    assert any("tax_breakdown" in msg.lower() for msg in msgs)


def test_invoice_validator_success_all_fields_present():
    """Test that validator succeeds when all required fields are present."""
    registro = Registro.create(
        fecha="2024-01-01",
        cuenta="4000",
        cantidad=1000.0,
        descripcion="Sale with complete invoice"
    )
    registro.extra["has_invoice"] = True
    registro.extra["emitter_rfc"] = "AAA010101AAA"
    registro.extra["receiver_rfc"] = "XAXX010101000"
    registro.extra["folio"] = "A123"
    registro.extra["subtotal"] = 1000.0
    registro.extra["total"] = 1160.0
    registro.extra["tax_breakdown"] = {"IVA_trasladado": 160.0}
    
    ok, msgs = validate_invoice_fields(registro)
    assert ok is True
    assert len(msgs) == 0


def test_invoice_validator_with_serie_instead_of_folio():
    """Test that validator accepts serie when folio is missing."""
    registro = Registro.create(
        fecha="2024-01-01",
        cuenta="4000",
        cantidad=1000.0,
        descripcion="Sale with invoice serie"
    )
    registro.extra["has_cfdi"] = True
    registro.extra["emitter_rfc"] = "AAA010101AAA"
    registro.extra["receiver_rfc"] = "XAXX010101000"
    registro.extra["serie"] = "A"  # Serie instead of folio
    registro.extra["subtotal"] = 1000.0
    registro.extra["total"] = 1160.0
    registro.extra["tax_breakdown"] = {"IVA": 160.0}
    
    ok, msgs = validate_invoice_fields(registro)
    assert ok is True
    assert len(msgs) == 0


def test_invoice_validator_integrated_with_registro_validate():
    """Test that Registro.validate() calls invoice validators when needed."""
    registro = Registro.create(
        fecha="2024-01-01",
        cuenta="4000",
        cantidad=1000.0,
        descripcion="Sale with invoice"
    )
    registro.extra["has_invoice"] = True
    # Missing all invoice fields
    
    ok, msgs = registro.validate()
    assert ok is False
    # Should have multiple validation errors for missing invoice fields
    assert len(msgs) > 0
    # Check for at least one invoice-related error
    assert any("emitter" in msg.lower() or "receiver" in msg.lower() or 
               "folio" in msg.lower() or "subtotal" in msg.lower() or 
               "total" in msg.lower() or "tax" in msg.lower() for msg in msgs)


def test_invoice_validator_zero_amounts_fail():
    """Test that zero or negative amounts fail validation."""
    registro = Registro.create(
        fecha="2024-01-01",
        cuenta="4000",
        cantidad=1000.0,
        descripcion="Sale with invoice"
    )
    registro.extra["has_invoice"] = True
    registro.extra["emitter_rfc"] = "AAA010101AAA"
    registro.extra["receiver_rfc"] = "XAXX010101000"
    registro.extra["folio"] = "A123"
    registro.extra["subtotal"] = 0.0  # Zero subtotal
    registro.extra["total"] = 0.0  # Zero total
    registro.extra["tax_breakdown"] = {"IVA": 0.0}
    
    ok, msgs = validate_invoice_fields(registro)
    assert ok is False
    assert any("subtotal" in msg.lower() and "mayor" in msg.lower() for msg in msgs)
    assert any("total" in msg.lower() and "mayor" in msg.lower() for msg in msgs)
