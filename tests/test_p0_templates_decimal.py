"""
P0-2 TEST: Verify that template expressions use Decimal, not float.
"""

import pytest
from decimal import Decimal
from aqorath.templates import (
    fixed_amount_expr, base_amount_expr, percent_expr,
    total_with_vat_expr, gross_base_expr, gross_vat_expr,
    net_amount_expr, net_amount_dual_expr
)


def test_template_expressions_return_decimal():
    """
    Verify that all template expression functions return Decimal, not float.
    """
    # Test fixed_amount_expr
    expr = fixed_amount_expr(100.5)
    result = expr(999, {})
    assert isinstance(result, Decimal), f"fixed_amount_expr returned {type(result)}, expected Decimal"
    assert result == Decimal("100.5"), f"fixed_amount_expr value wrong: {result}"
    
    # Test base_amount_expr
    expr = base_amount_expr()
    result = expr(Decimal("123.45"), {})
    assert isinstance(result, Decimal), f"base_amount_expr returned {type(result)}, expected Decimal"
    
    # Test percent_expr
    expr = percent_expr(0.1)
    result = expr(Decimal("1000"), {})
    assert isinstance(result, Decimal), f"percent_expr returned {type(result)}, expected Decimal"
    assert result == Decimal("100.00"), f"percent_expr calculation wrong: {result}"
    
    # Test total_with_vat_expr
    expr = total_with_vat_expr("vat_rate", amount_is_net=True)
    result = expr(Decimal("1000"), {"vat_rate": 0.16})
    assert isinstance(result, Decimal), f"total_with_vat_expr returned {type(result)}, expected Decimal"
    assert result == Decimal("1160.00"), f"total_with_vat_expr calculation wrong: {result}"
    
    # Test gross_base_expr
    expr = gross_base_expr("vat_rate")
    result = expr(Decimal("1160"), {"vat_rate": 0.16})
    assert isinstance(result, Decimal), f"gross_base_expr returned {type(result)}, expected Decimal"
    # 1160 / 1.16 = 1000
    assert result == Decimal("1000.00"), f"gross_base_expr calculation wrong: {result}"
    
    # Test gross_vat_expr
    expr = gross_vat_expr("vat_rate")
    result = expr(Decimal("1160"), {"vat_rate": 0.16})
    assert isinstance(result, Decimal), f"gross_vat_expr returned {type(result)}, expected Decimal"
    # 1160 - 1000 = 160
    assert result == Decimal("160.00"), f"gross_vat_expr calculation wrong: {result}"
    
    # Test net_amount_expr
    expr = net_amount_expr(0.15)
    result = expr(Decimal("1000"), {})
    assert isinstance(result, Decimal), f"net_amount_expr returned {type(result)}, expected Decimal"
    # 1000 * (1 - 0.15) = 850
    assert result == Decimal("850.00"), f"net_amount_expr calculation wrong: {result}"
    
    # Test net_amount_dual_expr
    expr = net_amount_dual_expr(0.15, 0.0275)
    result = expr(Decimal("1000"), {})
    assert isinstance(result, Decimal), f"net_amount_dual_expr returned {type(result)}, expected Decimal"
    # 1000 * (1 - 0.15 - 0.0275) = 822.5
    assert result == Decimal("822.50"), f"net_amount_dual_expr calculation wrong: {result}"


def test_no_decimal_float_loss():
    """
    Verify that Decimal values are not converted to float and back.
    """
    # Create an expression that should preserve exactness
    expr = percent_expr(0.1)
    
    # Test with a value that has float representation issues
    # 0.1 + 0.2 should equal 0.3 exactly with Decimal, not 0.30000000000000004 with float
    amount = Decimal("0.1") + Decimal("0.2")  # Should be exactly 0.3
    result = expr(amount, {})
    
    # percent_expr(0.1) of 0.3 should be 0.03 exactly
    expected = Decimal("0.03")
    assert result == expected, f"Expected {expected}, got {result} (float loss)"
    assert "000000000" not in str(result), f"Decimal contains float artifacts: {result}"
