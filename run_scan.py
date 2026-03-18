from __future__ import annotations

import pandas as pd

from minervini_system.config import ScanConfig
from minervini_system.data import download_ohlcv
from minervini_system.scanner import latest_scan_table


MARKETS = {
    "US": {
        "tickers": [
            "NVDA",
            "META",
            "MSFT",
            "AMZN",
            "TSLA",
            "AAPL",
            "AVGO",
            "PLTR",
            "CRWD",
            "SNOW",
            "SHOP",
            "DUOL",
            "ELF",
            "ANET",
            "AMD",
        ],
        "benchmark": "^GSPC",
    },
    "KR": {
        "tickers": [
            "005930.KS",
            "000660.KS",
            "035420.KS",
            "035720.KS",
            "068270.KS",
            "247540.KQ",
            "086520.KQ",
            "196170.KQ",
            "042700.KS",
            "214150.KQ",
        ],
        "benchmark": "^KS11",
    },
}


def scan_market(market: str, tickers: list[str], benchmark: str, start: str) -> pd.DataFrame:
    data_map = download_ohlcv(tickers, start=start)
    benchmark_map = download_ohlcv([benchmark], start=start)
    benchmark_df = benchmark_map[benchmark]
    result = latest_scan_table(data_map, benchmark_df, ScanConfig())
    if result.empty:
        return result
    result["Market"] = market
    return result


def main() -> None:
    results = []
    for market, market_config in MARKETS.items():
        market_result = scan_market(
            market=market,
            tickers=market_config["tickers"],
            benchmark=market_config["benchmark"],
            start="2023-01-01",
        )
        if not market_result.empty:
            results.append(market_result)

    result = pd.concat(results, ignore_index=True) if results else pd.DataFrame()
    print(result.to_string(index=False))
    result.to_csv("scan_results.csv", index=False)
    print("\nSaved to scan_results.csv")


if __name__ == "__main__":
    main()
