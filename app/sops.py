import os
import yaml
from typing import Dict, Any, List, Tuple

SEVERITY_SCORE = {
    "critical": 5,
    "high": 4,
    "moderate": 3,
    "low": 2,
    "info": 1
}

ALLOWED_SCOPES = {"current", "today", "day", "next_6h", "window"}
ALLOWED_AGGS = {"max", "min", "sum", "mean", "first", "any_hour"}
ALLOWED_OPS = {">", ">=", "<", "<=", "==", "in"}

CURRENT_FIELDS = {"time", "interval", "temperature_2m", "apparent_temperature", "relative_humidity_2m", "precipitation", "rain", "weather_code", "wind_speed_10m", "wind_gusts_10m", "uv_index"}
HOURLY_FIELDS = {"time", "temperature_2m", "apparent_temperature", "precipitation_probability", "precipitation", "weather_code", "wind_speed_10m", "wind_gusts_10m", "uv_index", "visibility"}
DAILY_FIELDS = {"time", "precipitation_sum", "precipitation_hours", "weather_code", "wind_gusts_10m_max", "uv_index_max", "temperature_2m_max", "temperature_2m_min"}
KNOWN_FIELDS = CURRENT_FIELDS | HOURLY_FIELDS | DAILY_FIELDS

ACTIVITIES = {
    "cycling", "walking", "running", "driving", "picnic", 
    "kids_outdoor", "elderly_outdoor", "pets", "commute", "general"
}

def resolve_slice(weather: Dict, field: str, scope: str, sop: Dict, target_day: int) -> List[Any]:
    current_time_str = weather.get("current", {}).get("time", "")
    if not current_time_str:
        return []
    
    date_str, time_str = current_time_str.split("T")
    current_hour = int(time_str.split(":")[0])
    
    daily_times = weather.get("daily", {}).get("time", [])
    if len(daily_times) <= target_day:
        return []
    target_date = daily_times[target_day]
    
    if scope == "current":
        val = weather.get("current", {}).get(field)
        return [val] if val is not None else []
        
    if scope in ("today", "day"):
        daily = weather.get("daily", {})
        if field in daily:
            vals = daily[field]
            if target_day < len(vals) and vals[target_day] is not None:
                return [vals[target_day]]
            return []
            
    hourly = weather.get("hourly", {})
    if field not in hourly:
        return []
        
    vals = hourly[field]
    times = hourly.get("time", [])
    slice_vals = []
    
    if scope in ("today", "day"):
        for t, v in zip(times, vals):
            if t.startswith(target_date) and v is not None:
                slice_vals.append(v)
                
    elif scope == "window":
        # Note: for target_day=0, this evaluates all hours in the window, even if they have already passed today.
        # This keeps safety consistent for the day's overall risk profile and avoids changing the answer mid-day.
        window = sop.get("time_window", {})
        sh = window.get("start_hour", 0)
        eh = window.get("end_hour", 23)
        for t, v in zip(times, vals):
            if t.startswith(target_date):
                try:
                    hour = int(t.split("T")[1].split(":")[0])
                    if sh <= hour <= eh and v is not None:
                        slice_vals.append(v)
                except (IndexError, ValueError):
                    pass
                    
    elif scope == "next_6h":
        start_idx = -1
        target_hour_prefix = f"{date_str}T{current_hour:02d}:00"
        for i, t in enumerate(times):
            if t == target_hour_prefix:
                start_idx = i
                break
        
        if start_idx == -1:
            for i, t in enumerate(times):
                if t >= current_time_str:
                    start_idx = i
                    break
                    
        if start_idx != -1:
            for v in vals[start_idx : start_idx + 6]:
                if v is not None:
                    slice_vals.append(v)
                    
    return slice_vals

def evaluate_op(actual: Any, op: str, expected: Any) -> bool:
    if actual is None:
        return False
    try:
        if op == ">": return actual > expected
        if op == ">=": return actual >= expected
        if op == "<": return actual < expected
        if op == "<=": return actual <= expected
        if op == "==": return actual == expected
        if op == "in": return actual in expected
    except TypeError:
        return False
    return False

def evaluate_condition(cond: Dict, weather: Dict, sop: Dict, target_day: int) -> Tuple[bool, Dict]:
    field = cond["field"]
    scope = cond["scope"]
    agg = cond["agg"]
    op = cond["op"]
    threshold = cond["value"]
    
    slice_vals = resolve_slice(weather, field, scope, sop, target_day)
    if not slice_vals:
        return False, {"field": field, "scope": scope, "agg": agg, "value": None, "op": op, "threshold": threshold}
        
    if agg == "any_hour":
        for v in slice_vals:
            if evaluate_op(v, op, threshold):
                return True, {"field": field, "scope": scope, "agg": agg, "value": v, "op": op, "threshold": threshold}
        return False, {"field": field, "scope": scope, "agg": agg, "value": slice_vals[0] if slice_vals else None, "op": op, "threshold": threshold}
        
    if agg == "max": actual = max(slice_vals)
    elif agg == "min": actual = min(slice_vals)
    elif agg == "sum": actual = sum(slice_vals)
    elif agg == "mean": actual = sum(slice_vals) / len(slice_vals)
    elif agg == "first": actual = slice_vals[0]
    else:
        raise ValueError(f"Unknown agg: {agg}")
        
    matched = evaluate_op(actual, op, threshold)
    return matched, {"field": field, "scope": scope, "agg": agg, "value": actual, "op": op, "threshold": threshold}

