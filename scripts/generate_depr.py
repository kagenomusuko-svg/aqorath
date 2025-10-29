"""
Utility script to generate depreciation entries for a given year/month.

Usage:
    # monthly for Oct 2025
    python -m scripts.generate_depr 2025 10

    # annual for 2025 (no month param)
    python -m scripts.generate_depr 2025
"""
import sys
from aqorath.storage import init_db
from aqorath.assets import generate_depreciation_entries_for_period

def main(argv):
    if len(argv) < 2:
        print("Usage: python -m scripts.generate_depr YEAR [MONTH]")
        return 1
    year = int(argv[1])
    month = int(argv[2]) if len(argv) >= 3 else None
    init_db()
    ids = generate_depreciation_entries_for_period(year, month)
    print(f"Created {len(ids)} depreciation entries: {ids}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))