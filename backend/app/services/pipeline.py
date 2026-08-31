from __future__ import annotations
from app.models.schemas import  MatchStatus
from app.services.stage1_exact import run_stage1
from app.services.stage2_fuzzy import run_stage2
from app.services.stage3_llm import run_stage3


def _auto_count(matches_list):
    return len([m for m in matches_list if m.status == MatchStatus.AUTO_MATCHED])


def _pending_count(matches_list):
    return len([m for m in matches_list if m.status == MatchStatus.PENDING_REVIEW])


def _write_audit_log(matches_list):
    import json as _json
    import os as _os
    from datetime import datetime as _datetime

    log_path = _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "data", "audit_log.jsonl")
    _os.makedirs(_os.path.dirname(log_path), exist_ok=True)

    timestamp = _datetime.now().isoformat()
    with open(log_path, "a") as f:
        for m in matches_list:
            entry = {
                "bank_txn": m.transaction_id,
                "matched_to": m.ledger_id,
                "stage": m.stage.value,
                "confidence": m.confidence,
                "reasoning": m.reasoning,
                "status": m.status.value if hasattr(m.status, "value") else m.status,
                "auto_approved": (m.status.value if hasattr(m.status, "value") else m.status) == "auto_matched",
                "timestamp": timestamp,
            }
            f.write(_json.dumps(entry) + "\n")


import json as _json
import os as _os

_PROCESSED_IDS_PATH = _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "data", "processed_ids.json")


def _load_processed_ids():
    if _os.path.exists(_PROCESSED_IDS_PATH):
        with open(_PROCESSED_IDS_PATH) as f:
            return set(_json.load(f))
    return set()


def _save_processed_ids(ids_set):
    _os.makedirs(_os.path.dirname(_PROCESSED_IDS_PATH), exist_ok=True)
    with open(_PROCESSED_IDS_PATH, "w") as f:
        _json.dump(sorted(ids_set), f)


def run_pipeline(transactions, ledger_entries, use_llm=True, stage2_config=None, enforce_idempotency=True):
    stage2_config = stage2_config or {}

    
    duplicate_count = 0
    if enforce_idempotency:
        processed_ids = _load_processed_ids()
        original_count = len(transactions)
        new_transactions = [t for t in transactions if t.id not in processed_ids]
        duplicate_count = original_count - len(new_transactions)
        transactions = new_transactions

    total_txns = len(transactions)

    all_matches = []

    s1_matches, unmatched_txns, unmatched_ledger = run_stage1(transactions, ledger_entries)
    all_matches.extend(s1_matches)

    s2_matches, unmatched_txns, unmatched_ledger = run_stage2(
        unmatched_txns, unmatched_ledger, **stage2_config
    )
    all_matches.extend(s2_matches)

    s3_real_matches = []
    s3_stats = {"llm_call_count": 0, "llm_total_time_sec": 0.0, "cache_hit_count": 0}
    if use_llm and unmatched_txns:
        s3_matches, unmatched_txns, s3_stats = run_stage3(unmatched_txns, unmatched_ledger)
        all_matches.extend(s3_matches)
        s3_real_matches = [m for m in s3_matches if m.status != MatchStatus.UNMATCHED]

    
    # slipping through on a borderline confidence score.
    import statistics
    txn_amounts = [abs(t.amount) for t in transactions] if transactions else [0]
    median_amount = statistics.median(txn_amounts) if txn_amounts else 0
    high_value_threshold = median_amount * 10
    SAFETY_CONFIDENCE_FLOOR = 0.95

    txn_amount_by_id = {t.id: abs(t.amount) for t in transactions}
    safety_overrides = 0
    for m in all_matches:
        if m.status == MatchStatus.AUTO_MATCHED:
            amt = txn_amount_by_id.get(m.transaction_id, 0)
            if amt > high_value_threshold and m.confidence < SAFETY_CONFIDENCE_FLOOR:
                m.status = MatchStatus.PENDING_REVIEW
                m.log("safety_guardrail",
                      f"High-value transaction (Rs {amt:.0f} > 10x median Rs {median_amount:.0f}) "
                      f"with confidence {m.confidence*100:.0f}% (below {SAFETY_CONFIDENCE_FLOOR*100:.0f}% safety floor) "
                      f"-- forced to human review regardless of auto-threshold.")
                safety_overrides += 1

    review_queue = [m for m in all_matches if m.status == MatchStatus.PENDING_REVIEW]

    stage1_auto = _auto_count(s1_matches)
    stage2_auto = _auto_count(s2_matches)
    stage3_auto = _auto_count(s3_real_matches)
    stage2_pending = _pending_count(s2_matches)
    stage3_pending = _pending_count(s3_real_matches)

    llm_calls = s3_stats["llm_call_count"]
    llm_time = s3_stats["llm_total_time_sec"]
    cache_hits = s3_stats.get("cache_hit_count", 0)
    avg_time_per_txn = round(llm_time / llm_calls, 2) if llm_calls > 0 else 0.0
    
    pct_cost_saved_vs_naive = round(100 * (1 - (llm_calls / max(total_txns, 1))), 1)

    summary = {
        "safety_guardrail_overrides": safety_overrides,
        "high_value_threshold": round(high_value_threshold, 2),
        "total_transactions": total_txns,
        "stage1_auto_matched": stage1_auto,
        "stage2_auto_matched": stage2_auto,
        "stage3_auto_matched": stage3_auto,
        "stage2_pending_review": stage2_pending,
        "stage3_pending_review": stage3_pending,
        "pending_human_review": len(review_queue),
        "still_unmatched": len(unmatched_txns),
        "pct_resolved_without_llm": round(100 * (stage1_auto + stage2_auto) / max(total_txns, 1), 1),
        "pct_auto_resolved": round(100 * (stage1_auto + stage2_auto + stage3_auto) / max(total_txns, 1), 1),
        "pct_matched_including_pending": round(100 * (total_txns - len(unmatched_txns)) / max(total_txns, 1), 1),
       
        "llm_calls_made": llm_calls,
        "cache_hit_count": cache_hits,
        "llm_total_time_sec": llm_time,
        "llm_avg_time_per_call_sec": avg_time_per_txn,
        "pct_cost_saved_vs_llm_for_everything": pct_cost_saved_vs_naive,
    }

    if enforce_idempotency:
        newly_processed = {t.id for t in transactions}
        all_processed = _load_processed_ids() | newly_processed
        _save_processed_ids(all_processed)

    summary["duplicate_transactions_skipped"] = duplicate_count

    
    _write_audit_log(all_matches)

    return {
        "matches": all_matches,
        "review_queue": review_queue,
        "unmatched_transactions": unmatched_txns,
        "summary": summary,
    }
