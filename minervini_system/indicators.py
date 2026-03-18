from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def avg_dollar_volume(df: pd.DataFrame, window: int = 50) -> pd.Series:
    return (df["Close"] * df["Volume"]).rolling(window).mean()


def relative_strength_vs_benchmark(
    stock_close: pd.Series,
    benchmark_close: pd.Series,
    lookback: int = 126,
) -> pd.Series:
    stock_ret = stock_close / stock_close.shift(lookback) - 1
    bench_ret = benchmark_close / benchmark_close.shift(lookback) - 1
    return stock_ret - bench_ret


def rolling_range_pct(df: pd.DataFrame, window: int) -> pd.Series:
    high = df["High"].rolling(window).max()
    low = df["Low"].rolling(window).min()
    return (high - low) / low


def average_volume(df: pd.DataFrame, window: int = 50) -> pd.Series:
    return df["Volume"].rolling(window).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["SMA50"] = sma(out["Close"], 50)
    out["SMA150"] = sma(out["Close"], 150)
    out["SMA200"] = sma(out["Close"], 200)
    out["ADV50"] = avg_dollar_volume(out, 50)
    out["VOL50"] = average_volume(out, 50)
    out["RANGE5"] = rolling_range_pct(out, 5)
    out["RANGE10"] = rolling_range_pct(out, 10)
    out["RANGE20"] = rolling_range_pct(out, 20)
    out["52W_HIGH"] = out["Close"].rolling(252).max()
    out["52W_LOW"] = out["Close"].rolling(252).min()
    return out
