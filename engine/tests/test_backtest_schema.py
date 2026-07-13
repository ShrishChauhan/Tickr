import pandas as pd
import pytest

from app.schema.backtest import BacktestRequest, IndicatorSchema, RuleSchema, StrategySchema
from app.services.backtest import _strategy_from_schema, run_ticker_rule_backtest
from app.services.rule_engine import Indicator, Rule, Strategy, run_rule_backtest

# Same hand-verified 18-bar reference series as test_rule_engine.py.
PRICES = [100, 98, 96, 94, 92, 94, 96, 98, 100, 102, 104, 106, 104, 102, 100, 98, 100, 102]
DATES = list(pd.date_range("2024-01-01", periods=len(PRICES), freq="D").date)


def _series():
    return pd.Series(DATES), pd.Series(PRICES, dtype=float)


# ---------------------------------------------------------------------------
# Union[IndicatorSchema, float] discrimination
# ---------------------------------------------------------------------------

def test_rule_schema_right_bare_number_is_float():
    rule = RuleSchema.model_validate({
        "left": {"type": "RSI", "window": 14},
        "comparator": "CROSSES_BELOW",
        "right": 30,
    })
    assert isinstance(rule.right, float)
    assert rule.right == 30.0


def test_rule_schema_right_object_is_indicator():
    rule = RuleSchema.model_validate({
        "left": {"type": "SMA", "window": 50},
        "comparator": "CROSSES_ABOVE",
        "right": {"type": "SMA", "window": 200},
    })
    assert isinstance(rule.right, IndicatorSchema)
    assert rule.right.window == 200


def test_backtest_request_parses_mixed_rule_shapes():
    request = BacktestRequest.model_validate({
        "strategy": {
            "entry": {"left": {"type": "RSI", "window": 14}, "comparator": "CROSSES_BELOW", "right": 30.0},
            "exit": {"left": {"type": "RSI", "window": 14}, "comparator": "CROSSES_ABOVE", "right": 70.0},
        },
    })
    assert isinstance(request.strategy.entry.right, float)
    assert request.cost_pct == 0.001
    assert request.starting_capital == 100_000.0


# ---------------------------------------------------------------------------
# Dataclass <-> schema conversion round-trip
# ---------------------------------------------------------------------------

def test_strategy_from_schema_matches_hand_built_strategy():
    schema = StrategySchema(
        entry=RuleSchema(left=IndicatorSchema(type="SMA", window=3),
                          comparator="CROSSES_ABOVE",
                          right=IndicatorSchema(type="SMA", window=5)),
        exit=RuleSchema(left=IndicatorSchema(type="SMA", window=3),
                         comparator="CROSSES_BELOW",
                         right=IndicatorSchema(type="SMA", window=5)),
    )
    converted = _strategy_from_schema(schema)
    hand_built = Strategy(
        entry=Rule(Indicator("SMA", 3), "CROSSES_ABOVE", Indicator("SMA", 5)),
        exit=Rule(Indicator("SMA", 3), "CROSSES_BELOW", Indicator("SMA", 5)),
    )
    assert converted == hand_built

    dates, prices = _series()
    converted_result = run_rule_backtest(dates, prices, converted)
    hand_built_result = run_rule_backtest(dates, prices, hand_built)
    assert converted_result.equity_curve == pytest.approx(hand_built_result.equity_curve)
    assert converted_result.total_return_pct == pytest.approx(hand_built_result.total_return_pct)
    assert converted_result.num_trades == hand_built_result.num_trades


def test_strategy_from_schema_handles_scalar_right():
    schema = StrategySchema(
        entry=RuleSchema(left=IndicatorSchema(type="RSI", window=14), comparator="CROSSES_BELOW", right=30.0),
        exit=RuleSchema(left=IndicatorSchema(type="RSI", window=14), comparator="CROSSES_ABOVE", right=70.0),
    )
    converted = _strategy_from_schema(schema)
    assert converted.entry.right == 30.0
    assert converted.exit.right == 70.0


# ---------------------------------------------------------------------------
# run_ticker_rule_backtest orchestration (loader monkeypatched, mirrors
# test_backtest_service.py's pattern for run_ticker_backtest)
# ---------------------------------------------------------------------------

def test_run_ticker_rule_backtest_wires_params_through(monkeypatch):
    dates, prices = _series()
    df = pd.DataFrame({"date": dates, "adj_close": prices})

    from app.services import historical_data
    monkeypatch.setattr(historical_data, "load_price_history", lambda ticker, start=None, end=None: df)

    strategy = StrategySchema(
        entry=RuleSchema(left=IndicatorSchema(type="SMA", window=3),
                          comparator="CROSSES_ABOVE",
                          right=IndicatorSchema(type="SMA", window=5)),
        exit=RuleSchema(left=IndicatorSchema(type="SMA", window=3),
                         comparator="CROSSES_BELOW",
                         right=IndicatorSchema(type="SMA", window=5)),
    )
    response = run_ticker_rule_backtest("aapl", strategy, cost_pct=0.0, starting_capital=100_000.0)

    assert response.ticker == "AAPL"
    assert response.num_trades == 1
    assert response.trades[0].status == "closed"
    assert response.params["cost_pct"] == 0.0
    assert response.params["starting_capital"] == 100_000.0
