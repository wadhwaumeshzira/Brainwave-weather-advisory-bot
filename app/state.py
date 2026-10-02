from typing import TypedDict, List, Dict, Any, Optional

class GraphState(TypedDict, total=False):
    user_message: str
    last_location: str
    lat: float
    lon: float
    last_activity: str
    target_day: int
    weather: Dict[str, Any]
    error: str
    applicable_sops: List[str]
    candidate_sops: List[str]
    matched_sops: List[Dict]
    evidence: List[Dict]
    facts_dict: Dict[str, Any]
    reply: str
    retries: int
    out_of_scope: bool
    validation_ok: bool
    last_validation_error: str
    last_raw_reply: str
    evaluated_details: Dict[str, Any]
    llm_used: Dict[str, str]
