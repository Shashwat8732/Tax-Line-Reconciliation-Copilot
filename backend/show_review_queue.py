from app.services.ingestion import load_bank_statement, load_ledger
from app.services.pipeline import run_pipeline
from app.services.feedback import load_policy

txns = load_bank_statement("../sample_data/bank_statement.csv")
ledger = load_ledger("../sample_data/ledger.csv")
ledger_by_id = {e.id: e for e in ledger}
txn_by_id = {t.id: t for t in txns}

policy = load_policy()
result = run_pipeline(
    txns, ledger, use_llm=True,
    stage2_config={
        "amount_tolerance": 100.0, "date_window_days": 5,
        "auto_threshold": policy["stage2_auto_threshold"],
        "review_threshold": 0.5,
    },
)

print("=" * 70)
print("  HUMAN REVIEW QUEUE -- pending review cases")
print("=" * 70)
print()

if not result["review_queue"]:
    print("  No pending review cases.")
else:
    for i, m in enumerate(result["review_queue"], 1):
        txn = txn_by_id.get(m.transaction_id)
        entry = ledger_by_id.get(m.ledger_id) if m.ledger_id else None
        print(f"  [{i}] Match ID: {m.id}")
        print(f"      Bank txn : amount={txn.amount if txn else '?'} date={txn.date if txn else '?'} narration=\"{txn.narration if txn else ''}\"")
        if entry:
            print(f"      Suggested ledger match: {entry.vendor_name}, amount={entry.amount}, invoice={entry.invoice_number}")
        print(f"      Stage: {m.stage.value} | Confidence: {m.confidence*100:.0f}%")
        print(f"      System reasoning: {m.reasoning}")
        print(f"      >>> Waiting for human: CONFIRM or REJECT? <<<")
        print()

print("=" * 70)
print(f"  Total pending review: {len(result['review_queue'])}")
print("=" * 70)
