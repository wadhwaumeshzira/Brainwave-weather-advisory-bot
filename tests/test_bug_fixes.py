import os
import pytest
from app.sops import load_sops
from app.nodes import parse_intent, Intent
from app.state import GraphState
from unittest.mock import patch

def test_parse_intent_prompt_contains_definitions():
    class DummyLLM:
        def __init__(self):
            self.prompts_seen = []
        def invoke(self, prompt, **kwargs):
            self.prompts_seen.append(str(prompt))
            return Intent(location="Bhopal", activity="cycling", target_day=0, in_scope=True)
        def with_structured_output(self, schema):
            return self

    llm = DummyLLM()
    with patch("app.nodes.get_llm", return_value=llm):
        state = {"user_message": "is it safe to bike to work in Bhopal today?"}
        res = parse_intent(state)
        
        prompt = llm.prompts_seen[0]
        assert "cycling = bicycle, cycle, bike" in prompt
        assert "commute = going to work" in prompt
        assert "scooter/motorbike" in prompt

def test_picnic_sop_skips_heavy_rain(monkeypatch):
    from app.graph import graph
    monkeypatch.setenv("WEATHER_MODE", "fixture")
    monkeypatch.setenv("WEATHER_FIXTURE", "bhopal_heavyrain")
    
    config = {"configurable": {"thread_id": "test_picnic_skips"}}
    state = {"user_message": "picnic in bhopal", "last_activity": "picnic", "candidate_sops": ["FUZZY-PICNIC-01"], "target_day": 0}
    
    from app.weather import geocode, fetch_weather
    lat, lon, _ = geocode("bhopal")
    state["weather"] = fetch_weather(lat, lon)
    
    from app.nodes import evaluate_sops
    res = evaluate_sops(state)
    
    matched_ids = [s["id"] for s in res["matched_sops"]]
    assert "FUZZY-PICNIC-01" not in matched_ids

def test_load_sops_rejects_missing_field_scope(tmp_path):
    sops_dir = tmp_path / "sops"
    sops_dir.mkdir()
    
    bad_yaml = """
id: BAD-01
title: a
category: general
severity: info
description: a
applies_to: ['*']
conditions:
  all:
    - {field: wind_gusts_10m_max, agg: max, scope: current, op: ">", value: 40}
advice: a
facts_used: []
    """
    (sops_dir / "bad.yaml").write_text(bad_yaml)
    
    with pytest.raises(ValueError, match="is not in CURRENT_FIELDS"):
        load_sops(str(sops_dir))

def test_load_sops_rejects_missing_field_next_6h(tmp_path):
    sops_dir = tmp_path / "sops2"
    sops_dir.mkdir()
    
    bad_yaml = """
id: BAD-02
title: a
category: general
severity: info
description: a
applies_to: ['*']
conditions:
  all:
    - {field: wind_gusts_10m_max, agg: max, scope: next_6h, op: ">", value: 40}
advice: a
facts_used: [wind_gusts_10m_max]
    """
    (sops_dir / "bad.yaml").write_text(bad_yaml)
    
    with pytest.raises(ValueError, match="is not in HOURLY_FIELDS"):
        load_sops(str(sops_dir))

def test_load_sops_rejects_missing_field_no_scope(tmp_path):
    sops_dir = tmp_path / "sops3"
    sops_dir.mkdir()
    
    # Missing scope defaults to current
    bad_yaml = """
id: BAD-03
title: a
category: general
severity: info
description: a
applies_to: ['*']
conditions:
  all:
    - {field: precipitation_probability, agg: max, op: ">", value: 40}
advice: a
facts_used: [precipitation_probability]
    """
    (sops_dir / "bad.yaml").write_text(bad_yaml)
    
    with pytest.raises(ValueError, match="is not in CURRENT_FIELDS"):
        load_sops(str(sops_dir))
