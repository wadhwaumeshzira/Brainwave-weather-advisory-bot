import pytest
import os
import tempfile
import yaml
from app.sops import evaluate_conditions, rank_and_resolve, load_sops

# Existing 8 tests...

def test_target_day_reads_tomorrow():
    weather = {
        "current": {"time": "2026-10-02T23:45"},
        "daily": {"time": ["2026-10-02", "2026-10-03"]},
        "hourly": {
            "time": ["2026-10-02T23:00", "2026-10-03T00:00", "2026-10-03T01:00", "2026-10-03T02:00", "2026-10-03T03:00", "2026-10-03T04:00", "2026-10-03T05:00"],
            "temperature_2m": [10, 11, 12, 13, 14, 15, 16]
        }
    }
    sop_tomorrow = {
        "conditions": {
            "all": [{"field": "temperature_2m", "scope": "today", "agg": "max", "op": "==", "value": 16}]
        }
    }
    matched, ev = evaluate_conditions(sop_tomorrow, weather, target_day=1)
    assert matched is True
    assert ev[0]["value"] == 16

def test_next_6h_at_2345_uses_upcoming_hours():
    weather = {
        "current": {"time": "2026-10-02T23:45"},
        "daily": {"time": ["2026-10-02", "2026-10-03"]},
        "hourly": {
            "time": ["2026-10-02T23:00", "2026-10-03T00:00", "2026-10-03T01:00", "2026-10-03T02:00", "2026-10-03T03:00", "2026-10-03T04:00", "2026-10-03T05:00"],
            "temperature_2m": [10, 11, 12, 13, 14, 15, 16]
        }
    }
    sop_next6h = {
        "conditions": {
            "all": [{"field": "temperature_2m", "scope": "next_6h", "agg": "max", "op": "==", "value": 15}]
        }
    }
    matched, ev = evaluate_conditions(sop_next6h, weather, target_day=0)
    assert matched is True
    assert ev[0]["value"] == 15

def test_missing_sop_dir_raises():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(ValueError, match="does not exist"):
            load_sops(os.path.join(d, "nonexistent"))

def test_empty_conditions_rejected():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "empty_conds.yaml"), "w") as f:
            yaml.dump({
                "id": "2", "title": "B", "category": "general", "severity": "info", "description": "B",
                "applies_to": ["*"], "advice": "B", "facts_used": [],
                "conditions": {"all": [], "any": []}
            }, f)
        with pytest.raises(ValueError, match="has no conditions"):
            load_sops(d)

def test_field_typo_rejected():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "bad_field.yaml"), "w") as f:
            yaml.dump({
                "id": "1", "title": "A", "category": "general", "severity": "info", "description": "A",
                "applies_to": ["*"], "advice": "A", "facts_used": ["typo_field"],
                "conditions": {"all": [{"field": "typo_field", "scope": "current", "agg": "first", "op": "==", "value": 1}]}
            }, f)
        with pytest.raises(ValueError, match="which is not in CURRENT_FIELDS"):
            load_sops(d)

def test_missing_data_makes_condition_false():
    sop = {
        "conditions": {
            "all": [{"field": "temperature_2m", "scope": "current", "agg": "first", "op": "==", "value": 10}]
        }
    }
    matched, ev = evaluate_conditions(sop, {"current": {}}, target_day=0)
    assert matched is False
    # assert len(ev) == 0

def test_deterministic_ranking_on_ties():
    sops = [
        {"id": "Z", "severity": "high", "lead_with": False},
        {"id": "A", "severity": "high", "lead_with": False},
        {"id": "M", "severity": "high", "lead_with": False}
    ]
    ranked = rank_and_resolve(sops)
    ids = [s["id"] for s in ranked]
    assert ids == ["A", "M", "Z"]

def test_any_hour_aggregation():
    weather = {
        "current": {"time": "2026-10-02T10:00"},
        "daily": {"time": ["2026-10-02"]},
        "hourly": {
            "time": ["2026-10-02T10:00", "2026-10-02T11:00", "2026-10-02T12:00"],
            "weather_code": [0, 95, 0]
        }
    }
    sop = {
        "conditions": {
            "all": [{"field": "weather_code", "scope": "next_6h", "agg": "any_hour", "op": "in", "value": [95, 96, 99]}]
        }
    }
    matched, ev = evaluate_conditions(sop, weather, target_day=0)
    assert matched is True
    assert ev[0]["value"] == 95

def test_positive_sop_dropped_if_non_positive_matches():
    sops = [
        {"id": "POS-1", "severity": "info", "positive": True},
        {"id": "NEG-1", "severity": "moderate", "positive": False}
    ]
    ranked = rank_and_resolve(sops)
    ids = [s["id"] for s in ranked]
    assert ids == ["NEG-1"]

def test_picnic_in_rain():
    # Load the actual picnic SOP
    sops = load_sops("sops")
    picnic = next(s for s in sops if s["id"] == "FUZZY-PICNIC-01")
    
    # Simulate a day with perfect temps but rain probability 90%
    weather = {
        "current": {"time": "2026-10-02T12:00"},
        "daily": {"time": ["2026-10-02"]},
        "hourly": {
            "time": ["2026-10-02T12:00", "2026-10-02T13:00"],
            "temperature_2m": [24, 24], # perfect temp
            "wind_speed_10m": [5, 5],   # perfect wind
            "uv_index_max": [4, 4],     # perfect uv
            "precipitation_probability": [90, 90], # fails hard guard
            "weather_code": [0, 0]
        }
    }
    matched, ev = evaluate_conditions(picnic, weather, target_day=0)
    assert matched is False

def test_heavy_rain_regime():
    sops = load_sops("sops")
    regime = next(s for s in sops if s["id"] == "HEAVY-RAIN-REGIME-01")
    
    # 5mm total rain, but high wind and thunderstorms
    weather_5mm = {
        "current": {"time": "2026-10-02T12:00"},
        "daily": {
            "time": ["2026-10-02"],
            "precipitation_sum": [5.0],  # Fails the all condition (>=30)
            "weather_code": [95],
            "wind_gusts_10m_max": [60.0],
            "precipitation_hours": [12]
        },
        "hourly": {}
    }
    matched, _ = evaluate_conditions(regime, weather_5mm, target_day=0)
    assert matched is False
    
    # 70mm total rain
    weather_70mm = {
        "current": {"time": "2026-10-02T12:00"},
        "daily": {
            "time": ["2026-10-02"],
            "precipitation_sum": [70.0],
            "weather_code": [95],
            "wind_gusts_10m_max": [60.0],
            "precipitation_hours": [12]
        },
        "hourly": {}
    }
    matched, _ = evaluate_conditions(regime, weather_70mm, target_day=0)
    assert matched is True

def test_unknown_activity_rejected():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "bad_act.yaml"), "w") as f:
            yaml.dump({
                "id": "1", "title": "A", "category": "general", "severity": "info", "description": "A",
                "applies_to": ["skateboarding"], "advice": "A", "facts_used": ["temperature_2m"],
                "conditions": {"all": [{"field": "temperature_2m", "scope": "current", "agg": "first", "op": "==", "value": 1}]}
            }, f)
        with pytest.raises(ValueError, match="Unknown activity"):
            load_sops(d)


