from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from zoneinfo import ZoneInfo

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
        "timezone": "America/New_York",
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
        "timezone": "Asia/Seoul",
    },
}
REPORT_PATH = Path("scan_report.md")
HTML_REPORT_PATH = Path("scan_report.html")
TELEGRAM_PAYLOAD_PATH = Path("scan_report_telegram.json")
CSV_PATH = Path("scan_results.csv")
HISTORY_PATH = Path("report_history/scan_history.csv")

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


def ticker_url(ticker: str) -> str:
    return f"https://finance.yahoo.com/quote/{quote(ticker, safe='')}/"


def format_ticker_markdown(ticker: str) -> str:
    label = format_display_ticker(ticker)
    return f"[{label}]({ticker_url(ticker)})"


def format_ticker_html(ticker: str) -> str:
    label = escape(format_display_ticker(ticker))
    url = escape(ticker_url(ticker), quote=True)
    return f"<a href=\"{url}\" target=\"_blank\" rel=\"noopener noreferrer\">{label}</a>"


def row_highlight_class(row: pd.Series) -> str:
    if bool(row.get("BreakoutReady", False)) or bool(row.get("Breakout", False)):
        return "row-breakout"
    if bool(row.get("Watchlist", False)):
        return "row-watchlist"
    if bool(row.get("VCPCandidate", False)):
        return "row-vcp"
    if bool(row.get("NearHigh", False)) and bool(row.get("TrendTemplate", False)):
        return "row-nearmiss"
    return ""


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


def markdown_table(df: pd.DataFrame) -> str:
    display_df = df.copy()
    if "Close" in display_df.columns:
        display_df["Close"] = display_df.apply(format_close_by_market, axis=1)
    if "Ticker" in display_df.columns:
        display_df["Ticker"] = display_df["Ticker"].map(format_ticker_markdown)
    for column in ["RS_Rank", "RS_6M", "ADV50"]:
        if column in display_df.columns:
            display_df[column] = display_df[column].map(format_number)
    return display_df.astype(str).to_markdown(index=False, disable_numparse=True)


def build_markdown_report(
    result: pd.DataFrame,
    generated_at_utc: str,
    freshness: dict[str, str],
    skipped_markets: dict[str, str],
    market_regimes: dict[str, dict[str, object]],
) -> str:
    working = result.copy()
    summary_rows = []
    if not working.empty:
        summary_rows = (
            working.groupby("Market")[["BreakoutReady", "VCPCandidate", "Watchlist"]]
            .sum()
            .rename(
                columns={
                    "BreakoutReady": "Breakouts",
                    "VCPCandidate": "VCPs",
                    "Watchlist": "WatchlistNames",
                }
            )
            .reset_index()
            .to_dict("records")
        )

    lines = [
        "# Daily Market Scan",
        "",
        f"- Generated at (UTC): `{generated_at_utc}`",
        "",
    ]

    lines.append("## Scan Summary")
    lines.append("")
    if not summary_rows:
        lines.append("No summary available.")
    else:
        lines.append(pd.DataFrame(summary_rows).to_markdown(index=False))
    lines.append("")

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

        market_rows = working[working["Market"] == market]
        breakout_rows = market_rows[market_rows["BreakoutReady"]].head(10)
        vcp_rows = market_rows[market_rows["VCPCandidate"]].head(10)
        watchlist_rows = market_rows[market_rows["Watchlist"]].head(10)
        near_miss_rows = market_rows[
            (market_rows["NearHigh"])
            & (~market_rows["VCPCandidate"])
        ].sort_values(["RS_Rank", "TrendTemplate"], ascending=[False, False]).head(10)

        lines.append("### Breakout Candidates")
        lines.append("")
        if breakout_rows.empty:
            lines.append("No breakout candidates passed today.")
        else:
            lines.append(markdown_table(
                breakout_rows[
                    ["Ticker", "Close", "RS_Rank", "NearHigh", "QuietBase", "RS_6M"]
                ]
            ))

        lines.append("")
        lines.append("### VCP Candidates")
        lines.append("")
        if vcp_rows.empty:
            lines.append("No VCP candidates passed today.")
        else:
            lines.append(markdown_table(
                vcp_rows[
                    ["Ticker", "Close", "RS_Rank", "NearHigh", "QuietBase", "RS_6M"]
                ]
            ))

        lines.append("")
        lines.append("### Watchlist")
        lines.append("")
        if watchlist_rows.empty:
            lines.append("No watchlist names passed today.")
        else:
            lines.append(markdown_table(
                watchlist_rows[
                    ["Ticker", "Close", "RS_Rank", "NearHigh", "QuietBase", "RS_6M"]
                ]
            ))

        lines.append("")
        lines.append("### VCP Near Miss")
        lines.append("")
        if near_miss_rows.empty:
            lines.append("No near-miss names passed today.")
        else:
            lines.append(markdown_table(
                near_miss_rows[
                    ["Ticker", "Close", "RS_Rank", "TrendTemplate", "NearHigh", "QuietBase"]
                ]
            ))
        lines.append("")

    return "\n".join(lines)


