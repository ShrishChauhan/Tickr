# Filing reference — pointer to a regulatory filing for any supported market
from enum import Enum
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel
from .company import CompanyIdentity


class FilingType(str, Enum):
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    EIGHT_K = "8-K"
    DEF_14A = "DEF 14A"
    ANNUAL_REPORT = "ANNUAL_REPORT"         # India equivalent — Phase 4
    QUARTERLY_RESULTS = "QUARTERLY_RESULTS" # India equivalent — Phase 4


class FilingReference(BaseModel):
    company: CompanyIdentity
    filing_type: FilingType
    filed_date: date
    period_of_report: Optional[date] = None
    accession_number: Optional[str] = None  # SEC format "0001234567-23-000001" — US only
    url: str
    summary: Optional[str] = None           # AI-generated summary; cached long-term
    source: str
    fetched_at: datetime
