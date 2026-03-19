from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from minervini_system.config import BacktestConfig, ScanConfig
from minervini_system.signals import build_strategy_frame


@dataclass
class Position:
    ticker: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: int
    stop_price: float


def run_single_ticker_backtest(
    ticker: str,
    df: pd.DataFrame,
    scan_config: ScanConfig,
    bt_config: BacktestConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = build_strategy_frame(df, scan_config, bt_config).copy()
    data = data.dropna().copy()

    cash = bt_config.initial_cash
    position: Position | None = None
    equity_curve: list[dict] = []
    trades: list[dict] = []

    for dt, row in data.iterrows():
        low_p = float(row["Low"])
        close_p = float(row["Close"])

        if position is not None:
            if low_p <= position.stop_price:
                exit_price = position.stop_price * (1 - bt_config.slippage_pct)
                proceeds = position.shares * exit_price
                fee = proceeds * bt_config.commission_pct
                cash += proceeds - fee
                pnl = (exit_price - position.entry_price) * position.shares - fee
                trades.append(
                    {
                        "Ticker": ticker,
                        "EntryDate": position.entry_date,
                        "ExitDate": dt,
                        "EntryPrice": position.entry_price,
                        "ExitPrice": exit_price,
                        "Shares": position.shares,
                        "PnL": pnl,
                        "ExitReason": "STOP",
                    }
                )
                position = None
            elif bool(row["EXIT_SIGNAL"]):
                exit_price = close_p * (1 - bt_config.slippage_pct)
                proceeds = position.shares * exit_price
                fee = proceeds * bt_config.commission_pct
                cash += proceeds - fee
                pnl = (exit_price - position.entry_price) * position.shares - fee
                trades.append(
                    {
                        "Ticker": ticker,
                        "EntryDate": position.entry_date,
                        "ExitDate": dt,
                        "EntryPrice": position.entry_price,
                        "ExitPrice": exit_price,
                        "Shares": position.shares,
                        "PnL": pnl,
                        "ExitReason": "TRAIL",
                    }
                )
                position = None

        if position is None and bool(row["ENTRY_SIGNAL"]):
            entry_price = close_p * (1 + bt_config.slippage_pct)
            stop_price = entry_price * (1 - bt_config.stop_loss_pct)

            risk_amount = cash * bt_config.risk_per_trade
            risk_per_share = max(entry_price - stop_price, 1e-9)
            shares = math.floor(risk_amount / risk_per_share)
            max_affordable_shares = math.floor(
                cash / (entry_price * (1 + bt_config.commission_pct))
            )
            shares = min(shares, max_affordable_shares)

            if shares > 0:
                cost = shares * entry_price
                fee = cost * bt_config.commission_pct
                cash -= cost + fee
                position = Position(
                    ticker=ticker,
                    entry_date=dt,
                    entry_price=entry_price,
                    shares=shares,
                    stop_price=stop_price,
                )

        market_value = 0.0 if position is None else position.shares * close_p
        equity_curve.append(
            {
                "Date": dt,
                "Cash": cash,
                "MarketValue": market_value,
                "Equity": cash + market_value,
                "InPosition": position is not None,
            }
        )

    equity_df = pd.DataFrame(equity_curve).set_index("Date")
    trades_df = pd.DataFrame(trades)
    return equity_df, trades_df


def summarize_backtest(equity_df: pd.DataFrame, trades_df: pd.DataFrame) -> dict:
    if equity_df.empty:
        return {
            "TotalReturn": 0.0,
            "MaxDrawdown": 0.0,
            "NumTrades": 0,
            "WinRate": None,
            "AvgPnL": None,
            "ProfitFactor": None,
        }

    total_return = equity_df["Equity"].iloc[-1] / equity_df["Equity"].iloc[0] - 1
    rolling_max = equity_df["Equity"].cummax()
    drawdown = equity_df["Equity"] / rolling_max - 1
    max_drawdown = drawdown.min()

    if trades_df.empty:
        return {
            "TotalReturn": float(total_return),
            "MaxDrawdown": float(max_drawdown),
            "NumTrades": 0,
            "WinRate": None,
            "AvgPnL": None,
            "ProfitFactor": None,
        }

    wins = trades_df[trades_df["PnL"] > 0]
    losses = trades_df[trades_df["PnL"] <= 0]
    gross_profit = wins["PnL"].sum() if not wins.empty else 0.0
    gross_loss = abs(losses["PnL"].sum()) if not losses.empty else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    return {
        "TotalReturn": float(total_return),
        "MaxDrawdown": float(max_drawdown),
        "NumTrades": int(len(trades_df)),
        "WinRate": float(len(wins) / len(trades_df)),
        "AvgPnL": float(trades_df["PnL"].mean()),
        "ProfitFactor": None if profit_factor is None else float(profit_factor),
    }
