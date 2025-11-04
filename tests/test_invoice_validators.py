"""
Tests for invoice/fiscal validators in modelos/registro.py.
Tests both valid and invalid cases for fiscal field validation.
"""
import pytest
from datetime import date
from decimal import Decimal

from modelos.registro import Registro


def test_registro_without_invoice_flag():
    """Test that a regular registro without invoice flag doesn't require fiscal fields."""
    reg = Registro.create(
        fecha="2024-01-01",
        cuenta="1105",
        cantidad=100.0,
        descripcion="Test registro"
    )
    
    ok, msgs = reg.validate()
    assert ok is True
    assert len(msgs) == 0


def test_registro_with_invoice_flag_missing_fields():
    """Test that a registro with has_cfdi flag requires fiscal fields."""
    reg = Registro.create(
        fecha="2024-01-01",
        cuenta="1105",
        cantidad=100.0,
        descripcion="Test invoice"
    )
    reg.extra["has_cfdi"] = True
    
    ok, msgs = reg.validate()
    assert ok is False
    assert len(msgs) > 0
    # Should complain about missing fiscal fields
    assert any("emitter_rfc" in msg.lower() for msg in msgs)
    assert any("receiver_rfc" in msg.lower() for msg in msgs)
    assert any("serie" in msg.lower() for msg in msgs)
    assert any("folio" in msg.lower() for msg in msgs)
    assert any("subtotal" in msg.lower() for msg in msgs)
    assert any("total" in msg.lower() for msg in msgs)
    assert any("tax_breakdown" in msg.lower() for msg in msgs)


def test_registro_with_cfdi_flag_missing_fields():
    """Test that cfdi=True also triggers fiscal validation."""
    reg = Registro.create(
        fecha="2024-01-01",
        cuenta="1105",
        cantidad=100.0,
        descripcion="Test invoice",
        cfdi=True
    )
    
    ok, msgs = reg.validate()
    assert ok is False
    # Should complain about missing metodo_pago and fiscal fields
    assert any("metodo_pago" in msg.lower() or "método de pago" in msg.lower() for msg in msgs)
    assert any("emitter_rfc" in msg.lower() for msg in msgs)


def test_registro_with_valid_fiscal_fields():
    """Test that a registro with all required fiscal fields validates successfully."""
    reg = Registro.create(
        fecha="2024-01-01",
        cuenta="1105",
        cantidad=100.0,
        descripcion="Valid invoice"
    )
    reg.extra.update({
        "has_cfdi": True,
        "emitter_rfc": "ABC123456789",
        "receiver_rfc": "XYZ987654321",
        "serie": "A",
        "folio": "12345",
        "subtotal": 100.0,
        "total": 116.0,
        "tax_breakdown": {"IVA": 16.0}
    })
    
    ok, msgs = reg.validate()
    assert ok is True
    assert len(msgs) == 0


def test_registro_with_invalid_rfc():
    """Test that short RFC values are rejected."""
    reg = Registro.create(
        fecha="2024-01-01",
        cuenta="1105",
        cantidad=100.0,
        descripcion="Invalid RFC"
    )
    reg.extra.update({
        "has_cfdi": True,
        "emitter_rfc": "SHORT",  # Too short
        "receiver_rfc": "XYZ987654321",
        "serie": "A",
        "folio": "12345",
        "subtotal": 100.0,
        "total": 116.0,
        "tax_breakdown": {"IVA": 16.0}
    })
    
    ok, msgs = reg.validate()
    assert ok is False
    assert any("rfc del emisor inválido" in msg.lower() for msg in msgs)


def test_registro_with_zero_subtotal():
    """Test that zero or negative subtotal is rejected."""
    reg = Registro.create(
        fecha="2024-01-01",
        cuenta="1105",
        cantidad=100.0,
        descripcion="Zero subtotal"
    )
    reg.extra.update({
        "has_cfdi": True,
        "emitter_rfc": "ABC123456789",
        "receiver_rfc": "XYZ987654321",
        "serie": "A",
        "folio": "12345",
        "subtotal": 0.0,  # Invalid
        "total": 0.0,
        "tax_breakdown": {"IVA": 0.0}
    })
    
    ok, msgs = reg.validate()
    assert ok is False
    assert any("subtotal debe ser mayor a cero" in msg.lower() for msg in msgs)
    assert any("total debe ser mayor a cero" in msg.lower() for msg in msgs)


def test_registro_with_invalid_subtotal_type():
    """Test that non-numeric subtotal is rejected."""
    reg = Registro.create(
        fecha="2024-01-01",
        cuenta="1105",
        cantidad=100.0,
        descripcion="Invalid subtotal type"
    )
    reg.extra.update({
        "has_cfdi": True,
        "emitter_rfc": "ABC123456789",
        "receiver_rfc": "XYZ987654321",
        "serie": "A",
        "folio": "12345",
        "subtotal": "invalid",  # Not a number
        "total": 116.0,
        "tax_breakdown": {"IVA": 16.0}
    })
    
    ok, msgs = reg.validate()
    assert ok is False
    assert any("subtotal inválido" in msg.lower() for msg in msgs)


def test_validate_fiscal_fields_directly():
    """Test the validate_fiscal_fields method directly."""
    reg = Registro.create(
        fecha="2024-01-01",
        cuenta="1105",
        cantidad=100.0,
        descripcion="Test"
    )
    
    # Without fiscal fields
    reg.extra["has_cfdi"] = True
    ok, msgs = reg.validate_fiscal_fields()
    assert ok is False
    assert len(msgs) == 7  # 7 required fields
    
    # With all valid fields
    reg.extra.update({
        "emitter_rfc": "ABC123456789",
        "receiver_rfc": "XYZ987654321",
        "serie": "A",
        "folio": "12345",
        "subtotal": 100.0,
        "total": 116.0,
        "tax_breakdown": {"IVA": 16.0}
    })
    ok, msgs = reg.validate_fiscal_fields()
    assert ok is True
    assert len(msgs) == 0


def test_registro_with_has_invoice_flag():
    """Test that has_invoice flag also triggers fiscal validation."""
    reg = Registro.create(
        fecha="2024-01-01",
        cuenta="1105",
        cantidad=100.0,
        descripcion="Test invoice"
    )
    reg.extra["has_invoice"] = True
    
    ok, msgs = reg.validate()
    assert ok is False
    assert len(msgs) > 0
    # Should complain about missing fiscal fields
    assert any("emitter_rfc" in msg.lower() for msg in msgs)


def test_registro_fiscal_with_all_fields_valid():
    """Complete test with all fiscal fields properly set."""
    reg = Registro.create(
        fecha="2024-06-15",
        cuenta="4101",
        cantidad=1000.0,
        descripcion="Venta con factura",
        cfdi=True
    )
    reg.extra.update({
        "metodo_pago": "PUE",  # Required for cfdi=True
        "has_cfdi": True,
        "emitter_rfc": "XAXX010101000",
        "receiver_rfc": "VECJ880128KM5",
        "serie": "A",
        "folio": "001234",
        "subtotal": Decimal("1000.00"),
        "total": Decimal("1160.00"),
        "tax_breakdown": {
            "IVA_16": Decimal("160.00")
        }
    })
    
    ok, msgs = reg.validate()
    assert ok is True
    assert len(msgs) == 0
