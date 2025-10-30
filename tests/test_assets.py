from aqorath.assets import monthly_depreciation_straight
def test_monthly_depr():
    monthly = monthly_depreciation_straight(12000.0, 0.0, 5)
    # 12000 / 5 = 2400 anual => 200 mensual
    assert monthly == 200.0