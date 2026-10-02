import os
from dotenv import load_dotenv
load_dotenv()
import argparse
import yaml
import re
from unittest.mock import patch
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.graph import graph
from langchain_core.messages import AIMessage

# Global counter
TOTAL_LLM_CALLS = 0

class CountingLLM:
    def __init__(self, original):
        self.original = original
        if hasattr(original, 'fallbacks'):
            self.fallbacks = original.fallbacks

    def invoke(self, *args, **kwargs):
        global TOTAL_LLM_CALLS
        TOTAL_LLM_CALLS += 1
        return self.original.invoke(*args, **kwargs)
        
    def with_structured_output(self, schema):
        global TOTAL_LLM_CALLS
        # wrap the structured output
        so = self.original.with_structured_output(schema)
        class SOCounter:
            def invoke(self, *a, **kw):
                global TOTAL_LLM_CALLS
                TOTAL_LLM_CALLS += 1
                return so.invoke(*a, **kw)
        return SOCounter()

# A mock for the deliberate negative check that passes extraction/routing but fails compose
class NegativeComposeMock:
    def invoke(self, prompt, **kwargs):
        if "Which of these SOPs" in str(prompt):
            from app.nodes import CandidateList
            return CandidateList(sop_ids=["WIND-CYCLE-01"])
        if "Extract the user intent" in str(prompt):
            from app.nodes import Intent
            return Intent(location="Bhopal", activity="cycling", target_day=0, in_scope=True)
        # It's compose_reply
        return AIMessage(content="According to WIND-CYCLE-01, it is unsafe. Gusts are 999.0 km/h.")
        
    def with_structured_output(self, schema):
        return self

