"""
Manual data pipeline verification — throwaway script.
Run from repo root:
    engine\.venv\Scripts\python.exe engine/tests/manual_verify.py

Tests real live fetches via yfinance + EDGAR adapters directly.
No LLM calls. No faking. Print failures honestly.
"""
import sys
import asyncio
from pathlib import Path
from typing import Optional, List

# Allow `from app.xxx` imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.adapters.yfinance import YFinanceAdapter
from app.adapters.edgar import EdgarAdapter
from app.schema import Period, NormalizedFundamentals, CompanyIdentity, Ratios

# ─────────────────────────────────────────────────────────────
# Formatting
# ─────────────────────────────────────────────────────────────

def _B(v: Optional[float]) -> str:
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v)/1e9:.2f}B"

def _pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v*100:+.1f}%"

def _derive_margin(num: Optional[float], denom: Optional[float]) -> Optional[float]:
    if num is None or denom is None or denom == 0:
        return None
    return num / denom


def _flags(f: NormalizedFundamentals, is_bank: bool) -> List[str]:
    """Return human-readable warning flags for a single fundamentals record."""
    out = []
    is_ = f.income_statement
    bs  = f.balance_sheet
    r   = f.ratios

    # None fields we care about
    nones = []
    if is_.revenue is None:
        nones.append("revenue")
    if is_.net_income is None:
        nones.append("net_income")
    if is_.gross_profit is None and not is_bank:
        nones.append("gross_profit")
    if bs.total_assets is None:
        nones.append("total_assets")
    if bs.total_equity is None:
        nones.append("total_equity")
    if nones:
        out.append(f"None fields: {', '.join(nones)}")

    # Negative values — flag them but note that some are expected
    if is_.net_income is not None and is_.net_income < 0:
        out.append(f"NEGATIVE net_income = {_B(is_.net_income)}")
    if is_.operating_income is not None and is_.operating_income < 0:
        out.append(f"NEGATIVE operating_income = {_B(is_.operating_income)}")
    if is_.gross_profit is not None and is_.gross_profit < 0:
        out.append(f"NEGATIVE gross_profit = {_B(is_.gross_profit)}")

    # Structural sanity
    if is_.revenue is not None and is_.gross_profit is not None:
        if is_.gross_profit > is_.revenue * 1.01:
            out.append(f"SUSPICIOUS: gross_profit ({_B(is_.gross_profit)}) > revenue ({_B(is_.revenue)})")
    if bs.total_debt is not None and bs.total_debt < 0:
        out.append(f"SUSPICIOUS: negative total_debt = {_B(bs.total_debt)}")
    if bs.total_assets is not None and bs.total_liabilities is not None and bs.total_equity is not None:
        implied = bs.total_liabilities + bs.total_equity
        if abs(implied - bs.total_assets) / max(abs(bs.total_assets), 1) > 0.05:
            out.append(f"SUSPICIOUS: assets≠liab+equity ({_B(bs.total_assets)} vs {_B(implied)})")

    return out


def div(width=70, char="-"):
    print(char * width)

def header(title: str):
    print()
    div(70, "=")
    print(f"  {title}")
    div(70, "=")

def subhead(title: str):
    print(f"\n  +-- {title}")


# ─────────────────────────────────────────────────────────────
# Per-ticker verification
# ─────────────────────────────────────────────────────────────

async def verify_ticker(
    yf: YFinanceAdapter,
    ticker: str,
    note: str,
    is_bank: bool,
):
    header(f"{ticker}  —  {note}")

    # 1. Identity
    try:
        company = await yf.get_company(ticker)
        print(f"  Name    : {company.name}")
        print(f"  Exchange: {company.exchange.value}  |  Currency: {company.currency.value}  |  Market: {company.market.value}")
    except Exception as exc:
        print(f"  ERROR resolving identity: {exc}")
        return None

    # 2. Annual — latest 3 FY
    subhead("ANNUAL fundamentals — latest 3 fiscal years")
    try:
        annual = await yf.get_fundamentals(company, Period.ANNUAL, limit=3)
    except Exception as exc:
        print(f"  |  ERROR: {exc}")
        annual = []

    if not annual:
        print("  |  WARNING: no annual data returned")
    else:
        print(f"  |  {'FY':>4}  {'Period end':>12}  {'Revenue':>10}  {'Net Income':>11}  {'Total Debt':>11}  {'Gross Mgn':>9}  {'Op Mgn':>7}  {'Net Mgn':>7}  {'ROE':>7}")
        print(f"  |  " + "-" * 80)
        for f in annual:
            is_  = f.income_statement
            bs   = f.balance_sheet
            r    = f.ratios
            # Derive margins from statements if ratios are blank (older periods)
            gm  = r.gross_margin  or _derive_margin(is_.gross_profit, is_.revenue)
            opm = r.operating_margin or _derive_margin(is_.operating_income, is_.revenue)
            nm  = r.net_margin   or _derive_margin(is_.net_income, is_.revenue)
            roe = r.roe

            fy_label = str(f.fiscal_year) if f.fiscal_year else "????"
            print(
                f"  |  {fy_label:>4}  {str(f.period_end_date):>12}  "
                f"{_B(is_.revenue):>10}  {_B(is_.net_income):>11}  "
                f"{_B(bs.total_debt):>11}  "
                f"{_pct(gm):>9}  {_pct(opm):>7}  {_pct(nm):>7}  {_pct(roe):>7}"
            )
            for flag in _flags(f, is_bank):
                print(f"  |    [!] {flag}")

    # 3. Quarterly — latest 2
    subhead("QUARTERLY fundamentals — latest 2 quarters")
    try:
        quarterly = await yf.get_fundamentals(company, Period.QUARTERLY, limit=2)
    except Exception as exc:
        print(f"  |  ERROR: {exc}")
        quarterly = []

    if not quarterly:
        print("  |  WARNING: no quarterly data returned")
    else:
        has_2026 = False
        for f in quarterly:
            is_  = f.income_statement
            q_label = f"Q{f.fiscal_quarter}" if f.fiscal_quarter else "Q?"
            print(f"  |  {q_label} ({f.period_end_date})  Revenue={_B(is_.revenue)}  Net Income={_B(is_.net_income)}")
            if f.period_end_date.year >= 2026:
                has_2026 = True
        if has_2026:
            print(f"  |  [OK] 2026 quarter data confirmed")
        else:
            latest = quarterly[0].period_end_date if quarterly else None
            print(f"  |  [!] No 2026 data -- latest quarter ends {latest} (may lag by one quarter if not yet filed)")

    return company


