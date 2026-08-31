from datetime import date
from app.models.schemas import BankTransaction, LedgerEntry, MatchStatus
from app.services.stage1_exact import run_stage1
from app.services.stage2_fuzzy import run_stage2


def test_stage1_exact_match_by_reference():
   
    txns = [BankTransaction(id="t1", date=date(2025, 1, 1), amount=5000, reference="INV100")]
    ledger = [LedgerEntry(id="l1", date=date(2025, 1, 1), amount=5000, invoice_number="INV100", vendor_name="ACME")]

    matches, unmatched_txns = run_stage1(txns, ledger)

    assert len(matches) == 1
    assert matches[0].confidence == 1.0
    assert matches[0].status == MatchStatus.AUTO_MATCHED
    assert matches[0].ledger_id == "l1"
    assert len(unmatched_txns) == 0


def test_stage1_no_match_when_amount_and_ref_differ():
   
    txns = [BankTransaction(id="t1", date=date(2025, 1, 1), amount=5000, reference="INV100")]
    ledger = [LedgerEntry(id="l1", date=date(2025, 1, 5), amount=9999, invoice_number="INV999", vendor_name="ACME")]

    matches, unmatched_txns = run_stage1(txns, ledger)

    assert len(matches) == 0
    assert len(unmatched_txns) == 1


def test_stage2_fuzzy_within_tolerance():
   
    txns = [BankTransaction(id="t1", date=date(2025, 1, 1), amount=5002, reference=None, narration="Payment to Acme Corp")]
    ledger = [LedgerEntry(id="l1", date=date(2025, 1, 2), amount=5000, invoice_number="INV1", vendor_name="ACME CORP")]

    matches = run_stage2(
        txns, ledger, amount_tolerance=10.0, date_window_days=3, review_threshold=0.5
    )

    assert len(matches) == 1
    assert matches[0].confidence > 0.5
    assert matches[0].ledger_id == "l1"


def test_stage2_no_match_outside_tolerance():
   
    txns = [BankTransaction(id="t1", date=date(2025, 1, 1), amount=5000, reference=None, narration="Random payment")]
    ledger = [LedgerEntry(id="l1", date=date(2025, 6, 1), amount=99999, invoice_number="INV1", vendor_name="XYZ")]

    matches, unmatched_txns = run_stage2(
        txns, ledger, amount_tolerance=10.0, date_window_days=3, review_threshold=0.5
    )

    assert len(matches) == 0
    assert len(unmatched_txns) == 1


def test_stage1_does_not_reuse_ledger_entry():
   
    txns = [
        BankTransaction(id="t1", date=date(2025, 1, 1), amount=5000, reference="INV100"),
        BankTransaction(id="t2", date=date(2025, 1, 1), amount=5000, reference="INV100"),
    ]
    ledger = [LedgerEntry(id="l1", date=date(2025, 1, 1), amount=5000, invoice_number="INV100", vendor_name="ACME")]

    matches, unmatched_txns = run_stage1(txns, ledger)

    assert len(matches) == 1
    assert len(unmatched_txns) == 1


def test_clean_amount_handles_messy_formats():
    
    from app.services.ingestion import _clean_amount

    assert _clean_amount("Rs. 4,783.95") == 4783.95
    assert _clean_amount("INR 12,000") == 12000.0
    assert _clean_amount("$1,234.56") == 1234.56
    assert _clean_amount("(500.00)") == -500.0
    assert _clean_amount("1,23,456.78") == 123456.78
    assert _clean_amount("") == 0.0
