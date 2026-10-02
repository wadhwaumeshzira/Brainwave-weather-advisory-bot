import re
from typing import List, Dict, Tuple

def extract_numbers(text: str) -> set:
    text = re.sub(r'\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+\b', '', text)
    text = re.sub(r'\b\d{1,2}\s*(?:am|pm|AM|PM)\b', '', text)
    text = re.sub(r'\b\d{1,2}:\d{2}\b', '', text)
    # Use negative lookbehind/lookahead or just match floats without trailing \b
    # to support cases like '10.5mm' or '45km'
    # Find all sequences of digits, optionally followed by a dot and more digits.
    # We use (?<!\d) and (?!\d) equivalent implicitly by \d+
    nums = re.findall(r'(?<!\w)\d+(?:\.\d+)?|\d+(?:\.\d+)?(?=[a-zA-Z])', text)
    
    # Wait, simple way: just extract all float-like patterns and parse them.
    # \d+\.\d+|\d+
    nums2 = re.findall(r'\d+\.\d+|\d+', text)
    return set(float(n) for n in nums2)

def check_citations_valid(reply: str, matched_ids: List[str], all_ids: List[str]) -> bool:
    cited = [m for m in all_ids if m in reply]
    regex_cited = re.findall(r'\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+\b', reply)
    all_cited = set(cited + regex_cited)
    
    if not all_cited:
        return False
    
    for c in all_cited:
        if c not in matched_ids:
            return False
    return True

def check_numbers_grounded(reply: str, facts: Dict, matched_sops: List[Dict] = None) -> Tuple[bool, List[float], List[float]]:
    """
    Returns (is_valid, reply_nums, not_found_nums).
    Threshold numbers from SOP advice text and condition values are allowed,
    so the LLM can safely quote numbers like '40 km/h' if they appear in the SOP.
    """
    if matched_sops is None:
        matched_sops = []
        
    reply_nums = extract_numbers(reply)
    
    # 1. Gather all allowed numbers from facts
    fact_nums = set()
    for v in facts.values():
        try:
            fact_nums.add(float(v))
        except (ValueError, TypeError):
            pass
            
    # 2. Gather allowed numbers from SOP advice strings and condition thresholds
    for sop in matched_sops:
        advice_text = sop.get('advice', '')
        fact_nums.update(extract_numbers(advice_text))
        for cond_list in sop.get('conditions', {}).values():
            if not cond_list: continue
            for cond in cond_list:
                if isinstance(cond, dict) and 'value' in cond:
                    try:
                        fact_nums.add(float(cond['value']))
                    except (ValueError, TypeError):
                        pass

    not_found = [n for n in reply_nums if n not in fact_nums]
    return (len(not_found) == 0, list(reply_nums), not_found)
