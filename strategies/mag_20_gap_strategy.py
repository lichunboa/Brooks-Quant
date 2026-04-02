"""MAG 20/20 Setup 策略首版。"""

from __future__ import annotations

from strategies.ema20_h2_l2_trend_strategy import Ema20H2L2TrendStrategy


class Mag20GapStrategy(Ema20H2L2TrendStrategy):
    """EMA 外连续 gap bar 后回测均线的 Brooks MAG 首版。"""

    author: str = "Codex"

    min_gap_bars: int = 20
    max_gap_bars: int = 45
    long_setup_kinds: tuple[str, ...] = ("MAG多",)
    short_setup_kinds: tuple[str, ...] = ("MAG空",)

    parameters = Ema20H2L2TrendStrategy.parameters + ["min_gap_bars", "max_gap_bars"]
