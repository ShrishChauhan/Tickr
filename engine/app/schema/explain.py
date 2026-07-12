# Request/response for the "explain this" educational-context endpoint
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ExplainRequest(BaseModel):
    ticker: str
    asset_type: str
    current_price: float
    change_pct: Optional[float] = None
    gross_margin: Optional[float] = None
    pe_ratio: Optional[float] = None


class ExplainResult(BaseModel):
    ticker: str
    explanation: str
    generated_at: datetime
    cached: bool
