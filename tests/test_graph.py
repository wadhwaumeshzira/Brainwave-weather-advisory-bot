import os
import pytest
from app.graph import graph
from unittest.mock import patch, MagicMock
from app.nodes import Intent, CandidateList

@pytest.fixture(autouse=True)
def setup_env():
    os.environ["WEATHER_MODE"] = "fixture"
    os.environ["WEATHER_FORCE_FAIL"] = "0"
    yield
    if "WEATHER_MODE" in os.environ: del os.environ["WEATHER_MODE"]
    if "WEATHER_FORCE_FAIL" in os.environ: del os.environ["WEATHER_FORCE_FAIL"]

@pytest.fixture
def mock_llm():
    os.environ['WEATHER_FIXTURE'] = 'bhopal'
    with patch('app.nodes.get_llm') as mock_get_llm:
        mock_model = MagicMock()
        mock_get_llm.return_value = mock_model
        def with_structured_output(schema):
            mock_structured = MagicMock()
            if schema.__name__ == 'Intent':
                mock_structured.invoke.return_value = Intent(location='Bhopal', activity='cycling', target_day=0, in_scope=True)
            elif schema.__name__ == 'CandidateList':
                mock_structured.invoke.return_value = CandidateList(sop_ids=[])
            return mock_structured
        mock_model.with_structured_output = with_structured_output
        mock_result = MagicMock()
        mock_result.content = 'MOCKED REPLY'
        mock_model.invoke.return_value = mock_result
        yield mock_get_llm

def get_trace(events):
    return [list(e.keys())[0] for e in events]

def test_graph_success_and_memory(mock_llm):
    config = {"configurable": {"thread_id": "thread-1"}}
    events = list(graph.stream({"user_message": "a"}, config=config))
    trace = get_trace(events)
    assert "parse_intent" in trace
    assert "resolve_location" in trace

def test_graph_location_failure(mock_llm):
    def with_structured_output_fake(schema):
        mock_structured = MagicMock()
        if schema.__name__ == 'Intent':
            mock_structured.invoke.return_value = Intent(location='fakemakecity', activity='cycling', target_day=0, in_scope=True)
        return mock_structured
    mock_llm.return_value.with_structured_output = with_structured_output_fake
    if "WEATHER_FIXTURE" in os.environ: del os.environ["WEATHER_FIXTURE"]
    
    config = {"configurable": {"thread_id": "thread-fail-loc"}}
    events = list(graph.stream({"user_message": "fakemakecity"}, config=config))
    trace = get_trace(events)
    assert "honest_fallback" in trace

def test_graph_weather_failure(mock_llm):
    os.environ["WEATHER_FORCE_FAIL"] = "1"
    config = {"configurable": {"thread_id": "thread-fail-weather"}}
    events = list(graph.stream({"user_message": "Bhopal"}, config=config))
    trace = get_trace(events)
    assert "honest_fallback" in trace
    os.environ["WEATHER_FORCE_FAIL"] = "0"

def test_graph_no_sop_matched(mock_llm):
    with patch("app.nodes.evaluate_conditions", return_value=(False, [])):
        config = {"configurable": {"thread_id": "thread-no-match"}}
        events = list(graph.stream({"user_message": "Bhopal"}, config=config))
        trace = get_trace(events)
        assert "all_clear_reply" in trace

def test_graph_location_failure_real_api(mock_llm):
    os.environ["WEATHER_MODE"] = "live"
    def with_structured_output_fake(schema):
        mock_structured = MagicMock()
        if schema.__name__ == 'Intent':
            mock_structured.invoke.return_value = Intent(location='fakemakecity', activity='cycling', target_day=0, in_scope=True)
        return mock_structured
    mock_llm.return_value.with_structured_output = with_structured_output_fake
    
    with patch("httpx.get") as mock_get:
        mock_response = type("MockResponse", (), {"json": lambda self: {"results": []}, "raise_for_status": lambda self: None})()
        mock_get.return_value = mock_response
        config = {"configurable": {"thread_id": "thread-real-loc-fail"}}
        events = list(graph.stream({"user_message": "fakemakecity"}, config=config))
        trace = get_trace(events)
        assert "honest_fallback" in trace
    os.environ["WEATHER_MODE"] = "fixture"

def test_graph_weather_failure_http500(mock_llm):
    import httpx
    os.environ["WEATHER_MODE"] = "live"
    with patch("httpx.get") as mock_get:
        mock_geo_resp = type("MockResponse", (), {"json": lambda self: {"results": [{"latitude": 10, "longitude": 20, "name": "Test", "admin1": "St", "country": "Co"}]}, "raise_for_status": lambda self: None})()
        def side_effect(url, **kwargs):
            if "geocoding" in url: return mock_geo_resp
            raise httpx.HTTPError("Simulated 500")
        mock_get.side_effect = side_effect
        config = {"configurable": {"thread_id": "thread-http500"}}
        events = list(graph.stream({"user_message": "Bhopal"}, config=config))
        trace = get_trace(events)
        assert "honest_fallback" in trace
    os.environ["WEATHER_MODE"] = "fixture"

def test_graph_no_coverage(mock_llm):
    def with_structured_output_fake(schema):
        mock_structured = MagicMock()
        if schema.__name__ == 'Intent':
            mock_structured.invoke.return_value = Intent(location='Bhopal', activity='general', target_day=0, in_scope=False)
        return mock_structured
    mock_llm.return_value.with_structured_output = with_structured_output_fake

    config = {"configurable": {"thread_id": "thread-no-coverage-new"}}
    events = list(graph.stream({"user_message": "a"}, config=config))
    trace = get_trace(events)
    assert "no_coverage_reply" in trace
