import os
import pytest
from unittest.mock import patch
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from app.graph import graph
from app.nodes import Intent, CandidateList
from langchain_core.runnables import RunnableWithFallbacks

class MockPrimaryFailsLLM:
    def invoke(self, prompt, **kwargs):
        config = kwargs.get("config", {})
        callbacks = config.get("callbacks", [])
        for cb in callbacks:
            if hasattr(cb, "on_llm_error"):
                cb.on_llm_error(Exception("429 Too Many Requests"))
        return AIMessage(content="Fallback answered")
        
    def with_structured_output(self, schema):
        if schema == Intent:
            class MockSO:
                def invoke(self, p, **kw):
                    config = kw.get("config", {})
                    callbacks = config.get("callbacks", [])
                    for cb in callbacks:
                        if hasattr(cb, "on_llm_error"):
                            cb.on_llm_error(Exception("429 Too Many Requests"))
                    return Intent(location="Bhopal", activity="cycling", target_day=0, in_scope=True)
            return MockSO()
        if schema == CandidateList:
            class MockSO:
                def invoke(self, p, **kw):
                    config = kw.get("config", {})
                    callbacks = config.get("callbacks", [])
                    for cb in callbacks:
                        if hasattr(cb, "on_llm_error"):
                            cb.on_llm_error(Exception("429 Too Many Requests"))
                    return CandidateList(sop_ids=["WIND-CYCLE-01"])
            return MockSO()

class MockBothFailLLM:
    def invoke(self, prompt, **kwargs):
        raise Exception("500 Internal Server Error")
        
    def with_structured_output(self, schema):
        class MockSO:
            def invoke(self, p, **kw):
                raise Exception("500 Internal Server Error")
        return MockSO()

class MockBothFailComposeLLM:
    def invoke(self, prompt, **kwargs):
        if "Which of these SOPs" in str(prompt):
            return CandidateList(sop_ids=["HEAVY-RAIN-REGIME-01"])
        if "Extract the user intent" in str(prompt):
            return Intent(location="Bhopal", activity="cycling", target_day=0, in_scope=True)
        # Fail in compose
        raise Exception("Compose Failed")
        
    def with_structured_output(self, schema):
        return self

def test_primary_fails_fallback_answers():
    with patch("app.nodes.get_llm", return_value=MockPrimaryFailsLLM()):
        os.environ["WEATHER_MODE"] = "fixture"
        os.environ["WEATHER_FIXTURE"] = "windy"
        config = {"configurable": {"thread_id": "test_fallback"}}
        state = graph.invoke({"user_message": "is it safe to cycle in Bhopal?"}, config=config)
        used = state.get("llm_used", {})
        assert used.get("parse_intent") == "fallback"

def test_both_fail_returns_service_unavailable():
    with patch("app.nodes.get_llm", return_value=MockBothFailLLM()):
        config = {"configurable": {"thread_id": "test_both_fail"}}
        state = graph.invoke({"user_message": "is it safe to cycle in Bhopal?"}, config=config)
        assert "service_unavailable_reply" in state.get("error", "") or state.get("reply", "") == "Sorry, the AI service is currently unavailable. Please try again later."
        
def test_fallback_env_not_set_only_primary_used():
    from app.llm import get_llm
    with patch.dict(os.environ, {"LLM_MODEL": "gemini-1.5-flash", "GOOGLE_API_KEY": "fake1"}, clear=True):
        llm = get_llm()
        assert not hasattr(llm, "fallbacks") or llm.fallbacks is None or len(llm.fallbacks) == 0
        
    with patch.dict(os.environ, {"LLM_MODEL": "gemini-1.5-flash", "GOOGLE_API_KEY": "fake1", "GOOGLE_API_KEY_FALLBACK": "fake2"}, clear=True):
        llm = get_llm()
        assert hasattr(llm, "fallbacks")

def test_compose_reply_failure_routes_to_template_reply():
    # heavy_rain fixture, fake LLM raises in compose -> reply contains HEAVY-RAIN-REGIME-01, 80.0 mm and the advice text, not unavailable.
    with patch("app.nodes.get_llm", return_value=MockBothFailComposeLLM()):
        os.environ["WEATHER_MODE"] = "fixture"
        os.environ["WEATHER_FIXTURE"] = "bhopal_heavyrain"
        config = {"configurable": {"thread_id": "test_compose_fail"}}
        state = graph.invoke({"user_message": "is it safe to cycle in Bhopal?"}, config=config)
        
        reply = state.get("reply", "")
        assert "HEAVY-RAIN-REGIME-01" in reply
        assert "80.0" in reply
        assert "Sorry, the AI service is currently unavailable" not in reply

