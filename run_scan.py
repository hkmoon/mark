from __future__ import annotations

import pandas as pd

from minervini_system.config import ScanConfig
from minervini_system.data import download_ohlcv
from minervini_system.scanner import latest_scan_table


MARKETS = {
    "US": {
        "tickers": [
            "NVDA",
            "MSFT",
            "AVGO",
            "SMCI",
            "PLTR",
            "CRWD",
            "ANET",
            "AMD",
            "MU",
            "ARM",
            "TSM",
            "ASML",
            "AMAT",
            "LRCX",
            "KLAC",
            "MRVL",
            "QCOM",
            "MCHP",
        ],
        "benchmark": "^GSPC",
        "regime_symbol": "SPY",
    },
    "KR": {
        "tickers": [
            "000660.KS",
            "005930.KS",
            "042700.KS",
            "000990.KS",
            "058470.KQ",
            "039030.KQ",
            "086520.KQ",
            "247540.KQ",
            "240810.KQ",
            "078600.KQ",
        ],
        "benchmark": "^KS11",
        "regime_symbol": "^KS11",
    },
}

DISPLAY_NAMES = {
    "NVDA": "NVIDIA",
    "MSFT": "Microsoft",
    "AVGO": "Broadcom",
    "SMCI": "Super Micro Computer",
    "PLTR": "Palantir",
    "CRWD": "CrowdStrike",
    "ANET": "Arista Networks",
    "AMD": "AMD",
    "MU": "Micron",
    "ARM": "Arm Holdings",
    "TSM": "TSMC",
    "ASML": "ASML",
    "AMAT": "Applied Materials",
    "LRCX": "Lam Research",
    "KLAC": "KLA",
    "MRVL": "Marvell",
    "QCOM": "Qualcomm",
    "MCHP": "Microchip",
    "000660.KS": "SK hynix",
    "005930.KS": "Samsung Electronics",
    "042700.KS": "Hanmi Semiconductor",
    "000990.KS": "DB Hitek",
    "058470.KQ": "Leeno Industrial",
    "039030.KQ": "EO Technics",
    "086520.KQ": "EcoPro",
    "247540.KQ": "EcoPro BM",
    "240810.KQ": "Wonik IPS",
    "078600.KQ": "DMS",
}


def format_display_ticker(ticker: str) -> str:
    return f"{DISPLAY_NAMES.get(ticker, ticker)} ({ticker})"


def format_number(value: float | int | object) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):,.2f}"


def format_close_by_market(row: pd.Series) -> str:
    if pd.isna(row["Close"]):
        return ""
    market = row.get("Market")
    ticker = str(row.get("Ticker", ""))
    if market == "KR" or ticker.endswith((".KS", ".KQ")):
        return f"{float(row['Close']):,.0f}"
    return f"{float(row['Close']):,.2f}"


def scan_market(
    market: str,
    tickers: list[str],
    benchmark: str,
    regime_symbol: str,
    start: str,
) -> pd.DataFrame:
    data_map = download_ohlcv(tickers, start=start)
    benchmark_map = download_ohlcv([benchmark], start=start)
    regime_map = download_ohlcv([regime_symbol], start=start)
    benchmark_df = benchmark_map[benchmark]
    regime_df = regime_map[regime_symbol]
    result = latest_scan_table(data_map, benchmark_df, regime_df, ScanConfig())
    if result.empty:
        return result
    result["Market"] = market
    result["RegimeSymbol"] = regime_symbol
    result["Benchmark"] = benchmark
    return result


def main() -> None:
    results = []
    for market, market_config in MARKETS.items():
        market_result = scan_market(
            market=market,
            tickers=list(market_config["tickers"]),
            benchmark=market_config["benchmark"],
            regime_symbol=market_config["regime_symbol"],
            start="2023-01-01",
        )
        if not market_result.empty:
            results.append(market_result)

    result = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    if not result.empty:
        result["DisplayTicker"] = result["Ticker"].map(format_display_ticker)
        display_result = result.copy()
        display_result["Close"] = display_result.apply(format_close_by_market, axis=1)
        if "RS_Rank" in display_result.columns:
            display_result["RS_Rank"] = display_result["RS_Rank"].map(format_number)
        summary = (
            result.groupby("Market")[["BreakoutReady", "VCPCandidate", "Watchlist"]]
            .sum()
            .rename(
                columns={
                    "BreakoutReady": "Breakouts",
                    "VCPCandidate": "VCPs",
                    "Watchlist": "WatchlistNames",
                }
            )
            .reset_index()
        )
        print("=== Scan Summary ===")
        print(summary.to_string(index=False))
        print("")
        filtered = display_result[
            [
                "Market",
                "DisplayTicker",
                "Close",
                "MarketTrendOK",
                "TrendTemplate",
                "RS_Rank",
                "NearHigh",
                "QuietBase",
                "LeaderTicker",
                "VCPCandidate",
                "Breakout",
                "Watchlist",
                "BreakoutReady",
            ]
        ]
        print(filtered.to_string(index=False))
    else:
        print("No scan results.")
    result.to_csv("scan_results.csv", index=False)
    print("\nSaved to scan_results.csv")


if __name__ == "__main__":
    main()
