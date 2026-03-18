from dataclasses import dataclass


@dataclass
class ScanConfig:
    min_price: float = 10.0
    min_avg_dollar_volume: float = 5_000_000
    rs_rank_min: float = 80.0
    breakout_buffer: float = 0.001
    volume_ratio_threshold: float = 1.5
    lookback_high: int = 20
    base_lookback: int = 60
    contraction_window: int = 3
    max_contraction_ratio: float = 0.6
    near_high_ratio: float = 0.90
    tight_range_threshold: float = 0.12
    tight_close_std_threshold: float = 0.03
    quiet_volume_ratio: float = 0.70


@dataclass
class BacktestConfig:
    initial_cash: float = 100_000.0
    risk_per_trade: float = 0.01
    stop_loss_pct: float = 0.07
    max_positions: int = 5
    trailing_ma_window: int = 10
    slippage_pct: float = 0.0005
    commission_pct: float = 0.0005