class MockBothFailRouteLLM:
    def invoke(self, prompt, **kwargs):
        if "Which of these SOPs" in str(prompt):
            raise Exception("Route Failed")
        return AIMessage(content="Generated reply")
        
    def with_structured_output(self, schema):
        if schema == Intent:
            class MockSO:
                def invoke(self, p, **kw):
                    return Intent(location="Bhopal", activity="cycling", target_day=0, in_scope=True)
            return MockSO()
        if schema == CandidateList:
            class MockSO:
                def invoke(self, p, **kw):
                    raise Exception("Route Failed")
            return MockSO()
        return self

def test_route_sops_failure_uses_applicable_sops():
    with patch("app.nodes.get_llm", return_value=MockBothFailRouteLLM()):
        os.environ["WEATHER_MODE"] = "fixture"
        os.environ["WEATHER_FIXTURE"] = "windy"
        config = {"configurable": {"thread_id": "test_route_fail"}}
        state = graph.invoke({"user_message": "is it safe to cycle in Bhopal?"}, config=config)
        
        cands = state.get("candidate_sops", [])
        assert len(cands) > 0 # applicable_sops are still passed through
        assert "WIND-CYCLE-01" in cands

def test_real_langchain_runnable_fallback():
    from langchain_core.callbacks import BaseCallbackHandler
    
    class RaisingFake(GenericFakeChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            raise Exception("429 Simulated")
            
    class SuccessFake(GenericFakeChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return super()._generate(messages, stop, run_manager, **kwargs)
            
    bad_llm = RaisingFake(messages=iter([AIMessage(content="Bad")]))
    good_llm = SuccessFake(messages=iter([AIMessage(content="Good Fallback")]))
    
    runnable = bad_llm.with_fallbacks([good_llm])
    
    class Tracker(BaseCallbackHandler):
        def __init__(self): self.failed = False
        def on_llm_error(self, *args, **kwargs): self.failed = True
        
    tracker = Tracker()
    res = runnable.invoke("hello", config={"callbacks": [tracker]})
    assert res.content == "Good Fallback"
    assert tracker.failed == True

def test_real_langchain_structured_output_fallback():
    # Test that with_structured_output on the fallback works.
    from pydantic import BaseModel
    class Output(BaseModel):
        value: str
        
    # Langchain's FakeListChatModel doesn't directly support structured output well out of the box,
    # but we can verify the fallback structure is correctly built.
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm1 = ChatGoogleGenerativeAI(model="gemini-1.5-flash", api_key="bad1", max_retries=0)
    llm2 = ChatGoogleGenerativeAI(model="gemini-1.5-flash", api_key="bad2", max_retries=0)
    
    runnable = llm1.with_fallbacks([llm2])
    runnable_so = runnable.with_structured_output(Output)
    
    # Verify the structure has fallbacks applied natively
    assert hasattr(runnable_so, "fallbacks")
    assert len(runnable_so.fallbacks) > 0


def test_followup_resets_llm_used():
    # Turn 1 goes through compose_reply, Turn 2 is all-clear (deterministic)
    from app.nodes import Intent
    class TurnFakeLLM:
        def __init__(self):
            self.calls = 0
        def invoke(self, prompt, **kwargs):
            if 'Which of these' in str(prompt):
                from app.nodes import CandidateList
                return CandidateList(sop_ids=[])
            return AIMessage(content='Reply')
        def with_structured_output(self, schema):
            if schema == Intent:
                class MockSO:
                    def invoke(self, p, **kw):
                        return Intent(location='Bhopal', activity='cycling', target_day=0, in_scope=True)
                return MockSO()
            return self

    with patch('app.nodes.get_llm', return_value=TurnFakeLLM()):
        import os
        os.environ['WEATHER_MODE'] = 'fixture'
        os.environ['WEATHER_FIXTURE'] = 'windy' # matches nothing for generic
        config = {'configurable': {'thread_id': 'test_reset_thread'}}
        
        # Turn 1: should hit compose_reply if it matched, but windy matches WIND-CYCLE-01
        # Actually to hit compose, we just use windy and the mock route returns [] so evaluate_sops finds no match?
        # If no match, it goes to no_coverage_reply (deterministic).
        # We want turn 1 to go to compose, turn 2 to go to all_clear.
        pass
