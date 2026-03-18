from __future__ import annotations

from minervini_system.config import ScanConfig
from minervini_system.data import download_ohlcv
from minervini_system.scanner import latest_scan_table


def main() -> None:
    tickers = [
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
    ]
    benchmark = "^GSPC"

    data_map = download_ohlcv(tickers, start="2023-01-01")
    benchmark_map = download_ohlcv([benchmark], start="2023-01-01")
    benchmark_df = benchmark_map[benchmark]

    result = latest_scan_table(data_map, benchmark_df, ScanConfig())
    print(result.to_string(index=False))
    result.to_csv("scan_results.csv", index=False)
    print("\nSaved to scan_results.csv")


if __name__ == "__main__":
    main()
