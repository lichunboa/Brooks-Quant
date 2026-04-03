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
    runner_target_price: float = 0.0
    management_mode: str = "scalp"


def build_setup_candidates(
    bars: list[BarData],
    analysis: "BrooksAnalysis",
    pricetick: float,
    *,
    mag_min_gap_bars: int = 20,
    mag_max_gap_bars: int = 45,
) -> list[SetupCandidate]:
    """统一生成 H1/H2/L1/L2/MAG 候选。"""
    from . import logic as core

    measured_move_markers = core.detect_measured_move_markers(
        bars,
        strength=2,
        ema_values=analysis.ema_values,
        structure_phase_names=analysis.structure_phase_names,
        breakout_event_names=analysis.breakout_event_names,
    )
    candidates: list[SetupCandidate] = []
    candidates.extend(
        _build_pullback_candidates(
            bars,
            analysis,
            pricetick,
            direction="bull",
            measured_move_markers=measured_move_markers,
        )
    )
    candidates.extend(
        _build_pullback_candidates(
            bars,
            analysis,
            pricetick,
            direction="bear",
            measured_move_markers=measured_move_markers,
        )
    )
    candidates.extend(
        _build_mag_candidates(
            bars,
            analysis,
            pricetick,
            min_gap_bars=mag_min_gap_bars,
            max_gap_bars=mag_max_gap_bars,
            measured_move_markers=measured_move_markers,
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
    measured_move_markers,
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
            breakout_ref = core.find_recent_breakout_reference(index, bars, analysis.breakout_event_names, direction="bull")
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
            breakout_ref = core.find_recent_breakout_reference(index, bars, analysis.breakout_event_names, direction="bear")

        breakout_point_ok = False
        breakout_signal_ok = False
        breakout_reason = ""
        if breakout_ref:
            _breakout_index, breakout_point = breakout_ref
            breakout_point_ok = core.is_near_breakout_point(index, bars, range_ma, breakout_point, direction=direction)
            breakout_signal_ok = core.is_breakout_pullback_signal_bar(
                index,
                bars,
                ema_values,
                range_ma,
                breakout_point,
                direction=direction,
            )
            if breakout_point_ok:
                breakout_reason = "突破点回测"
            elif breakout_signal_ok:
                breakout_reason = "突破后小回调延续"

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
            if breakout_ref and breakout_signal_ok:
                trend_attempt_ok = True
            if not trend_attempt_ok:
                continue

        attempts += 1
        if attempts > 2:
            pullback_active = False
            continue

        near_key_level_ok = near_ema_ok or breakout_point_ok or breakout_signal_ok
        if not near_key_level_ok:
            if attempts >= 2:
                pullback_active = False
            continue

        if quality == "弱":
            if attempts >= 2:
                pullback_active = False
            continue

        background = analysis.structure_phase_names[index] if index < len(analysis.structure_phase_names) else "未就绪"
        target_price = resolve_candidate_target(
            measured_move_markers=measured_move_markers,
            direction=direction,
            signal_index=index,
            entry_price=entry_price,
            stop_price=stop_price,
            fallback_target=target_builder(prior_swing_price, entry_price, stop_price),
        )
        runner_target_price = resolve_runner_target(
            measured_move_markers=measured_move_markers,
            direction=direction,
            signal_index=index,
            entry_price=entry_price,
            stop_price=stop_price,
            first_target_price=target_price,
        )
        management_mode = "runner" if breakout_reason or attempts >= 2 else "scalp"
        location_text = breakout_reason or reason_text
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
                reason=f"{background} + {location_text} + 第{attempts}次尝试",
                background=background,
                runner_target_price=runner_target_price,
                management_mode=management_mode,
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
    measured_move_markers,
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
                    fallback_target = core.choose_buy_target(prior_extreme, entry_price, stop_price)
                    target_price = resolve_candidate_target(
                        measured_move_markers=measured_move_markers,
                        direction="bull",
                        signal_index=index,
                        entry_price=entry_price,
                        stop_price=stop_price,
                        fallback_target=fallback_target,
                    )
                    runner_target_price = resolve_runner_target(
                        measured_move_markers=measured_move_markers,
                        direction="bull",
                        signal_index=index,
                        entry_price=entry_price,
                        stop_price=stop_price,
                        first_target_price=target_price,
                    )
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
                            runner_target_price=runner_target_price,
                            management_mode="runner",
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
                    fallback_target = core.choose_sell_target(prior_extreme, entry_price, stop_price)
                    target_price = resolve_candidate_target(
                        measured_move_markers=measured_move_markers,
                        direction="bear",
                        signal_index=index,
                        entry_price=entry_price,
                        stop_price=stop_price,
                        fallback_target=fallback_target,
                    )
                    runner_target_price = resolve_runner_target(
                        measured_move_markers=measured_move_markers,
                        direction="bear",
                        signal_index=index,
                        entry_price=entry_price,
                        stop_price=stop_price,
                        first_target_price=target_price,
                    )
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
                            runner_target_price=runner_target_price,
                            management_mode="runner",
                        )
                    )

    return candidates


def resolve_candidate_target(
    *,
    measured_move_markers,
    direction: str,
    signal_index: int,
    entry_price: float,
    stop_price: float,
    fallback_target: float,
) -> float:
    """优先复用最近有效的测量走势目标。"""
    actual_risk = max(abs(entry_price - stop_price), 1e-12)
    candidates: list[float] = []
    for marker in measured_move_markers:
        if marker.direction != direction:
            continue
        if marker.projection_start_index > signal_index:
            continue
        if signal_index - marker.projection_start_index > 12:
            continue
        if direction == "bull":
            if marker.target_price <= entry_price + actual_risk * 0.7:
                continue
        else:
            if marker.target_price >= entry_price - actual_risk * 0.7:
                continue
        candidates.append(marker.target_price)

    if not candidates:
        return fallback_target
    if direction == "bull":
        return min(candidates)
    return max(candidates)


def resolve_runner_target(
    *,
    measured_move_markers,
    direction: str,
    signal_index: int,
    entry_price: float,
    stop_price: float,
    first_target_price: float,
) -> float:
    """为趋势恢复类 setup 选择更远的 runner 目标。"""
    actual_risk = max(abs(entry_price - stop_price), 1e-12)
    runner_candidates: list[float] = []
    for marker in measured_move_markers:
        if marker.direction != direction:
            continue
        if marker.projection_start_index > signal_index:
            continue
        if signal_index - marker.projection_start_index > 16:
            continue
        if direction == "bull":
            if marker.target_price <= first_target_price + actual_risk * 0.8:
                continue
        else:
            if marker.target_price >= first_target_price - actual_risk * 0.8:
                continue
        runner_candidates.append(marker.target_price)

    if runner_candidates:
        if direction == "bull":
            return min(runner_candidates)
        return max(runner_candidates)

    if direction == "bull":
        return max(first_target_price + actual_risk * 0.8, entry_price + actual_risk * 3.0)
    return min(first_target_price - actual_risk * 0.8, entry_price - actual_risk * 3.0)
