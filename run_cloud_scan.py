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
HTML_REPORT_PATH = Path("scan_report.html")
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


def _html_table(df: pd.DataFrame) -> str:
    display_df = df.copy()
    for column in ["Close", "RS_6M", "ADV50"]:
        if column in display_df.columns:
            display_df[column] = display_df[column].map(
                lambda value: f"{value:,.2f}" if pd.notna(value) else ""
            )
    return display_df.to_html(index=False, border=0, classes="scan-table")


def build_html_report(
    result: pd.DataFrame,
    generated_at_utc: str,
    freshness: dict[str, str],
    skipped_markets: dict[str, str],
) -> str:
    sections: list[str] = []

    for market in MARKETS:
        market_rows = result[result["Market"] == market]
        breakout_rows = market_rows[market_rows["Breakout"]].head(10)
        vcp_rows = market_rows[market_rows["VCPCandidate"]].head(10)
        status_html = ""
        if market in skipped_markets:
            status_html = (
                f"<p class='status skipped'>Skipped: {skipped_markets[market]}</p>"
            )

        breakout_html = (
            "<p class='empty'>No breakout candidates passed today.</p>"
            if breakout_rows.empty
            else _html_table(
                breakout_rows[
                    ["Ticker", "Close", "TrendTemplate", "VCPCandidate", "RS_6M", "ADV50"]
                ]
            )
        )
        vcp_html = (
            "<p class='empty'>No VCP candidates passed today.</p>"
            if vcp_rows.empty
            else _html_table(
                vcp_rows[
                    ["Ticker", "Close", "TrendTemplate", "Breakout", "RS_6M", "ADV50"]
                ]
            )
        )

        sections.append(
            f"""
            <section class="market-card">
              <h2>{market} Market</h2>
              <p class="meta">Latest market date: <strong>{freshness.get(market, "unknown")}</strong></p>
              {status_html}
              <h3>Breakout Candidates</h3>
              {breakout_html}
              <h3>VCP Candidates</h3>
              {vcp_html}
            </section>
            """
        )

    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Market Scan</title>
    <style>
      body {{
        margin: 0;
        padding: 24px;
        background: #f3f6fb;
        color: #10233a;
        font-family: Arial, Helvetica, sans-serif;
      }}
      .wrap {{
        max-width: 980px;
        margin: 0 auto;
      }}
      .hero {{
        background: linear-gradient(135deg, #0f3d66, #1d6fa5);
        color: #ffffff;
        border-radius: 18px;
        padding: 28px 32px;
        box-shadow: 0 12px 30px rgba(16, 35, 58, 0.18);
      }}
      .hero h1 {{
        margin: 0 0 8px 0;
        font-size: 28px;
      }}
      .hero p {{
        margin: 4px 0;
        opacity: 0.92;
      }}
      .market-card {{
        margin-top: 20px;
        background: #ffffff;
        border-radius: 18px;
        padding: 24px;
        box-shadow: 0 10px 24px rgba(16, 35, 58, 0.08);
      }}
      .market-card h2 {{
        margin: 0 0 8px 0;
        font-size: 22px;
        color: #0f3d66;
      }}
      .market-card h3 {{
        margin: 22px 0 10px 0;
        font-size: 16px;
        color: #1c4f7f;
      }}
      .meta {{
        margin: 0 0 8px 0;
        color: #4a6178;
      }}
      .status {{
        padding: 10px 12px;
        border-radius: 10px;
        font-size: 14px;
      }}
      .skipped {{
        background: #fff2df;
        color: #8a5a00;
      }}
      .empty {{
        padding: 14px 16px;
        border-radius: 12px;
        background: #eef4fb;
        color: #4a6178;
      }}
      table.scan-table {{
        width: 100%;
        border-collapse: collapse;
        overflow: hidden;
        border-radius: 12px;
      }}
      .scan-table thead th {{
        background: #e6f0fa;
        color: #173a5d;
        font-size: 13px;
        text-align: left;
        padding: 10px 12px;
      }}
      .scan-table tbody td {{
        border-top: 1px solid #e7edf4;
        padding: 10px 12px;
        font-size: 13px;
      }}
      .scan-table tbody tr:nth-child(even) {{
        background: #fbfdff;
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <section class="hero">
        <h1>Daily Market Scan</h1>
        <p>Generated at (UTC): <strong>{generated_at_utc}</strong></p>
        <p>Markets covered: U.S. and South Korea</p>
      </section>
      {"".join(sections)}
    </div>
  </body>
</html>
"""


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
    html_report = build_html_report(
        result=result,
        generated_at_utc=now_utc.isoformat(),
        freshness=freshness,
        skipped_markets=skipped_markets,
    )
    REPORT_PATH.write_text(report, encoding="utf-8")
    HTML_REPORT_PATH.write_text(html_report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
