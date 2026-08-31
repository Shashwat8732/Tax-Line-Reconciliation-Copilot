from __future__ import annotations
from rapidfuzz import fuzz
from app.models.schemas import MatchResult, MatchStage, MatchStatus


def _score_pair(txn, entry, amount_tolerance, date_window_days):
    amount_diff = abs(entry.amount - txn.amount)
    date_diff = abs((entry.date - txn.date).days)

    if amount_diff > amount_tolerance and date_diff > date_window_days:
        return None 

    amount_score = max(0.0, 1 - (amount_diff / max(amount_tolerance, 0.01)))
    amount_score = min(amount_score, 1.0)

    date_score = max(0.0, 1 - (date_diff / max(date_window_days, 1)))

    name_sim = fuzz.token_sort_ratio(
        (txn.narration or "").lower(), (entry.vendor_name or "").lower()
    ) / 100.0

    composite = (0.45 * amount_score) + (0.35 * date_score) + (0.20 * name_sim)

    return {
        "amount_diff": round(amount_diff, 2),
        "date_diff_days": date_diff,
        "name_similarity": round(name_sim, 2),
        "composite": round(composite, 4),
    }


def run_stage2(
    transactions, ledger_entries,
    amount_tolerance=3.0, date_window_days=4,
    auto_threshold=0.90, review_threshold=0.60,
):
    matches = []
    used_ledger_ids = set()
    unmatched_txns = []

    for txn in transactions:
        best_entry = None
        best_features = None

        for entry in ledger_entries:
            if entry.id in used_ledger_ids:
                continue
            features = _score_pair(txn, entry, amount_tolerance, date_window_days)
            if features is None:
                continue
            if best_features is None or features["composite"] > best_features["composite"]:
                best_entry = entry
                best_features = features

        if best_entry and best_features and best_features["composite"] >= review_threshold:
            used_ledger_ids.add(best_entry.id)
            confidence = best_features["composite"]
            status = MatchStatus.AUTO_MATCHED if confidence >= auto_threshold else MatchStatus.PENDING_REVIEW

            reason = (
                f"Amount differs by {best_features['amount_diff']}, date is {best_features['date_diff_days']} day(s) apart, "
                f"vendor name is {best_features['name_similarity']*100:.0f}% similar. Confidence {confidence*100:.0f}%."
            )
            m = MatchResult(
                transaction_id=txn.id,
                ledger_id=best_entry.id,
                stage=MatchStage.FUZZY,
                confidence=round(confidence, 3),
                status=status,
                reasoning=reason,
                features=best_features,
            )
            m.log("stage2_fuzzy", reason)
            matches.append(m)
        else:
            unmatched_txns.append(txn)

    unmatched_ledger = [e for e in ledger_entries if e.id not in used_ledger_ids]
    return matches, unmatched_txns, unmatched_ledger