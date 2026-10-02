import os
from dotenv import load_dotenv
load_dotenv()
import sys
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.graph import graph

def main():
    if not os.getenv("LLM_PROVIDER"):
        os.environ["LLM_PROVIDER"] = "google_genai"
    if not os.getenv("LLM_MODEL"):
        os.environ["LLM_MODEL"] = "gemini-3.5-flash"
        
    msg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "is it safe to bike to work in Bhopal today?"
    
    use_fake = "--fake" in sys.argv
    
    provider = os.getenv("LLM_PROVIDER")
    if not use_fake and provider in ("google", "google_genai"):
        if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
            raise RuntimeError("API key is missing! Pass --fake to mock it, or set GOOGLE_API_KEY in .env")

    config = {"configurable": {"thread_id": "try-chat-real"}}
    state = {"user_message": msg}
    
    print(f"User: {msg}")
    print("-" * 50)
    
    if use_fake:
        print("Using mocked LLM for demonstration.\\n")
        from unittest.mock import patch, MagicMock
        from app.nodes import Intent, CandidateList
        mock_model = MagicMock()
        def with_structured_output(schema):
            mock_structured = MagicMock()
            if schema.__name__ == 'Intent':
                mock_structured.invoke.return_value = Intent(location='Bhopal', activity='cycling', target_day=0, in_scope=True)
            elif schema.__name__ == 'CandidateList':
                mock_structured.invoke.return_value = CandidateList(sop_ids=[])
            return mock_structured
        mock_model.with_structured_output = with_structured_output
        mock_result = MagicMock()
        mock_result.content = 'Primary Advisory (HEAVY-RAIN-REGIME-01): Avoid non-essential travel and outdoor activity today in Bhopal. Total rain is 80.0 mm. Wind gusts up to 55.0 km/h.'
        mock_model.invoke.return_value = mock_result
        
        with patch('app.nodes.get_llm', return_value=mock_model):
            _run_chat(state, config)
    else:
        _run_chat(state, config)

def _run_chat(state, config):
    trace = []
    attempts = 0
    for event in graph.stream(state, config=config):
        node = list(event.keys())[0]
        trace.append(node)
        print(f"-> Node: {node}")
        
        if node == "compose_reply":
            attempts += 1
        elif node == "validate_reply":
            s = graph.get_state(config).values
            if not s.get("validation_ok"):
                print(f"   [Validator Rejected] Reason: {s.get('last_validation_error')}")
                print(f"   [Raw LLM Output]: {s.get('last_raw_reply')}")
        
    s = graph.get_state(config).values
    
    print("\n--- DEBUG BLOCK ---")
    print(f"Parsed Intent: Location={s.get('last_location')}, Activity={s.get('last_activity')}, Target Day={s.get('target_day')}, In Scope={not s.get('out_of_scope')}")
    print(f"Applicable SOPs (sent to router): {s.get('applicable_sops')}")
    print(f"Candidate SOPs (chosen by router/added by determinism): {s.get('candidate_sops')}")
    
    print("\nEvaluated SOPs:")
    evaluated = s.get("evaluated_details", {})
    for sid, details in evaluated.items():
        print(f" - {sid}: Matched={details['matched']}")
        if not details['evidence']:
            print("   Evidence: []")
        for ev in details['evidence']:
            print(f"   Evidence: field={ev.get('field')}, scope={ev.get('scope')}, agg={ev.get('agg')}, value={ev.get('value')} (vs {ev.get('op')} {ev.get('threshold')})")
            
    print("-" * 50)
    print("\nTrace:", trace)
    if s.get("llm_used"):
        print("LLM used per node:", s.get("llm_used"))
    
    if "template_reply" in trace or "all_clear_reply" in trace or "honest_fallback" in trace or "no_coverage_reply" in trace:
        path_taken = "deterministic (no LLM)"
    else:
        path_taken = f"llm attempt {attempts}"
    
    print(f"\nReply Path: {path_taken}")
    
    reply_text = s.get('reply', '')
    
    cited_ids = list(set(re.findall(r'\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+\b', reply_text)))
    
    print('\nCited SOPs (extracted from reply):', cited_ids if cited_ids else 'None')
    print('\nValidator result:', s.get('validation_ok', 'N/A'))
    print('\nReply:\n' + reply_text)
    
if __name__ == "__main__":
    main()
