# Analysis result returned by the analyze endpoint
from datetime import datetime
from pydantic import BaseModel


class AnalysisResult(BaseModel):
    ticker: str
    analysis: str
    disclaimer: str
    generated_at: datetime
    cached: bool
    source: str
    period: str
    periods_analyzed: int
