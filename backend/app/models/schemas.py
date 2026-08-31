from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
import uuid

# Stage and Status

class MatchStage(str, Enum):
    EXACT = "stage1_exact"
    FUZZY = "stage2_fuzzy"
    LLM_REASONING = "stage3_llm"
    UNMATCHED = "unmatched"


class MatchStatus(str, Enum):
    AUTO_MATCHED = "auto_matched"       # high confidence
    PENDING_REVIEW = "pending_review"    # low confidence,
    CONFIRMED = "confirmed"              # confirmed by human
    REJECTED = "rejected"                # rejected by human
    UNMATCHED = "unmatched"              # no match found


# Bank statement

@dataclass
class BankTransaction:
    id: str
    date: date
    amount: float
    currency: str = "INR"
    reference: str | None = None
    narration: str = ""
    raw: dict = field(default_factory=dict) 


# Ledger/Invoice 

@dataclass
class LedgerEntry:
    id: str
    date: date
    amount: float
    currency: str = "INR"
    invoice_number: str | None = None
    vendor_name: str = ""
    raw: dict = field(default_factory=dict)


# a match result between a bank transaction and a ledger entry

@dataclass
class MatchResult:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    transaction_id: str = ""
    ledger_id: str | None = None
    stage: MatchStage = MatchStage.UNMATCHED
    confidence: float = 0.0            
    status: MatchStatus = MatchStatus.UNMATCHED
    reasoning: str = ""                 
    features: dict = field(default_factory=dict)  
    cost_usd: float = 0.0               
    audit_trail: list = field(default_factory=list)

    def log(self, event: str, detail: str):
        
        self.audit_trail.append({"event": event, "detail": detail})