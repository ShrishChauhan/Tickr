# Adapter registry — import adapters here; engine uses DataAdapter interface only
from .base import DataAdapter
from .edgar import EdgarAdapter
from .yfinance import YFinanceAdapter

__all__ = ["DataAdapter", "EdgarAdapter", "YFinanceAdapter"]
