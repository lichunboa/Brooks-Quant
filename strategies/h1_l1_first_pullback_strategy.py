"""H1/L1 首次回调顺势策略。"""

from __future__ import annotations

from strategies.ema20_h2_l2_trend_strategy import Ema20H2L2TrendStrategy


class H1L1FirstPullbackStrategy(Ema20H2L2TrendStrategy):
    """按 Brooks 首次回调语义实现的 H1/L1 首版。"""

    author: str = "Codex"
    long_setup_kinds: tuple[str, ...] = ("H1",)
    short_setup_kinds: tuple[str, ...] = ("L1",)
