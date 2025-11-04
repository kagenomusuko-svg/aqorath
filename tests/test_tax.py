"""
Tests for tax calculation engine.
Covers IVA 16%, IVA 0%, IVA exento, retentions, rounding, and edge cases.
"""
from decimal import Decimal
from aqorath.tax import calculate_taxes, calculate_simple_iva, calculate_with_retentions


def test_calculate_taxes_empty():
    """Test calculate_taxes with empty list returns zero values."""
    result = calculate_taxes([])
    assert result["subtotal"] == 0.0
    assert result["iva_trasladado"] == 0.0
    assert result["iva_retenido"] == 0.0
    assert result["isr_retenido"] == 0.0
    assert result["total"] == 0.0


def test_calculate_taxes_iva_16_percent():
    """Test standard IVA 16% calculation."""
    result = calculate_taxes([
        {"amount": 1000, "iva_rate": 16, "description": "Product A"}
    ])
    
    assert result["subtotal"] == 1000.0
    assert result["iva_trasladado"] == 160.0  # 1000 * 0.16
    assert result["total"] == 1160.0  # 1000 + 160
    assert len(result["breakdown"]) == 1
    assert result["breakdown"][0]["iva_trasladado"] == 160.0


def test_calculate_taxes_iva_0_percent():
    """Test IVA 0% (tasa cero) calculation."""
    result = calculate_taxes([
        {"amount": 1000, "iva_type": "tasa_cero", "description": "Zero-rated item"}
    ])
    
    assert result["subtotal"] == 1000.0
    assert result["iva_trasladado"] == 0.0
    assert result["total"] == 1000.0


def test_calculate_taxes_iva_exento():
    """Test IVA exento (exempt) calculation."""
    result = calculate_taxes([
        {"amount": 1000, "iva_type": "exento", "description": "Exempt item"}
    ])
    
    assert result["subtotal"] == 1000.0
    assert result["iva_trasladado"] == 0.0
    assert result["total"] == 1000.0
    assert result["summary"]["IVA_exento"] == 1000.0


def test_calculate_taxes_multiple_lines():
    """Test calculation with multiple line items."""
    result = calculate_taxes([
        {"amount": 1000, "iva_rate": 16, "description": "Item 1"},
        {"amount": 500, "iva_rate": 16, "description": "Item 2"},
        {"amount": 250, "iva_type": "tasa_cero", "description": "Item 3"}
    ])
    
    # Subtotal: 1000 + 500 + 250 = 1750
    assert result["subtotal"] == 1750.0
    # IVA: (1000 * 0.16) + (500 * 0.16) + 0 = 160 + 80 = 240
    assert result["iva_trasladado"] == 240.0
    # Total: 1750 + 240 = 1990
    assert result["total"] == 1990.0
    assert len(result["breakdown"]) == 3


def test_calculate_taxes_with_iva_retenido():
    """Test IVA retention (retenido)."""
    result = calculate_taxes([
        {
            "amount": 10000,
            "iva_rate": 16,
            "iva_retenido_rate": 10.67,  # Common IVA retention rate (2/3 of 16%)
            "description": "Professional services"
        }
    ])
    
    # Subtotal: 10000
    assert result["subtotal"] == 10000.0
    # IVA trasladado: 10000 * 0.16 = 1600
    assert result["iva_trasladado"] == 1600.0
    # IVA retenido: 10000 * 0.1067 = 1067
    assert result["iva_retenido"] == 1067.0
    # Total: 10000 + 1600 - 1067 = 10533
    assert result["total"] == 10533.0


def test_calculate_taxes_with_isr_retenido():
    """Test ISR retention."""
    result = calculate_taxes([
        {
            "amount": 10000,
            "iva_rate": 16,
            "isr_retenido_rate": 10,  # 10% ISR retention
            "description": "Honorarios"
        }
    ])
    
    # Subtotal: 10000
    assert result["subtotal"] == 10000.0
    # IVA: 1600
    assert result["iva_trasladado"] == 1600.0
    # ISR retenido: 10000 * 0.10 = 1000
    assert result["isr_retenido"] == 1000.0
    # Total: 10000 + 1600 - 1000 = 10600
    assert result["total"] == 10600.0


def test_calculate_taxes_with_both_retentions():
    """Test with both IVA and ISR retentions."""
    result = calculate_taxes([
        {
            "amount": 10000,
            "iva_rate": 16,
            "iva_retenido_rate": 10.67,
            "isr_retenido_rate": 10,
            "description": "Services with full retentions"
        }
    ])
    
    assert result["subtotal"] == 10000.0
    assert result["iva_trasladado"] == 1600.0
    assert result["iva_retenido"] == 1067.0
    assert result["isr_retenido"] == 1000.0
    # Total: 10000 + 1600 - 1067 - 1000 = 9533
    assert result["total"] == 9533.0


