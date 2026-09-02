# Tax-Line Reconciliation Copilot

**Confidence-tiered - Cost-aware - Explainable - Gated**

Built for Razorpay Build Fest -- Track 04: AI Finance Controller

An AI agent that closes the bank-to-ledger reconciliation loop across a batch of transactions -- reporting its match rate, its cost, and an honest list of exceptions it could not resolve.

---

## Demo

- Live Deployed App: https://tax-line-reconciliation-copilot-main.streamlit.app
- Demo Video: [Add your video link here]
- GitHub Repo: [Add your repo link here]

---

## The Problem

Finance teams manually match hundreds of bank transactions to invoices every week -- it's slow, repetitive, and error-prone. Most automation attempts fail in one of two ways:

- Rule-based matchers are fast and free, but miss anything even slightly messy (a rounding difference, a shortened vendor name, a delayed posting date).
- "LLM-for-everything" approaches are smart, but slow, expensive, and impossible to audit at scale.

We built something in between.

---

## How It Works -- A 4-Stage, Confidence-Tiered Pipeline

The system processes each bank transaction through up to 4 steps, stopping as soon as a confident match is found:

1. **Stage 1 -- Exact match (free, instant).** Reference/invoice number or exact amount+date match. Resolves about 40% of transactions with zero AI cost.

2. **Stage 2 -- Fuzzy match (free, rule-based).** A weighted score on amount tolerance, date window, and vendor-name similarity. Resolves another 10-15%, still without any AI call.

3. **Stage 3 -- LLM reasoning (AI, bounded).** Only the genuinely ambiguous cases reach this stage -- vague narrations, partial-payment-like amounts. This is the only stage that costs money, and it only runs on roughly one-third of transactions.

4. **Human Review Queue (gated).** Anything below the confidence threshold -- or any unusually high-value match -- is never auto-approved. It waits for a human to confirm or reject.

Every match, from any stage, carries a confidence score, a plain-English reason, and is written to a permanent audit log.

---

## Measured Results (not assumed)

Tested on a 63-transaction synthetic batch with a labeled ground truth:

| Metric | Value |
|---|---|
| Precision | 100% -- zero false matches |
| Recall | 98.2% |
| F1 Score | 99.1% |
| LLM calls made | 23 / 63 (only the ambiguous ~35%) |
| Cost saved vs. calling an LLM on every transaction | 63.5% |
| Unit tests passing | 6 / 6 |

We didn't cherry-pick this -- the eval script (evaluate.py) is in the repo and reproducible against the included sample data.

---

## What Makes This Different From a Generic Reconciliation Tool

Enterprise reconciliation tools (Tally, Zoho Books, HighRadius) already exist -- we're not claiming to have invented the category. What we focused on instead:

- **Full explainability.** Every match has a human-readable reason, not a black-box score. You can see why the system thinks two records match.
- **Bounded AI cost by design.** The architecture routes only genuinely ambiguous cases to the LLM -- proven at 63% cost savings on our test batch, not a marketing number.
- **Safety guardrails, not blind trust.** Any transaction more than 10x the batch's typical size is always routed to a human, regardless of confidence.
- **Honest exceptions, not hidden failures.** If the LLM API rate-limits or fails mid-run, the system doesn't crash -- it marks the transaction as needing review and logs exactly why. We hit this live during testing and verified it holds.
- **A real feedback loop.** When a human confirms or rejects a borderline match, the system's auto-approval thresholds adjust -- no model retraining required.

---

## Project Structure

- backend/app/models/schemas.py -- Data models (Transaction, Ledger, Match)
- backend/app/services/ingestion.py -- CSV parsing and normalization
- backend/app/services/stage1_exact.py -- Deterministic matcher
- backend/app/services/stage2_fuzzy.py -- Fuzzy matcher (rapidfuzz)
- backend/app/services/stage3_llm.py -- LLM reasoning for hard cases (cached, fallback-safe)
- backend/app/services/pipeline.py -- Orchestrates all stages, safety guardrail, audit log
- backend/app/services/feedback.py -- Human feedback loop (threshold tuning)
- backend/dashboard.py -- Streamlit dashboard (upload, run, review, export)
- backend/evaluate.py -- Precision, Recall, F1 against ground truth
- backend/test_matching.py -- Unit tests
- sample_data/bank_statement.csv -- 63 sample bank transactions
- sample_data/ledger.csv -- 62 sample ledger entries
- sample_data/ground_truth.csv -- Labeled correct answers for accuracy measurement

---

## Quick Start

Install dependencies:

cd backend
pip install -r requirements.txt

Add your Groq API key to a .env file:

echo "GROQ_API_KEY=your_key_here" > .env

Run the dashboard:

streamlit run dashboard.py

Then in the browser: upload bank_statement.csv, ledger.csv, and optionally ground_truth_hard.csv from sample_data/, and click Run Reconciliation.

Or run the evaluation directly (no UI):

python3 evaluate.py

Run unit tests:

pytest test_matching.py -v

---

## Known Limitations (documented honestly, not hidden)

- Currency mismatch -- assumes single-currency; no exchange-rate normalization yet.
- Partial payments -- one invoice split across multiple bank transactions is not resolved (one-to-one matching only). The system correctly flags these as exceptions rather than guessing.
- GST/tax-inclusive amounts -- a bank amount that includes 18% GST on top of the invoice base amount falls outside our tolerance and is honestly reported as unmatched.
- Duplicate invoices -- if two ledger entries genuinely share the same amount, date, and vendor, the system may pick either.
- LLM provider -- currently uses Groq's free tier, which has daily rate limits. The architecture is model-agnostic; swapping in a production LLM (Claude, GPT-4) is a one-line change in stage3_llm.py.

---

## Business Impact

Manual reconciliation takes roughly 5 minutes per transaction. On our 63-transaction test batch:

- About 40% of transactions resolved in seconds, with zero human involvement.
- Only 23 transactions (36.5%) needed an LLM call -- and even fewer needed human eyes.
- Estimated time savings: 85-90% for a batch this size, and the savings compound at scale since Stages 1-2 are free and scale linearly.

---

## Tech Stack

- Backend logic: Python
- Fuzzy matching: RapidFuzz
- LLM reasoning: Groq (openai/gpt-oss-120b)
- Dashboard: Streamlit
- Testing: pytest

---

**Made by Shashwat Raj** | [GitHub](https://github.com/Shashwat8732) | [LinkedIn](https://www.linkedin.com/in/shashwatraj1412/)

