from __future__ import annotations
from app.models.schemas import BankTransaction, LedgerEntry, MatchResult, MatchStage, MatchStatus


def _norm_ref(s: str | None) -> str:
   
    if not s:
        return ""
    return "".join(ch for ch in s.upper() if ch.isalnum())


def run_stage1(
    transactions: list[BankTransaction],
    ledger_entries: list[LedgerEntry],
) -> tuple[list[MatchResult], list[BankTransaction], list[LedgerEntry]]:
  
    matches: list[MatchResult] = []
    used_ledger_ids: set[str] = set()
    unmatched_txns: list[BankTransaction] = []

   
    ledger_by_ref: dict[str, list[LedgerEntry]] = {}
    for entry in ledger_entries:
        key = _norm_ref(entry.invoice_number)
        if key:
            ledger_by_ref.setdefault(key, []).append(entry)

    for txn in transactions:
        found = None
        reason = ""

       
        ref_key = _norm_ref(txn.reference)
        if ref_key and ref_key in ledger_by_ref:
            candidates = [e for e in ledger_by_ref[ref_key] if e.id not in used_ledger_ids]
            if candidates:
                found = candidates[0]
                reason = f"Reference '{txn.reference}' matches invoice number exactly."

        
        if not found:
            for entry in ledger_entries:
                if entry.id in used_ledger_ids:
                    continue
                if entry.date == txn.date and abs(entry.amount - txn.amount) < 0.005:
                    found = entry
                    reason = f"Amount ({txn.amount}) and date ({txn.date}) are an exact match."
                    break

        if found:
            used_ledger_ids.add(found.id)
            m = MatchResult(
                transaction_id=txn.id,
                ledger_id=found.id,
                stage=MatchStage.EXACT,
                confidence=1.0,
                status=MatchStatus.AUTO_MATCHED,
                reasoning=reason,
            )
            m.log("stage1_exact", reason)
            matches.append(m)
        else:
            unmatched_txns.append(txn)

    unmatched_ledger = [e for e in ledger_entries if e.id not in used_ledger_ids]
    return matches, unmatched_txns, unmatched_ledger