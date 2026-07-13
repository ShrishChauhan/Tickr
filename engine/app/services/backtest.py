# Thin orchestrator wiring historical_data (I/O) into ma_crossover (pure
# math). No async/CacheBackend: DuckDB is blocking and nothing here hits a
# rate-limited or costly external API, so there's no cache to populate and
# no reason to fake async I/O that doesn't exist.
from typing import Optional

from . import historical_data
from . import ma_crossover

DEFAULT_SHORT_WINDOW = 50
DEFAULT_LONG_WINDOW = 200
DEFAULT_COST_PCT = 0.001
DEFAULT_STARTING_CAPITAL = 100_000.0


def run_ticker_backtest(
    ticker: str,
    short_window: int = DEFAULT_SHORT_WINDOW,
    long_window: int = DEFAULT_LONG_WINDOW,
    cost_pct: float = DEFAULT_COST_PCT,
    starting_capital: float = DEFAULT_STARTING_CAPITAL,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> ma_crossover.BacktestResult:
    df = historical_data.load_price_history(ticker, start=start, end=end)
    return ma_crossover.run_backtest(
        df["date"], df["adj_close"],
        short_window=short_window, long_window=long_window,
        cost_pct=cost_pct, starting_capital=starting_capital,
    )
