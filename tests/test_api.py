import pytest
import os
from fastapi.testclient import TestClient
from app.main import app
from unittest.mock import patch, MagicMock
from app.nodes import Intent, CandidateList

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_llm():
    os.environ['WEATHER_MODE'] = 'fixture'
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
        mock_result.content = 'MOCKED REPLY (HEAVY-RAIN-REGIME-01)'
        mock_model.invoke.return_value = mock_result
        yield mock_get_llm

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

def test_serve_html():
    response = client.get("/")
    assert response.status_code == 200

def test_chat_normal():
    response = client.post("/chat", json={"session_id": "test-session-1", "message": "is it safe?"})
    assert response.status_code == 200
    assert "reply" in response.json()

def test_chat_follow_up():
    client.post("/chat", json={"session_id": "test-session-mem", "message": "Bhopal"})
    r2 = client.post("/chat", json={"session_id": "test-session-mem", "message": "tomorrow"})
    assert r2.status_code == 200

def test_chat_different_session(mock_llm):
    client.post("/chat", json={"session_id": "test-session-A", "message": "Bhopal"})
    
    def with_structured_output_b(schema):
        mock_structured = MagicMock()
        if schema.__name__ == 'Intent':
            # Force empty location, AND clear the fixture so geocode fails!
            if "WEATHER_FIXTURE" in os.environ:
                del os.environ["WEATHER_FIXTURE"]
            mock_structured.invoke.return_value = Intent(location="", activity='cycling', target_day=0, in_scope=True)
        return mock_structured
    mock_llm.return_value.with_structured_output = with_structured_output_b
    
    r2 = client.post("/chat", json={"session_id": "test-session-B", "message": "is it safe?"})
    assert "honest_fallback" in r2.json()["trace"]

def test_chat_empty_message(mock_llm):
    def with_structured_output_empty(schema):
        mock_structured = MagicMock()
        if schema.__name__ == 'Intent':
            mock_structured.invoke.return_value = Intent(location=None, activity='general', target_day=0, in_scope=False)
        return mock_structured
    mock_llm.return_value.with_structured_output = with_structured_output_empty
    response = client.post("/chat", json={"session_id": "test-session-empty", "message": " "})
    assert response.status_code == 200

def test_chat_too_long_message():
    long_msg = "a" * 501
    response = client.post("/chat", json={"session_id": "test-session-long", "message": long_msg})
    assert response.status_code == 422
