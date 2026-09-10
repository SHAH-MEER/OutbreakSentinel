import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import data as api_data  # noqa: E402


def _synthetic_panel() -> pd.DataFrame:
    rows = []
    for i, week in enumerate(range(1, 22)):
        rows.append(
            {"region": "Texas", "disease": "Measles, Indigenous", "year": 2024, "week": week, "cases": 80.0 if week == 21 else 2.0}
        )
    for week in range(1, 11):
        rows.append({"region": "California", "disease": "Mumps", "year": 2024, "week": week, "cases": 5.0})
    return pd.DataFrame(rows)


@pytest.fixture(autouse=True)
def _patch_panel(monkeypatch):
    # _panel is replaced outright (monkeypatch restores the original,
    # real lru_cache-wrapped function automatically after the test) — but
    # _dev_alerts itself isn't replaced, just fed different data each
    # test via the patched _panel, so its own cache needs clearing on
    # both sides or results leak between tests.
    api_data._dev_alerts.cache_clear()
    monkeypatch.setattr(api_data, "_panel", lambda: _synthetic_panel())
    yield
    api_data._dev_alerts.cache_clear()


def test_get_series_returns_full_history_with_anomaly_overlay():
    result = api_data.get_series("Texas", "Measles, Indigenous")
    assert result is not None
    assert len(result["weeks"]) == 21
    assert result["cases"][-1] == 80.0
    assert any(result["anomaly"])


def test_get_series_returns_none_for_unknown_series():
    assert api_data.get_series("Nowhere", "Nothing") is None


def test_list_regions_and_diseases():
    out = api_data.list_regions_and_diseases()
    assert out["regions"] == ["California", "Texas"]
    assert out["diseases"] == ["Measles, Indigenous", "Mumps"]


def test_get_alerts_filters_by_region_and_disease():
    alerts = api_data.get_alerts()
    assert any(a["region"] == "Texas" for a in alerts)

    filtered = api_data.get_alerts(region="California")
    assert all(a["region"] == "California" for a in filtered)

    filtered = api_data.get_alerts(disease="Mumps")
    assert all(a["disease"] == "Mumps" for a in filtered)


def test_get_alerts_min_severity_filter():
    alerts = api_data.get_alerts(min_severity=0.0)
    high_severity = api_data.get_alerts(min_severity=1e9)
    assert len(high_severity) <= len(alerts)
    assert all(a["severity"] >= 1e9 for a in high_severity)
