# Batch fan-out orchestration for the screener — one server-side request replaces
# the ~N client-side requests the browser used to make per universe.
import asyncio
import logging
import time
from typing import List

from ..adapters.yfinance import YFinanceAdapter
from ..cache.base import CacheBackend
from ..schema import ScreenerRow
from .fundamentals import get_lite_fundamentals
from .universes import load_universe

logger = logging.getLogger(__name__)

# Matches the frontend's previously-proven-safe pool size; yfinance can soft-rate-limit a single
# IP at higher concurrency, and this now runs behind one shared server IP instead of many browsers.
CONCURRENCY = 8

# Bounds a single hung/slow ticker so it can't stall the whole batch.
PER_TICKER_TIMEOUT_SECONDS = 10

# Safety net, not the expected path. Measured: yfinance's `.info` call (not the 3 extra statement
# calls it skips) is the dominant per-ticker cost, so the lite path is NOT dramatically faster than
# the old full-fetch client pool — cold S&P 500 at concurrency=8 measured ~120-140s wall clock, similar
# to the previous "1-2 min" estimate. 150s gives headroom without letting a bad run hang indefinitely;
# once the A5 pre-warm cron exists, cold runs (and this ceiling) become rare in practice.
BATCH_TIMEOUT_SECONDS = 150


async def get_screener_rows(
    adapter: YFinanceAdapter,
    cache: CacheBackend,
    universe_key: str,
    source: str,
) -> List[ScreenerRow]:
    constituents = load_universe(universe_key)  # raises UnknownUniverseError -> 404 at the route
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def fetch_one(item: dict) -> ScreenerRow:
        async with semaphore:
            try:
                fields = await asyncio.wait_for(
                    get_lite_fundamentals(adapter, cache, item["ticker"], source),
                    timeout=PER_TICKER_TIMEOUT_SECONDS,
                )
                return ScreenerRow(ticker=item["ticker"], name=item["name"], **fields.model_dump())
            except Exception:
                return ScreenerRow(ticker=item["ticker"], name=item["name"])

    tasks = [asyncio.create_task(fetch_one(item)) for item in constituents]
    start = time.monotonic()
    done, pending = await asyncio.wait(tasks, timeout=BATCH_TIMEOUT_SECONDS)
    for task in pending:
        task.cancel()

    rows = [
        task.result() if task not in pending else ScreenerRow(ticker=item["ticker"], name=item["name"])
        for item, task in zip(constituents, tasks)
    ]

    succeeded = sum(1 for row in rows if row.market_cap is not None)
    logger.info(
        "screener %s: %d/%d tickers succeeded in %.1fs (%d timed out)",
        universe_key, succeeded, len(rows), time.monotonic() - start, len(pending),
    )
    return rows
