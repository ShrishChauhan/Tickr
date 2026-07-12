# AI analysis interface — TODO(Phase 2): wire to LLM provider; output is cached long-term
from abc import ABC, abstractmethod
from typing import List
from ..schema import CompanyIdentity, NormalizedFundamentals, FilingReference


class AnalysisEngine(ABC):
    @abstractmethod
    async def analyze_company(
        self,
        company: CompanyIdentity,
        fundamentals: List[NormalizedFundamentals],
        filings: List[FilingReference],
        question: str,
    ) -> str:
        """Return a plain-English analysis of the company given the provided data and question."""
        ...

    @abstractmethod
    async def explain(self, context: str) -> str:
        """Return a short (1-3 sentence) educational note. Must not claim a specific,
        unverified cause for a price move — no news/event data is available."""
        ...