def test_calculate_taxes_rounding():
    """Test proper rounding to 2 decimals."""
    # Amount that produces non-trivial rounding
    result = calculate_taxes([
        {"amount": 333.33, "iva_rate": 16}
    ])
    
    # IVA should be 333.33 * 0.16 = 53.3328 -> 53.33 (rounded)
    assert result["iva_trasladado"] == 53.33
    assert result["total"] == 386.66  # 333.33 + 53.33


def test_calculate_taxes_rounding_edge_case():
    """Test rounding edge cases (e.g., .005)."""
    # Test ROUND_HALF_UP behavior
    result = calculate_taxes([
        {"amount": 100.005, "iva_rate": 16}
    ])
    
    # Amount: 100.005 -> 100.01 (rounded)
    # IVA: 100.01 * 0.16 = 16.0016 -> 16.00
    assert result["subtotal"] == 100.01
    assert result["iva_trasladado"] == 16.00


def test_calculate_taxes_summary():
    """Test that summary aggregates taxes correctly."""
    result = calculate_taxes([
        {"amount": 1000, "iva_rate": 16},
        {"amount": 500, "iva_rate": 16},
        {"amount": 200, "iva_type": "tasa_cero"},
        {"amount": 100, "iva_type": "exento"}
    ])
    
    summary = result["summary"]
    # IVA 16%: (1000 + 500) * 0.16 = 240
    assert summary["IVA_trasladado_16%"] == 240.0
    # IVA 0%: 0 (tasa_cero)
    assert summary["IVA_trasladado_0%"] == 0.0
    # IVA exento: 100
    assert summary["IVA_exento"] == 100.0


def test_calculate_simple_iva():
    """Test convenience function calculate_simple_iva."""
    result = calculate_simple_iva(1000, rate=16)
    
    assert result["subtotal"] == 1000.0
    assert result["iva"] == 160.0
    assert result["total"] == 1160.0


def test_calculate_simple_iva_zero_rate():
    """Test simple IVA with 0% rate."""
    result = calculate_simple_iva(1000, rate=0)
    
    assert result["subtotal"] == 1000.0
    assert result["iva"] == 0.0
    assert result["total"] == 1000.0


def test_calculate_with_retentions_convenience():
    """Test convenience function calculate_with_retentions."""
    result = calculate_with_retentions(
        amount=10000,
        iva_rate=16,
        iva_retenido_rate=10.67,
        isr_retenido_rate=10
    )
    
    assert result["subtotal"] == 10000.0
    assert result["iva_trasladado"] == 1600.0
    assert result["iva_retenido"] == 1067.0
    assert result["isr_retenido"] == 1000.0
    assert result["total"] == 9533.0


def test_calculate_taxes_mixed_scenarios():
    """Test complex scenario with mixed IVA types and retentions."""
    result = calculate_taxes([
        {"amount": 1000, "iva_rate": 16, "description": "Standard product"},
        {"amount": 500, "iva_type": "tasa_cero", "description": "Zero-rated"},
        {"amount": 200, "iva_type": "exento", "description": "Exempt"},
        {
            "amount": 3000,
            "iva_rate": 16,
            "iva_retenido_rate": 10.67,
            "isr_retenido_rate": 10,
            "description": "Services with retentions"
        }
    ])
    
    # Subtotal: 1000 + 500 + 200 + 3000 = 4700
    assert result["subtotal"] == 4700.0
    # IVA trasladado: (1000 * 0.16) + 0 + 0 + (3000 * 0.16) = 160 + 480 = 640
    assert result["iva_trasladado"] == 640.0
    # IVA retenido: 3000 * 0.1067 = 320.10
    assert result["iva_retenido"] == 320.10
    # ISR retenido: 3000 * 0.10 = 300
    assert result["isr_retenido"] == 300.0
    # Total: 4700 + 640 - 320.10 - 300 = 4719.90
    assert result["total"] == 4719.90


def test_calculate_taxes_breakdown_structure():
    """Test that breakdown has correct structure."""
    result = calculate_taxes([
        {"amount": 1000, "iva_rate": 16, "description": "Test item"}
    ])
    
    assert "breakdown" in result
    assert len(result["breakdown"]) == 1
    
    entry = result["breakdown"][0]
    assert "line" in entry
    assert "description" in entry
    assert "amount" in entry
    assert "iva_type" in entry
    assert "iva_rate" in entry
    assert "iva_trasladado" in entry
    assert "iva_retenido" in entry
    assert "isr_retenido" in entry


def test_calculate_taxes_string_amounts():
    """Test that string amounts are handled correctly."""
    result = calculate_taxes([
        {"amount": "1000.50", "iva_rate": 16}
    ])
    
    assert result["subtotal"] == 1000.50
    assert result["iva_trasladado"] == 160.08  # 1000.50 * 0.16
    assert result["total"] == 1160.58


def test_calculate_taxes_decimal_amounts():
    """Test that Decimal amounts are handled correctly."""
    result = calculate_taxes([
        {"amount": Decimal("1000.50"), "iva_rate": 16}
    ])
    
    assert result["subtotal"] == 1000.50
    assert result["iva_trasladado"] == 160.08
