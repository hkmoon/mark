from __future__ import annotations

from minervini_system.backtest import run_single_ticker_backtest, summarize_backtest
from minervini_system.config import BacktestConfig, ScanConfig
from minervini_system.data import download_ohlcv


def main() -> None:
    ticker = "NVDA"
    data_map = download_ohlcv([ticker], start="2020-01-01")
    df = data_map.get(ticker)
    if df is None or df.empty:
        raise RuntimeError(f"No OHLCV data downloaded for {ticker}")

    equity_df, trades_df = run_single_ticker_backtest(
        ticker=ticker,
        df=df,
        scan_config=ScanConfig(),
        bt_config=BacktestConfig(),
    )
    summary = summarize_backtest(equity_df, trades_df)

    print("=== Summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")

    print("\n=== Trades ===")
    if trades_df.empty:
        print("No trades")
    else:
        print(trades_df.to_string(index=False))

    equity_df.to_csv(f"{ticker}_equity.csv")
    trades_df.to_csv(f"{ticker}_trades.csv", index=False)
    print(f"\nSaved {ticker}_equity.csv and {ticker}_trades.csv")


if __name__ == "__main__":
    main()
