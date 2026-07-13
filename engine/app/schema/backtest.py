from datetime import date
from typing import Literal, Optional, Union
from pydantic import BaseModel


class IndicatorSchema(BaseModel):
    type: Literal["SMA", "PRICE", "RSI"]
    window: Optional[int] = None


class RuleSchema(BaseModel):
    left: IndicatorSchema
    comparator: Literal["CROSSES_ABOVE", "CROSSES_BELOW"]
    right: Union[IndicatorSchema, float]


class StrategySchema(BaseModel):
    entry: RuleSchema
    exit: RuleSchema


class BacktestRequest(BaseModel):
    strategy: StrategySchema
    cost_pct: float = 0.001
    starting_capital: float = 100_000.0
    start: Optional[str] = None
    end: Optional[str] = None


class TradeSchema(BaseModel):
    entry_date: date
    entry_price: float
    exit_date: Optional[date]
    exit_price: Optional[float]
    pnl: Optional[float]
    pnl_pct: Optional[float]
    status: Literal["closed", "open"]


class BacktestResponse(BaseModel):
    ticker: str
    dates: list[date]
    equity_curve: list[float]
    trades: list[TradeSchema]
    total_return_pct: float
    max_drawdown_pct: float
    num_trades: int
    win_rate_pct: Optional[float]
    final_status: Literal["flat", "open"]
    params: dict
