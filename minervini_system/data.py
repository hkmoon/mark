from __future__ import annotations

import pandas as pd
import yfinance as yf


OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _extract_ohlcv_frame(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        if ticker in raw.columns.get_level_values(0):
            df = raw[ticker].copy()
        else:
            df = raw.copy()
            df.columns = df.columns.get_level_values(-1)
    else:
        df = raw.copy()

    return df[OHLCV_COLUMNS].dropna()


def download_ohlcv(
    tickers: list[str],
    start: str = "2020-01-01",
    end: str | None = None,
    auto_adjust: bool = True,
) -> dict[str, pd.DataFrame]:
    """
    Return a mapping of ticker -> OHLCV dataframe.
    """
    raw = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        auto_adjust=auto_adjust,
        group_by="ticker",
        progress=False,
        threads=True,
    )

    result: dict[str, pd.DataFrame] = {}

    if len(tickers) == 1:
        result[tickers[0]] = _extract_ohlcv_frame(raw, tickers[0])
        return result

    for ticker in tickers:
        if ticker not in raw.columns.get_level_values(0):
            continue
        df = _extract_ohlcv_frame(raw, ticker)
        if not df.empty:
            result[ticker] = df

    return result
