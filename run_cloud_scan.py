from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from zoneinfo import ZoneInfo

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
        "timezone": "America/New_York",
    },
    "KR": {
        "ticker_source": "kospi200",
        "benchmark": "^KS11",
        "regime_symbol": "^KS11",
        "timezone": "Asia/Seoul",
    },
}
REPORT_PATH = Path("scan_report.md")
HTML_REPORT_PATH = Path("scan_report.html")
CSV_PATH = Path("scan_results.csv")
HISTORY_PATH = Path("report_history/scan_history.csv")


def resolve_tickers(market_config: dict[str, object]) -> list[str]:
    if market_config.get("ticker_source") == "kospi200":
        return get_kospi200_tickers()
    return list(market_config["tickers"])


def build_markdown_report(
    result: pd.DataFrame,
    generated_at_utc: str,
    freshness: dict[str, str],
    skipped_markets: dict[str, str],
    market_regimes: dict[str, dict[str, object]],
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
        regime = market_regimes.get(market, {})
        if regime:
            lines.append(
                f"- Market trend: `{'ON' if regime.get('MarketTrendOK') else 'OFF'}` "
                f"(50DMA={regime.get('Above50DMA')}, 200DMA={regime.get('Above200DMA')})"
            )
        if market in skipped_markets:
            lines.append(f"- Status: skipped ({skipped_markets[market]})")
            lines.append("")
            continue

        market_rows = result[result["Market"] == market]
        breakout_rows = market_rows[market_rows["BreakoutReady"]].head(10)
        vcp_rows = market_rows[market_rows["Watchlist"]].head(10)

        lines.append("### Breakout Candidates")
        lines.append("")
        if breakout_rows.empty:
            lines.append("No breakout candidates passed today.")
        else:
            lines.append(
                breakout_rows[
                    ["Ticker", "Close", "RS_Rank", "NearHigh", "QuietBase", "RS_6M"]
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
                    ["Ticker", "Close", "RS_Rank", "NearHigh", "QuietBase", "RS_6M"]
                ].to_markdown(index=False)
            )
        lines.append("")

    return "\n".join(lines)


def _html_table(df: pd.DataFrame) -> str:
    display_df = df.copy()
    for column in ["Close", "RS_6M", "ADV50", "RS_Rank"]:
        if column in display_df.columns:
            display_df[column] = display_df[column].map(
                lambda value: f"{value:,.2f}" if pd.notna(value) else ""
            )
    return display_df.to_html(index=False, border=0, classes="scan-table")


def _svg_line_chart(series: pd.Series, title: str, stroke: str) -> str:
    clean = series.dropna().tail(90)
    if clean.empty or len(clean) < 2:
        return "<p class='empty'>Not enough data for chart.</p>"

    values = clean.astype(float).tolist()
    width = 720
    height = 220
    pad_x = 18
    pad_y = 20
    chart_w = width - (pad_x * 2)
    chart_h = height - (pad_y * 2)
    min_v = min(values)
    max_v = max(values)
    span = max(max_v - min_v, 1e-9)

    points = []
    for idx, value in enumerate(values):
        x = pad_x + (chart_w * idx / (len(values) - 1))
        y = pad_y + chart_h - (((value - min_v) / span) * chart_h)
        points.append(f"{x:.1f},{y:.1f}")

    first_v = values[0]
    last_v = values[-1]
    change_pct = ((last_v / first_v) - 1) * 100 if first_v else 0.0
    label_color = "#1e7a46" if change_pct >= 0 else "#a33a2b"
    baseline = pad_y + chart_h

    return f"""
    <div class="chart-wrap">
      <div class="chart-header">
        <div>
          <p class="chart-title">{title}</p>
          <p class="chart-subtitle">Last 90 trading sessions</p>
        </div>
        <div class="chart-stats">
          <span class="chart-last">{last_v:,.2f}</span>
          <span class="chart-change" style="color: {label_color};">{change_pct:+.2f}%</span>
        </div>
      </div>
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="{title} trend chart">
        <line x1="{pad_x}" y1="{baseline:.1f}" x2="{width - pad_x}" y2="{baseline:.1f}" stroke="#d7e2ee" stroke-width="1" />
        <line x1="{pad_x}" y1="{pad_y}" x2="{pad_x}" y2="{baseline:.1f}" stroke="#d7e2ee" stroke-width="1" />
        <polyline fill="none" stroke="{stroke}" stroke-width="3" points="{' '.join(points)}" />
        <circle cx="{points[-1].split(',')[0]}" cy="{points[-1].split(',')[1]}" r="4" fill="{stroke}" />
      </svg>
    </div>
    """


def _svg_multi_line_chart(
    df: pd.DataFrame,
    title: str,
    series_config: list[tuple[str, str, str]],
) -> str:
    chart_df = df.tail(30).copy()
    if chart_df.empty or len(chart_df) < 2:
        return "<p class='empty'>Not enough history for chart.</p>"

    width = 720
    height = 240
    pad_x = 22
    pad_y = 20
    chart_w = width - (pad_x * 2)
    chart_h = height - (pad_y * 2)

    valid_columns = [column for column, _, _ in series_config if column in chart_df.columns]
    if not valid_columns:
        return "<p class='empty'>Not enough history for chart.</p>"

    all_values = []
    for column in valid_columns:
        all_values.extend(chart_df[column].fillna(0).astype(float).tolist())

    min_v = min(all_values)
    max_v = max(all_values)
    span = max(max_v - min_v, 1.0)
    baseline = pad_y + chart_h

    polylines = []
    legend_items = []
    for column, label, color in series_config:
        if column not in chart_df.columns:
            continue
        values = chart_df[column].fillna(0).astype(float).tolist()
        points = []
        for idx, value in enumerate(values):
            x = pad_x + (chart_w * idx / (len(values) - 1))
            y = pad_y + chart_h - (((value - min_v) / span) * chart_h)
            points.append(f"{x:.1f},{y:.1f}")
        polylines.append(
            f"<polyline fill='none' stroke='{color}' stroke-width='3' points='{' '.join(points)}' />"
        )
        legend_items.append(
            f"<span class='legend-item'><span class='legend-dot' style='background:{color};'></span>{label}</span>"
        )

    return f"""
    <div class="chart-wrap">
      <div class="chart-header">
        <div>
          <p class="chart-title">{title}</p>
          <p class="chart-subtitle">Last 30 recorded sessions</p>
        </div>
        <div class="chart-legend">{''.join(legend_items)}</div>
      </div>
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="{title}">
        <line x1="{pad_x}" y1="{baseline:.1f}" x2="{width - pad_x}" y2="{baseline:.1f}" stroke="#d7e2ee" stroke-width="1" />
        <line x1="{pad_x}" y1="{pad_y}" x2="{pad_x}" y2="{baseline:.1f}" stroke="#d7e2ee" stroke-width="1" />
        {''.join(polylines)}
      </svg>
    </div>
    """


def load_history() -> pd.DataFrame:
    if not HISTORY_PATH.exists():
        return pd.DataFrame()
    history = pd.read_csv(HISTORY_PATH)
    if history.empty:
        return history
    history["Date"] = pd.to_datetime(history["Date"])
    return history


def update_history(history: pd.DataFrame, snapshots: list[dict]) -> pd.DataFrame:
    incoming = pd.DataFrame(snapshots)
    if incoming.empty:
        return history

    incoming["Date"] = pd.to_datetime(incoming["Date"])
    combined = pd.concat([history, incoming], ignore_index=True) if not history.empty else incoming
    combined = combined.sort_values(["Market", "Date"]).drop_duplicates(
        subset=["Market", "Date"],
        keep="last",
    )
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined_to_save = combined.copy()
    combined_to_save["Date"] = combined_to_save["Date"].dt.strftime("%Y-%m-%d")
    combined_to_save.to_csv(HISTORY_PATH, index=False)
    return combined


def build_html_report(
    result: pd.DataFrame,
    generated_at_utc: str,
    freshness: dict[str, str],
    skipped_markets: dict[str, str],
    benchmark_history: dict[str, pd.Series],
    metric_history: pd.DataFrame,
    market_regimes: dict[str, dict[str, object]],
) -> str:
    sections: list[str] = []
    chart_colors = {"US": "#0b7285", "KR": "#d9480f"}

    for market in MARKETS:
        market_rows = result[result["Market"] == market]
        breakout_rows = market_rows[market_rows["BreakoutReady"]].head(10)
        vcp_rows = market_rows[market_rows["Watchlist"]].head(10)
        status_html = ""
        if market in skipped_markets:
            status_html = (
                f"<p class='status skipped'>Skipped: {skipped_markets[market]}</p>"
            )
        regime = market_regimes.get(market, {})
        regime_html = ""
        if regime:
            tone = "good" if regime.get("MarketTrendOK") else "warning"
            regime_html = (
                f"<p class='status {tone}'>Market trend "
                f"{'ON' if regime.get('MarketTrendOK') else 'OFF'}: "
                f"above 50DMA={regime.get('Above50DMA')}, above 200DMA={regime.get('Above200DMA')}</p>"
            )

        breakout_html = (
            "<p class='empty'>No breakout candidates passed today.</p>"
            if breakout_rows.empty
            else _html_table(
                breakout_rows[
                    ["Ticker", "Close", "RS_Rank", "NearHigh", "QuietBase", "RS_6M"]
                ]
            )
        )
        vcp_html = (
            "<p class='empty'>No VCP candidates passed today.</p>"
            if vcp_rows.empty
            else _html_table(
                vcp_rows[
                    ["Ticker", "Close", "RS_Rank", "NearHigh", "QuietBase", "RS_6M"]
                ]
            )
        )
        chart_html = _svg_line_chart(
            benchmark_history.get(market, pd.Series(dtype=float)),
            f"{market} benchmark trend",
            chart_colors.get(market, "#1d6fa5"),
        )
        market_history = metric_history[metric_history["Market"] == market].copy()
        activity_chart = _svg_multi_line_chart(
            market_history,
            f"{market} setup activity",
            [
                ("BreakoutCount", "Breakouts", "#1c7ed6"),
                ("VCPCount", "VCP", "#f08c00"),
                ("TrendTemplateCount", "Trend", "#2b8a3e"),
            ],
        )

        sections.append(
            f"""
            <section class="market-card">
              <h2>{market} Market</h2>
              <p class="meta">Latest market date: <strong>{freshness.get(market, "unknown")}</strong></p>
              {status_html}
              {regime_html}
              <h3>Benchmark Trend</h3>
              {chart_html}
              <h3>Setup Activity Trend</h3>
              {activity_chart}
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
      .chart-wrap {{
        background: #f8fbfe;
        border: 1px solid #e3ebf5;
        border-radius: 14px;
        padding: 14px 14px 10px 14px;
      }}
      .chart-header {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: flex-start;
        margin-bottom: 8px;
      }}
      .chart-title {{
        margin: 0;
        font-size: 14px;
        font-weight: bold;
        color: #173a5d;
      }}
      .chart-subtitle {{
        margin: 4px 0 0 0;
        font-size: 12px;
        color: #5b7288;
      }}
      .chart-stats {{
        text-align: right;
      }}
      .chart-legend {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        justify-content: flex-end;
        font-size: 12px;
        color: #4a6178;
      }}
      .legend-item {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }}
      .legend-dot {{
        width: 10px;
        height: 10px;
        border-radius: 999px;
        display: inline-block;
      }}
      .chart-last {{
        display: block;
        font-size: 18px;
        font-weight: bold;
        color: #173a5d;
      }}
      .chart-change {{
        display: block;
        margin-top: 4px;
        font-size: 13px;
        font-weight: bold;
      }}
      svg {{
        width: 100%;
        height: auto;
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
      .good {{
        background: #e6f7ef;
        color: #13663c;
      }}
      .warning {{
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
    return result


def main() -> None:
    now_utc = datetime.now(UTC)
    fresh_results = []
    freshness: dict[str, str] = {}
    skipped_markets: dict[str, str] = {}
    benchmark_history: dict[str, pd.Series] = {}
    history_snapshots: list[dict] = []
    market_regimes: dict[str, dict[str, object]] = {}

    for market, market_config in MARKETS.items():
        tickers = resolve_tickers(market_config)
        benchmark = market_config["benchmark"]
        regime_symbol = market_config["regime_symbol"]
        market_tz = ZoneInfo(market_config["timezone"])
        market_today = now_utc.astimezone(market_tz).date()

        data_map = download_ohlcv(tickers, start="2023-01-01")
        benchmark_map = download_ohlcv([benchmark], start="2023-01-01")
        regime_map = download_ohlcv([regime_symbol], start="2023-01-01")
        benchmark_df = benchmark_map[benchmark]
        regime_df = regime_map[regime_symbol]
        benchmark_history[market] = benchmark_df["Close"]
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
            regime_symbol=regime_symbol,
            start="2023-01-01",
        )
        if not market_result.empty:
            market_regimes[market] = {
                "MarketTrendOK": bool(market_result["MarketTrendOK"].iloc[0]),
                "Above50DMA": bool(market_result["Above50DMA"].iloc[0]),
                "Above200DMA": bool(market_result["Above200DMA"].iloc[0]),
            }
        breakout_count = 0 if market_result.empty else int(market_result["Breakout"].sum())
        vcp_count = 0 if market_result.empty else int(market_result["VCPCandidate"].sum())
        trend_count = 0 if market_result.empty else int(market_result["TrendTemplate"].sum())
        top_rs_ticker = (
            ""
            if market_result.empty
            else str(
                market_result.sort_values("RS_6M", ascending=False)
                .iloc[0]["Ticker"]
            )
        )
        history_snapshots.append(
            {
                "Date": str(latest_market_date),
                "Market": market,
                "BreakoutCount": breakout_count,
                "VCPCount": vcp_count,
                "TrendTemplateCount": trend_count,
                "TopRSTicker": top_rs_ticker,
            }
        )
        if not market_result.empty:
            fresh_results.append(market_result)

    result = pd.concat(fresh_results, ignore_index=True) if fresh_results else pd.DataFrame()
    if not result.empty:
        result.to_csv(CSV_PATH, index=False)
    history_df = load_history()
    history_df = update_history(history_df, history_snapshots)
    report = build_markdown_report(
        result=result,
        generated_at_utc=now_utc.isoformat(),
        freshness=freshness,
        skipped_markets=skipped_markets,
        market_regimes=market_regimes,
    )
    html_report = build_html_report(
        result=result,
        generated_at_utc=now_utc.isoformat(),
        freshness=freshness,
        skipped_markets=skipped_markets,
        benchmark_history=benchmark_history,
        metric_history=history_df,
        market_regimes=market_regimes,
    )
    REPORT_PATH.write_text(report, encoding="utf-8")
    HTML_REPORT_PATH.write_text(html_report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
