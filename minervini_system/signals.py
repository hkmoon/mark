from __future__ import annotations

import pandas as pd

from minervini_system.config import BacktestConfig, ScanConfig
from minervini_system.indicators import add_indicators
from minervini_system.scanner import breakout_signal, trend_template_pass, vcp_candidate


def build_strategy_frame(
    df: pd.DataFrame,
    scan_config: ScanConfig,
    bt_config: BacktestConfig,
) -> pd.DataFrame:
    out = add_indicators(df)
    out["TREND_OK"] = trend_template_pass(
        out,
        min_price=scan_config.min_price,
        min_adv=scan_config.min_avg_dollar_volume,
    )
    out["VCP_CANDIDATE"] = vcp_candidate(out, scan_config)
    out["ENTRY_SIGNAL"] = (
        breakout_signal(out, scan_config) & out["TREND_OK"] & out["VCP_CANDIDATE"]
    )
    out["TRAIL_MA"] = out["Close"].rolling(bt_config.trailing_ma_window).mean()
    out["EXIT_SIGNAL"] = (out["Close"] < out["TRAIL_MA"]).fillna(False)
    return out
