import pytest
from app.validators import check_citations_valid, check_numbers_grounded, extract_numbers
from app.state import GraphState
from app.nodes import validate_reply, template_reply

def test_extract_numbers():
    text = "The temperature is 31.5 and wind is 12 km/h. It's 6 pm right now. Check WIND-CYCLE-01."
    nums = extract_numbers(text)
    assert nums == {31.5, 12.0}

def test_check_citations_valid():
    all_ids = ["WIND-01", "HEAVY-RAIN-REGIME-01", "THUNDERSTORM-01"]
    matched = ["WIND-01", "HEAVY-RAIN-REGIME-01", "THUNDERSTORM-01"]
    
    assert check_citations_valid("Watch out (WIND-01)!", matched, all_ids) is True
    assert check_citations_valid("Watch out (HEAVY-RAIN-REGIME-01)!", matched, all_ids) is True
    assert check_citations_valid("Watch out (THUNDERSTORM-01)!", matched, all_ids) is True
    
    assert check_citations_valid("Watch out!", matched, all_ids) is False
    assert check_citations_valid("Watch out (RAIN-01)!", ["WIND-01"], all_ids) is False
    assert check_citations_valid("Fake citation (SOP-999)", matched, all_ids) is False

def test_check_numbers_grounded():
    facts = {"temp": 31.5, "wind": 15.0}
    # Valid
    ok, _, _ = check_numbers_grounded("Temp is 31.5 and wind 15.", facts)
    assert ok is True
    
    # Fake number
    ok, _, _ = check_numbers_grounded("Temp is 32 and wind 15.", facts)
    assert ok is False

def test_validate_reply_catches_fake_number_and_bad_citation():
    state: GraphState = {
        "reply": "Temp is 99 (SOP-999).",
        "matched_sops": [{"id": "WIND-01", "advice": "Be careful"}],
        "facts_dict": {"temp": 31.0},
        "retries": 0
    }
    
    res = validate_reply(state)
    assert res["validation_ok"] is False
    assert res["retries"] == 1
    
    state["retries"] = 1
    res2 = validate_reply(state)
    assert res2["validation_ok"] is False
    assert res2["retries"] == 2
    
    res_temp = template_reply(state)
    assert "WIND-01" in res_temp["reply"]
    assert "Be careful" in res_temp["reply"]
