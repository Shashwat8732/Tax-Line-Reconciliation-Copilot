from __future__ import annotations
import os
import json
import time
import hashlib
from groq import Groq
from app.models.schemas import MatchResult, MatchStage, MatchStatus

MODEL = "openai/gpt-oss-120b"

_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "llm_cache.json")


def _load_cache():
    if os.path.exists(_CACHE_PATH):
        with open(_CACHE_PATH) as f:
            return json.load(f)
    return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    with open(_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def _cache_key(prompt):
    return hashlib.sha256(prompt.encode()).hexdigest()


def _top_k_candidates(txn, ledger_entries, k=5, loose_amount_pct=0.15, loose_date_days=15):
    scored = []
    for entry in ledger_entries:
        amount_diff_pct = abs(entry.amount - txn.amount) / max(abs(txn.amount), 1)
        date_diff = abs((entry.date - txn.date).days)
        if amount_diff_pct <= loose_amount_pct or date_diff <= loose_date_days:
            scored.append((amount_diff_pct + date_diff / 100, entry))
    scored.sort(key=lambda x: x[0])
    return [e for _, e in scored[:k]]


def _build_prompt(txn, candidates):
    cand_lines = []
    for i, c in enumerate(candidates):
        cand_lines.append(
            f"  [{i}] invoice={c.invoice_number} vendor={c.vendor_name} amount={c.amount} date={c.date}"
        )
    return f"""You are a financial reconciliation assistant matching bank payments to
invoices. Real-world payments often do NOT match invoices exactly:
- Amounts can differ by up to ~5% (partial payments, rounding, bank fees deducted)
- Dates can differ by up to ~10 days (posting delays, weekends, processing lag)
- Vendor names in bank narrations are often abbreviated or informal versions of the
  official ledger vendor name

Use REASONING, not exact-match rules. If a candidate is CLOSE on amount and date and
the vendor name is plausibly the same entity (even if abbreviated/reordered), that is
likely the correct match. Only return -1 if truly no candidate is plausible.

Bank transaction:
  amount={txn.amount} date={txn.date} reference={txn.reference}
  narration="{txn.narration}"

Candidates:
{chr(10).join(cand_lines) if cand_lines else "  (none)"}

Respond with ONLY valid JSON, nothing else -- no markdown fences, no explanation outside the JSON:
{{"match_index": <index or -1>, "confidence": <0.0-1.0>, "reasoning": "<short reason>"}}"""


def run_stage3(transactions, ledger_entries, auto_threshold=0.85, review_threshold=0.50, api_key=None):
    client = Groq(api_key=api_key or os.environ.get("GROQ_API_KEY"))
    cache = _load_cache()

    llm_call_count = 0       
    cache_hit_count = 0
    llm_total_time = 0.0

    matches = []
    still_unmatched = []
    used_ledger_ids = set()

    for txn in transactions:
        available = [e for e in ledger_entries if e.id not in used_ledger_ids]
        candidates = _top_k_candidates(txn, available)

        if not candidates:
            m = MatchResult(
                transaction_id=txn.id, stage=MatchStage.UNMATCHED,
                confidence=0.0, status=MatchStatus.UNMATCHED,
                reasoning="No plausible candidate found within loose window; LLM call skipped.",
            )
            matches.append(m)
            continue

        prompt = _build_prompt(txn, candidates)
        ckey = _cache_key(prompt)

        if ckey in cache:
           
            parsed = dict(cache[ckey]) 
            parsed["reasoning"] = "[cached] " + parsed.get("reasoning", "")
            cache_hit_count += 1
        else:
           
            _call_start = time.time()
            try:
                llm_call_count += 1
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024,
                    temperature=0,  
                )
                raw_text = response.choices[0].message.content.strip()
                raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                parsed = json.loads(raw_text)
                cache[ckey] = parsed 
                _save_cache(cache)
            except Exception as e:
               
                parsed = {
                    "match_index": -1,
                    "confidence": 0.0,
                    "reasoning": f"LLM call failed or response could not be parsed ({type(e).__name__}): {str(e)[:100]}",
                }
            finally:
                llm_total_time += time.time() - _call_start

        idx = parsed.get("match_index", -1)
        confidence = float(parsed.get("confidence", 0.0))
        reasoning = parsed.get("reasoning", "")

        if idx is not None and 0 <= idx < len(candidates) and confidence >= review_threshold:
            matched_entry = candidates[idx]
            used_ledger_ids.add(matched_entry.id)
            status = MatchStatus.AUTO_MATCHED if confidence >= auto_threshold else MatchStatus.PENDING_REVIEW
            m = MatchResult(
                transaction_id=txn.id, ledger_id=matched_entry.id,
                stage=MatchStage.LLM_REASONING, confidence=confidence,
                status=status, reasoning=reasoning,
            )
            matches.append(m)
        else:
            m = MatchResult(
                transaction_id=txn.id, stage=MatchStage.UNMATCHED,
                confidence=confidence, status=MatchStatus.UNMATCHED,
                reasoning=reasoning or "LLM could not find a confident match.",
            )
            matches.append(m)
            still_unmatched.append(txn)

    stats = {
        "llm_call_count": llm_call_count,
        "cache_hit_count": cache_hit_count,
        "llm_total_time_sec": round(llm_total_time, 2),
    }
    return matches, still_unmatched, stats
