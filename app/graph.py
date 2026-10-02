from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from app.state import GraphState
from app.nodes import (
    service_unavailable_reply,
    parse_intent, resolve_location, fetch_weather_node, honest_fallback,
    route_sops, evaluate_sops, no_coverage_reply, all_clear_reply, resolve_conflicts,
    compose_reply, validate_reply, template_reply
)

def build_graph():
    builder = StateGraph(GraphState)
    
    builder.add_node("parse_intent", parse_intent)
    builder.add_node("resolve_location", resolve_location)
    builder.add_node("fetch_weather", fetch_weather_node)
    builder.add_node("honest_fallback", honest_fallback)
    builder.add_node("service_unavailable_reply", service_unavailable_reply)
    builder.add_node("route_sops", route_sops)
    builder.add_node("evaluate_sops", evaluate_sops)
    builder.add_node("no_coverage_reply", no_coverage_reply)
    builder.add_node("all_clear_reply", all_clear_reply)
    builder.add_node("resolve_conflicts", resolve_conflicts)
    builder.add_node("compose_reply", compose_reply)
    builder.add_node("validate_reply", validate_reply)
    builder.add_node("template_reply", template_reply)
    
    builder.add_edge(START, "parse_intent")
    
    builder.add_conditional_edges("parse_intent",
        lambda s: "error" if s.get("error") == "llm_failed" else ("out" if s.get("out_of_scope") else "ok"),
        {"error": "service_unavailable_reply", "out": "no_coverage_reply", "ok": "resolve_location"}
    )
    
    builder.add_conditional_edges("resolve_location", 
        lambda s: "error" if s.get("error") else "ok",
        {"error": "honest_fallback", "ok": "fetch_weather"}
    )
    
    builder.add_conditional_edges("fetch_weather",
        lambda s: "error" if s.get("error") else "ok",
        {"error": "honest_fallback", "ok": "route_sops"}
    )
    
    builder.add_edge("honest_fallback", END)
    builder.add_edge("service_unavailable_reply", END)
    builder.add_edge("route_sops", "evaluate_sops")
    
    builder.add_conditional_edges("evaluate_sops",
        lambda s: "ok" if s.get("matched_sops") else ("all_clear" if s.get("applicable_sops") else "empty"),
        {"empty": "no_coverage_reply", "all_clear": "all_clear_reply", "ok": "resolve_conflicts"}
    )
    
    builder.add_edge("no_coverage_reply", END)
    builder.add_edge("all_clear_reply", END)
    builder.add_edge("resolve_conflicts", "compose_reply")
    builder.add_conditional_edges("compose_reply",
        lambda s: "error" if s.get("error") == "compose_failed" else "ok",
        {"error": "template_reply", "ok": "validate_reply"}
    )
    
    builder.add_conditional_edges("validate_reply",
        lambda s: "ok" if s.get("validation_ok") else ("retry" if s.get("retries", 0) <= 1 else "fail"),
        {"ok": END, "retry": "compose_reply", "fail": "template_reply"}
    )
    
    builder.add_edge("template_reply", END)
    
    memory = MemorySaver()
    return builder.compile(checkpointer=memory)

graph = build_graph()
