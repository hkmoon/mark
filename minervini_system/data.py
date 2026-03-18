from __future__ import annotations

import re

import pandas as pd
import requests
import yfinance as yf
from pykrx import stock


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


def get_kospi200_tickers() -> list[str]:
    """
    Return current KOSPI 200 constituents as Yahoo Finance tickers.

    pykrx documents `stock.get_index_portfolio_deposit_file("1028")` for KOSPI 200.
    """
    for date in _recent_seoul_business_days():
        try:
            tickers = stock.get_index_portfolio_deposit_file("1028", date=date)
        except Exception:
            continue

        normalized = []
        for ticker in tickers:
            ticker = str(ticker).zfill(6)
            if ticker.isdigit():
                normalized.append(f"{ticker}.KS")

        unique_tickers = sorted(set(normalized))
        if len(unique_tickers) >= 180:
            return unique_tickers

    return _get_kospi200_tickers_from_investing()


def _recent_seoul_business_days(lookback_days: int = 14) -> list[str]:
    today = pd.Timestamp.now(tz="Asia/Seoul").normalize()
    dates: list[str] = []
    for offset in range(lookback_days + 1):
        candidate = today - pd.Timedelta(days=offset)
        if candidate.weekday() >= 5:
            continue
        dates.append(candidate.strftime("%Y%m%d"))
    return dates


def _get_kospi200_tickers_from_investing() -> list[str]:
    url = "https://www.investing.com/indices/kospi-200-components"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    symbols = re.findall(r'"symbol":"(\d{6})"', response.text)
    tickers = sorted({f"{symbol}.KS" for symbol in symbols})
    if len(tickers) < 180:
        raise RuntimeError("Could not fetch a reliable KOSPI 200 constituent list.")
    return tickers
