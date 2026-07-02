# Groq-backed AnalysisEngine — implements the abstract interface; swap provider by adding a new file
import asyncio
import logging
from typing import List

from .interface import AnalysisEngine
from ..schema import CompanyIdentity, NormalizedFundamentals, FilingReference
from ..schema.fundamentals import Period
from ..config import settings

logger = logging.getLogger(__name__)


class GroqAnalysisEngine(AnalysisEngine):

    def __init__(self):
        from groq import Groq
        self._client = Groq(api_key=settings.GROQ_API_KEY)
        self._model = settings.GROQ_MODEL

    async def analyze_company(
        self,
        company: CompanyIdentity,
        fundamentals: List[NormalizedFundamentals],
        filings: List[FilingReference],
        question: str = "",
    ) -> str:
        prompt = self._build_prompt(company, fundamentals, filings, question)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._call_groq, prompt)

    def _call_groq(self, prompt: str) -> str:
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a financial analyst providing objective, data-driven analysis. "
                        "Ground every statement in specific figures provided to you. "
                        "Never speculate beyond what the data shows."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1500,
            temperature=0.1,
        )
        return completion.choices[0].message.content

    def _build_prompt(
        self,
        company: CompanyIdentity,
        fundamentals: List[NormalizedFundamentals],
        filings: List[FilingReference],
        question: str,
    ) -> str:
        lines: List[str] = []

        lines.append(
            f"COMPANY: {company.name} ({company.ticker})"
            f" — {company.exchange.value}, reporting in {company.currency.value}"
        )
        lines.append("")

        # Oldest → newest so trends read left-to-right
        sorted_funds = sorted(fundamentals, key=lambda f: f.period_end_date)

        def _label(f: NormalizedFundamentals) -> str:
            if f.period == Period.ANNUAL:
                return f"FY{f.fiscal_year}" if f.fiscal_year else str(f.period_end_date)
            if f.period == Period.QUARTERLY:
                q = f"Q{f.fiscal_quarter}" if f.fiscal_quarter else ""
                yr = f" FY{f.fiscal_year}" if f.fiscal_year else ""
                return q + yr or str(f.period_end_date)
            return "TTM"

        def _b(v) -> str:
            return f"${v / 1_000_000_000:.1f}B" if v is not None else "—"

        def _eps(v) -> str:
            return f"${v:.2f}" if v is not None else "—"

        period_labels = [_label(f) for f in sorted_funds]

        rows = [
            ("Revenue",          [_b(f.income_statement.revenue) for f in sorted_funds]),
            ("Gross Profit",     [_b(f.income_statement.gross_profit) for f in sorted_funds]),
            ("Operating Income", [_b(f.income_statement.operating_income) for f in sorted_funds]),
            ("EBITDA",           [_b(f.income_statement.ebitda) for f in sorted_funds]),
            ("Net Income",       [_b(f.income_statement.net_income) for f in sorted_funds]),
            ("EPS (diluted)",    [_eps(f.income_statement.eps_diluted) for f in sorted_funds]),
            ("Free Cash Flow",   [_b(f.cash_flow.free_cash_flow) for f in sorted_funds]),
            ("Total Debt",       [_b(f.balance_sheet.total_debt) for f in sorted_funds]),
            ("Cash & Equiv.",    [_b(f.balance_sheet.cash_and_equivalents) for f in sorted_funds]),
            ("Total Assets",     [_b(f.balance_sheet.total_assets) for f in sorted_funds]),
        ]

        col_w = max(len(l) for l in period_labels) + 2
        lbl_w = max(len(r[0]) for r in rows) + 2

        header = " " * lbl_w + "  ".join(l.center(col_w) for l in period_labels)
        lines.append("FINANCIAL SUMMARY:")
        lines.append(header)
        lines.append("-" * len(header))
        for name, vals in rows:
            lines.append(name.ljust(lbl_w) + "  ".join(v.center(col_w) for v in vals))
        lines.append("")

        # Key ratios from most recent period only (they are TTM-based)
        recent = sorted_funds[-1]
        rt = recent.ratios
        # yfinance returns margin/return ratios as decimals (0–1), not percentages — multiply by 100
        ratio_parts = []
        for label, val, fmt, scale in [
            ("P/E",         rt.pe_ratio,        "{:.1f}x",  1),
            ("P/S",         rt.ps_ratio,        "{:.1f}x",  1),
            ("EV/EBITDA",   rt.ev_ebitda,       "{:.1f}x",  1),
            ("Gross Margin",rt.gross_margin,    "{:.1f}%",  100),
            ("Op. Margin",  rt.operating_margin,"{:.1f}%",  100),
            ("Net Margin",  rt.net_margin,      "{:.1f}%",  100),
            ("ROE",         rt.roe,             "{:.1f}%",  100),
            ("Debt/Equity", rt.debt_to_equity,  "{:.2f}",   1),
        ]:
            if val is not None:
                ratio_parts.append(f"{label}: {fmt.format(val * scale)}")
        if ratio_parts:
            lines.append(f"KEY RATIOS (most recent, as of {recent.period_end_date}):")
            lines.append("  " + " | ".join(ratio_parts))
            lines.append("")

        if filings:
            lines.append("RECENT FILINGS:")
            for f in sorted(filings, key=lambda x: x.filed_date, reverse=True)[:5]:
                lines.append(f"  - {f.filing_type.value} filed {f.filed_date}")
            lines.append("")

        lines.append("=" * 60)
        lines.append("")
        if question:
            lines.append(f"Specific question: {question}")
            lines.append("")

        lines.append(
            "Based ONLY on the data above, write a structured financial analysis with these five sections:"
        )
        lines.append("1. Financial Trend Summary — revenue and income direction across the periods shown")
        lines.append("2. Profitability Analysis — margin trends and earnings quality")
        lines.append("3. Balance Sheet & Leverage — debt levels, cash position, financial strength")
        lines.append("4. Cash Flow Analysis — operating and free cash flow quality")
        lines.append("5. Investment Considerations: identify exactly one specific financial strength and one specific financial risk clearly visible in this data, each supported by the exact figures from the table above. Do not repeat figures already cited in sections 1–4. Do not add generic statements about financial health.")
        lines.append("")
        lines.append("Rules:")
        lines.append("- Cite specific figures for every claim (e.g. 'revenue grew from $X to $Y').")
        lines.append("- Do NOT invent, estimate, or reference any figure not shown in the data above.")
        lines.append("- Do not speculate about future performance or make investment recommendations.")
        lines.append("- Keep each section concise (3-5 sentences).")

        return "\n".join(lines)
