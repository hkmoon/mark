from __future__ import annotations

import pandas as pd

from minervini_system.config import ScanConfig
from minervini_system.data import download_ohlcv, get_kospi200_tickers
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
        "ticker_source": "kospi200",
        "benchmark": "^KS11",
        "regime_symbol": "^KS11",
    },
}


def resolve_tickers(market_config: dict[str, object]) -> list[str]:
    if market_config.get("ticker_source") == "kospi200":
        return get_kospi200_tickers()
    return list(market_config["tickers"])


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
            tickers=resolve_tickers(market_config),
            benchmark=market_config["benchmark"],
            regime_symbol=market_config["regime_symbol"],
            start="2023-01-01",
        )
        if not market_result.empty:
            results.append(market_result)

    result = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    if not result.empty:
        filtered = result[
            [
                "Market",
                "Ticker",
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