def _rich_cell(text: str, *, header: bool = False, align: str = "left") -> dict[str, object]:
    cell: dict[str, object] = {"text": text or "-", "align": align, "valign": "middle"}
    if header:
        cell["is_header"] = True
    return cell


def _rich_table_block(df: pd.DataFrame) -> dict[str, object]:
    display_df = df.copy()
    if "Close" in display_df.columns:
        display_df["Close"] = display_df.apply(format_close_by_market, axis=1)
    for column in ["RS_Rank", "RS_6M", "ADV50"]:
        if column in display_df.columns:
            display_df[column] = display_df[column].map(format_number)
    left_columns = {"Ticker", "NearHigh", "QuietBase", "TrendTemplate"}
    columns = list(display_df.columns)
    rows = [
        [
            _rich_cell(column, header=True, align="left" if column in left_columns else "right")
            for column in columns
        ]
    ]
    for _, row in display_df.iterrows():
        cells = []
        for column in columns:
            if column == "Ticker":
                ticker = str(row[column])
                cells.append(
                    _rich_cell("", align="left")
                    | {
                        "text": {
                            "type": "url",
                            "text": format_display_ticker(ticker) or ticker,
                            "url": ticker_url(ticker),
                        }
                    }
                )
            else:
                cells.append(
                    _rich_cell(str(row[column]), align="left" if column in left_columns else "right")
                )
        rows.append(cells)
    return {
        "type": "table",
        "cells": rows,
        "is_bordered": True,
        "is_striped": True,
        "is_compact": True,
    }


