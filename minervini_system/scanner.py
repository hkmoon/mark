from __future__ import annotations

import pandas as pd

from minervini_system.config import ScanConfig
from minervini_system.indicators import add_indicators, relative_strength_vs_benchmark


def trend_template_pass(df: pd.DataFrame, min_price: float, min_adv: float) -> pd.Series:
    close = df["Close"]
    sma50 = df["SMA50"]
    sma150 = df["SMA150"]
    sma200 = df["SMA200"]
    low_52w = df["52W_LOW"]
    high_52w = df["52W_HIGH"]
    adv50 = df["ADV50"]

    cond = (
        (close > sma50)
        & (close > sma150)
        & (close > sma200)
        & (sma50 > sma150)
        & (sma150 > sma200)
        & (sma200 > sma200.shift(20))
        & (close >= low_52w * 1.30)
        & (close >= high_52w * 0.75)
        & (close >= min_price)
        & (adv50 >= min_adv)
    )
    return cond.fillna(False)


def vcp_candidate(df: pd.DataFrame, config: ScanConfig) -> pd.Series:
    range_contracted = df["RANGE5"] < (df["RANGE20"] * config.max_contraction_ratio)
    volume_dryup = df["Volume"].rolling(5).mean() < (df["VOL50"] * 0.8)
    return (range_contracted & volume_dryup).fillna(False)


def breakout_signal(df: pd.DataFrame, config: ScanConfig) -> pd.Series:
    pivot = df["High"].shift(1).rolling(config.lookback_high).max()
    volume_ratio = df["Volume"] / df["VOL50"]
    signal = (
        (df["Close"] > pivot * (1 + config.breakout_buffer))
        & (volume_ratio >= config.volume_ratio_threshold)
    )
    return signal.fillna(False)


def scan_one_ticker(
    ticker: str,
    df: pd.DataFrame,
    benchmark_close: pd.Series | None,
    config: ScanConfig,
) -> pd.DataFrame:
    out = add_indicators(df)
    out["TREND_OK"] = trend_template_pass(out, config.min_price, config.min_avg_dollar_volume)
    out["VCP_CANDIDATE"] = vcp_candidate(out, config)
    out["BREAKOUT"] = breakout_signal(out, config)

    if benchmark_close is not None:
        aligned_bench = benchmark_close.reindex(out.index).ffill()
        out["RS_6M"] = relative_strength_vs_benchmark(out["Close"], aligned_bench, 126)
    else:
        out["RS_6M"] = pd.NA

    out["TICKER"] = ticker
    return out


def latest_scan_table(
    data_map: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame | None,
    config: ScanConfig,
) -> pd.DataFrame:
    rows = []
    benchmark_close = benchmark_df["Close"] if benchmark_df is not None else None

    for ticker, df in data_map.items():
        if len(df) < 252:
            continue

        scanned = scan_one_ticker(ticker, df, benchmark_close, config)
        last = scanned.iloc[-1]
        rows.append(
            {
                "Ticker": ticker,
                "Date": scanned.index[-1],
                "Close": float(last["Close"]),
                "TrendTemplate": bool(last["TREND_OK"]),
                "VCPCandidate": bool(last["VCP_CANDIDATE"]),
                "Breakout": bool(last["BREAKOUT"]),
                "RS_6M": None if pd.isna(last["RS_6M"]) else float(last["RS_6M"]),
                "ADV50": float(last["ADV50"]) if pd.notna(last["ADV50"]) else None,
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    return result.sort_values(
        by=["Breakout", "TrendTemplate", "VCPCandidate", "RS_6M"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
