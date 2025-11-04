"""
Tests for tax calculation engine (aqorath/tax.py).
Tests IVA 16%, 0%, exento, rounding, and multiple lines.
"""
import pytest
from decimal import Decimal

from aqorath.tax import (
    calculate_taxes,
    calculate_iva_16,
    calculate_iva_retencion,
    calculate_isr_retencion,
    split_amount_with_iva,
    validate_tax_calculation
)


def test_calculate_taxes_single_line_iva_16():
    """Test calculate_taxes with a single line at 16% IVA."""
    line_items = [
        {"amount": 1000, "iva_rate": 16}
    ]
    
    result = calculate_taxes(line_items)
    
    assert result["subtotal"] == 1000.0
    assert result["iva_trasladado"] == 160.0
    assert result["iva_retenido"] == 0.0
    assert result["isr_retenido"] == 0.0
    assert result["total"] == 1160.0
    assert len(result["lines"]) == 1


def test_calculate_taxes_single_line_iva_0():
    """Test calculate_taxes with a single line at 0% IVA."""
    line_items = [
        {"amount": 500, "iva_rate": 0}
    ]
    
    result = calculate_taxes(line_items)
    
    assert result["subtotal"] == 500.0
    assert result["iva_trasladado"] == 0.0
    assert result["total"] == 500.0


def test_calculate_taxes_single_line_exento():
    """Test calculate_taxes with a single line exempt from IVA (no iva_rate)."""
    line_items = [
        {"amount": 300}
    ]
    
    result = calculate_taxes(line_items)
    
    assert result["subtotal"] == 300.0
    assert result["iva_trasladado"] == 0.0
    assert result["total"] == 300.0


def test_calculate_taxes_multiple_lines():
    """Test calculate_taxes with multiple lines at different rates."""
    line_items = [
        {"amount": 1000, "iva_rate": 16, "description": "Product A"},
        {"amount": 500, "iva_rate": 0, "description": "Product B"},
        {"amount": 200, "description": "Exempt product"}
    ]
    
    result = calculate_taxes(line_items)
    
    assert result["subtotal"] == 1700.0
    assert result["iva_trasladado"] == 160.0  # Only first line
    assert result["total"] == 1860.0
    assert len(result["lines"]) == 3


def test_calculate_taxes_with_iva_retencion():
    """Test calculate_taxes with IVA retention."""
    line_items = [
        {
            "amount": 1000,
            "iva_rate": 16,
            "iva_retencion_rate": 10.67  # 2/3 of 16%
        }
    ]
    
    result = calculate_taxes(line_items)
    
    assert result["subtotal"] == 1000.0
    assert result["iva_trasladado"] == 160.0
    assert result["iva_retenido"] == 106.7
    # Total = 1000 + 160 - 106.7 = 1053.3
    assert result["total"] == 1053.3


def test_calculate_taxes_with_isr_retencion():
    """Test calculate_taxes with ISR retention."""
    line_items = [
        {
            "amount": 1000,
            "iva_rate": 16,
            "isr_retencion_rate": 10  # 10% ISR for professional services
        }
    ]
    
    result = calculate_taxes(line_items)
    
    assert result["subtotal"] == 1000.0
    assert result["iva_trasladado"] == 160.0
    assert result["isr_retenido"] == 100.0
    # Total = 1000 + 160 - 100 = 1060
    assert result["total"] == 1060.0


def test_calculate_taxes_with_all_retentions():
    """Test calculate_taxes with both IVA and ISR retentions."""
    line_items = [
        {
            "amount": 10000,
            "iva_rate": 16,
            "iva_retencion_rate": 10.67,
            "isr_retencion_rate": 10,
            "description": "Professional services"
        }
    ]
    
    result = calculate_taxes(line_items)
    
    assert result["subtotal"] == 10000.0
    assert result["iva_trasladado"] == 1600.0
    assert result["iva_retenido"] == 1067.0
    assert result["isr_retenido"] == 1000.0
    # Total = 10000 + 1600 - 1067 - 1000 = 9533
    assert result["total"] == 9533.0


def test_calculate_taxes_rounding():
    """Test that taxes are rounded to 2 decimals properly."""
    line_items = [
        {"amount": 100.33, "iva_rate": 16}
    ]
    
    result = calculate_taxes(line_items)
    
    # 100.33 * 0.16 = 16.0528 -> should round to 16.05
    assert result["iva_trasladado"] == 16.05
    assert result["total"] == 116.38


