import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.eda import build_panel, normalize_region_casing  # noqa: E402


def test_normalize_region_casing_merges_case_variants():
    # Mirrors the real CDC NNDSS bug: same region reported as "TEXAS"
    # through 2024, "Texas" from 2025 on. Without normalizing, these are
    # two different regions to every downstream groupby.
    panel = pd.DataFrame(
        [
            {"region": "TEXAS", "disease": "Measles, Indigenous", "year": 2024, "week": 52, "cases": 0.0},
            {"region": "Texas", "disease": "Measles, Indigenous", "year": 2025, "week": 1, "cases": 0.0},
            {"region": "Texas", "disease": "Measles, Indigenous", "year": 2025, "week": 15, "cases": 50.0},
        ]
    )
    normalized = normalize_region_casing(panel)
    assert normalized["region"].nunique() == 1
    # Canonicalizes to the casing used in the most recent week.
    assert set(normalized["region"]) == {"Texas"}


def test_normalize_region_casing_leaves_consistent_regions_alone():
    panel = pd.DataFrame(
        [
            {"region": "California", "disease": "Mumps", "year": 2023, "week": 1, "cases": 1.0},
            {"region": "California", "disease": "Mumps", "year": 2024, "week": 1, "cases": 2.0},
        ]
    )
    normalized = normalize_region_casing(panel)
    assert list(normalized["region"]) == ["California", "California"]


def test_build_panel_produces_one_series_across_a_casing_change():
    df = pd.DataFrame(
        [
            {"states": "TEXAS", "label": "Measles, Indigenous", "year": "2024", "week": "52", "m1": "0"},
            {"states": "Texas", "label": "Measles, Indigenous", "year": "2025", "week": "1", "m1": "0"},
        ]
    )
    panel = build_panel(df)
    assert panel["region"].nunique() == 1
    assert len(panel[panel["region"] == "Texas"]) == 2
