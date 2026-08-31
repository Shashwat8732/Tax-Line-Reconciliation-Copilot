import csv
from app.services.ingestion import load_bank_statement, load_ledger
from app.services.pipeline import run_pipeline
from app.services.feedback import load_policy

# Ground truth 
ground_truth = {}
with open("../sample_data/ground_truth_hard.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        gt_id = row["ground_truth_ledger_id"].strip()
        ground_truth[row["bank_transaction_id"]] = None if gt_id in ("NO_MATCH", "") else gt_id


txns = load_bank_statement("../sample_data/bank_statement_hard.csv")
ledger = load_ledger("../sample_data/ledger_hard.csv")
policy = load_policy()
result = run_pipeline(
    txns, ledger, use_llm=True,
    stage2_config={
        "amount_tolerance": 100.0, "date_window_days": 5,
        "auto_threshold": policy["stage2_auto_threshold"],
        "review_threshold": 0.5,
    },
    enforce_idempotency=False,
)

# Predictions 
predictions = {}
stage_of = {}
for m in result["matches"]:
    predictions[m.transaction_id] = m.ledger_id  
    stage_of[m.transaction_id] = m.stage.value

# Confusion counts
tp = fp = fn = tn = 0
tp_by_stage = {}

for bank_id, gt_ledger in ground_truth.items():
    pred_ledger = predictions.get(bank_id)
    stage = stage_of.get(bank_id, "unknown")

    if gt_ledger is not None and pred_ledger == gt_ledger:
        tp += 1
        tp_by_stage[stage] = tp_by_stage.get(stage, 0) + 1
    elif pred_ledger is not None and pred_ledger != gt_ledger:
        fp += 1
    elif gt_ledger is not None and pred_ledger is None:
        fn += 1
    elif gt_ledger is None and pred_ledger is None:
        tn += 1

precision = tp / (tp + fp) if (tp + fp) > 0 else 0
recall = tp / (tp + fn) if (tp + fn) > 0 else 0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

print("=" * 60)
print("  GROUND TRUTH EVALUATION")
print("=" * 60)
print(f"  True Positives  (correct match)      : {tp}")
print(f"  False Positives (wrong match)         : {fp}")
print(f"  False Negatives (missed real match)   : {fn}")
print(f"  True Negatives  (correctly no-match)  : {tn}")
print("-" * 60)
print(f"  Precision : {precision*100:.1f}%")
print(f"  Recall    : {recall*100:.1f}%")
print(f"  F1 Score  : {f1*100:.1f}%")
print("-" * 60)
print("  Correct matches by stage:")
for stage, count in sorted(tp_by_stage.items()):
    print(f"    {stage:20s}: {count}")
print("=" * 60)

print()
print("=" * 60)
print("  COST / LATENCY (from pipeline summary)")
print("=" * 60)
s = result["summary"]
print(f"  LLM calls made              : {s['llm_calls_made']}")
print(f"  Total transactions          : {s['total_transactions']}")
print(f"  Total LLM time (sec)        : {s['llm_total_time_sec']}")
print(f"  Avg time per LLM call (sec) : {s['llm_avg_time_per_call_sec']}")
print(f"  Cost saved vs LLM-for-all   : {s['pct_cost_saved_vs_llm_for_everything']}%")
print("-" * 60)
print(f"  Resolved without LLM        : {s['pct_resolved_without_llm']}%")
print(f"  Auto-resolved (incl. LLM)   : {s['pct_auto_resolved']}%")
print(f"  Matched incl. pending       : {s['pct_matched_including_pending']}%")
print("=" * 60)

print()
print("=" * 60)
print("  SAFETY GUARDRAIL")
print("=" * 60)
print(f"  High-value threshold (10x median) : Rs {s['high_value_threshold']}")
print(f"  Cases forced to human review       : {s['safety_guardrail_overrides']}")
print("=" * 60)
