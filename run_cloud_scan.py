from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from zoneinfo import ZoneInfo

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
        "timezone": "America/New_York",
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
        "timezone": "Asia/Seoul",
    },
}
REPORT_PATH = Path("scan_report.md")
CSV_PATH = Path("scan_results.csv")


def build_markdown_report(
    result: pd.DataFrame,
    generated_at_utc: str,
    freshness: dict[str, str],
    skipped_markets: dict[str, str],
) -> str:
    lines = [
        "# Daily Market Scan",
        "",
        f"- Generated at (UTC): `{generated_at_utc}`",
        "",
    ]

    for market in MARKETS:
        lines.append(f"## {market} Market")
        lines.append("")
        lines.append(f"- Latest market date: `{freshness.get(market, 'unknown')}`")
        if market in skipped_markets:
            lines.append(f"- Status: skipped ({skipped_markets[market]})")
            lines.append("")
            continue

        market_rows = result[result["Market"] == market]
        breakout_rows = market_rows[market_rows["Breakout"]].head(10)
        vcp_rows = market_rows[market_rows["VCPCandidate"]].head(10)

        lines.append("### Breakout Candidates")
        lines.append("")
        if breakout_rows.empty:
            lines.append("No breakout candidates passed today.")
        else:
            lines.append(
                breakout_rows[
                    ["Ticker", "Close", "TrendTemplate", "VCPCandidate", "RS_6M", "ADV50"]
                ].to_markdown(index=False)
            )

        lines.append("")
        lines.append("### VCP Candidates")
        lines.append("")
        if vcp_rows.empty:
            lines.append("No VCP candidates passed today.")
        else:
            lines.append(
                vcp_rows[
                    ["Ticker", "Close", "TrendTemplate", "Breakout", "RS_6M", "ADV50"]
                ].to_markdown(index=False)
            )
        lines.append("")

    return "\n".join(lines)


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
    now_utc = datetime.now(UTC)
    fresh_results = []
    freshness: dict[str, str] = {}
    skipped_markets: dict[str, str] = {}

    for market, market_config in MARKETS.items():
        tickers = market_config["tickers"]
        benchmark = market_config["benchmark"]
        market_tz = ZoneInfo(market_config["timezone"])
        market_today = now_utc.astimezone(market_tz).date()

        data_map = download_ohlcv(tickers, start="2023-01-01")
        latest_market_timestamp = max(df.index.max() for df in data_map.values())
        latest_market_date = pd.Timestamp(latest_market_timestamp).date()
        freshness[market] = str(latest_market_date)

        data_age_days = (market_today - latest_market_date).days
        if data_age_days > 1:
            skipped_markets[market] = "fresh data unavailable or market closed"
            continue

        market_result = scan_market(
            market=market,
            tickers=tickers,
            benchmark=benchmark,
            start="2023-01-01",
        )
        if not market_result.empty:
            fresh_results.append(market_result)

    result = pd.concat(fresh_results, ignore_index=True) if fresh_results else pd.DataFrame()
    if not result.empty:
        result.to_csv(CSV_PATH, index=False)
    report = build_markdown_report(
        result=result,
        generated_at_utc=now_utc.isoformat(),
        freshness=freshness,
        skipped_markets=skipped_markets,
    )
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
