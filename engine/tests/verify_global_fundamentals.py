"""
Global fundamentals diagnostic — surfaces IFRS label gaps vs US GAAP baseline.
Run from repo root:
    engine\\.venv\\Scripts\\python.exe engine/tests/verify_global_fundamentals.py

For each ticker: fetches one year of annual fundamentals through the engine's
normalization path, prints which fields are populated vs None, then prints a
gap analysis flagging fields present in AAPL that are missing for each global ticker.
"""
import sys
import asyncio
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.adapters.yfinance import YFinanceAdapter
from app.schema import Period, NormalizedFundamentals

TICKERS = [
    ("AAPL",        "US baseline / GAAP"),
    ("SHEL.L",      "UK / IFRS"),
    ("SAP.DE",      "Germany / IFRS"),
    ("7203.T",      "Japan / IFRS"),
    ("RELIANCE.NS", "India / IFRS"),
    ("PETR4.SA",    "Brazil / IFRS"),
    ("WALMEX.MX",   "Mexico / IFRS"),
]


def _extract_fields(f: NormalizedFundamentals) -> dict[str, Optional[float]]:
    is_ = f.income_statement
    bs  = f.balance_sheet
    cf  = f.cash_flow
    r   = f.ratios
    return {
        "revenue":             is_.revenue,
        "cost_of_revenue":     is_.cost_of_revenue,
        "gross_profit":        is_.gross_profit,
        "operating_income":    is_.operating_income,
        "ebitda":              is_.ebitda,
        "net_income":          is_.net_income,
        "eps_diluted":         is_.eps_diluted,
        "total_assets":        bs.total_assets,
        "total_liabilities":   bs.total_liabilities,
        "total_equity":        bs.total_equity,
        "total_debt":          bs.total_debt,
        "operating_cash_flow": cf.operating_cash_flow,
        "free_cash_flow":      cf.free_cash_flow,
        "pe_ratio":            r.pe_ratio,
        "gross_margin":        r.gross_margin,
        "operating_margin":    r.operating_margin,
        "net_margin":          r.net_margin,
        "roe":                 r.roe,
    }


def div(char: str = "-", width: int = 62) -> None:
    print(char * width)


async def probe_ticker(
    adapter: YFinanceAdapter,
    ticker: str,
    label: str,
) -> dict[str, Optional[float]]:
    print()
    div("=")
    print(f"  {ticker}  ({label})")
    div("=")

    try:
        company = await adapter.get_company(ticker)
        print(f"  Name     : {company.name}")
        print(
            f"  Exchange : {company.exchange.value}"
            f"  |  Currency : {company.currency.value}"
            f"  |  Market : {company.market.value}"
        )
    except Exception as exc:
        print(f"  ERROR resolving identity: {exc}")
        return {}

    try:
        periods = await adapter.get_fundamentals(company, Period.ANNUAL, limit=1)
    except Exception as exc:
        print(f"  ERROR fetching fundamentals: {exc}")
        return {}

    if not periods:
        print("  WARNING: no fundamentals returned")
        return {}

    f = periods[0]
    print(f"  Period   : FY{f.fiscal_year} ({f.period_end_date})")

    field_values = _extract_fields(f)
    populated = sorted(k for k, v in field_values.items() if v is not None)
    null_fields = sorted(k for k, v in field_values.items() if v is None)

    print(f"\n  Populated ({len(populated):2d}): {', '.join(populated) or '—'}")
    print(f"  NULL      ({len(null_fields):2d}): {', '.join(null_fields) or '[all populated]'}")

    return field_values


async def main() -> None:
    adapter = YFinanceAdapter()
    results: dict[str, dict[str, Optional[float]]] = {}

    for ticker, label in TICKERS:
        try:
            results[ticker] = await probe_ticker(adapter, ticker, label)
        except Exception as exc:
            print(f"\n  FATAL ERROR for {ticker}: {exc}")
            results[ticker] = {}

    # Gap analysis vs AAPL baseline
    print()
    div("=")
    print("  IFRS GAP ANALYSIS vs AAPL baseline")
    print("  Fields listed below are populated in AAPL but NULL here.")
    print("  These are the label mappings worth adding in a future session.")
    div("=")

    baseline = results.get("AAPL", {})
    baseline_populated = {k for k, v in baseline.items() if v is not None}

    any_gap = False
    for ticker, label in TICKERS[1:]:
        field_values = results.get(ticker, {})
        if not field_values:
            print(f"\n  {ticker}: no data to compare")
            continue
        populated = {k for k, v in field_values.items() if v is not None}
        gaps = sorted(baseline_populated - populated)
        print(f"\n  {ticker} ({label})")
        if gaps:
            any_gap = True
            print(f"    Gaps: {', '.join(gaps)}")
        else:
            print(f"    No gaps vs AAPL — all baseline fields populated")

    if not any_gap:
        print("\n  All global tickers match AAPL baseline. No IFRS gaps found.")

    print()
    div("=")
    print("  Done.")
    div("=")
    print()


if __name__ == "__main__":
    asyncio.run(main())
