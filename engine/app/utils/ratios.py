from typing import Optional
from ..schema.fundamentals import NormalizedFundamentals, Ratios


def _safe_div(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den == 0:
        return None
    return num / den


def derive_ratios(fund: NormalizedFundamentals) -> Ratios:
    """Fill in non-valuation ratios computable from statement data.

    Preserves values already set (e.g. live market ratios on the most recent
    period from yfinance .info). All margin/return values are stored as decimals
    (0.44 = 44%); callers must multiply by 100 to display as a percentage.

    Valuation ratios (P/E, P/S, P/B, EV multiples) are passed through unchanged
    — they require a market price and cannot be derived from statements alone.
    """
    is_ = fund.income_statement
    bs  = fund.balance_sheet
    r   = fund.ratios

    # yfinance returns grossMargins=0.0 for financials (banks, insurers) where
    # gross_profit is N/A. Treat that as absent rather than a real 0% margin.
    gm_raw = None if (r.gross_margin == 0.0 and is_.gross_profit is None) else r.gross_margin

    return Ratios(
        # Valuation — not derivable; pass through
        pe_ratio  = r.pe_ratio,
        ps_ratio  = r.ps_ratio,
        pb_ratio  = r.pb_ratio,
        ev_ebitda = r.ev_ebitda,
        ev_revenue= r.ev_revenue,

        # Profitability
        gross_margin     = gm_raw             if gm_raw             is not None else _safe_div(is_.gross_profit,    is_.revenue),
        operating_margin = r.operating_margin if r.operating_margin is not None else _safe_div(is_.operating_income, is_.revenue),
        net_margin       = r.net_margin       if r.net_margin       is not None else _safe_div(is_.net_income,       is_.revenue),
        roe              = r.roe              if r.roe              is not None else _safe_div(is_.net_income,       bs.total_equity),
        roa              = r.roa              if r.roa              is not None else _safe_div(is_.net_income,       bs.total_assets),
        roic             = r.roic,  # needs NOPAT decomposition — not available in schema

        # Leverage
        debt_to_equity = r.debt_to_equity if r.debt_to_equity is not None else _safe_div(bs.total_debt, bs.total_equity),
        debt_to_ebitda = r.debt_to_ebitda if r.debt_to_ebitda is not None else _safe_div(bs.total_debt, is_.ebitda),

        # No interest_expense field in schema — pass through
        interest_coverage = r.interest_coverage,

        # Current/quick ratios need current assets/liabilities (not in BalanceSheet schema) — pass through
        current_ratio = r.current_ratio,
        quick_ratio   = r.quick_ratio,
    )
