import pytest
import os
from app.graph import graph
from app.validators import check_citations_valid, check_numbers_grounded
from app.nodes import template_reply

def test_heavy_rain_fixture_matches_both_HEAVY_RAIN_REGIME_01_and_WIND_CYCLE_01_with_regime_first():
    """
    (a) heavy-rain fixture matches BOTH HEAVY-RAIN-REGIME-01 and WIND-CYCLE-01 for cycling 
    with the regime first, even when the fake router returns nothing.
    """
    os.environ["WEATHER_MODE"] = "fixture"
    os.environ["WEATHER_FIXTURE"] = "bhopal_heavyrain"
    
    # We simulate a fake router returning nothing by directly invoking evaluate_sops 
    # but providing an empty candidate list in the state. Wait, the rule is the router 
    # returns candidate_sops. evaluate_sops evaluates them.
    # Actually, the deterministic determinism is that `route_sops` passes ALL applicable SOPs 
    # in `candidate_sops` even if LLM returns empty!
    from app.nodes import route_sops, evaluate_sops, fetch_weather_node
    
    state = {
        "user_message": "cycling", 
        "last_activity": "cycling",
        "last_location": "Bhopal",
        "lat": 23.25,
        "lon": 77.41,
        "target_day": 0
    }
    
    state.update(fetch_weather_node(state))
    
    # Mock LLM inside route_sops to return empty
    from unittest.mock import patch, MagicMock
    from app.nodes import CandidateList
    mock_model = MagicMock()
    mock_model.with_structured_output.return_value.invoke.return_value = CandidateList(sop_ids=[])
    
    with patch("app.nodes.get_llm", return_value=mock_model):
        route_state = route_sops(state)
        
    state.update(route_state)
    eval_state = evaluate_sops(state)
    
    # Check that they match
    matched_ids = [s["id"] for s in eval_state["matched_sops"]]
    assert "HEAVY-RAIN-REGIME-01" in matched_ids
    assert "WIND-CYCLE-01" in matched_ids
    
    # Now run resolve_conflicts to rank them
    from app.nodes import resolve_conflicts
    state.update(eval_state)
    final_state = resolve_conflicts(state)
    
    ranked_ids = [s["id"] for s in final_state["matched_sops"]]
    # Regime MUST be first
    assert ranked_ids[0] == "HEAVY-RAIN-REGIME-01"

def test_citation_extractor_on_THUNDERSTORM_01_HEAVY_RAIN_REGIME_01_and_SOP_999():
    """
    (b) citation extractor on THUNDERSTORM-01, HEAVY-RAIN-REGIME-01 and SOP-999
    """
    reply = "It is dangerous (THUNDERSTORM-01) and (HEAVY-RAIN-REGIME-01). Ignore (SOP-999)."
    matched_ids = ["THUNDERSTORM-01", "HEAVY-RAIN-REGIME-01"]
    all_ids = ["THUNDERSTORM-01", "HEAVY-RAIN-REGIME-01", "WIND-CYCLE-01"]
    
    # This should fail because SOP-999 is cited but not matched
    assert check_citations_valid(reply, matched_ids, all_ids) is False
    
    # If we remove SOP-999, it should pass
    reply2 = "It is dangerous (THUNDERSTORM-01) and (HEAVY-RAIN-REGIME-01)."
    assert check_citations_valid(reply2, matched_ids, all_ids) is True

def test_reply_with_SOP_threshold_number_passes_invented_fails():
    """
    (c) a reply containing an SOP-threshold number like 40 passes, a reply with an invented number 77 fails
    """
    facts = {"temp": 25.0}
    sops = [{
        "id": "WIND-01",
        "advice": "Gusts above 40 km/h make it unsafe.",
        "conditions": {"all": [{"field": "wind_gusts_10m", "value": 40}]}
    }]
    
    # 40 is from SOP, 25 is from facts. Should pass.
    ok, rep, not_found = check_numbers_grounded("Temp is 25 and gusts are 40.", facts, sops)
    assert ok is True
    
    # 77 is invented. Should fail.
    ok, rep, not_found = check_numbers_grounded("Temp is 25 and gusts are 77.", facts, sops)
    assert ok is False
    assert 77.0 in not_found

def test_when_fake_llm_fails_twice_final_reply_contains_evidence_and_advice():
    """
    (d) when the fake LLM fails twice, the final reply contains the real evidence numbers and the SOP advice.
    """
    state = {
        "matched_sops": [
            {"id": "WIND-CYCLE-01", "advice": "Avoid riding today."}
        ],
        "facts_dict": {
            "target_rain_sum": 10.5,
            "target_gusts_max": 45.0,
            "target_temp_max": 28.0
        },
        "target_day": 0
    }
    
    res = template_reply(state)
    reply = res["reply"]
    
    # Contains SOP advice
    assert "WIND-CYCLE-01" in reply
    assert "Avoid riding today." in reply
    
    # Contains Evidence numbers
    assert "10.5" in reply
    assert "45.0" in reply
    assert "28.0" in reply
