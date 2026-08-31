from __future__ import annotations
import pandas as pd
import re
from datetime import datetime
from app.models.schemas import BankTransaction, LedgerEntry


def _clean_amount(raw) -> float:
   
    if pd.isna(raw):
        return 0.0
    s = str(raw).strip()
    if not s:
        return 0.0

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    if s.startswith("-"):
        negative = True


    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return 0.0

    
    last_comma = s.rfind(",")
    last_dot = s.rfind(".")

    if last_comma == -1 and last_dot == -1:
        # No separators at all, e.g. "478395"
        cleaned = s
    elif last_comma != -1 and last_dot == -1:
        
        digits_after = s[last_comma + 1:]
        if len(digits_after) == 3:
            cleaned = s.replace(",", "")
        else:
            cleaned = s.replace(",", ".")
    elif last_comma > last_dot:
       
        cleaned = s.replace(".", "").replace(",", ".")
    else:
      
        cleaned = s.replace(",", "")

    
    if cleaned.count(".") > 1:
        head, _, tail = cleaned.rpartition(".")
        cleaned = head.replace(".", "") + "." + tail

    try:
        val = float(cleaned)
    except ValueError:
        return 0.0

    return -abs(val) if negative else val


def _parse_date(raw) -> datetime.date:
    if pd.isna(raw):
        raise ValueError("empty date")
    s = str(raw).strip()
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return pd.to_datetime(s).date()


def load_bank_statement(csv_path: str) -> list[BankTransaction]:
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]

    col_date = next((c for c in df.columns if "date" in c), None)
    col_amount = next((c for c in df.columns if "amount" in c), None)
    col_ref = next((c for c in df.columns if "ref" in c), None)
    col_narr = next((c for c in df.columns if "narrat" in c), None)

    txns = []
    for i, row in df.iterrows():
        txns.append(BankTransaction(
            id=f"bank_{i}",
            date=_parse_date(row[col_date]),
            amount=_clean_amount(row[col_amount]),
            reference=str(row[col_ref]).strip() if col_ref and not pd.isna(row[col_ref]) else None,
            narration=str(row[col_narr]).strip() if col_narr and not pd.isna(row[col_narr]) else "",
            raw=row.to_dict(),
        ))
    return txns


def load_ledger(csv_path: str) -> list[LedgerEntry]:
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]

    col_date = next((c for c in df.columns if "date" in c), None)
    col_amount = next((c for c in df.columns if "amount" in c), None)
    col_inv = next((c for c in df.columns if "invoice" in c), None)
    col_vendor = next((c for c in df.columns if "vendor" in c), None)

    entries = []
    for i, row in df.iterrows():
        entries.append(LedgerEntry(
            id=f"ledger_{i}",
            date=_parse_date(row[col_date]),
            amount=_clean_amount(row[col_amount]),
            invoice_number=str(row[col_inv]).strip() if col_inv and not pd.isna(row[col_inv]) else None,
            vendor_name=str(row[col_vendor]).strip() if col_vendor and not pd.isna(row[col_vendor]) else "",
            raw=row.to_dict(),
        ))
    return entries
