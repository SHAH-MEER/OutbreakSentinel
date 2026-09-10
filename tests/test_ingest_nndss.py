import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.ingest_nndss import clean  # noqa: E402


def test_clean_fills_missing_m1_as_zero():
    rows = [{"states": "Texas", "label": "Measles, Indigenous", "year": "2025", "week": "1", "m1_flag": "-"}]
    cleaned = clean(rows)
    assert cleaned[0]["m1"] == 0.0


def test_clean_casts_numeric_and_year_week():
    rows = [
        {
            "states": "Texas",
            "label": "Measles, Indigenous",
            "year": "2025",
            "week": "15",
            "m1": "50",
            "m2": "50",
            "m3": "229",
            "m4": "0",
        }
    ]
    cleaned = clean(rows)[0]
    assert cleaned["m1"] == 50.0
    assert cleaned["year"] == 2025
    assert cleaned["week"] == 15
    assert isinstance(cleaned["year"], int)
