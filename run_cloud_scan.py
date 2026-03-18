from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from zoneinfo import ZoneInfo

from minervini_system.config import ScanConfig
from minervini_system.data import download_ohlcv
from minervini_system.scanner import latest_scan_table


TICKERS = [
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
BENCHMARK = "^GSPC"
REPORT_PATH = Path("scan_report.md")
CSV_PATH = Path("scan_results.csv")


def build_markdown_report(
    result: pd.DataFrame,
    market_date: str,
    generated_at_utc: str,
    skipped: bool = False,
    reason: str | None = None,
) -> str:
    lines = [
        "# Daily Market Scan",
        "",
        f"- Market date: `{market_date}`",
        f"- Generated at (UTC): `{generated_at_utc}`",
        "",
    ]

    if skipped:
        lines.append(f"Skipped: {reason or 'No fresh market data available.'}")
        lines.append("")
        return "\n".join(lines)

    breakout_rows = result[result["Breakout"]].head(10)
    vcp_rows = result[result["VCPCandidate"]].head(10)

    lines.append("## Breakout Candidates")
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
    lines.append("## VCP Candidates")
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


def main() -> None:
    now_utc = datetime.now(UTC)
    ny_tz = ZoneInfo("America/New_York")
    ny_today = now_utc.astimezone(ny_tz).date()

    data_map = download_ohlcv(TICKERS, start="2023-01-01")
    benchmark_map = download_ohlcv([BENCHMARK], start="2023-01-01")
    benchmark_df = benchmark_map[BENCHMARK]
    result = latest_scan_table(data_map, benchmark_df, ScanConfig())

    latest_market_timestamp = max(df.index.max() for df in data_map.values())
    latest_market_date = pd.Timestamp(latest_market_timestamp).date()

    if latest_market_date < ny_today:
        report = build_markdown_report(
            result=result,
            market_date=str(latest_market_date),
            generated_at_utc=now_utc.isoformat(),
            skipped=True,
            reason="Fresh U.S. market close data is not available yet, or the market was closed.",
        )
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(report)
        return

    result.to_csv(CSV_PATH, index=False)
    report = build_markdown_report(
        result=result,
        market_date=str(latest_market_date),
        generated_at_utc=now_utc.isoformat(),
    )
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
