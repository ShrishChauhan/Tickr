"""
Per-period ratio derivation cross-check.
Run from repo root: engine\.venv\Scripts\python.exe engine/tests/verify_ratios.py

Checks:
  1. Derived margins vary across periods (catches "all same" bug)
  2. Derived values are decimals, not percentages (catches ×100 scale bug)
  3. Most recent period's derived margin agrees with yfinance .info TTM (±15%)
"""
import sys
import asyncio
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.adapters.yfinance import YFinanceAdapter
from app.schema import Period
from app.utils.ratios import derive_ratios

import yfinance as yf


def _pct(v: Optional[float]) -> str:
    if v is None:
        return "      —  "
    return f"{v * 100:+7.2f}%"


def _check_scale(label: str, v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    if abs(v) > 2.0:
        return f"[!!] SCALE BUG: {label} = {v:.3f}  (|value| > 2.0 — looks like a percentage stored as-is)"
    return None


async def verify_ticker(adapter: YFinanceAdapter, ticker: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {ticker}")
    print(f"{'=' * 72}")

    company   = await adapter.get_company(ticker)
    raw_funds = await adapter.get_fundamentals(company, Period.ANNUAL, limit=5)

    if not raw_funds:
        print("  No data returned.")
        return

    enriched = [derive_ratios(f) for f in raw_funds]

    print(f"\n  {'FY':>4}  {'Period end':>12}  {'Gross Mgn':>10}  {'Op Mgn':>10}  {'Net Mgn':>10}  {'ROE':>10}  {'D/E':>6}")
    print(f"  " + "-" * 66)

    gross_margins = []
    errors = []

    for f, r in zip(raw_funds, enriched):
        fy  = str(f.fiscal_year) if f.fiscal_year else "????"
        gm  = r.gross_margin
        opm = r.operating_margin
        nm  = r.net_margin
        roe = r.roe
        de  = r.debt_to_equity

        de_str = f"{de:>6.2f}" if de is not None else f"{'—':>6}"
        print(f"  {fy:>4}  {str(f.period_end_date):>12}  {_pct(gm):>10}  {_pct(opm):>10}  {_pct(nm):>10}  {_pct(roe):>10}  {de_str}")

        if gm is not None:
            gross_margins.append(gm)

        for label, v in [("gross_margin", gm), ("operating_margin", opm), ("net_margin", nm), ("roe", roe)]:
            err = _check_scale(label, v)
            if err:
                errors.append(err)

    # Variation check
    print()
    if len(gross_margins) >= 2:
        spread = max(gross_margins) - min(gross_margins)
        if spread < 0.001:
            errors.append("[!!] ALL-SAME BUG: gross_margin is identical across all periods")
        else:
            print(f"  [OK] Gross margin varies across periods  (range: {spread * 100:.1f}pp)")
    else:
        print(f"  [--] Only {len(gross_margins)} period(s) — cannot check variation")

    # Scale check errors
    for e in errors:
        print(f"  {e}")

    # Cross-check most recent FY vs live .info (TTM — may differ, tolerance ±15%)
    info     = yf.Ticker(ticker).info
    live_gm  = info.get("grossMargins")
    live_opm = info.get("operatingMargins")
    live_nm  = info.get("profitMargins")

    r0 = enriched[0]
    print(f"\n  Cross-check: most recent FY derived vs yfinance .info TTM")
    print(f"  (FY values ≠ TTM; expect agreement within ~15pp)")
    print(f"  {'':22}  {'Derived':>10}  {'Live .info':>10}  Result")
    print(f"  " + "-" * 56)

    for label, d, live in [
        ("Gross Margin",     r0.gross_margin,     live_gm),
        ("Operating Margin", r0.operating_margin, live_opm),
        ("Net Margin",       r0.net_margin,       live_nm),
    ]:
        if d is None or live is None:
            status = "—  (one side missing)"
        else:
            delta = abs(d - live)
            status = "OK" if delta < 0.15 else f"MISMATCH  (delta={delta * 100:.1f}pp)"
        print(f"  {label:22}  {_pct(d):>10}  {_pct(live):>10}  {status}")


async def main() -> None:
    print("\nTickr — per-period ratio derivation verification")
    print("Tickers: AAPL, NVDA  |  5 annual periods each  |  No LLM, no DB\n")

    adapter = YFinanceAdapter()
    for ticker in ["AAPL", "NVDA"]:
        try:
            await verify_ticker(adapter, ticker)
        except Exception as exc:
            print(f"\n[FATAL] {ticker}: {exc}")

    print(f"\n{'=' * 72}")
    print("  Done.")
    print(f"{'=' * 72}\n")


if __name__ == "__main__":
    asyncio.run(main())