def evaluate_conditions(sop: Dict, weather: Dict, target_day: int = 0) -> Tuple[bool, List[Dict]]:
    conds = sop.get("conditions", {})
    evidence = []
    
    all_matched = True
    all_c = conds.get("all", [])
    if all_c:
        for c in all_c:
            matched, ev = evaluate_condition(c, weather, sop, target_day)
            evidence.append(ev)
            if not matched: all_matched = False
            
    any_matched = True if not conds.get("any") else False
    any_c = conds.get("any", [])
    if any_c:
        for c in any_c:
            matched, ev = evaluate_condition(c, weather, sop, target_day)
            evidence.append(ev)
            if matched: any_matched = True
            
    n_of_matched = True
    n_of = conds.get("n_of")
    if n_of:
        min_n = n_of.get("min", 1)
        of_list = n_of.get("of", [])
        matches = 0
        for c in of_list:
            matched, ev = evaluate_condition(c, weather, sop, target_day)
            evidence.append(ev)
            if matched: matches += 1
        if matches < min_n: n_of_matched = False
            
    final_match = all_matched and any_matched and n_of_matched
    return final_match, evidence

def rank_and_resolve(matched_sops: List[Dict]) -> List[Dict]:
    has_non_positive = any(not s.get("positive", False) for s in matched_sops)
    if has_non_positive:
        matched_sops = [s for s in matched_sops if not s.get("positive", False)]
        
    sops_sorted_by_id = sorted(matched_sops, key=lambda s: s["id"])
    return sorted(sops_sorted_by_id, key=lambda s: (1 if s.get("lead_with") else 0, SEVERITY_SCORE.get(s.get("severity", "info"), 0)), reverse=True)

def load_sops(directory: str = "sops") -> List[Dict]:
    sops = []
    seen_ids = set()
    req_keys = {"id", "title", "category", "severity", "description", "applies_to", "conditions", "advice", "facts_used"}
    
    if not os.path.exists(directory):
        raise ValueError(f"SOP directory {directory} does not exist.")
        
    filenames = sorted(os.listdir(directory))
    if not filenames:
        raise ValueError(f"SOP directory {directory} is empty.")
        
    for fname in filenames:
        if fname.endswith((".yaml", ".yml")):
            path = os.path.join(directory, fname)
            with open(path, "r", encoding="utf-8") as f:
                sop = yaml.safe_load(f)
                
            if not sop:
                continue
                
            missing = req_keys - set(sop.keys())
            if missing:
                raise ValueError(f"Missing required keys {missing} in {fname}")
                
            if sop["id"] in seen_ids:
                raise ValueError(f"Duplicate SOP id {sop['id']}")
                
            if sop["severity"] not in SEVERITY_SCORE:
                raise ValueError(f"Invalid severity {sop['severity']} in {fname}")
                
            for act in sop.get("applies_to", []):
                if act != "*" and act not in ACTIVITIES:
                    raise ValueError(f"Unknown activity '{act}' in {fname}")
                
            conds = sop["conditions"]
            all_c = conds.get("all", [])
            any_c = conds.get("any", [])
            n_of = conds.get("n_of")
            
            has_cond = bool(all_c or any_c or (n_of and n_of.get("of")))
            if not has_cond:
                raise ValueError(f"SOP {fname} has no conditions.")
            
            for cond in all_c + any_c + (n_of.get("of", []) if n_of else []):
                f_name = cond.get("field")
                scope = cond.get("scope", "current")
                
                # window uses hourly fields
                if scope == "window" and f_name not in HOURLY_FIELDS:
                    raise ValueError(f"SOP {fname} uses field '{f_name}' which is not in HOURLY_FIELDS (required for scope window)")
                elif scope == "next_6h" and f_name not in HOURLY_FIELDS:
                    raise ValueError(f"SOP {fname} uses field '{f_name}' which is not in HOURLY_FIELDS (required for scope next_6h)")
                elif scope == "current" and f_name not in CURRENT_FIELDS:
                    raise ValueError(f"SOP {fname} uses field '{f_name}' which is not in CURRENT_FIELDS")
                elif scope in ("today", "day") and f_name not in DAILY_FIELDS:
                    # Some aggregations on hourly arrays are done with scope 'today'
                    if f_name not in DAILY_FIELDS and f_name not in HOURLY_FIELDS:
                        raise ValueError(f"SOP {fname} uses field '{f_name}' which is not valid for scope {scope}")
                
            all_conds = all_c + any_c + (n_of.get("of", []) if n_of else [])
            
            facts_used = set(sop.get("facts_used", []))
            
            for c in all_conds:
                field = c.get("field")
                if field not in KNOWN_FIELDS:
                    raise ValueError(f"Unknown field {field} in {fname}")
                if c.get("scope") not in ALLOWED_SCOPES:
                    raise ValueError(f"Unknown scope {c.get('scope')} in {fname}")
                if c.get("agg") not in ALLOWED_AGGS:
                    raise ValueError(f"Unknown agg {c.get('agg')} in {fname}")
                if c.get("op") not in ALLOWED_OPS:
                    raise ValueError(f"Unknown op {c.get('op')} in {fname}")
                if field not in facts_used:
                    raise ValueError(f"SOP {sop['id']} uses field '{field}' in conditions but it is missing from facts_used.")
                    
            seen_ids.add(sop["id"])
            sops.append(sop)
            
    if not sops:
        raise ValueError(f"No valid SOPs found in {directory}.")
        
    return sops