def build_telegram_rich_message(
    result: pd.DataFrame,
    generated_at_utc: str,
    freshness: dict[str, str],
    skipped_markets: dict[str, str],
    market_regimes: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Build an InputRichMessage (Bot API sendRichMessage) with explicit blocks."""
    working = result.copy()
    summary_rows = []
    if not working.empty:
        summary_rows = (
            working.groupby("Market")[["BreakoutReady", "VCPCandidate", "Watchlist"]]
            .sum()
            .rename(
                columns={
                    "BreakoutReady": "Breakouts",
                    "VCPCandidate": "VCPs",
                    "Watchlist": "WatchlistNames",
                }
            )
            .reset_index()
            .to_dict("records")
        )

    def heading(text: str, size: int) -> dict[str, object]:
        return {"type": "heading", "text": text, "size": size}

    def paragraph(text: object) -> dict[str, object]:
        return {"type": "paragraph", "text": text}

    def labeled(label: str, value: str) -> dict[str, object]:
        return paragraph([f"{label}: ", {"type": "code", "text": value}])

    blocks: list[dict[str, object]] = [
        heading("Daily Market Scan", 1),
        labeled("Generated at (UTC)", generated_at_utc),
        heading("Scan Summary", 2),
    ]
    if not summary_rows:
        blocks.append(paragraph("No summary available."))
    else:
        summary_df = pd.DataFrame(summary_rows)
        summary_columns = list(summary_df.columns)
        summary_cells = [
            [
                _rich_cell(column, header=True, align="left" if column == "Market" else "right")
                for column in summary_columns
            ]
        ]
        for _, row in summary_df.iterrows():
            summary_cells.append(
                [
                    _rich_cell(str(row[column]), align="left" if column == "Market" else "right")
                    for column in summary_columns
                ]
            )
        blocks.append(
            {
                "type": "table",
                "cells": summary_cells,
                "is_bordered": True,
                "is_striped": True,
                "is_compact": True,
            }
        )

    for market in MARKETS:
        blocks.append(heading(f"{market} Market", 2))
        blocks.append(labeled("Latest market date", freshness.get(market, "unknown")))
        regime = market_regimes.get(market, {})
        if regime:
            blocks.append(
                labeled(
                    "Market trend",
                    f"{'ON' if regime.get('MarketTrendOK') else 'OFF'} "
                    f"(50DMA={regime.get('Above50DMA')}, 200DMA={regime.get('Above200DMA')})",
                )
            )
        if market in skipped_markets:
            blocks.append(paragraph(f"Status: skipped ({skipped_markets[market]})"))
            continue

        market_rows = working[working["Market"] == market]
        breakout_rows = market_rows[market_rows["BreakoutReady"]].head(10)
        vcp_rows = market_rows[market_rows["VCPCandidate"]].head(10)
        watchlist_rows = market_rows[market_rows["Watchlist"]].head(10)
        near_miss_rows = market_rows[
            (market_rows["NearHigh"])
            & (~market_rows["VCPCandidate"])
        ].sort_values(["RS_Rank", "TrendTemplate"], ascending=[False, False]).head(10)

        standard_columns = ["Ticker", "Close", "RS_Rank", "NearHigh", "QuietBase", "RS_6M"]
        sections = [
            ("Breakout Candidates", breakout_rows, standard_columns, "No breakout candidates passed today."),
            ("VCP Candidates", vcp_rows, standard_columns, "No VCP candidates passed today."),
            ("Watchlist", watchlist_rows, standard_columns, "No watchlist names passed today."),
            (
                "VCP Near Miss",
                near_miss_rows,
                ["Ticker", "Close", "RS_Rank", "TrendTemplate", "NearHigh", "QuietBase"],
                "No near-miss names passed today.",
            ),
        ]
        for title, rows, columns, empty_text in sections:
            blocks.append(heading(title, 3))
            if rows.empty:
                blocks.append(paragraph(empty_text))
            else:
                blocks.append(_rich_table_block(rows[columns]))

    return {"blocks": blocks, "skip_entity_detection": True}


def _html_table(df: pd.DataFrame, columns: list[str] | None = None) -> str:
    source_df = df.copy()
    display_df = df.copy()
    if "Close" in display_df.columns:
        display_df["Close"] = display_df.apply(format_close_by_market, axis=1)
    if "Ticker" in display_df.columns:
        display_df["Ticker"] = display_df["Ticker"].map(format_ticker_html)
    for column in ["RS_6M", "ADV50", "RS_Rank"]:
        if column in display_df.columns:
            display_df[column] = display_df[column].map(format_number)
    visible_columns = columns or list(display_df.columns)
    header_html = "".join(f"<th>{escape(column)}</th>" for column in visible_columns)
    rows_html = []
    for idx, row in display_df.iterrows():
        row_class = row_highlight_class(source_df.loc[idx])
        class_attr = f" class=\"{row_class}\"" if row_class else ""
        cells = []
        for column in visible_columns:
            value = row[column]
            cell_html = value if column == "Ticker" else escape(str(value))
            cells.append(f"<td>{cell_html}</td>")
        rows_html.append(f"<tr{class_attr}>{''.join(cells)}</tr>")
    return (
        "<table class=\"scan-table\">"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )


def _json_for_script(payload: object) -> str:
    """Serialize for a <script type="application/json"> block without </script> breakouts."""
    return (
        json.dumps(payload, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


CHART_JS = r"""
(function () {
  "use strict";
  var SVG_NS = "http://www.w3.org/2000/svg";
  var FONT = 11;
  var CHAR_W = 6.6;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function svgEl(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    for (var key in attrs) { node.setAttribute(key, attrs[key]); }
    return node;
  }
  function htmlEl(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }
  function fmtNum(v, digits) {
    return v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }
  function fmtPct(v) { return (v >= 0 ? "+" : "") + v.toFixed(2) + "%"; }
  function pctColor(v) { return v >= 0 ? "#1e7a46" : "#a33a2b"; }
  function tipRow(tip, label, value, color, dotColor) {
    var row = htmlEl("div", "chart-tip-row");
    var name = htmlEl("span", "chart-tip-label");
    if (dotColor) {
      var dot = htmlEl("span", "legend-dot");
      dot.style.background = dotColor;
      name.appendChild(dot);
    }
    name.appendChild(document.createTextNode(label));
    var val = htmlEl("span", "chart-tip-value", value);
    if (color) { val.style.color = color; }
    row.appendChild(name);
    row.appendChild(val);
    tip.appendChild(row);
  }

  /* ---- layout helpers (all in real CSS pixels: viewBox matches rendered width) ---- */
  function measure(svg) {
    var w = svg.getBoundingClientRect().width;
    return w > 0 ? Math.round(w) : 720;
  }
  function watchWidth(svg, redraw) {
    var last = measure(svg);
    function check() {
      var w = measure(svg);
      if (w !== last) { last = w; redraw(); }
    }
    if (window.ResizeObserver) { new ResizeObserver(check).observe(svg); }
    else { window.addEventListener("resize", check); }
  }
  function swapBase(svg, st, g) {
    if (st.base) { svg.replaceChild(g, st.base); }
    else {
      while (svg.firstChild) { svg.removeChild(svg.firstChild); }
      svg.appendChild(g);
    }
    st.base = g;
  }

  function yTicks(min, max, target, integer) {
    var raw = (max - min) / target;
    if (!(raw > 0)) { raw = 1; }
    var pow = Math.pow(10, Math.floor(Math.log10(raw)));
    var f = raw / pow;
    var step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * pow;
    if (integer) { step = Math.max(1, Math.round(step)); }
    var decimals = step >= 1 ? 0 : Math.min(6, Math.ceil(-Math.log10(step) - 1e-9));
    var ticks = [];
    for (var k = Math.ceil(min / step - 1e-9); k * step <= max + 1e-9; k++) {
      ticks.push(+(k * step).toFixed(10));
    }
    return { ticks: ticks, decimals: decimals };
  }

  function parts(s) { return [+s.slice(0, 4), +s.slice(5, 7), +s.slice(8, 10)]; }
  function labelW(s) { return s.length * CHAR_W; }

  /* returns [{i, label}] over indexes 0..m-1; xOf(i) gives pixel x */
  function xTicks(dates, xOf, W, innerW) {
    var m = dates.length;
    if (m < 2 || !dates[0] || !dates[m - 1]) { return []; }
    var p0 = parts(dates[0]), p1 = parts(dates[m - 1]);
    var days = (Date.UTC(p1[0], p1[1] - 1, p1[2]) - Date.UTC(p0[0], p0[1] - 1, p0[2])) / 86400000;
    var crosses = p0[0] !== p1[0];
    var steps = [1, 3, 6, 12];
    var start = days <= 200 ? 0 : days <= 800 ? 1 : days <= 1600 ? 2 : 3;
    var out = null, t, i;
    for (t = start; t < steps.length && !out; t++) {
      var step = steps[t], kept = [], lastX = -1e9;
      for (i = 1; i < m; i++) {
        var a = parts(dates[i - 1]), b = parts(dates[i]);
        if ((b[0] !== a[0] || b[1] !== a[1]) && (b[1] - 1) % step === 0) {
          var x = xOf(i);
          if (x - lastX >= 70) { kept.push(i); lastX = x; }
        }
      }
      if (kept.length >= 2) {
        var prevYear = null;
        out = kept.map(function (idx) {
          var b = parts(dates[idx]), label;
          if (step === 12) { label = String(b[0]); }
          else if (step === 1) {
            label = MONTHS[b[1] - 1] + (prevYear === null || prevYear !== b[0] ? " '" + String(b[0]).slice(2) : "");
          } else { label = MONTHS[b[1] - 1] + " '" + String(b[0]).slice(2); }
          prevYear = b[0];
          return { i: idx, label: label };
        });
      }
    }
    if (!out) {
      var k = Math.max(2, Math.min(5, Math.floor(innerW / 90)));
      out = [];
      for (var j = 0; j < k; j++) {
        var idx2 = Math.round((j * (m - 1)) / (k - 1));
        var q = parts(dates[idx2]);
        out.push({ i: idx2, label: MONTHS[q[1] - 1] + " " + q[2] + (crosses ? " '" + String(q[0]).slice(2) : "") });
      }
    }
    /* clamp into the svg and drop any label that would touch its neighbour */
    var res = [], edge = -1e9;
    out.forEach(function (tk) {
      var w = labelW(tk.label);
      var x = Math.max(w / 2 + 2, Math.min(xOf(tk.i), W - w / 2 - 2));
      if (x - w / 2 >= edge + 8) {
        res.push({ i: tk.i, label: tk.label, tx: x });
        edge = x + w / 2;
      }
    });
    return res;
  }

  function drawFrame(g, geo, yt, yLabels, xt, yOf, xOf) {
    var gridColor = "#e3ebf5", textColor = "#5b7288";
    var right = geo.W - geo.padR, bottom = geo.H - geo.padB;
    xt.forEach(function (tk) {
      var x = xOf(tk.i).toFixed(1);
      g.appendChild(svgEl("line", { x1: x, y1: geo.padT, x2: x, y2: bottom, stroke: gridColor, "stroke-width": "1" }));
    });
    yt.ticks.forEach(function (v, n) {
      var y = yOf(v);
      g.appendChild(svgEl("line", { x1: geo.padL, y1: y.toFixed(1), x2: right, y2: y.toFixed(1), stroke: gridColor, "stroke-width": "1" }));
      var t = svgEl("text", { x: geo.padL - 6, y: (y + FONT * 0.35).toFixed(1), "text-anchor": "end", "font-size": FONT, fill: textColor });
      t.textContent = yLabels[n];
      g.appendChild(t);
    });
    g.appendChild(svgEl("line", { x1: geo.padL, y1: bottom, x2: right, y2: bottom, stroke: "#d7e2ee", "stroke-width": "1" }));
    g.appendChild(svgEl("line", { x1: geo.padL, y1: geo.padT, x2: geo.padL, y2: bottom, stroke: "#d7e2ee", "stroke-width": "1" }));
    xt.forEach(function (tk) {
      var t = svgEl("text", { x: tk.tx.toFixed(1), y: bottom + FONT + 6, "text-anchor": "middle", "font-size": FONT, fill: textColor });
      t.textContent = tk.label;
      g.appendChild(t);
    });
  }

  function makeGeo(W, H, yLabels) {
    var maxLen = 0;
    yLabels.forEach(function (s) { if (s.length > maxLen) { maxLen = s.length; } });
    return { W: W, H: H, padL: Math.max(34, Math.ceil(maxLen * CHAR_W) + 14), padR: 14, padT: 12, padB: 28 };
  }

  /* cfg: geom() -> {width, top, bottom, padX, innerW}; count(); x(i); markers(i) -> [{y, color}]; fill(tip, i) */
  function attachHover(wrap, svg, cfg) {
    var layer = svgEl("g", { "pointer-events": "none", display: "none" });
    var guide = svgEl("line", { stroke: "#8aa3bb", "stroke-width": "1", "stroke-dasharray": "3 3" });
    var dots = [];
    var tip = htmlEl("div", "chart-tip");
    tip.style.display = "none";
    layer.appendChild(guide);
    svg.appendChild(layer);
    wrap.appendChild(tip);

    function hide() {
      layer.setAttribute("display", "none");
      tip.style.display = "none";
    }

    function show(i) {
      var geo = cfg.geom();
      var x = cfg.x(i);
      var pts = cfg.markers(i);
      guide.setAttribute("x1", x);
      guide.setAttribute("x2", x);
      guide.setAttribute("y1", geo.top);
      guide.setAttribute("y2", geo.bottom);
      while (dots.length < pts.length) {
        var c = svgEl("circle", { r: "4.5", stroke: "#ffffff", "stroke-width": "2" });
        layer.appendChild(c);
        dots.push(c);
      }
      for (var j = 0; j < dots.length; j++) {
        if (j < pts.length) {
          dots[j].setAttribute("cx", x);
          dots[j].setAttribute("cy", pts[j].y);
          dots[j].setAttribute("fill", pts[j].color);
          dots[j].setAttribute("display", "inline");
        } else {
          dots[j].setAttribute("display", "none");
        }
      }
      layer.setAttribute("display", "inline");

      tip.textContent = "";
      cfg.fill(tip, i);
      tip.style.display = "block";

      var wr = wrap.getBoundingClientRect();
      var sr = svg.getBoundingClientRect();
      var avail = wrap.clientWidth;
      var px = sr.left - (wr.left + wrap.clientLeft) + (x * sr.width) / geo.width;
      var top = sr.top - (wr.top + wrap.clientTop) + 6;
      var tw = tip.offsetWidth;
      var left = px + 14;
      if (left + tw > avail - 4) { left = px - 14 - tw; }
      left = Math.max(4, Math.min(left, avail - tw - 4));
      tip.style.left = left + "px";
      tip.style.top = top + "px";
    }

    function onPointer(e) {
      var sr = svg.getBoundingClientRect();
      var n = cfg.count();
      var geo = cfg.geom();
      if (!sr.width || n < 1) { return; }
      var vx = ((e.clientX - sr.left) * geo.width) / sr.width;
      var i = Math.round(((vx - geo.padX) / geo.innerW) * (n - 1));
      show(Math.max(0, Math.min(n - 1, i)));
    }

    svg.addEventListener("pointerdown", onPointer);
    svg.addEventListener("pointermove", onPointer);
    svg.addEventListener("pointerleave", function (e) {
      if (e.pointerType !== "touch") { hide(); }
    });
    svg.addEventListener("pointercancel", hide);
    document.addEventListener("pointerdown", function (e) {
      if (!svg.contains(e.target)) { hide(); }
    });
    return { hide: hide };
  }

  function initBenchmark(wrap, data) {
    var svg = wrap.querySelector("svg");
    var subEl = wrap.querySelector(".chart-subtitle");
    var lastEl = wrap.querySelector(".chart-last");
    var chgEl = wrap.querySelector(".chart-change");
    var stats = wrap.querySelector(".chart-stats");
    var dates = data.dates, vals = data.values, n = vals.length;
    var defaultSub = subEl.textContent;
    var st = { base: null, start: Math.max(0, n - 90), geo: null, xs: [], ys: [] };
    var hover;

    function render() {
      var W = measure(svg);
      var H = Math.max(180, Math.round((W * 220) / 720));
      var start = st.start, m = n - start, min = Infinity, max = -Infinity, i;
      for (i = start; i < n; i++) {
        if (vals[i] < min) { min = vals[i]; }
        if (vals[i] > max) { max = vals[i]; }
      }
      var span = Math.max(max - min, 1e-9);
      var yt = yTicks(min, max, Math.max(3, Math.min(5, Math.round((H - 40) / 45))), false);
      var yLabels = yt.ticks.map(function (v) { return fmtNum(v, yt.decimals); });
      var geo = makeGeo(W, H, yLabels);
      var cw = W - geo.padL - geo.padR, ch = H - geo.padT - geo.padB;
      function xOf(k) { return geo.padL + (cw * k) / (m - 1); }
      function yOf(v) { return geo.padT + ch - ((v - min) / span) * ch; }
      var xt = xTicks(dates.slice(start), xOf, W, cw);

      var g = svgEl("g", {});
      drawFrame(g, geo, yt, yLabels, xt, yOf, xOf);
      var xs = [], ys = [], pts = [];
      for (i = 0; i < m; i++) {
        xs.push(xOf(i)); ys.push(yOf(vals[start + i]));
        pts.push(xs[i].toFixed(1) + "," + ys[i].toFixed(1));
      }
      g.appendChild(svgEl("polyline", { fill: "none", stroke: data.stroke, "stroke-width": "2.5", "stroke-linejoin": "round", points: pts.join(" ") }));
      g.appendChild(svgEl("circle", { cx: xs[m - 1].toFixed(1), cy: ys[m - 1].toFixed(1), r: "4", fill: data.stroke }));
      svg.setAttribute("viewBox", "0 0 " + W + " " + H);
      swapBase(svg, st, g);
      st.geo = { width: W, top: geo.padT, bottom: H - geo.padB, padX: geo.padL, innerW: cw };
      st.xs = xs; st.ys = ys;

      var first = vals[start], last = vals[n - 1];
      var chg = first ? (last / first - 1) * 100 : 0;
      lastEl.textContent = fmtNum(last, 2);
      chgEl.textContent = fmtPct(chg);
      chgEl.style.color = pctColor(chg);
      subEl.textContent = start === 0 && n > 90
        ? "Full history, " + dates[0] + " to " + dates[n - 1] + ", " + n + " sessions"
        : defaultSub;
    }
    render();

    hover = attachHover(wrap, svg, {
      geom: function () { return st.geo; },
      count: function () { return n - st.start; },
      x: function (i) { return st.xs[i]; },
      markers: function (i) { return [{ y: st.ys[i], color: data.stroke }]; },
      fill: function (tip, i) {
        var k = st.start + i;
        tip.appendChild(htmlEl("div", "chart-tip-date", dates[k]));
        tipRow(tip, "Close", fmtNum(vals[k], 2));
        if (k > 0 && vals[k - 1]) {
          var d = (vals[k] / vals[k - 1] - 1) * 100;
          tipRow(tip, "vs prev session", fmtPct(d), pctColor(d));
        }
        if (vals[st.start]) {
          var r = (vals[k] / vals[st.start] - 1) * 100;
          tipRow(tip, "vs range start", fmtPct(r), pctColor(r));
        }
      }
    });
    watchWidth(svg, function () { render(); hover.hide(); });

    if (n > 90 && stats) {
      var group = htmlEl("div", "chart-toggle");
      group.setAttribute("role", "group");
      group.setAttribute("aria-label", "Chart range");
      var buttons = [["90 sessions", false], ["Full", true]].map(function (opt) {
        var b = htmlEl("button", "", opt[0]);
        b.type = "button";
        b.addEventListener("click", function () {
          st.start = opt[1] ? 0 : Math.max(0, n - 90);
          sync();
          render();
          hover.hide();
        });
        group.appendChild(b);
        return { el: b, full: opt[1] };
      });
      var sync = function () {
        buttons.forEach(function (b) {
          b.el.setAttribute("aria-pressed", String((st.start === 0) === b.full));
        });
      };
      sync();
      stats.appendChild(group);
    }
  }

  function initActivity(wrap, data) {
    var svg = wrap.querySelector("svg");
    var dates = data.dates, series = data.series, n = dates.length;
    var min = Infinity, max = -Infinity;
    series.forEach(function (s) {
      s.values.forEach(function (v) {
        if (v < min) { min = v; }
        if (v > max) { max = v; }
      });
    });
    var span = Math.max(max - min, 1);
    var st = { base: null, geo: null, xOf: null, yOf: null };

    function render() {
      var W = measure(svg);
      var H = Math.max(180, Math.round((W * 240) / 720));
      var yt = yTicks(min, min + span, Math.max(3, Math.min(5, Math.round((H - 40) / 45))), true);
      var yLabels = yt.ticks.map(function (v) { return fmtNum(v, 0); });
      var geo = makeGeo(W, H, yLabels);
      var cw = W - geo.padL - geo.padR, ch = H - geo.padT - geo.padB;
      function xOf(k) { return geo.padL + (cw * k) / (n - 1); }
      function yOf(v) { return geo.padT + ch - ((v - min) / span) * ch; }
      var g = svgEl("g", {});
      drawFrame(g, geo, yt, yLabels, xTicks(dates, xOf, W, cw), yOf, xOf);
      series.forEach(function (s) {
        var pts = s.values.map(function (v, k) { return xOf(k).toFixed(1) + "," + yOf(v).toFixed(1); });
        g.appendChild(svgEl("polyline", { fill: "none", stroke: s.color, "stroke-width": "2.5", "stroke-linejoin": "round", points: pts.join(" ") }));
      });
      svg.setAttribute("viewBox", "0 0 " + W + " " + H);
      swapBase(svg, st, g);
      st.geo = { width: W, top: geo.padT, bottom: H - geo.padB, padX: geo.padL, innerW: cw };
      st.xOf = xOf; st.yOf = yOf;
    }
    render();

    var hover = attachHover(wrap, svg, {
      geom: function () { return st.geo; },
      count: function () { return n; },
      x: function (i) { return st.xOf(i); },
      markers: function (i) {
        return series.map(function (s) { return { y: st.yOf(s.values[i]), color: s.color }; });
      },
      fill: function (tip, i) {
        if (dates[i]) { tip.appendChild(htmlEl("div", "chart-tip-date", dates[i])); }
        series.forEach(function (s) {
          tipRow(tip, s.label, String(Math.round(s.values[i])), null, s.color);
        });
      }
    });
    watchWidth(svg, function () { render(); hover.hide(); });
  }

  var wraps = document.querySelectorAll(".chart-wrap[data-chart]");
  Array.prototype.forEach.call(wraps, function (wrap) {
    try {
      var holder = wrap.querySelector("script.chart-data");
      var data = JSON.parse(holder.textContent);
      if (wrap.getAttribute("data-chart") === "benchmark") { initBenchmark(wrap, data); }
      else { initActivity(wrap, data); }
    } catch (err) {
      if (window.console) { console.error("chart init failed", err); }
    }
  });
})();
"""


def _svg_line_chart(series: pd.Series, title: str, stroke: str) -> str:
    full = series.dropna()
    clean = full.tail(90)
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
    chart_data = _json_for_script(
        {
            "stroke": stroke,
            "dates": pd.to_datetime(full.index).strftime("%Y-%m-%d").tolist(),
            "values": [round(float(v), 4) for v in full.tolist()],
        }
    )

    return f"""
    <div class="chart-wrap" data-chart="benchmark">
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
      <script type="application/json" class="chart-data">{chart_data}</script>
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

    if "Date" in chart_df.columns:
        date_labels = (
            pd.to_datetime(chart_df["Date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("").tolist()
        )
    else:
        date_labels = [""] * len(chart_df)
    data_series = []

    polylines = []
    legend_items = []
    for column, label, color in series_config:
        if column not in chart_df.columns:
            continue
        values = chart_df[column].fillna(0).astype(float).tolist()
        data_series.append({"label": label, "color": color, "values": values})
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

    chart_data = _json_for_script({"dates": date_labels, "series": data_series})

    return f"""
    <div class="chart-wrap" data-chart="activity">
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
      <script type="application/json" class="chart-data">{chart_data}</script>
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
    working = result.copy()
    if working.empty:
        summary_html = "<p class='empty'>No summary available.</p>"
    else:
        summary_df = (
            working.groupby("Market")[["BreakoutReady", "VCPCandidate", "Watchlist"]]
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
        summary_html = _html_table(summary_df)

    for market in MARKETS:
        if working.empty or "Market" not in working.columns:
            market_rows = working
            breakout_rows = vcp_rows = watchlist_rows = near_miss_rows = working
        else:
            market_rows = working[working["Market"] == market]
            breakout_rows = market_rows[market_rows["BreakoutReady"]].head(10)
            vcp_rows = market_rows[market_rows["VCPCandidate"]].head(10)
            watchlist_rows = market_rows[market_rows["Watchlist"]].head(10)
            near_miss_rows = market_rows[
                (market_rows["NearHigh"])
                & (~market_rows["VCPCandidate"])
            ].sort_values(["RS_Rank", "TrendTemplate"], ascending=[False, False]).head(10)
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
                    [
                        "Ticker",
                        "Close",
                        "RS_Rank",
                        "NearHigh",
                        "QuietBase",
                        "RS_6M",
                        "BreakoutReady",
                        "Breakout",
                        "Watchlist",
                        "VCPCandidate",
                        "TrendTemplate",
                    ]
                ],
                columns=["Ticker", "Close", "RS_Rank", "NearHigh", "QuietBase", "RS_6M"],
            )
        )
        vcp_html = (
            "<p class='empty'>No VCP candidates passed today.</p>"
            if vcp_rows.empty
            else _html_table(
                vcp_rows[
                    [
                        "Ticker",
                        "Close",
                        "RS_Rank",
                        "NearHigh",
                        "QuietBase",
                        "RS_6M",
                        "BreakoutReady",
                        "Breakout",
                        "Watchlist",
                        "VCPCandidate",
                        "TrendTemplate",
                    ]
                ],
                columns=["Ticker", "Close", "RS_Rank", "NearHigh", "QuietBase", "RS_6M"],
            )
        )
        watchlist_html = (
            "<p class='empty'>No watchlist names passed today.</p>"
            if watchlist_rows.empty
            else _html_table(
                watchlist_rows[
                    [
                        "Ticker",
                        "Close",
                        "RS_Rank",
                        "NearHigh",
                        "QuietBase",
                        "RS_6M",
                        "BreakoutReady",
                        "Breakout",
                        "Watchlist",
                        "VCPCandidate",
                        "TrendTemplate",
                    ]
                ],
                columns=["Ticker", "Close", "RS_Rank", "NearHigh", "QuietBase", "RS_6M"],
            )
        )
        near_miss_html = (
            "<p class='empty'>No near-miss names passed today.</p>"
            if near_miss_rows.empty
            else _html_table(
                near_miss_rows[
                    [
                        "Ticker",
                        "Close",
                        "RS_Rank",
                        "TrendTemplate",
                        "NearHigh",
                        "QuietBase",
                        "BreakoutReady",
                        "Breakout",
                        "Watchlist",
                        "VCPCandidate",
                    ]
                ],
                columns=["Ticker", "Close", "RS_Rank", "TrendTemplate", "NearHigh", "QuietBase"],
            )
        )
        chart_html = _svg_line_chart(
            benchmark_history.get(market, pd.Series(dtype=float)),
            f"{market} benchmark trend",
            chart_colors.get(market, "#1d6fa5"),
        )
        if metric_history.empty or "Market" not in metric_history.columns:
            market_history = metric_history
        else:
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
              <h3>Watchlist</h3>
              {watchlist_html}
              <h3>VCP Near Miss</h3>
              {near_miss_html}
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
        position: relative;
      }}
      .chart-wrap svg {{
        cursor: crosshair;
        touch-action: pan-y;
      }}
      .chart-toggle {{
        display: inline-flex;
        margin-top: 8px;
        border: 1px solid #e3ebf5;
        border-radius: 8px;
        overflow: hidden;
        background: #ffffff;
      }}
      .chart-toggle button {{
        border: 0;
        background: #ffffff;
        color: #1c4f7f;
        font: inherit;
        font-size: 12px;
        padding: 4px 10px;
        cursor: pointer;
      }}
      .chart-toggle button + button {{
        border-left: 1px solid #e3ebf5;
      }}
      .chart-toggle button[aria-pressed="true"] {{
        background: #0f3d66;
        color: #ffffff;
      }}
      .chart-tip {{
        position: absolute;
        z-index: 2;
        pointer-events: none;
        min-width: 130px;
        max-width: calc(100% - 8px);
        box-sizing: border-box;
        padding: 8px 10px;
        background: #ffffff;
        border: 1px solid #e3ebf5;
        border-radius: 10px;
        box-shadow: 0 6px 16px rgba(16, 35, 58, 0.16);
        font-size: 12px;
        color: #173a5d;
      }}
      .chart-tip-date {{
        font-weight: bold;
        margin-bottom: 4px;
      }}
      .chart-tip-row {{
        display: flex;
        justify-content: space-between;
        gap: 12px;
        margin-top: 2px;
      }}
      .chart-tip-label {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #4a6178;
      }}
      .chart-tip-value {{
        font-weight: bold;
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
      .scan-table tbody tr.row-breakout {{
        background: #fff3bf;
      }}
      .scan-table tbody tr.row-watchlist {{
        background: #e6fcf5;
      }}
      .scan-table tbody tr.row-vcp {{
        background: #fff4e6;
      }}
      .scan-table tbody tr.row-nearmiss {{
        background: #edf2ff;
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
      <section class="market-card">
        <h2>Scan Summary</h2>
        {summary_html}
      </section>
      {"".join(sections)}
    </div>
    <script>{CHART_JS}</script>
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
        tickers = list(market_config["tickers"])
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
    telegram_payload = build_telegram_rich_message(
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
    TELEGRAM_PAYLOAD_PATH.write_text(
        json.dumps(telegram_payload, ensure_ascii=False), encoding="utf-8"
    )
    print(report)


if __name__ == "__main__":
    main()
