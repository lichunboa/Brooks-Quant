"""Brooks 建仓信号共享模块。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vnpy.trader.object import BarData

if TYPE_CHECKING:
    from .logic import BrooksAnalysis, SignalAnnotation


@dataclass(frozen=True)
class SetupCandidate:
    """未确认触发前的建仓候选。"""

    kind: str
    quality: str
    signal_index: int
    pullback_start_index: int
    entry_price: float
    stop_price: float
    target_price: float
    ema_value: float
    reason: str
    background: str


def build_setup_candidates(
    bars: list[BarData],
    analysis: "BrooksAnalysis",
    pricetick: float,
    *,
    mag_min_gap_bars: int = 20,
    mag_max_gap_bars: int = 45,
) -> list[SetupCandidate]:
    """统一生成 H1/H2/L1/L2/MAG 候选。"""
    candidates: list[SetupCandidate] = []
    candidates.extend(_build_pullback_candidates(bars, analysis, pricetick, direction="bull"))
    candidates.extend(_build_pullback_candidates(bars, analysis, pricetick, direction="bear"))
    candidates.extend(
        _build_mag_candidates(
            bars,
            analysis,
            pricetick,
            min_gap_bars=mag_min_gap_bars,
            max_gap_bars=mag_max_gap_bars,
        )
    )
    candidates.sort(key=lambda item: (item.signal_index, item.kind))
    return candidates


def confirm_setup_candidates(
    bars: list[BarData],
    candidates: list[SetupCandidate],
) -> list["SignalAnnotation"]:
    """把候选转换成已触发的图表标注信号。"""
    from .logic import SignalAnnotation, confirm_buy_trigger, confirm_sell_trigger

    signals: list[SignalAnnotation] = []
    for candidate in candidates:
        if candidate.kind.startswith("H") or candidate.kind == "MAG多":
            trigger_index = confirm_buy_trigger(candidate.signal_index, bars, candidate.entry_price, candidate.stop_price)
        else:
            trigger_index = confirm_sell_trigger(candidate.signal_index, bars, candidate.entry_price, candidate.stop_price)

        if trigger_index < 0:
            continue

        signals.append(
            SignalAnnotation(
                kind=candidate.kind,
                quality=candidate.quality,
                signal_index=candidate.signal_index,
                trigger_index=trigger_index,
                pullback_start_index=candidate.pullback_start_index,
                entry_price=candidate.entry_price,
                stop_price=candidate.stop_price,
                target_price=candidate.target_price,
                ema_value=candidate.ema_value,
                reason=candidate.reason,
                background=candidate.background,
            )
        )

    return signals


def _build_pullback_candidates(
    bars: list[BarData],
    analysis: "BrooksAnalysis",
    pricetick: float,
    *,
    direction: str,
) -> list[SetupCandidate]:
    """生成顺势回调类候选。"""
    from . import logic as core

    candidates: list[SetupCandidate] = []
    ema_values = analysis.ema_values
    range_ma = analysis.range_ma

    pullback_active = False
    pullback_start = 0
    attempts = 0
    prior_swing_price = 0.0

    for index in range(2, len(bars)):
        bar = bars[index]
        if direction == "bull":
            context_ok = core.is_signal_context_supported(analysis, index, "bull", signal_family="pullback")
            start_ok = core.is_pullback_start_for_bull(index, bars, ema_values)
            trend_attempt_ok = core.is_first_bar_of_up_attempt(index, bars)
            near_ema_ok = core.is_near_ema_for_bull(index, bars, ema_values, range_ma)
            quality = core.evaluate_bull_signal_quality(bar)
            entry_price = bar.high_price + pricetick
            stop_price = bar.low_price - pricetick
            exhausted = bar.high_price > prior_swing_price and bar.close_price > ema_values[index]
            kind_prefix = "H"
            target_builder = core.choose_buy_target
            reason_text = "EMA20 附近回调"
        else:
            context_ok = core.is_signal_context_supported(analysis, index, "bear", signal_family="pullback")
            start_ok = core.is_pullback_start_for_bear(index, bars, ema_values)
            trend_attempt_ok = core.is_first_bar_of_down_attempt(index, bars)
            near_ema_ok = core.is_near_ema_for_bear(index, bars, ema_values, range_ma)
            quality = core.evaluate_bear_signal_quality(bar)
            entry_price = bar.low_price - pricetick
            stop_price = bar.high_price + pricetick
            exhausted = bar.low_price < prior_swing_price and bar.close_price < ema_values[index]
            kind_prefix = "L"
            target_builder = core.choose_sell_target
            reason_text = "EMA20 附近反弹"

        if not pullback_active:
            if context_ok and start_ok:
                pullback_active = True
                pullback_start = index
                attempts = 0
                history = bars[max(0, index - 20):index]
                if history:
                    prior_swing_price = (
                        max(item.high_price for item in history)
                        if direction == "bull"
                        else min(item.low_price for item in history)
                    )
            continue

        if not context_ok:
            pullback_active = False
            continue

        if index - pullback_start > 12:
            pullback_active = False
            continue

        if exhausted:
            pullback_active = False
            continue

        if not trend_attempt_ok:
            continue

        attempts += 1
        if attempts > 2:
            pullback_active = False
            continue

        if not near_ema_ok:
            if attempts >= 2:
                pullback_active = False
            continue

        if quality == "弱":
            if attempts >= 2:
                pullback_active = False
            continue

        background = analysis.structure_phase_names[index] if index < len(analysis.structure_phase_names) else "未就绪"
        target_price = target_builder(prior_swing_price, entry_price, stop_price)
        candidates.append(
            SetupCandidate(
                kind=f"{kind_prefix}{attempts}",
                quality=quality,
                signal_index=index,
                pullback_start_index=pullback_start,
                entry_price=entry_price,
                stop_price=stop_price,
                target_price=target_price,
                ema_value=ema_values[index],
                reason=f"{background} + {reason_text} + 第{attempts}次尝试",
                background=background,
            )
        )

        if attempts >= 2:
            pullback_active = False

    return candidates


def _build_mag_candidates(
    bars: list[BarData],
    analysis: "BrooksAnalysis",
    pricetick: float,
    *,
    min_gap_bars: int,
    max_gap_bars: int,
) -> list[SetupCandidate]:
    """生成 MAG 候选。"""
    from . import logic as core

    candidates: list[SetupCandidate] = []
    ema_values = analysis.ema_values

    for index in range(20, len(bars)):
        bar = bars[index]
        ema_value = ema_values[index]

        if core.is_signal_context_supported(analysis, index, "bull", signal_family="mag"):
            gap_count = core.count_consecutive_gap_bars(index, bars, ema_values, "bull")
            touched_ema = bar.low_price <= ema_value and bar.close_price >= ema_value
            if min_gap_bars <= gap_count <= max_gap_bars and touched_ema:
                quality = core.evaluate_bull_signal_quality(bar)
                if quality != "弱":
                    entry_price = bar.high_price + pricetick
                    stop_price = bar.low_price - pricetick
                    prior_extreme = max(item.high_price for item in bars[max(0, index - gap_count - 6):index])
                    target_price = core.choose_buy_target(prior_extreme, entry_price, stop_price)
                    background = analysis.structure_phase_names[index]
                    candidates.append(
                        SetupCandidate(
                            kind="MAG多",
                            quality=quality,
                            signal_index=index,
                            pullback_start_index=max(0, index - gap_count),
                            entry_price=entry_price,
                            stop_price=stop_price,
                            target_price=target_price,
                            ema_value=ema_value,
                            reason=f"{background} + {gap_count}根 EMA 缺口后的首次回测",
                            background=background,
                        )
                    )

        if core.is_signal_context_supported(analysis, index, "bear", signal_family="mag"):
            gap_count = core.count_consecutive_gap_bars(index, bars, ema_values, "bear")
            touched_ema = bar.high_price >= ema_value and bar.close_price <= ema_value
            if min_gap_bars <= gap_count <= max_gap_bars and touched_ema:
                quality = core.evaluate_bear_signal_quality(bar)
                if quality != "弱":
                    entry_price = bar.low_price - pricetick
                    stop_price = bar.high_price + pricetick
                    prior_extreme = min(item.low_price for item in bars[max(0, index - gap_count - 6):index])
                    target_price = core.choose_sell_target(prior_extreme, entry_price, stop_price)
                    background = analysis.structure_phase_names[index]
                    candidates.append(
                        SetupCandidate(
                            kind="MAG空",
                            quality=quality,
                            signal_index=index,
                            pullback_start_index=max(0, index - gap_count),
                            entry_price=entry_price,
                            stop_price=stop_price,
                            target_price=target_price,
                            ema_value=ema_value,
                            reason=f"{background} + {gap_count}根 EMA 缺口后的首次回测",
                            background=background,
                        )
                    )

    return candidates
