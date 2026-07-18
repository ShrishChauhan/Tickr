# ParquetOHLCLoader / historical_data.load_ohlc_bars — Chunk 3 of the
# Loader-registry refactor. Uses a throwaway Parquet file under a
# monkeypatched _DATA_DIR, not the real data_historical/ tree — no
# dependency on the 567-ticker backfill actually existing in CI.
import asyncio
from datetime import date, timedelta

import pandas as pd
import pytest

from app.adapters.base import LoaderLicense
from app.adapters.parquet_history import ParquetOHLCLoader
from app.services import historical_data


def _write_fake_parquet(path, rows):
    df = pd.DataFrame(rows)
    df.to_parquet(path)


@pytest.fixture
def fake_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(historical_data, "_DATA_DIR", tmp_path)
    return tmp_path


def test_load_ohlc_bars_selects_adj_close_and_raw_ohl(fake_data_dir):
    """Close must come from 'Adj Close' (matches live yfinance's dividend-
    adjusted convention); Open/High/Low stay raw (split-adjusted only)."""
    rows = [
        {"date": pd.Timestamp("2026-07-16", tz="UTC"), "Open": 10.0, "High": 12.0,
         "Low": 9.0, "Close": 11.0, "Adj Close": 10.5, "Volume": 1000},
        {"date": pd.Timestamp("2026-07-17", tz="UTC"), "Open": 11.0, "High": 13.0,
         "Low": 10.0, "Close": 12.0, "Adj Close": 11.5, "Volume": 2000},
    ]
    _write_fake_parquet(fake_data_dir / "FAKE.parquet", rows)

    df = historical_data.load_ohlc_bars("FAKE")

    assert [d.date() for d in df["date"]] == [date(2026, 7, 16), date(2026, 7, 17)]
    assert list(df["close"]) == [10.5, 11.5]  # Adj Close, not Close
    assert list(df["open"]) == [10.0, 11.0]
    assert list(df["volume"]) == [1000, 2000]


def test_load_ohlc_bars_raises_for_missing_ticker(fake_data_dir):
    with pytest.raises(historical_data.HistoricalDataError):
        historical_data.load_ohlc_bars("NOPE")


def test_parquet_loader_license_is_personal_only():
    loader = ParquetOHLCLoader()
    assert loader.license == LoaderLicense.PERSONAL_ONLY
    assert loader.name == "parquet"


def test_parquet_loader_get_ohlc_returns_bars_and_local_as_of(fake_data_dir):
    rows = [
        {"date": pd.Timestamp("2026-07-16", tz="UTC"), "Open": 10.0, "High": 12.0,
         "Low": 9.0, "Close": 11.0, "Adj Close": 10.5, "Volume": 1000},
        {"date": pd.Timestamp("2026-07-17", tz="UTC"), "Open": 11.0, "High": 13.0,
         "Low": 10.0, "Close": 12.0, "Adj Close": 11.5, "Volume": 2000},
    ]
    _write_fake_parquet(fake_data_dir / "FAKE.parquet", rows)
    loader = ParquetOHLCLoader()

    bars, as_of = asyncio.run(loader.get_ohlc("FAKE"))

    assert as_of == "2026-07-17"  # the local file's actual last row date, not now()
    assert len(bars) == 2
    assert bars[-1]["close"] == 11.5


def test_parquet_loader_get_ohlc_declines_for_missing_ticker(fake_data_dir):
    loader = ParquetOHLCLoader()

    bars, as_of = asyncio.run(loader.get_ohlc("NOPE"))

    assert bars == []
    assert as_of is None


def test_parquet_loader_windows_to_one_year_from_latest_local_row(fake_data_dir):
    """The 1y window is anchored to the freshest local row, not today() — the
    backfill is a point-in-time snapshot, so today() would under-fill it."""
    latest = pd.Timestamp("2026-07-17", tz="UTC")
    rows = [
        {"date": latest - pd.Timedelta(days=400), "Open": 1.0, "High": 1.0,
         "Low": 1.0, "Close": 1.0, "Adj Close": 1.0, "Volume": 1},
        {"date": latest - pd.Timedelta(days=100), "Open": 2.0, "High": 2.0,
         "Low": 2.0, "Close": 2.0, "Adj Close": 2.0, "Volume": 1},
        {"date": latest, "Open": 3.0, "High": 3.0,
         "Low": 3.0, "Close": 3.0, "Adj Close": 3.0, "Volume": 1},
    ]
    _write_fake_parquet(fake_data_dir / "FAKE.parquet", rows)
    loader = ParquetOHLCLoader()

    bars, _ = asyncio.run(loader.get_ohlc("FAKE"))

    # 400-days-back row falls outside the 365-day window; the other two don't.
    assert len(bars) == 2
    assert [b["close"] for b in bars] == [2.0, 3.0]
