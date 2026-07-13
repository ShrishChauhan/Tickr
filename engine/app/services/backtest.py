# Thin orchestrator wiring historical_data (I/O) into ma_crossover / rule_engine
# (pure math). No async/CacheBackend: DuckDB is blocking and nothing here hits a
# rate-limited or costly external API, so there's no cache to populate and
# no reason to fake async I/O that doesn't exist.
from dataclasses import asdict
from typing import Optional

from ..schema.backtest import (
    IndicatorSchema, RuleSchema, StrategySchema, TradeSchema, BacktestResponse,
)
from . import historical_data
from . import ma_crossover
from . import rule_engine
from .rule_engine import Indicator, Rule, Strategy
from .backtest_core import BacktestResult

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


def _indicator_from_schema(s: IndicatorSchema) -> Indicator:
    return Indicator(type=s.type, window=s.window)


def _rule_from_schema(s: RuleSchema) -> Rule:
    right = _indicator_from_schema(s.right) if isinstance(s.right, IndicatorSchema) else s.right
    return Rule(left=_indicator_from_schema(s.left), comparator=s.comparator, right=right)


def _strategy_from_schema(s: StrategySchema) -> Strategy:
    return Strategy(entry=_rule_from_schema(s.entry), exit=_rule_from_schema(s.exit))


def _result_to_response(ticker: str, result: BacktestResult) -> BacktestResponse:
    return BacktestResponse(
        ticker=ticker,
        dates=result.dates,
        equity_curve=result.equity_curve,
        trades=[TradeSchema(**asdict(t)) for t in result.trades],
        total_return_pct=result.total_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        num_trades=result.num_trades,
        win_rate_pct=result.win_rate_pct,
        final_status=result.final_status,
        params=result.params,
    )


def run_ticker_rule_backtest(
    ticker: str,
    strategy: StrategySchema,
    cost_pct: float = DEFAULT_COST_PCT,
    starting_capital: float = DEFAULT_STARTING_CAPITAL,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> BacktestResponse:
    df = historical_data.load_price_history(ticker, start=start, end=end)
    result = rule_engine.run_rule_backtest(
        df["date"], df["adj_close"], _strategy_from_schema(strategy),
        cost_pct=cost_pct, starting_capital=starting_capital,
    )
    return _result_to_response(ticker.upper(), result)
