from dotenv import load_dotenv
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import streamlit as st
import pandas as pd
import csv
import io
from app.services.ingestion import load_bank_statement, load_ledger
from app.services.pipeline import run_pipeline
from app.services.feedback import load_policy, apply_feedback, save_policy, DEFAULT_POLICY
from app.models.schemas import MatchStatus as _MS

load_dotenv()  

st.set_page_config(page_title="Tax-Line Reconciliation Copilot", layout="wide")

st.title("💰 Tax-Line Reconciliation Copilot")
st.caption("Confidence-tiered | Cost-aware | Explainable | Gated")

# SIDEBAR
st.sidebar.header("Upload Data")
st.sidebar.info(
    "👉 Click **Run Reconciliation** to try it with sample data -- "
    "or upload your own CSVs (see `sample_data/` in our repo for format).\n\n"
    "New data takes a few seconds per LLM call (free-tier Groq); repeat runs are instant (cached)."
)
bank_file = st.sidebar.file_uploader("Bank statement CSV", type="csv")
ledger_file = st.sidebar.file_uploader("Ledger CSV", type="csv")
ground_truth_file = st.sidebar.file_uploader("Ground truth CSV (optional -- for accuracy metrics)", type="csv")

use_llm = st.sidebar.checkbox("Use Stage 3 (LLM)", value=True)
run_button = st.sidebar.button("Run Reconciliation", type="primary")

st.sidebar.divider()
if st.sidebar.button("🔄 Reset to Default Thresholds"):
    
    save_policy(dict(DEFAULT_POLICY))
    st.sidebar.success(f"Reset: {DEFAULT_POLICY}")

if "result" not in st.session_state:
    st.session_state.result = None
if "ground_truth" not in st.session_state:
    st.session_state.ground_truth = None

if run_button:
    with st.spinner("Running pipeline..."):
        import os as _os

        _sample_dir = _os.path.join(_os.path.dirname(__file__), "..", "sample_data")
        _default_bank = _os.path.join(_sample_dir, "bank_statement_hard.csv")
        _default_ledger = _os.path.join(_sample_dir, "ledger_hard.csv")

        if bank_file:
            with open("/tmp/_bank.csv", "wb") as f:
                f.write(bank_file.getbuffer())
            bank_path = "/tmp/_bank.csv"
        else:
            bank_path = _default_bank
            st.sidebar.info("No bank CSV uploaded -- using sample data.")

        if ledger_file:
            with open("/tmp/_ledger.csv", "wb") as f:
                f.write(ledger_file.getbuffer())
            ledger_path = "/tmp/_ledger.csv"
        else:
            ledger_path = _default_ledger
            st.sidebar.info("No ledger CSV uploaded -- using sample data.")

        txns = load_bank_statement(bank_path)
        ledger = load_ledger(ledger_path)
        policy = load_policy()
        result = run_pipeline(
            txns, ledger, use_llm=use_llm,
            stage2_config={
                "amount_tolerance": 100.0, "date_window_days": 5,
                "auto_threshold": policy["stage2_auto_threshold"],
                "review_threshold": 0.5,
            },
            enforce_idempotency=False,
        )
        st.session_state.result = result
        st.session_state.txn_by_id = {t.id: t for t in txns}
        st.session_state.ledger_by_id = {e.id: e for e in ledger}

        if ground_truth_file:
            gt = {}
            reader = csv.DictReader(io.StringIO(ground_truth_file.getvalue().decode("utf-8")))
            for row in reader:
                gt_id = row["ground_truth_ledger_id"].strip()
                gt[row["bank_transaction_id"]] = None if gt_id in ("NO_MATCH", "") else gt_id
            st.session_state.ground_truth = gt
        else:
            _default_gt = _os.path.join(_sample_dir, "ground_truth_hard.csv")
            if _os.path.exists(_default_gt):
                gt = {}
                with open(_default_gt) as gtf:
                    reader = csv.DictReader(gtf)
                    for row in reader:
                        gt_id = row["ground_truth_ledger_id"].strip()
                        gt[row["bank_transaction_id"]] = None if gt_id in ("NO_MATCH", "") else gt_id
                st.session_state.ground_truth = gt
                st.sidebar.info("Using sample ground truth for accuracy metrics.")
            else:
                st.session_state.ground_truth = None
    st.success("Done!")

    cache_hits = result["summary"].get("cache_hit_count", 0)
    live_calls = result["summary"].get("llm_calls_made", 0)
    if cache_hits > 0:
        st.info(f"💾 {cache_hits} response(s) loaded from cache -- {live_calls} new LLM call(s) made. Faster and rate-limit safe.")

result = st.session_state.result

