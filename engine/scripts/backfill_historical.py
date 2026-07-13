"""
One-time historical OHLC backfill — Phase 7.1.

Fetches 20 years of daily OHLC per ticker via yfinance for every unique ticker
across the 4 existing screener universes, and writes one Parquet file per
ticker to engine/data_historical/. This is a manual, one-off script (not
scheduled) — proof of the backfill mechanism, not production infrastructure.

Run from repo root:
  engine/.venv/Scripts/python.exe engine/scripts/backfill_historical.py
"""
import sys
import time
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.universes import known_universe_keys, load_universe

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data_historical"
PERIOD = "20y"


def unique_tickers() -> list[str]:
    tickers: set[str] = set()
    for key in known_universe_keys():
        tickers.update(row["ticker"] for row in load_universe(key))
    return sorted(tickers)


def backfill_one(ticker: str) -> tuple[bool, str]:
    df = yf.Ticker(ticker).history(period=PERIOD, interval="1d", auto_adjust=False)
    if df.empty:
        return False, "empty history"

    df = df.reset_index()
    df.rename(columns={"Date": "date"}, inplace=True)
    df.insert(0, "ticker", ticker)

    out_path = OUTPUT_DIR / f"{ticker}.parquet"
    df.to_parquet(out_path, engine="pyarrow", compression="snappy")
    return True, f"{len(df)} rows, {df['date'].min().date()} -> {df['date'].max().date()}"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tickers = unique_tickers()
    print(f"Backfilling {len(tickers)} unique tickers ({PERIOD} daily OHLC) -> {OUTPUT_DIR}")

    ok, failed = 0, []
    start = time.time()
    for i, ticker in enumerate(tickers, 1):
        try:
            success, detail = backfill_one(ticker)
        except Exception as exc:
            success, detail = False, str(exc)

        status = "OK" if success else "SKIP"
        print(f"[{i}/{len(tickers)}] {ticker}: {status} ({detail})")
        if success:
            ok += 1
        else:
            failed.append(ticker)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s — {ok} succeeded, {len(failed)} skipped.")
    if failed:
        print("Skipped:", ", ".join(failed))


if __name__ == "__main__":
    main()
