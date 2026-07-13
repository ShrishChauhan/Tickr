"""
DuckDB-over-Parquet probe — Phase 7.1.

Goal: prove the actual mechanism ARCHITECTURE.md §5d calls for — DuckDB querying
Parquet directly, no DB server — against the local files backfill_historical.py
produced. R2 is deferred (see plan); this points at local disk instead of
R2-over-HTTP, but the query mechanism is identical either way.

Run from repo root (after backfill_historical.py has populated data_historical/):
  engine/.venv/Scripts/python.exe engine/tests/probe_duckdb_local.py

No assertions on live-fetched values, just cross-checks against what the
backfill run itself reported.
"""
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data_historical"
GLOB = str(DATA_DIR / "*.parquet")

SPOT_CHECK_TICKERS = ["AAPL", "MMM", "TCS.NS", "RELIANCE.NS"]


def main() -> None:
    files = list(DATA_DIR.glob("*.parquet"))
    print(f"Found {len(files)} Parquet files in {DATA_DIR}")
    if not files:
        print("Nothing to query — run backfill_historical.py first.")
        return

    con = duckdb.connect()

    total_rows, distinct_tickers = con.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT ticker) FROM read_parquet('{GLOB}')"
    ).fetchone()
    print(f"Cross-file query: {total_rows} total rows across {distinct_tickers} distinct tickers")

    print(f"\n{'TICKER':<14}{'ROWS':<8}{'FIRST DATE':<13}{'LAST DATE':<13}{'LATEST CLOSE'}")
    print("-" * 65)
    for ticker in SPOT_CHECK_TICKERS:
        row = con.execute(
            f"""
            SELECT COUNT(*), MIN(date), MAX(date),
                   arg_max(close, date) AS latest_close
            FROM read_parquet('{GLOB}')
            WHERE ticker = ?
            """,
            [ticker],
        ).fetchone()
        if row is None or row[0] == 0:
            print(f"{ticker:<14}NOT FOUND")
            continue
        count, first_date, last_date, latest_close = row
        print(f"{ticker:<14}{count:<8}{str(first_date):<13}{str(last_date):<13}{latest_close:.2f}")

    total_size_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
    print(f"\nTotal local Parquet size: {total_size_mb:.1f} MB across {len(files)} files")


if __name__ == "__main__":
    main()