# ─────────────────────────────────────────────────────────────
# Cross-source revenue check
# ─────────────────────────────────────────────────────────────

async def cross_source_check(
    yf: YFinanceAdapter,
    edgar: EdgarAdapter,
    ticker: str,
):
    print(f"\n  -- {ticker}")
    try:
        yf_company     = await yf.get_company(ticker)
        edgar_company  = await edgar.get_company(ticker)
    except Exception as exc:
        print(f"     ERROR resolving company: {exc}")
        return

    # yfinance latest annual
    try:
        yf_data = await yf.get_fundamentals(yf_company, Period.ANNUAL, limit=1)
        yf_rev  = yf_data[0].income_statement.revenue if yf_data else None
        yf_fy   = yf_data[0].fiscal_year if yf_data else None
        yf_date = yf_data[0].period_end_date if yf_data else None
    except Exception as exc:
        print(f"     yfinance ERROR: {exc}")
        yf_rev = yf_fy = yf_date = None

    # EDGAR latest annual
    try:
        ed_data = await edgar.get_fundamentals(edgar_company, Period.ANNUAL, limit=1)
        ed_rev  = ed_data[0].income_statement.revenue if ed_data else None
        ed_fy   = ed_data[0].fiscal_year if ed_data else None
        ed_date = ed_data[0].period_end_date if ed_data else None
    except Exception as exc:
        print(f"     edgar ERROR: {exc}")
        ed_rev = ed_fy = ed_date = None

    print(f"     yfinance : FY{yf_fy}  ({yf_date})  revenue = {_B(yf_rev)}")
    print(f"     edgar    : FY{ed_fy}  ({ed_date})  revenue = {_B(ed_rev)}")

    if yf_rev is not None and ed_rev is not None:
        if yf_fy != ed_fy:
            print(f"     [!] Different fiscal years reported ({yf_fy} vs {ed_fy}) -- compare same-period rows manually")
        else:
            diff_pct = abs(yf_rev - ed_rev) / max(abs(yf_rev), abs(ed_rev)) * 100
            if diff_pct < 2.0:
                print(f"     [OK] Agreement within {diff_pct:.2f}% -- sources consistent")
            else:
                print(f"     [!!] MISMATCH: {diff_pct:.1f}% difference -- investigate extraction logic")
    else:
        print(f"     [!] Cannot compare -- one or both returned None")


# ─────────────────────────────────────────────────────────────
# Test basket
# ─────────────────────────────────────────────────────────────

TEST_BASKET = [
    # (ticker, description,            is_bank)
    ("AAPL",  "Large-cap baseline",    False),
    ("JPM",   "Bank — no gross_profit expected",  True),
    ("KO",    "Large-cap variety",     False),
    ("RDDT",  "Recent IPO, loss-making (Reddit)", False),
    ("NVDA",  "Fast-growth trend",     False),
]

CROSS_SOURCE_TICKERS = ["AAPL", "NVDA"]


async def main():
    print()
    div(70, "=")
    print("  Tickr -- Data Pipeline Manual Verification")
    print("  Live fetches only. No mocking. Report honest failures.")
    div(70, "=")
    print()

    yf_adapter    = YFinanceAdapter()
    edgar_adapter = EdgarAdapter()

    for ticker, note, is_bank in TEST_BASKET:
        try:
            await verify_ticker(yf_adapter, ticker, note, is_bank)
        except Exception as exc:
            header(f"{ticker} — FATAL ERROR")
            print(f"  {exc}")

    header("CROSS-SOURCE CHECK  —  EDGAR vs yfinance revenue")
    print("  Same ticker, same fiscal year, both sources.")
    for ticker in CROSS_SOURCE_TICKERS:
        await cross_source_check(yf_adapter, edgar_adapter, ticker)

    print()
    div(70, "=")
    print("  Done.")
    div(70, "=")
    print()


if __name__ == "__main__":
    asyncio.run(main())