if result:
    s = result["summary"]

    
    

    live_pending = len([m for m in result["matches"] if m.status == _MS.PENDING_REVIEW])
    live_confirmed = len([m for m in result["matches"] if m.status == _MS.CONFIRMED])
    live_rejected = len([m for m in result["matches"] if m.status == _MS.REJECTED])

    st.subheader(f"📊 Batch Summary -- {s['total_transactions']} bank transactions processed")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Stage 1 (Exact)", s["stage1_auto_matched"])
    col2.metric("Stage 2 (Fuzzy)", s["stage2_auto_matched"])
    col3.metric("Stage 3 (LLM)", s["stage3_auto_matched"])
    col4.metric("Pending Review", live_pending)
    col5.metric("Unmatched", s["still_unmatched"])

    st.caption(f"✅ Confirmed: {live_confirmed}  |  ❌ Rejected: {live_rejected}")

    st.divider()

    # ACCURACY (only if ground truth provided) 
    if st.session_state.ground_truth:
        predictions = {m.transaction_id: m.ledger_id for m in result["matches"]}
        tp = fp = fn = tn = 0
        for bank_id, gt_ledger in st.session_state.ground_truth.items():
            pred_ledger = predictions.get(bank_id)
            if gt_ledger is not None and pred_ledger == gt_ledger:
                tp += 1
            elif pred_ledger is not None and pred_ledger != gt_ledger:
                fp += 1
            elif gt_ledger is not None and pred_ledger is None:
                fn += 1
            elif gt_ledger is None and pred_ledger is None:
                tn += 1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        st.subheader("🎯 Measured Accuracy (vs ground truth)")
        a1, a2, a3 = st.columns(3)
        a1.metric("Precision", f"{precision*100:.1f}%")
        a2.metric("Recall", f"{recall*100:.1f}%")
        a3.metric("F1 Score", f"{f1*100:.1f}%")
        st.divider()

    # COST/LATENCY 
    st.subheader("💸 Cost & Latency")
    c1, c2, c3 = st.columns(3)
    c1.metric("LLM Calls Made", s["llm_calls_made"])
    c2.metric("Avg Time/Call", f"{s['llm_avg_time_per_call_sec']}s")
    c3.metric("Cost Saved vs LLM-for-all", f"{s['pct_cost_saved_vs_llm_for_everything']}%")

    st.divider()

    # SAFETY
    st.subheader("🔒 Safety Guardrail")
    st.write(f"High-value threshold (10x median): **Rs {s['high_value_threshold']}**")
    st.write(f"Cases force-routed to human review: **{s['safety_guardrail_overrides']}**")

    st.divider()

    
    
    still_pending = [m for m in result["review_queue"] if m.status == _MS.PENDING_REVIEW]

    st.subheader(f"👤 Human Review Queue ({len(still_pending)} cases)")

    for m in still_pending:
        txn = st.session_state.txn_by_id.get(m.transaction_id)
        entry = st.session_state.ledger_by_id.get(m.ledger_id) if m.ledger_id else None

        with st.container(border=True):
            cols = st.columns([3, 1, 1])
            with cols[0]:
                st.write(f"**Bank txn:** amount={txn.amount if txn else '?'} date={txn.date if txn else '?'}")
                st.caption(f"narration: {txn.narration if txn else ''}")
                if entry:
                    st.write(f"**Suggested match:** {entry.vendor_name}, amount={entry.amount}, invoice={entry.invoice_number}")
                st.caption(f"Stage: {m.stage.value} | Confidence: {m.confidence*100:.0f}%")
                is_cached = m.reasoning.startswith("[cached]")
                clean_reasoning = m.reasoning.replace("[cached] ", "")
                if is_cached:
                    st.caption(f"💾 Cached response | Reasoning: {clean_reasoning}")
                else:
                    st.caption(f"Reasoning: {clean_reasoning}")
            with cols[1]:
                if st.button("✅ Confirm", key=f"confirm_{m.id}"):
                    vendor = entry.vendor_name if entry else None
                    apply_feedback(m, confirmed=True, vendor_name=vendor)
                    st.rerun()
            with cols[2]:
                if st.button("❌ Reject", key=f"reject_{m.id}"):
                    vendor = entry.vendor_name if entry else None
                    apply_feedback(m, confirmed=False, vendor_name=vendor)
                    st.rerun()

    st.divider()

    # ALL MATCHES TABLE
    st.subheader("📋 All Matches")
    rows = []
    for m in result["matches"]:
        rows.append({
            "Stage": m.stage.value,
            "Confidence": f"{m.confidence*100:.0f}%",
            "Status": m.status.value if hasattr(m.status, "value") else m.status,
            "Reasoning": ("💾 " if m.reasoning.startswith("[cached]") else "") + m.reasoning.replace("[cached] ", "")[:150],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    # Full export
    full_rows = []
    for m in result["matches"]:
        status_val = m.status.value if hasattr(m.status, "value") else m.status
        full_rows.append({
            "transaction_id": m.transaction_id,
            "matched_to": m.ledger_id,
            "stage": m.stage.value,
            "confidence": m.confidence,
            "status": status_val,
            "reasoning": m.reasoning.replace("[cached] ", ""),
        })
    full_csv = pd.DataFrame(full_rows).to_csv(index=False)
    st.download_button(
        "📥 Download full results (CSV, untruncated reasoning)",
        data=full_csv,
        file_name="reconciliation_results.csv",
        mime="text/csv",
    )

else:
    st.info("👈 Upload your Bank and Ledger CSVs in the sidebar, then click 'Run Reconciliation'.")
