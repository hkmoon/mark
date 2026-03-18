from __future__ import annotations

import pandas as pd

from minervini_system.config import ScanConfig
from minervini_system.indicators import add_indicators, relative_strength_vs_benchmark


US_LEADER_TICKERS = {
    "NVDA",
    "AVGO",
    "SMCI",
    "PLTR",
    "AMD",
    "ANET",
    "CRWD",
    "MSFT",
    "META",
}


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
    near_high = df["Close"] >= (df["52W_HIGH"] * config.near_high_ratio)
    return (range_contracted & volume_dryup & near_high).fillna(False)


def tight_action(df: pd.DataFrame, config: ScanConfig) -> pd.Series:
    close_std_pct = df["Close"].rolling(10).std() / df["Close"].rolling(10).mean()
    return (
        (df["RANGE10"] <= config.tight_range_threshold)
        & (close_std_pct <= config.tight_close_std_threshold)
    ).fillna(False)


def quiet_base(df: pd.DataFrame, config: ScanConfig) -> pd.Series:
    quiet_volume = df["Volume"].rolling(10).mean() <= (df["VOL50"] * config.quiet_volume_ratio)
    near_high = df["Close"] >= (df["52W_HIGH"] * config.near_high_ratio)
    return (quiet_volume & tight_action(df, config) & near_high).fillna(False)


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
    out["TIGHT_ACTION"] = tight_action(out, config)
    out["QUIET_BASE"] = quiet_base(out, config)
    out["BREAKOUT"] = breakout_signal(out, config)

    if benchmark_close is not None:
        aligned_bench = benchmark_close.reindex(out.index).ffill()
        out["RS_6M"] = relative_strength_vs_benchmark(out["Close"], aligned_bench, 126)
    else:
        out["RS_6M"] = pd.NA

    out["TICKER"] = ticker
    return out


def market_trend_status(benchmark_df: pd.DataFrame) -> dict[str, object]:
    enriched = add_indicators(benchmark_df)
    last = enriched.iloc[-1]
    close = float(last["Close"])
    sma50 = float(last["SMA50"]) if pd.notna(last["SMA50"]) else None
    sma200 = float(last["SMA200"]) if pd.notna(last["SMA200"]) else None
    above_50 = bool(sma50 is not None and close > sma50)
    above_200 = bool(sma200 is not None and close > sma200)
    return {
        "MarketTrendOK": above_50 and above_200,
        "BenchmarkClose": close,
        "BenchmarkSMA50": sma50,
        "BenchmarkSMA200": sma200,
        "Above50DMA": above_50,
        "Above200DMA": above_200,
    }


def latest_scan_table(
    data_map: dict[str, pd.DataFrame],
    benchmark_df: pd.DataFrame | None,
    regime_df: pd.DataFrame | None,
    config: ScanConfig,
) -> pd.DataFrame:
    rows = []
    benchmark_close = benchmark_df["Close"] if benchmark_df is not None else None
    market_status = (
        market_trend_status(regime_df) if regime_df is not None else {"MarketTrendOK": True}
    )

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
                "QuietBase": bool(last["QUIET_BASE"]),
                "TightAction": bool(last["TIGHT_ACTION"]),
                "Breakout": bool(last["BREAKOUT"]),
                "RS_6M": None if pd.isna(last["RS_6M"]) else float(last["RS_6M"]),
                "ADV50": float(last["ADV50"]) if pd.notna(last["ADV50"]) else None,
                "NearHigh": bool(pd.notna(last["52W_HIGH"]) and last["Close"] >= last["52W_HIGH"] * config.near_high_ratio),
                "MarketTrendOK": bool(market_status["MarketTrendOK"]),
                "Above50DMA": bool(market_status.get("Above50DMA", True)),
                "Above200DMA": bool(market_status.get("Above200DMA", True)),
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    result["RS_Rank"] = result["RS_6M"].rank(pct=True, method="average") * 100
    result["RS_Rank"] = result["RS_Rank"].fillna(0.0)
    result["LeaderTicker"] = result["Ticker"].isin(US_LEADER_TICKERS) | result["Ticker"].str.endswith(".KS")
    result["Watchlist"] = (
        result["MarketTrendOK"]
        & result["TrendTemplate"]
        & (result["RS_Rank"] >= config.rs_rank_min)
        & result["NearHigh"]
        & result["QuietBase"]
        & result["VCPCandidate"]
        & result["LeaderTicker"]
    )
    result["BreakoutReady"] = result["Watchlist"] & result["Breakout"]

    return result.sort_values(
        by=["BreakoutReady", "Watchlist", "QuietBase", "RS_Rank", "Breakout", "TrendTemplate", "VCPCandidate", "RS_6M"],
        ascending=[False, False, False, False, False, False, False, False],
    ).reset_index(drop=True)