def test_calculate_iva_16_helper():
    """Test the calculate_iva_16 helper function."""
    iva = calculate_iva_16(1000)
    assert iva == Decimal("160.00")
    
    iva = calculate_iva_16(100.33)
    assert iva == Decimal("16.05")


def test_calculate_iva_retencion_helper():
    """Test the calculate_iva_retencion helper function."""
    ret = calculate_iva_retencion(1000)
    assert ret == Decimal("106.70")  # 1000 * 10.67 / 100
    
    ret = calculate_iva_retencion(1000, rate=16)
    assert ret == Decimal("160.00")


def test_calculate_isr_retencion_helper():
    """Test the calculate_isr_retencion helper function."""
    ret = calculate_isr_retencion(1000, rate=10)
    assert ret == Decimal("100.00")
    
    ret = calculate_isr_retencion(5000, rate=1.25)  # Rent
    assert ret == Decimal("62.50")


def test_split_amount_with_iva():
    """Test splitting a total amount that includes IVA."""
    result = split_amount_with_iva(1160)
    
    assert result["subtotal"] == Decimal("1000.00")
    assert result["iva"] == Decimal("160.00")
    assert result["total"] == Decimal("1160")


def test_split_amount_with_iva_custom_rate():
    """Test splitting with a custom IVA rate."""
    result = split_amount_with_iva(1080, iva_rate=8)
    
    # 1080 / 1.08 = 1000
    assert result["subtotal"] == Decimal("1000.00")
    assert result["iva"] == Decimal("80.00")


def test_validate_tax_calculation():
    """Test the validate_tax_calculation helper."""
    # Valid calculation
    assert validate_tax_calculation(1000, 160, 1160) is True
    
    # Invalid calculation (off by more than tolerance)
    assert validate_tax_calculation(1000, 160, 1200) is False
    
    # Within tolerance (default 0.02)
    assert validate_tax_calculation(1000, 160, 1160.01) is True
    assert validate_tax_calculation(1000, 160, 1160.03) is False


def test_calculate_taxes_empty_lines():
    """Test calculate_taxes with empty line items."""
    result = calculate_taxes([])
    
    assert result["subtotal"] == 0.0
    assert result["iva_trasladado"] == 0.0
    assert result["total"] == 0.0
    assert len(result["lines"]) == 0


def test_calculate_taxes_with_decimals():
    """Test calculate_taxes with Decimal inputs."""
    line_items = [
        {"amount": Decimal("1000.00"), "iva_rate": 16}
    ]
    
    result = calculate_taxes(line_items)
    
    assert result["subtotal"] == 1000.0
    assert result["iva_trasladado"] == 160.0


def test_calculate_taxes_invalid_amount():
    """Test calculate_taxes with invalid amount (should default to 0)."""
    line_items = [
        {"amount": "invalid", "iva_rate": 16}
    ]
    
    result = calculate_taxes(line_items)
    
    assert result["subtotal"] == 0.0
    assert result["iva_trasladado"] == 0.0


def test_calculate_taxes_multiple_lines_complex():
    """Test a complex scenario with multiple lines and different tax rates."""
    line_items = [
        {
            "amount": 5000,
            "iva_rate": 16,
            "description": "Consulting services"
        },
        {
            "amount": 3000,
            "iva_rate": 16,
            "iva_retencion_rate": 10.67,
            "isr_retencion_rate": 10,
            "description": "Professional fees"
        },
        {
            "amount": 2000,
            "iva_rate": 0,
            "description": "Books (0% IVA)"
        }
    ]
    
    result = calculate_taxes(line_items)
    
    # Subtotal: 5000 + 3000 + 2000 = 10000
    assert result["subtotal"] == 10000.0
    
    # IVA trasladado: (5000 * 0.16) + (3000 * 0.16) + 0 = 800 + 480 = 1280
    assert result["iva_trasladado"] == 1280.0
    
    # IVA retenido: only on second line = 3000 * 0.1067 = 320.1
    assert result["iva_retenido"] == 320.1
    
    # ISR retenido: only on second line = 3000 * 0.10 = 300
    assert result["isr_retenido"] == 300.0
    
    # Total = 10000 + 1280 - 320.1 - 300 = 10659.9
    assert result["total"] == 10659.9
    
    assert len(result["lines"]) == 3
