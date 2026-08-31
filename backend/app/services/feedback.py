from __future__ import annotations
import json
import os
from app.models.schemas import MatchStatus
from app.models.schemas import MatchStatus

POLICY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "policy.json")
SEEN_PATTERNS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "seen_patterns.json")

DEFAULT_POLICY = {
    "stage2_auto_threshold": 0.90,
    "stage3_auto_threshold": 0.85,
    "learning_rate": 0.02,
}


def load_policy():
    if os.path.exists(POLICY_PATH):
        with open(POLICY_PATH) as f:
            return json.load(f)
    return dict(DEFAULT_POLICY)


def save_policy(policy):
    os.makedirs(os.path.dirname(POLICY_PATH), exist_ok=True)
    with open(POLICY_PATH, "w") as f:
        json.dump(policy, f, indent=2)


def _load_seen_patterns():
    if os.path.exists(SEEN_PATTERNS_PATH):
        with open(SEEN_PATTERNS_PATH) as f:
            return json.load(f)
    return {}


def _save_seen_patterns(patterns):
    os.makedirs(os.path.dirname(SEEN_PATTERNS_PATH), exist_ok=True)
    with open(SEEN_PATTERNS_PATH, "w") as f:
        json.dump(patterns, f, indent=2)


def _pattern_signature(match, vendor_name=None):
    
    conf_bucket = round(match.confidence * 20) / 20  
    vendor_key = (vendor_name or "unknown").strip().upper()
    return f"{match.stage.value}|{vendor_key}|{conf_bucket}"


def apply_feedback(match, confirmed: bool, vendor_name=None):
    
    policy = load_policy()
    lr = policy["learning_rate"]

    
    seen_patterns = _load_seen_patterns()
    sig = _pattern_signature(match, vendor_name)
    was_seen_before = sig in seen_patterns
    prior_decision = seen_patterns.get(sig)

    stage_key = "stage3" if match.stage.value == "stage3_llm" else "stage2"
    auto_key = f"{stage_key}_auto_threshold"

    if confirmed:
        match.status = MatchStatus.CONFIRMED
        if match.confidence < policy[auto_key]:
            
            policy[auto_key] = round(max(0.5, policy[auto_key] - lr), 3)
    else:
        match.status = MatchStatus.REJECTED
        if match.confidence >= policy[auto_key] - 0.05:
           
            policy[auto_key] = round(min(0.99, policy[auto_key] + lr), 3)

   
    seen_patterns[sig] = "confirmed" if confirmed else "rejected"
    _save_seen_patterns(seen_patterns)

    save_policy(policy)
    return {
        "policy": policy,
        "was_seen_before": was_seen_before,
        "prior_decision": prior_decision,
        "pattern_signature": sig,
    }