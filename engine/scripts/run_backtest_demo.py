"""Runs the default 50/200-day MA crossover on a real ticker (AAPL by
default) against the local Parquet history — manual sanity-check, not a
pytest test (no assertions on live-fetched values, mirrors
probe_duckdb_local.py's stance).

Run from repo root:
  engine/.venv/Scripts/python.exe engine/scripts/run_backtest_demo.py [TICKER]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services import backtest, historical_data


def main() -> None:
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
    result = backtest.run_ticker_backtest(ticker)

    # Buy-and-hold benchmark over the identical window: buy at the first bar,
    # hold to the last, same per-side cost_pct convention as the strategy's
    # own fills (so the two numbers are comparable on equal footing, not just
    # a raw price-ratio vs. a cost-laden strategy return).
    df = historical_data.load_price_history(ticker)
    cost_pct = result.params["cost_pct"]
    entry = df["adj_close"].iloc[0] * (1 + cost_pct)
    exit_ = df["adj_close"].iloc[-1] * (1 - cost_pct)
    buy_and_hold_pct = (exit_ / entry - 1) * 100

    print(f"Ticker: {ticker}")
    print(f"Params: {result.params}")
    print(f"Date range: {result.dates[0]} -> {result.dates[-1]} ({len(result.dates)} bars)")
    print()
    print(f"Total return:  {result.total_return_pct:.2f}%  (50/200 crossover)")
    print(f"Buy & hold:    {buy_and_hold_pct:.2f}%  (same window, same cost_pct)")
    print(f"Max drawdown:  {result.max_drawdown_pct:.2f}%")
    print(f"Num trades:    {result.num_trades} (closed)")
    win_rate = f"{result.win_rate_pct:.1f}%" if result.win_rate_pct is not None else "n/a (no closed trades)"
    print(f"Win rate:      {win_rate}")
    print(f"Final status:  {result.final_status}")
    print()
    print(f"Trades ({len(result.trades)}):")
    for t in result.trades:
        if t.status == "closed":
            print(f"  {t.entry_date} @ {t.entry_price:.2f}  ->  {t.exit_date} @ {t.exit_price:.2f}  "
                  f"pnl={t.pnl:+.2f} ({t.pnl_pct:+.2f}%)")
        else:
            print(f"  {t.entry_date} @ {t.entry_price:.2f}  ->  OPEN (unrealized, marked-to-market at final bar)")


if __name__ == "__main__":
    main()