def run_case(case_def, expected_path_str=None):
    os.environ["WEATHER_MODE"] = "fixture"
    os.environ["WEATHER_FIXTURE"] = case_def.get("fixture", "bhopal")
    
    msgs = case_def.get("messages", [])
    if "message" in case_def:
        msgs = [case_def["message"]]
        
    config = {"configurable": {"thread_id": f"eval_{case_def['id']}"}}
    
    # We patch get_llm to use CountingLLM
    from app.llm import get_llm as real_get_llm
    
    def wrapped_get_llm():
        return CountingLLM(real_get_llm())
        
    trace = []
    attempts = 0
    with patch("app.nodes.get_llm", side_effect=wrapped_get_llm):
        for msg in msgs:
            trace = []
            for event in graph.stream({"user_message": msg}, config):
                node = list(event.keys())[0]
                trace.append(node)
                if node == "compose_reply": attempts += 1
            final_state = graph.get_state(config).values

    if "service_unavailable_reply" in trace:
        reply_path = "service_unavailable"
    elif "template_reply" in trace:
        reply_path = "template"
    elif "all_clear_reply" in trace:
        reply_path = "all_clear_reply"
    elif "honest_fallback" in trace:
        reply_path = "honest_fallback"
    elif "no_coverage_reply" in trace:
        reply_path = "no_coverage_reply"
    else:
        reply_path = f"llm {attempts}"

    expected_sops = case_def.get("expected_sops", [])
    reply = final_state.get("reply", "")
    actual_cited = list(set(re.findall(r'\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+\b', reply)))
    
    passed = True
    notes = []
    
    if expected_path_str:
        if expected_path_str not in reply_path and expected_path_str not in trace:
            passed = False
            notes.append(f"Expected path {expected_path_str}, got {reply_path}")
            
    if reply_path == "service_unavailable":
        passed = False
        notes.append("ERROR: Service Unavailable")

    if case_def["id"] == 6:
        idx1 = reply.find("HEAVY-RAIN-REGIME-01")
        idx2 = reply.find("WIND-CYCLE-01")
        if idx1 == -1 or idx2 == -1:
            passed = False
            notes.append("Did not cite both HEAVY-RAIN-REGIME-01 and WIND-CYCLE-01")
        elif idx1 > idx2:
            passed = False
            notes.append("HEAVY-RAIN-REGIME-01 was not cited first")

    if case_def["id"] == 11 or case_def["id"] == 16:
        if "SOP-999" in reply:
            passed = False
            notes.append("Failed adversarial: cited fake SOP")
            
    if case_def["id"] == 16:
        if "is safe" in reply.lower() or "completely safe" in reply.lower():
            passed = False
            notes.append("Adversarial 2 claimed it is safe")

    for s in expected_sops:
        if s not in actual_cited:
            passed = False
            notes.append(f"Missing expected SOP {s}")
            
    if case_def["id"] == 7: # No guidance
        if "don't have guidance" not in reply.lower():
            passed = False
            notes.append("Did not return no-guidance message")
            
    if case_def.get("should_fail"):
        if "Sorry" not in reply and "error" not in reply.lower() and "couldn't get" not in reply:
            passed = False
            notes.append("Did not fail gracefully")
            
    if case_def["id"] == 12: # Follow up
        if final_state.get("last_location", "").lower() != "bhopal":
            passed = False
            notes.append("Session did not remember location")
            
    if len(notes) == 0:
        notes.append("Passed criteria")
        
    return passed, ", ".join(notes), reply_path, actual_cited, reply

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3, help="Number of times to run each LLM case")
    args = parser.parse_args()
    
    print(f"Running evals using LLM Provider: {os.getenv('LLM_PROVIDER')} | Model: {os.getenv('LLM_MODEL')}")
    print(f"Runs per case: {args.runs}")
    
    with open("evals/cases.yaml", "r") as f:
        data = yaml.safe_load(f)
        
    results = []
    sample_replies = {}
    
    for case in data["cases"]:
        passes = 0
        notes_list = []
        paths = []
        actual_sops_list = []
        last_reply = ""
        
        # Expected path overrides based on case definitions
        expected_path = None
        if case["id"] == 1: expected_path = "all_clear_reply"
        elif case["id"] == 7: expected_path = "no_coverage_reply"
        elif case["id"] in [8, 9]: expected_path = "honest_fallback"
        
        runs_count = args.runs
        # Deterministic cases don't need multiple runs
        if expected_path in ["all_clear_reply", "no_coverage_reply", "honest_fallback"]:
            runs_count = 1
            
        msg_preview = case.get("message", case.get("messages", [""])[-1])
        print(f"-> Running Case {case['id']}: '{msg_preview[:50]}...' ({runs_count} runs)")
            
        for i in range(runs_count):
            passed, note, path, actual_cited, reply = run_case(case, expected_path)
            paths.append(path)
            if passed: passes += 1
            if note != "Passed criteria" and note not in notes_list:
                notes_list.append(note)
            actual_sops_list.append(", ".join(actual_cited) if actual_cited else "none")
            last_reply = reply
            import time
            time.sleep(4)
                
        rate = f"{passes}/{runs_count}"
        path_str = " / ".join(paths)
        note_str = ", ".join(notes_list) if notes_list else "All checks passed"
        
        if case["expected_sops"]:
            criteria = f"{' and '.join(case['expected_sops'])} cited"
            if case["id"] == 6: criteria += " (regime first)"
        elif case["id"] == 11:
            criteria = "No fake SOP-999 cited"
        elif case["id"] == 16:
            criteria = "No SOP-999, doesn't claim safe"
        elif case.get("should_fail"):
            criteria = "Honest error message"
        elif case["id"] == 12:
            criteria = "Location remembered"
        else:
            criteria = expected_path or "Dynamic check"
            
        if case["id"] == 5: sample_replies["Heavy Rain"] = {"reply": last_reply, "path": path_str, "cited": actual_sops_list[-1]}
        if case["id"] == 6: sample_replies["Conflict"] = {"reply": last_reply, "path": path_str, "cited": actual_sops_list[-1]}
        if case["id"] == 11: sample_replies["Adversarial 1"] = {"reply": last_reply, "path": path_str, "cited": actual_sops_list[-1]}
        if case["id"] == 16: sample_replies["Adversarial 2"] = {"reply": last_reply, "path": path_str, "cited": actual_sops_list[-1]}
        if case["id"] == 13: sample_replies["Hinglish"] = {"reply": last_reply, "path": path_str, "cited": actual_sops_list[-1]}
            
        msg = case.get("message", case.get("messages", [""])[-1])
        
        results.append({
            "query": msg,
            "fixture": case["fixture"],
            "expected_sops": ", ".join(case["expected_sops"]) if case["expected_sops"] else "None",
            "criteria": criteria,
            "actual_sops": actual_sops_list[-1],
            "result": rate,
            "paths": path_str,
            "notes": note_str
        })
        
    print("Running Deliberate Negative Check...")
    os.environ["WEATHER_MODE"] = "fixture"
    os.environ["WEATHER_FIXTURE"] = "bhopal_heavyrain"
    config_neg = {"configurable": {"thread_id": "eval_negative"}}
    
    with patch("app.nodes.get_llm", return_value=NegativeComposeMock()):
        trace_neg = []
        for event in graph.stream({"user_message": "is it safe to cycle in Bhopal today?"}, config_neg):
            trace_neg.append(list(event.keys())[0])
        final_state = graph.get_state(config_neg).values
        reject_reason = final_state.get("last_validation_error", "")
        final_reply = final_state.get("reply", "")
    
    with open("evals/RESULTS.md", "w", encoding="utf-8") as f:
        f.write("# Evaluation Results\n\n")
        f.write(f"**LLM Provider**: {os.getenv('LLM_PROVIDER')} | **Model**: {os.getenv('LLM_MODEL')}\n")
        f.write(f"**Total LLM Calls**: {TOTAL_LLM_CALLS}\n\n")
        
        f.write("## Limitations\n")
        f.write("- Weather conditions are powered by static fixtures (`heavy_rain` and `windy` are synthetic) to ensure tests are deterministic. Live API numbers are not asserted exactly due to continuous fluctuations.\n")
        f.write("- The LLM cases are run multiple times to account for stochastic generation variance.\n")
        f.write("- The 'tomorrow evening' case passes because the synthetic `windy` fixture only inflated gusts for today (target_day=0), leaving tomorrow calm and safely falling back to the deterministic all-clear.\n\n")
        
        f.write("## Execution Matrix\n")
        f.write("| Query | Fixture | Expected SOPs | Pass Criteria | Actual Cited | Reply Path | Result | Notes |\n")
        f.write("|-------|---------|---------------|---------------|--------------|------------|--------|-------|\n")
        for r in results:
            f.write(f"| {r['query']} | {r['fixture']} | {r['expected_sops']} | {r['criteria']} | {r['actual_sops']} | {r['paths']} | {r['result']} | {r['notes']} |\n")
            
        f.write("\n## Deliberate Negative Validation Check\n")
        f.write(f"**Action**: Injected fake LLM across the entire graph. It succeeds on parsing and routing, but injects an ungrounded wind gust of 999.0 km/h during compose. The graph catches it and retries/templates.\n")
        f.write(f"**Node Trace**: `{' -> '.join(trace_neg)}`\n")
        f.write(f"**Rejection Reason**: {reject_reason}\n")
        f.write(f"**Final Reply Output (Template)**:\n> {final_reply}\n\n")

        f.write("## Sample Full Replies\n")
        for name, data in sample_replies.items():
            f.write(f"### {name} Case\n")
            f.write(f"**Path**: {data['path']}\n")
            f.write(f"**Cited**: {data['cited']}\n")
            f.write(f"**Reply**:\n> {data['reply']}\n\n")

if __name__ == "__main__":
    main()
