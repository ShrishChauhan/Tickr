"""
DuckDB-over-R2 (HTTP) probe — Phase 7.1 follow-up.

Goal: prove DuckDB can query the same Parquet data over R2-via-HTTP that
probe_duckdb_local.py already proved works against local disk — same query
mechanism (read_parquet with a glob), different URI scheme (r2:// instead of
a local path). Uses DuckDB's current recommended R2 auth (CREATE SECRET with
TYPE r2), not the legacy SET s3_endpoint/s3_url_style statements, so
credentials never appear in query text.

Run from repo root (after upload_to_r2.py has populated the R2 bucket):
  engine/.venv/Scripts/python.exe engine/tests/probe_duckdb_r2.py

No assertions on live-fetched values, just cross-checks against the known-good
local numbers from Session 31 (2,588,596 rows / 567 distinct tickers).
"""
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings

GLOB = f"r2://{settings.R2_BUCKET_NAME}/*.parquet"
SPOT_CHECK_TICKERS = ["AAPL", "MMM", "TCS.NS", "RELIANCE.NS"]

KNOWN_LOCAL_TOTAL_ROWS = 2_588_596
KNOWN_LOCAL_DISTINCT_TICKERS = 567


def main() -> None:
    con = duckdb.connect()
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(
        "CREATE SECRET (TYPE r2, KEY_ID ?, SECRET ?, ACCOUNT_ID ?)",
        [settings.R2_ACCESS_KEY_ID, settings.R2_SECRET_ACCESS_KEY, settings.R2_ACCOUNT_ID],
    )

    print(f"Querying {GLOB} over HTTP via R2")

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

    print(f"\nKnown-good local values: {KNOWN_LOCAL_TOTAL_ROWS} rows / {KNOWN_LOCAL_DISTINCT_TICKERS} tickers")
    match = (total_rows == KNOWN_LOCAL_TOTAL_ROWS) and (distinct_tickers == KNOWN_LOCAL_DISTINCT_TICKERS)
    print("MATCH" if match else "MISMATCH — R2 data does not match local Session 31 numbers")


if __name__ == "__main__":
    main()
