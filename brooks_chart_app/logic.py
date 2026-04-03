"""
Brooks 图表标注逻辑。

说明：
这里实现的是程序化近似版，用来辅助图表核对，不是对 Brooks 全部细节的机械复刻。
"""

from __future__ import annotations

from dataclasses import dataclass

from vnpy.trader.object import BarData


@dataclass
class SignalAnnotation:
    """单个信号的图表标注结果。"""

    kind: str
    quality: str
    signal_index: int
    trigger_index: int
    pullback_start_index: int
    entry_price: float
    stop_price: float
    target_price: float
    ema_value: float
    reason: str
    background: str


@dataclass
class BackgroundPhase:
    """单个背景片段。"""

    name: str
    start_index: int
    end_index: int
    direction: str


@dataclass
class BreakoutEventContext:
    """突破事件上下文。"""

    direction: str
    start_index: int
    setup_level: float
    avg_range: float
    followthrough_seen: bool = False
    test_seen: bool = False


@dataclass
class StructureContext:
    """结构层的多窗口上下文。"""

    short_metrics: dict[str, float | int | str]
    long_metrics: dict[str, float | int | str]
    direction: str
    swing_point_count: int
    leg_count: int
    directional_swing_score: float
    counter_swing_score: float
    trendline_alignment: float
    ema_touch_ratio: float
    magnet_confluence_score: float
    magnet_reaction_score: float
    trend_touch_score: float
    channel_touch_score: float
    breach_ratio: float
    channel_span_ratio: float
    geometry_quality_score: float


@dataclass
class ChannelGeometry:
    """趋势线和通道线的近似几何信息。"""

    trend_anchor1: tuple[int, float] | None
    trend_anchor2: tuple[int, float] | None
    opposite_anchor: tuple[int, float] | None
    trend_touch_score: float
    channel_touch_score: float
    breach_ratio: float
    anchor_span_bars: int
    quality_score: float


@dataclass
class PatternMarker:
    """ii / ioi / oo 等局部形态标记。"""

    label: str
    start_index: int
    end_index: int
    anchor_index: int


@dataclass
class MicroGapMarker:
    """微缺口标记。"""

    direction: str
    center_index: int
    left_index: int
    right_index: int
    top_price: float
    bottom_price: float


@dataclass
class OpeningRangeMarker:
    """开盘区间与 ORBO 标记。"""

    start_index: int
    first_bar_high: float
    first_bar_low: float
    opening_end_index: int
    high_price: float
    low_price: float
    bom_index: int | None
    bar18_index: int | None
    breakout_index: int | None
    breakout_direction: str = ""


@dataclass
class MeasuredMoveMarker:
    """AB=CD / Leg1=Leg2 测量走势标记。"""

    direction: str
    leg_start_index: int
    leg_start_price: float
    leg_end_index: int
    leg_end_price: float
    projection_start_index: int
    end_index: int
    target_price: float
    label: str
    category: str = ""


@dataclass
class BrooksAnalysis:
    """统一缓存图表与策略共用的 Brooks 上下文。"""

    ema_values: list[float]
    range_ma: list[float]
    structure_contexts: list[StructureContext | None]
    structure_phase_names: list[str]
    breakout_event_names: list[str]
    direction_names: list[str]
    higher_structure_phase_names: list[str]
    higher_direction_names: list[str]


def build_brooks_annotations(
    bars: list[BarData],
    pricetick: float,
) -> tuple[
    list[float],
    list[SignalAnnotation],
    str,
    list[str],
    list[BackgroundPhase],
    list[str],
    list[BackgroundPhase],
]:
    """生成 EMA20、H1/H2/L1/L2、双层背景标签和细化背景片段。"""
    if not bars:
        return [], [], "无数据", [], [], [], []

    analysis = analyze_brooks_context(bars)
    from .setup_engine import build_setup_candidates, confirm_setup_candidates

    candidates = build_setup_candidates(bars, analysis, pricetick)
    signals = confirm_setup_candidates(bars, candidates)
    signals.sort(key=lambda item: (item.signal_index, item.kind))

    breakout_event_names = analysis.breakout_event_names
    structure_phase_names = analysis.structure_phase_names
    breakout_event_phases = compress_background_phases(breakout_event_names, analysis.direction_names)
    structure_phases = compress_background_phases(structure_phase_names, analysis.direction_names)
    background_label = build_background_summary(
        structure_phase_names,
        breakout_event_names,
        analysis.direction_names,
    )
    enrich_signal_backgrounds(signals, structure_phase_names, breakout_event_names)
    return (
        analysis.ema_values,
        signals,
        background_label,
        structure_phase_names,
        structure_phases,
        breakout_event_names,
        breakout_event_phases,
    )


def analyze_brooks_context(
    bars: list[BarData],
    *,
    enable_higher_timeframe_filter: bool = True,
) -> BrooksAnalysis:
    """构建图表与策略共用的多层上下文。"""
    if not bars:
        return BrooksAnalysis([], [], [], [], [], [], [], [])

    ema_values = calculate_ema([bar.close_price for bar in bars], 20)
    range_ma = calculate_range_ma(bars, 20)
    structure_contexts = build_structure_context_series(bars, ema_values, range_ma)

    higher_structure_phase_names = ["未就绪"] * len(bars)
    higher_direction_names = ["中性"] * len(bars)
    if enable_higher_timeframe_filter:
        higher_structure_phase_names, higher_direction_names = build_higher_timeframe_context_map(bars)

    breakout_event_names = build_breakout_event_names(
        bars,
        ema_values,
        range_ma,
        structure_contexts=structure_contexts,
        higher_structure_phase_names=higher_structure_phase_names,
        higher_direction_names=higher_direction_names,
    )
    structure_phase_names = build_structure_phase_names(
        bars,
        ema_values,
        range_ma,
        breakout_event_names,
        structure_contexts=structure_contexts,
    )
    direction_names = build_background_direction_names(structure_phase_names, structure_contexts)
    return BrooksAnalysis(
        ema_values=ema_values,
        range_ma=range_ma,
        structure_contexts=structure_contexts,
        structure_phase_names=structure_phase_names,
        breakout_event_names=breakout_event_names,
        direction_names=direction_names,
        higher_structure_phase_names=higher_structure_phase_names,
        higher_direction_names=higher_direction_names,
    )


def calculate_ema(values: list[float], period: int) -> list[float]:
    """按 Brooks 常用口径计算 20 bar EMA。"""
    if not values:
        return []
    if period <= 1:
        return list(values)

    alpha: float = 2 / (period + 1)
    if len(values) < period:
        running_sum: float = 0.0
        warmup_values: list[float] = []
        for index, value in enumerate(values, start=1):
            running_sum += value
            warmup_values.append(running_sum / index)
        return warmup_values

    warmup_values: list[float] = []
    running_sum = 0.0
    for index in range(period - 1):
        running_sum += values[index]
        warmup_values.append(running_sum / (index + 1))

    seed: float = sum(values[:period]) / period
    ema_values: list[float] = warmup_values + [seed]
    ema_value: float = seed

    for value in values[period:]:
        ema_value = alpha * value + (1 - alpha) * ema_value
        ema_values.append(ema_value)

    return ema_values


def calculate_range_ma(bars: list[BarData], period: int) -> list[float]:
    """计算平均波动范围。"""
    ranges: list[float] = [max(bar.high_price - bar.low_price, 0.0) for bar in bars]
    outputs: list[float] = []

    for i in range(len(ranges)):
        start: int = max(0, i - period + 1)
        window: list[float] = ranges[start:i + 1]
        avg_range: float = sum(window) / len(window)
        outputs.append(max(avg_range, 1e-12))

    return outputs


def build_structure_context_series(
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
) -> list[StructureContext | None]:
    """为每根 K 线预计算结构上下文。"""
    contexts: list[StructureContext | None] = []
    for index in range(len(bars)):
        if index < 20:
            contexts.append(None)
            continue
        contexts.append(calculate_structure_context(index, bars, ema_values, range_ma))
    return contexts


def find_long_signals(
    bars: list[BarData],
    analysis: BrooksAnalysis,
    pricetick: float,
) -> list[SignalAnnotation]:
    """寻找 EMA20 附近的 H1/H2 顺势多。"""
    from .setup_engine import build_setup_candidates, confirm_setup_candidates

    candidates = [item for item in build_setup_candidates(bars, analysis, pricetick) if item.kind in {"H1", "H2"}]
    return confirm_setup_candidates(bars, candidates)


def find_short_signals(
    bars: list[BarData],
    analysis: BrooksAnalysis,
    pricetick: float,
) -> list[SignalAnnotation]:
    """寻找 EMA20 附近的 L1/L2 顺势空。"""
    from .setup_engine import build_setup_candidates, confirm_setup_candidates

    candidates = [item for item in build_setup_candidates(bars, analysis, pricetick) if item.kind in {"L1", "L2"}]
    return confirm_setup_candidates(bars, candidates)


def find_mag_signals(
    bars: list[BarData],
    analysis: BrooksAnalysis,
    pricetick: float,
    min_gap_bars: int = 20,
    max_gap_bars: int = 45,
) -> list[SignalAnnotation]:
    """识别 20 均线缺口 / 第一均线缺口语境下的 MAG 信号。"""
    from .setup_engine import build_setup_candidates, confirm_setup_candidates

    candidates = [
        item
        for item in build_setup_candidates(
            bars,
            analysis,
            pricetick,
            mag_min_gap_bars=min_gap_bars,
            mag_max_gap_bars=max_gap_bars,
        )
        if item.kind in {"MAG多", "MAG空"}
    ]
    return confirm_setup_candidates(bars, candidates)


def build_background_summary(
    structure_phase_names: list[str],
    breakout_event_names: list[str],
    direction_names: list[str],
) -> str:
    """构建图表顶部展示用的背景摘要。"""
    structure_name = structure_phase_names[-1] if structure_phase_names else "未就绪"
    if structure_name == "未就绪":
        structure_name = "震荡"

    event_name = breakout_event_names[-1] if breakout_event_names else "无事件"
    if event_name == "未就绪":
        event_name = "无事件"

    direction = direction_names[-1] if direction_names else "中性"
    event_text = "无" if event_name == "无事件" else event_name
    return f"结构: {structure_name}（{direction}） | 事件: {event_text}"


def enrich_signal_backgrounds(
    signals: list[SignalAnnotation],
    structure_phase_names: list[str],
    breakout_event_names: list[str],
) -> None:
    """把双层背景信息写回信号说明。"""
    for signal in signals:
        if signal.signal_index >= len(structure_phase_names):
            continue
        structure_name = structure_phase_names[signal.signal_index]
        event_name = breakout_event_names[signal.signal_index] if signal.signal_index < len(breakout_event_names) else "无事件"
        if event_name and event_name not in {"无事件", "未就绪"}:
            signal.background = f"{structure_name} | {event_name}"
        else:
            signal.background = structure_name


def build_structure_phase_names(
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
    breakout_event_names: list[str],
    structure_contexts: list[StructureContext | None] | None = None,
) -> list[str]:
    """按市场循环状态机构建底层结构背景。"""
    phase_names: list[str] = []
    current_state: str = "震荡"
    state_direction: str = "中性"
    last_breakout_index: int = -100
    pending_state: str = ""
    pending_count: int = 0

    for index in range(len(bars)):
        if index < 20:
            phase_names.append("未就绪")
            continue

        context = (
            structure_contexts[index]
            if structure_contexts is not None and index < len(structure_contexts)
            else calculate_structure_context(index, bars, ema_values, range_ma)
        )
        if context is None:
            phase_names.append("未就绪")
            continue
        short_metrics = context.short_metrics
        long_metrics = context.long_metrics
        raw_state = infer_raw_structure_phase_from_context(context)
        event_name = breakout_event_names[index] if index < len(breakout_event_names) else "无事件"
        inferred_direction = infer_context_direction(context)
        bars_since_breakout = index - last_breakout_index
        short_progress_ratio = float(short_metrics["progress_ratio"])
        short_pullback_depth_ratio = float(short_metrics["pullback_depth_ratio"])
        long_progress_ratio = float(long_metrics["progress_ratio"])
        long_reversal_count = int(long_metrics["reversal_count"])

        proposed_state = current_state

        if current_state == "震荡":
            if event_name in {"突破起爆", "突破跟进"}:
                proposed_state = "窄幅通道"
                last_breakout_index = index
            elif raw_state == "宽幅通道":
                proposed_state = "宽幅通道"
            elif raw_state == "趋势交易区间":
                proposed_state = "趋势交易区间"
        elif current_state == "窄幅通道":
            if event_name == "失败突破":
                if raw_state == "宽幅通道":
                    proposed_state = "宽幅通道"
                elif raw_state == "趋势交易区间" or short_pullback_depth_ratio >= 1.0:
                    proposed_state = "趋势交易区间"
                elif short_progress_ratio < 0.24:
                    proposed_state = "震荡"
            elif event_name in {"突破起爆", "突破跟进"}:
                proposed_state = "窄幅通道"
                last_breakout_index = index
            elif bars_since_breakout <= 2 and raw_state in {"趋势交易区间", "震荡"}:
                proposed_state = "窄幅通道"
            elif raw_state == "宽幅通道":
                proposed_state = "宽幅通道"
            elif raw_state == "趋势交易区间":
                proposed_state = "趋势交易区间"
            elif raw_state == "震荡":
                if short_pullback_depth_ratio >= 1.15 and long_progress_ratio >= 0.18:
                    proposed_state = "趋势交易区间"
                elif short_pullback_depth_ratio >= 1.15 and short_progress_ratio >= 0.28:
                    proposed_state = "宽幅通道"
                elif bars_since_breakout > 6 and short_progress_ratio < 0.22 and long_progress_ratio < 0.12:
                    proposed_state = "震荡"
        elif current_state == "宽幅通道":
            if event_name in {"突破起爆", "突破跟进"} and raw_state == "窄幅通道":
                proposed_state = "窄幅通道"
                last_breakout_index = index
            elif raw_state == "趋势交易区间":
                proposed_state = "趋势交易区间"
            elif raw_state == "震荡" and not is_trending_trading_range_phase_from_context(context):
                proposed_state = "震荡"
        else:
            if event_name in {"突破起爆", "突破跟进"} and raw_state == "窄幅通道":
                proposed_state = "窄幅通道"
                last_breakout_index = index
            elif raw_state == "宽幅通道":
                proposed_state = "宽幅通道"
            elif raw_state == "震荡" and long_progress_ratio < 0.10 and long_reversal_count >= 4:
                proposed_state = "震荡"
            elif raw_state == "趋势交易区间":
                proposed_state = "趋势交易区间"

        confirmation_bars = required_structure_confirmation(
            current_state,
            proposed_state,
            event_name,
            context,
        )

        if proposed_state == current_state:
            pending_state = ""
            pending_count = 0
        else:
            if pending_state == proposed_state:
                pending_count += 1
            else:
                pending_state = proposed_state
                pending_count = 1

            if pending_count >= confirmation_bars:
                current_state = proposed_state
                pending_state = ""
                pending_count = 0

        if current_state in {"震荡", "趋势交易区间"}:
            state_direction = "中性"
        elif inferred_direction != "中性":
            state_direction = inferred_direction

        phase_names.append(current_state)
    return phase_names


def build_breakout_event_names(
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
    structure_contexts: list[StructureContext | None] | None = None,
    higher_structure_phase_names: list[str] | None = None,
    higher_direction_names: list[str] | None = None,
) -> list[str]:
    """构建突破事件层。"""
    event_names: list[str] = []
    active_event: BreakoutEventContext | None = None
    session_bar_counts = build_session_bar_counts(bars)
    bar_minutes = infer_bar_minutes(bars)

    for index in range(len(bars)):
        if index < 20:
            if is_opening_reversal_event(index, bars, ema_values, range_ma, session_bar_counts, bar_minutes):
                event_names.append("开盘反转")
            else:
                event_names.append("未就绪")
            continue

        if active_event:
            event_name, keep_active = classify_breakout_event(index, active_event, bars, ema_values, range_ma)
            if event_name:
                event_names.append(event_name)
                if not keep_active:
                    active_event = None
                continue
            active_event = None

        breakout_direction = detect_breakout_start_direction(
            index,
            bars,
            ema_values,
            range_ma,
            structure_contexts=structure_contexts,
            higher_structure_phase_names=higher_structure_phase_names,
            higher_direction_names=higher_direction_names,
        )
        if breakout_direction:
            active_event = create_breakout_event_context(index, breakout_direction, bars, range_ma)
            event_names.append("突破起爆")
        else:
            if is_opening_reversal_event(index, bars, ema_values, range_ma, session_bar_counts, bar_minutes):
                event_names.append("开盘反转")
            elif is_midday_reversal_event(index, bars, ema_values, range_ma, session_bar_counts, bar_minutes):
                event_names.append("午间反转")
            else:
                event_names.append("无事件")

    return event_names


def compress_background_phases(
    phase_names: list[str],
    direction_names: list[str],
) -> list[BackgroundPhase]:
    """把逐 bar 背景压缩成片段。"""
    if not phase_names:
        return []

    phases: list[BackgroundPhase] = []
    start_index = 0
    current_name = phase_names[0]

    for index in range(1, len(phase_names)):
        if phase_names[index] == current_name:
            continue

        direction = direction_names[max(start_index, index - 1)] if direction_names else "中性"
        phases.append(BackgroundPhase(current_name, start_index, index - 1, direction))
        start_index = index
        current_name = phase_names[index]

    direction = direction_names[len(phase_names) - 1] if direction_names else "中性"
    phases.append(BackgroundPhase(current_name, start_index, len(phase_names) - 1, direction))
    return phases


def detect_bar_patterns(bars: list[BarData]) -> list[PatternMarker]:
    """识别 ii、ioi、oo 这类常见压缩形态。"""
    markers: list[PatternMarker] = []
    for index in range(2, len(bars)):
        current = bars[index]
        prev = bars[index - 1]
        prior = bars[index - 2]

        if is_inside_bar(prev, prior) and is_inside_bar(current, prev):
            markers.append(PatternMarker("ii", index - 2, index, index))
            continue

        if is_outside_bar(prev, prior) and is_inside_bar(current, prev):
            markers.append(PatternMarker("ioi", index - 2, index, index))
            continue

        if is_outside_bar(prev, prior) and is_outside_bar(current, prev):
            markers.append(PatternMarker("oo", index - 2, index, index))

    return markers


def detect_micro_gaps(bars: list[BarData]) -> list[MicroGapMarker]:
    """按 Brooks 的前后不重叠口径识别微缺口。"""
    markers: list[MicroGapMarker] = []
    for index in range(1, len(bars) - 1):
        prev_bar = bars[index - 1]
        bar = bars[index]
        next_bar = bars[index + 1]

        if is_bull_trend_bar(bar) and next_bar.low_price > prev_bar.high_price:
            markers.append(
                MicroGapMarker(
                    direction="bull",
                    center_index=index,
                    left_index=index - 1,
                    right_index=index + 1,
                    top_price=next_bar.low_price,
                    bottom_price=prev_bar.high_price,
                )
            )
            continue

        if is_bear_trend_bar(bar) and next_bar.high_price < prev_bar.low_price:
            markers.append(
                MicroGapMarker(
                    direction="bear",
                    center_index=index,
                    left_index=index - 1,
                    right_index=index + 1,
                    top_price=prev_bar.low_price,
                    bottom_price=next_bar.high_price,
                )
            )

    return markers


def build_opening_range_markers(
    bars: list[BarData],
    *,
    opening_bar_count: int = 18,
) -> list[OpeningRangeMarker]:
    """按自然日生成开盘区间、Bar 18 与首个 ORBO。"""
    if opening_bar_count <= 0:
        return []

    markers: list[OpeningRangeMarker] = []
    start_index = 0
    while start_index < len(bars):
        session_date = bars[start_index].datetime.date()
        end_index = start_index
        while end_index + 1 < len(bars) and bars[end_index + 1].datetime.date() == session_date:
            end_index += 1

        opening_end_index = min(start_index + opening_bar_count - 1, end_index)
        opening_slice = bars[start_index:opening_end_index + 1]
        if opening_slice:
            first_bar = opening_slice[0]
            opening_high = max(bar.high_price for bar in opening_slice)
            opening_low = min(bar.low_price for bar in opening_slice)
            bar18_index = opening_end_index if len(opening_slice) >= opening_bar_count else None
            high_break_index: int | None = None
            low_break_index: int | None = None
            bom_index: int | None = None
            for cursor in range(start_index + 1, opening_end_index + 1):
                bar = bars[cursor]
                if high_break_index is None and bar.high_price > first_bar.high_price:
                    high_break_index = cursor
                if low_break_index is None and bar.low_price < first_bar.low_price:
                    low_break_index = cursor
                if high_break_index is not None and low_break_index is not None:
                    bom_index = cursor
                    break

            breakout_index: int | None = None
            breakout_direction: str = ""
            search_start = opening_end_index + 1 if bar18_index is not None else end_index + 1
            for cursor in range(search_start, end_index + 1):
                bar = bars[cursor]
                if bar.close_price > opening_high:
                    breakout_index = cursor
                    breakout_direction = "bull"
                    break
                if bar.close_price < opening_low:
                    breakout_index = cursor
                    breakout_direction = "bear"
                    break

            markers.append(
                OpeningRangeMarker(
                    start_index=start_index,
                    first_bar_high=first_bar.high_price,
                    first_bar_low=first_bar.low_price,
                    opening_end_index=opening_end_index,
                    high_price=opening_high,
                    low_price=opening_low,
                    bom_index=bom_index,
                    bar18_index=bar18_index,
                    breakout_index=breakout_index,
                    breakout_direction=breakout_direction,
                )
            )

        start_index = end_index + 1

    return markers


def detect_measured_move_markers(
    bars: list[BarData],
    *,
    strength: int = 2,
    ema_values: list[float] | None = None,
    structure_phase_names: list[str] | None = None,
    breakout_event_names: list[str] | None = None,
) -> list[MeasuredMoveMarker]:
    """识别 Brooks 常见的几类测量走势。"""
    avg_range = max(sum(max(bar.high_price - bar.low_price, 0.0) for bar in bars) / max(len(bars), 1), 1e-6)
    if ema_values is None:
        ema_values = calculate_ema([bar.close_price for bar in bars], 20)
    markers: list[MeasuredMoveMarker] = []
    markers.extend(
        _detect_leg_equal_leg_markers(
            bars,
            strength=strength,
            avg_range=avg_range,
            ema_values=ema_values,
            structure_phase_names=structure_phase_names,
        )
    )
    markers.extend(
        _detect_tr_height_measured_move_markers(
            bars,
            avg_range=avg_range,
            structure_phase_names=structure_phase_names,
            breakout_event_names=breakout_event_names,
        )
    )
    markers.extend(_detect_breakout_body_measured_move_markers(bars, avg_range=avg_range))
    markers.extend(
        _detect_measuring_gap_measured_move_markers(
            bars,
            avg_range=avg_range,
            ema_values=ema_values,
            structure_phase_names=structure_phase_names,
            breakout_event_names=breakout_event_names,
        )
    )

    markers.sort(key=lambda item: (item.projection_start_index, item.label, item.direction))
    deduped: list[MeasuredMoveMarker] = []
    for marker in markers:
        if (
            deduped
            and marker.label == deduped[-1].label
            and marker.direction == deduped[-1].direction
            and abs(marker.target_price - deduped[-1].target_price) <= avg_range * (
                0.55 if marker.label.startswith("Leg1=Leg2") else 0.45 if marker.label.startswith("TR MM") else 0.2
            )
            and abs(marker.projection_start_index - deduped[-1].projection_start_index) <= (
                3 if marker.label.startswith("Leg1=Leg2") else 4 if marker.label.startswith("TR MM") else 1
            )
        ):
            deduped[-1] = marker
            continue
        deduped.append(marker)
    return deduped


def _detect_leg_equal_leg_markers(
    bars: list[BarData],
    *,
    strength: int,
    avg_range: float,
    ema_values: list[float],
    structure_phase_names: list[str] | None,
) -> list[MeasuredMoveMarker]:
    """识别 Leg1=Leg2 / AB=CD。"""
    swings = find_pivot_swings(bars, strength)
    if len(swings) < 3:
        return []

    markers: list[MeasuredMoveMarker] = []
    for index in range(2, len(swings)):
        left = swings[index - 2]
        middle = swings[index - 1]
        right = swings[index]
        phase_name = structure_phase_names[right[0]] if structure_phase_names and right[0] < len(structure_phase_names) else ""
        ema_value = ema_values[right[0]] if right[0] < len(ema_values) else bars[right[0]].close_price

        if left[1] == "L" and middle[1] == "H" and right[1] == "L":
            leg_size = middle[2] - left[2]
            leg_bar_count = middle[0] - left[0] + 1
            pullback_bar_count = right[0] - middle[0]
            if leg_size < avg_range * 2.4 or leg_bar_count < 4 or pullback_bar_count < 2:
                continue
            pullback_size = middle[2] - right[2]
            pullback_ratio = pullback_size / max(leg_size, 1e-6)
            near_ema = abs(bars[right[0]].close_price - ema_value) <= avg_range * 0.9
            leg_context = evaluate_leg_equal_context(
                bars=bars,
                left=left,
                middle=middle,
                right=right,
                phase_name=phase_name,
                pullback_ratio=pullback_ratio,
                near_ema=near_ema,
                direction="bull",
                leg_size=leg_size,
            )
            if not leg_context:
                continue
            target_price = right[2] + leg_size
            end_index = resolve_measured_move_end_index(
                bars,
                start_index=right[0],
                direction="bull",
                target_price=target_price,
                invalidation_price=right[2],
                avg_range=avg_range,
                max_bars=max(10, (middle[0] - left[0]) * 3),
            )
            markers.append(
                MeasuredMoveMarker(
                    direction="bull",
                    leg_start_index=left[0],
                    leg_start_price=left[2],
                    leg_end_index=middle[0],
                    leg_end_price=middle[2],
                    projection_start_index=right[0],
                    end_index=end_index,
                    target_price=target_price,
                    label="Leg1=Leg2↑",
                    category=leg_context,
                )
            )
            continue

        if left[1] == "H" and middle[1] == "L" and right[1] == "H":
            leg_size = left[2] - middle[2]
            leg_bar_count = middle[0] - left[0] + 1
            pullback_bar_count = right[0] - middle[0]
            if leg_size < avg_range * 2.4 or leg_bar_count < 4 or pullback_bar_count < 2:
                continue
            pullback_size = right[2] - middle[2]
            pullback_ratio = pullback_size / max(leg_size, 1e-6)
            near_ema = abs(bars[right[0]].close_price - ema_value) <= avg_range * 0.9
            leg_context = evaluate_leg_equal_context(
                bars=bars,
                left=left,
                middle=middle,
                right=right,
                phase_name=phase_name,
                pullback_ratio=pullback_ratio,
                near_ema=near_ema,
                direction="bear",
                leg_size=leg_size,
            )
            if not leg_context:
                continue
            target_price = right[2] - leg_size
            end_index = resolve_measured_move_end_index(
                bars,
                start_index=right[0],
                direction="bear",
                target_price=target_price,
                invalidation_price=right[2],
                avg_range=avg_range,
                max_bars=max(10, (middle[0] - left[0]) * 3),
            )
            markers.append(
                MeasuredMoveMarker(
                    direction="bear",
                    leg_start_index=left[0],
                    leg_start_price=left[2],
                    leg_end_index=middle[0],
                    leg_end_price=middle[2],
                    projection_start_index=right[0],
                    end_index=end_index,
                    target_price=target_price,
                    label="Leg1=Leg2↓",
                    category=leg_context,
                )
            )

    return markers


def _detect_tr_height_measured_move_markers(
    bars: list[BarData],
    *,
    avg_range: float,
    structure_phase_names: list[str] | None,
    breakout_event_names: list[str] | None,
) -> list[MeasuredMoveMarker]:
    """识别基于交易区间高度的测量走势。"""
    if len(bars) < 10:
        return []

    markers: list[MeasuredMoveMarker] = []
    for index in range(8, len(bars)):
        window = bars[index - 8:index]
        range_high = max(bar.high_price for bar in window)
        range_low = min(bar.low_price for bar in window)
        range_height = range_high - range_low
        if range_height < avg_range * 1.35:
            continue

        phase_name = structure_phase_names[index] if structure_phase_names and index < len(structure_phase_names) else ""
        if phase_name in {"", "未就绪", "宽幅通道"}:
            continue

        if structure_phase_names:
            phase_window = structure_phase_names[index - 8:index]
            range_like_count = sum(1 for name in phase_window if name in {"震荡", "趋势交易区间"})
            if range_like_count < max(5, len(phase_window) - 3):
                continue

        overlap_count = 0
        for left_bar, right_bar in zip(window[:-1], window[1:]):
            overlap = min(left_bar.high_price, right_bar.high_price) - max(left_bar.low_price, right_bar.low_price)
            if overlap > 0:
                overlap_count += 1
        if count_breakout_mode_reversals(window) < 3 or overlap_count < max(5, len(window) - 3):
            continue

        if breakout_event_names:
            recent_events = breakout_event_names[max(0, index - 2):index + 1]
            if not any(name in {"突破起爆", "突破跟进"} for name in recent_events):
                continue

        bar = bars[index]
        body_height = get_bar_body(bar)
        if (
            is_bull_trend_bar(bar)
            and body_height >= avg_range * 0.65
            and bar.close_price > range_high + avg_range * 0.12
        ):
            target_price = range_high + range_height
            end_index = resolve_measured_move_end_index(
                bars,
                start_index=index,
                direction="bull",
                target_price=target_price,
                invalidation_price=range_low,
                avg_range=avg_range,
                max_bars=18,
            )
            markers.append(
                MeasuredMoveMarker(
                    direction="bull",
                    leg_start_index=index - 1,
                    leg_start_price=range_low,
                    leg_end_index=index - 1,
                    leg_end_price=range_high,
                    projection_start_index=index,
                    end_index=end_index,
                    target_price=target_price,
                    label="TR MM↑",
                    category="交易区间高度",
                )
            )
            continue

        if (
            is_bear_trend_bar(bar)
            and body_height >= avg_range * 0.65
            and bar.close_price < range_low - avg_range * 0.12
        ):
            target_price = range_low - range_height
            end_index = resolve_measured_move_end_index(
                bars,
                start_index=index,
                direction="bear",
                target_price=target_price,
                invalidation_price=range_high,
                avg_range=avg_range,
                max_bars=18,
            )
            markers.append(
                MeasuredMoveMarker(
                    direction="bear",
                    leg_start_index=index - 1,
                    leg_start_price=range_high,
                    leg_end_index=index - 1,
                    leg_end_price=range_low,
                    projection_start_index=index,
                    end_index=end_index,
                    target_price=target_price,
                    label="TR MM↓",
                    category="交易区间高度",
                )
            )

    return markers


def _detect_breakout_body_measured_move_markers(
    bars: list[BarData],
    *,
    avg_range: float,
) -> list[MeasuredMoveMarker]:
    """识别基于突破实体高度的测量走势。"""
    if len(bars) < 6:
        return []

    markers: list[MeasuredMoveMarker] = []
    for index in range(5, len(bars)):
        bar = bars[index]
        body_height = abs(bar.close_price - bar.open_price)
        if body_height < avg_range * 0.9:
            continue

        prior_window = bars[index - 5:index]
        prior_high = max(item.high_price for item in prior_window)
        prior_low = min(item.low_price for item in prior_window)

        if is_bull_trend_bar(bar) and bar.close_price > prior_high + avg_range * 0.05:
            target_price = bar.close_price + body_height
            end_index = resolve_measured_move_end_index(
                bars,
                start_index=index,
                direction="bull",
                target_price=target_price,
                invalidation_price=bar.low_price,
                avg_range=avg_range,
                max_bars=10,
            )
            markers.append(
                MeasuredMoveMarker(
                    direction="bull",
                    leg_start_index=index,
                    leg_start_price=min(bar.open_price, bar.close_price),
                    leg_end_index=index,
                    leg_end_price=max(bar.open_price, bar.close_price),
                    projection_start_index=index,
                    end_index=end_index,
                    target_price=target_price,
                    label="BO MM↑",
                    category="突破高度",
                )
            )
            continue

        if is_bear_trend_bar(bar) and bar.close_price < prior_low - avg_range * 0.05:
            target_price = bar.close_price - body_height
            end_index = resolve_measured_move_end_index(
                bars,
                start_index=index,
                direction="bear",
                target_price=target_price,
                invalidation_price=bar.high_price,
                avg_range=avg_range,
                max_bars=10,
            )
            markers.append(
                MeasuredMoveMarker(
                    direction="bear",
                    leg_start_index=index,
                    leg_start_price=max(bar.open_price, bar.close_price),
                    leg_end_index=index,
                    leg_end_price=min(bar.open_price, bar.close_price),
                    projection_start_index=index,
                    end_index=end_index,
                    target_price=target_price,
                    label="BO MM↓",
                    category="突破高度",
                )
            )

    return markers


def _detect_measuring_gap_measured_move_markers(
    bars: list[BarData],
    *,
    avg_range: float,
    ema_values: list[float],
    structure_phase_names: list[str] | None,
    breakout_event_names: list[str] | None,
) -> list[MeasuredMoveMarker]:
    """识别基于 Measuring Gap 的测量走势。"""
    if len(bars) < 8:
        return []

    markers: list[MeasuredMoveMarker] = []
    for index in range(8, len(bars)):
        recent_events = breakout_event_names[max(0, index - 4):index + 1] if breakout_event_names else []

        markers.extend(
            build_measuring_gap_markers(
                index,
                bars,
                ema_values,
                avg_range,
                recent_events,
                direction="bull",
            )
        )
        markers.extend(
            build_measuring_gap_markers(
                index,
                bars,
                ema_values,
                avg_range,
                recent_events,
                direction="bear",
            )
        )

    return markers


def build_measuring_gap_markers(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    avg_range: float,
    recent_events: list[str],
    *,
    direction: str,
) -> list[MeasuredMoveMarker]:
    """构建一组 Measuring Gap 相关 MM。"""
    standard = build_measuring_gap_marker(
        index,
        bars,
        ema_values,
        avg_range,
        recent_events,
        direction=direction,
    )
    markers: list[MeasuredMoveMarker] = []
    if standard:
        markers.append(standard)
        markers.extend(build_measuring_gap_middle_line_variants(standard, avg_range=avg_range))

    negative = build_negative_measuring_gap_marker(
        index,
        bars,
        ema_values,
        avg_range,
        recent_events,
        direction="bull",
    ) if direction == "bull" else build_negative_measuring_gap_marker(
        index,
        bars,
        ema_values,
        avg_range,
        recent_events,
        direction="bear",
    )
    if negative:
        markers.append(negative)
    return markers


def build_measuring_gap_marker(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    avg_range: float,
    recent_events: list[str],
    *,
    direction: str,
) -> MeasuredMoveMarker | None:
    """构建单个 Measuring Gap MM。"""
    breakout_index = -1
    breakout_point = 0.0
    move_start = 0.0
    for cursor in range(index - 1, max(4, index - 6) - 1, -1):
        prior_window = bars[max(0, cursor - 8):cursor]
        if len(prior_window) < 5:
            continue

        if direction == "bull":
            point = max(bar.high_price for bar in prior_window)
            if is_bull_trend_bar(bars[cursor]) and bars[cursor].close_price > point + avg_range * 0.08:
                breakout_index = cursor
                breakout_point = point
                move_start = min(bar.low_price for bar in prior_window)
                break
        else:
            point = min(bar.low_price for bar in prior_window)
            if is_bear_trend_bar(bars[cursor]) and bars[cursor].close_price < point - avg_range * 0.08:
                breakout_index = cursor
                breakout_point = point
                move_start = max(bar.high_price for bar in prior_window)
                break

    if breakout_index < 0:
        return None
    if recent_events and not any(name in {"突破起爆", "突破跟进", "开盘反转"} for name in recent_events):
        return None

    post_breakout = bars[breakout_index + 1:index + 1]
    if not post_breakout:
        return None

    if direction == "bull":
        pullback_bars = [bar for bar in post_breakout if bar.close_price < bar.open_price or bar.low_price < bar.high_price - avg_range * 0.2]
        if not pullback_bars:
            return None
        gap_boundary = min(bar.low_price for bar in pullback_bars)
        if gap_boundary <= breakout_point + avg_range * 0.03:
            return None
        gap_mid = (gap_boundary + breakout_point) / 2
        target_price = gap_mid + (gap_mid - move_start)
        end_index = resolve_measured_move_end_index(
            bars,
            start_index=index,
            direction="bull",
            target_price=target_price,
            invalidation_price=breakout_point,
            avg_range=avg_range,
            max_bars=16,
        )
        return MeasuredMoveMarker(
            direction="bull",
            leg_start_index=breakout_index,
            leg_start_price=breakout_point,
            leg_end_index=index,
            leg_end_price=gap_boundary,
            projection_start_index=index,
            end_index=end_index,
            target_price=target_price,
            label="MG MM↑",
            category="测量缺口",
        )

    pullback_bars = [bar for bar in post_breakout if bar.close_price > bar.open_price or bar.high_price > bar.low_price + avg_range * 0.2]
    if not pullback_bars:
        return None
    gap_boundary = max(bar.high_price for bar in pullback_bars)
    if gap_boundary >= breakout_point - avg_range * 0.03:
        return None
    gap_mid = (gap_boundary + breakout_point) / 2
    target_price = gap_mid - (move_start - gap_mid)
    end_index = resolve_measured_move_end_index(
        bars,
        start_index=index,
        direction="bear",
        target_price=target_price,
        invalidation_price=breakout_point,
        avg_range=avg_range,
        max_bars=16,
    )
    return MeasuredMoveMarker(
        direction="bear",
        leg_start_index=breakout_index,
        leg_start_price=breakout_point,
        leg_end_index=index,
        leg_end_price=gap_boundary,
        projection_start_index=index,
        end_index=end_index,
        target_price=target_price,
        label="MG MM↓",
        category="测量缺口",
    )


def build_negative_measuring_gap_marker(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    avg_range: float,
    recent_events: list[str],
    *,
    direction: str,
) -> MeasuredMoveMarker | None:
    """构建 Negative Measuring Gap。"""
    standard = build_measuring_gap_marker(
        index,
        bars,
        ema_values,
        avg_range,
        recent_events,
        direction=direction,
    )
    if standard:
        return None

    breakout_index = -1
    breakout_point = 0.0
    move_start = 0.0
    for cursor in range(index - 1, max(4, index - 6) - 1, -1):
        prior_window = bars[max(0, cursor - 8):cursor]
        if len(prior_window) < 5:
            continue
        if direction == "bull":
            point = max(bar.high_price for bar in prior_window)
            if is_bull_trend_bar(bars[cursor]) and bars[cursor].close_price > point + avg_range * 0.08:
                breakout_index = cursor
                breakout_point = point
                move_start = min(bar.low_price for bar in prior_window)
                break
        else:
            point = min(bar.low_price for bar in prior_window)
            if is_bear_trend_bar(bars[cursor]) and bars[cursor].close_price < point - avg_range * 0.08:
                breakout_index = cursor
                breakout_point = point
                move_start = max(bar.high_price for bar in prior_window)
                break

    if breakout_index < 0:
        return None

    post_breakout = bars[breakout_index + 1:index + 1]
    if not post_breakout:
        return None

    if direction == "bull":
        below_breakout = [bar for bar in post_breakout if bar.low_price < breakout_point - avg_range * 0.03]
        if not below_breakout:
            return None
        boundary = min(bar.low_price for bar in below_breakout)
        if boundary < breakout_point - avg_range * 0.6:
            return None
        midline = (breakout_point + boundary) / 2
        target_price = midline + (midline - move_start)
        end_index = resolve_measured_move_end_index(
            bars,
            start_index=index,
            direction="bull",
            target_price=target_price,
            invalidation_price=boundary,
            avg_range=avg_range,
            max_bars=12,
        )
        return MeasuredMoveMarker(
            direction="bull",
            leg_start_index=breakout_index,
            leg_start_price=breakout_point,
            leg_end_index=index,
            leg_end_price=boundary,
            projection_start_index=index,
            end_index=end_index,
            target_price=target_price,
            label="Neg MG↑",
            category="负测量缺口",
        )

    above_breakout = [bar for bar in post_breakout if bar.high_price > breakout_point + avg_range * 0.03]
    if not above_breakout:
        return None
    boundary = max(bar.high_price for bar in above_breakout)
    if boundary > breakout_point + avg_range * 0.6:
        return None
    midline = (breakout_point + boundary) / 2
    target_price = midline - (move_start - midline)
    end_index = resolve_measured_move_end_index(
        bars,
        start_index=index,
        direction="bear",
        target_price=target_price,
        invalidation_price=boundary,
        avg_range=avg_range,
        max_bars=12,
    )
    return MeasuredMoveMarker(
        direction="bear",
        leg_start_index=breakout_index,
        leg_start_price=breakout_point,
        leg_end_index=index,
        leg_end_price=boundary,
        projection_start_index=index,
        end_index=end_index,
        target_price=target_price,
        label="Neg MG↓",
        category="负测量缺口",
    )


def build_measuring_gap_middle_line_variants(
    marker: MeasuredMoveMarker,
    *,
    avg_range: float,
) -> list[MeasuredMoveMarker]:
    """为 Measuring Gap 提供多种中线口径。"""
    if marker.category != "测量缺口":
        return []
    gap_size = abs(marker.leg_end_price - marker.leg_start_price)
    if gap_size < avg_range * 0.08:
        return []

    standard_mid = (marker.leg_start_price + marker.leg_end_price) / 2
    smaller_mid = marker.leg_start_price + (marker.leg_end_price - marker.leg_start_price) * 0.65
    if marker.direction == "bear":
        smaller_mid = marker.leg_start_price + (marker.leg_end_price - marker.leg_start_price) * 0.35

    variants: list[MeasuredMoveMarker] = []
    for label, midline, category in (
        ("MG Mid1↑" if marker.direction == "bull" else "MG Mid1↓", standard_mid, "测量缺口中线/标准"),
        ("MG Mid2↑" if marker.direction == "bull" else "MG Mid2↓", smaller_mid, "测量缺口中线/较小"),
    ):
        target_offset = marker.target_price - standard_mid
        variants.append(
            MeasuredMoveMarker(
                direction=marker.direction,
                leg_start_index=marker.leg_start_index,
                leg_start_price=marker.leg_start_price,
                leg_end_index=marker.leg_end_index,
                leg_end_price=midline,
                projection_start_index=marker.projection_start_index,
                end_index=marker.end_index,
                target_price=midline + target_offset,
                label=label,
                category=category,
            )
        )
    return variants


def resolve_leg_equal_category(
    *,
    phase_name: str,
    pullback_ratio: float,
    near_ema: bool,
) -> str:
    """细分 Leg1=Leg2 的语境。"""
    if phase_name in {"震荡", "趋势交易区间"}:
        return "交易区间内部"
    if pullback_ratio >= 0.5:
        return "强趋势深回调"
    if near_ema:
        return "EMA配合"
    return "基础"


def count_trend_bars_in_segment(
    bars: list[BarData],
    start_index: int,
    end_index: int,
    *,
    direction: str,
) -> int:
    """统计一段走势里顺势趋势棒的数量。"""
    count = 0
    for index in range(max(0, start_index), min(len(bars) - 1, end_index) + 1):
        bar = bars[index]
        if direction == "bull" and is_bull_trend_bar(bar):
            count += 1
        elif direction == "bear" and is_bear_trend_bar(bar):
            count += 1
    return count


def max_consecutive_trend_bars_in_segment(
    bars: list[BarData],
    start_index: int,
    end_index: int,
    *,
    direction: str,
) -> int:
    """统计一段走势里最长连续顺势趋势棒。"""
    longest = 0
    current = 0
    for index in range(max(0, start_index), min(len(bars) - 1, end_index) + 1):
        bar = bars[index]
        is_trend = (direction == "bull" and is_bull_trend_bar(bar)) or (direction == "bear" and is_bear_trend_bar(bar))
        if is_trend:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def evaluate_leg_equal_context(
    *,
    bars: list[BarData],
    left: tuple[int, str, float],
    middle: tuple[int, str, float],
    right: tuple[int, str, float],
    phase_name: str,
    pullback_ratio: float,
    near_ema: bool,
    direction: str,
    leg_size: float,
) -> str:
    """只在更接近 Brooks 语境时才放行 Leg1=Leg2。"""
    leg_bar_count = max(1, middle[0] - left[0] + 1)
    leg_trend_count = count_trend_bars_in_segment(
        bars,
        left[0],
        middle[0],
        direction=direction,
    )
    leg_trend_ratio = leg_trend_count / leg_bar_count
    max_leg_streak = max_consecutive_trend_bars_in_segment(
        bars,
        left[0],
        middle[0],
        direction=direction,
    )
    segment_avg_range = max(
        sum(max(bar.high_price - bar.low_price, 0.0) for bar in bars[left[0]:middle[0] + 1]) / leg_bar_count,
        1e-6,
    )

    if phase_name in {"", "未就绪"}:
        return ""

    in_trade_range = phase_name in {"震荡", "趋势交易区间"}
    deep_pullback = pullback_ratio >= 0.68 and near_ema
    ema_context = near_ema and pullback_ratio >= 0.58 and phase_name in {"宽幅通道", "震荡", "趋势交易区间"}
    weaker_leg = leg_trend_ratio <= 0.48 or max_leg_streak <= 2
    overly_one_sided = leg_trend_ratio >= 0.60 and max_leg_streak >= 3
    meaningful_leg = leg_size >= segment_avg_range * 3.0 and leg_bar_count >= 5

    if in_trade_range:
        if pullback_ratio >= 0.45 and (weaker_leg or near_ema) and meaningful_leg:
            return "交易区间内部"
        return ""
    if deep_pullback and phase_name != "窄幅通道" and meaningful_leg:
        return "强趋势深回调"
    if ema_context and not overly_one_sided and meaningful_leg:
        return "EMA配合"
    return ""


def resolve_measured_move_end_index(
    bars: list[BarData],
    *,
    start_index: int,
    direction: str,
    target_price: float,
    invalidation_price: float,
    avg_range: float,
    max_bars: int,
) -> int:
    """为测量走势寻找合理的结束边界。"""
    if not bars:
        return start_index

    limit = min(len(bars) - 1, start_index + max(1, max_bars))
    for index in range(start_index, limit + 1):
        bar = bars[index]
        if direction == "bull":
            if bar.high_price >= target_price:
                return index
            if bar.low_price < invalidation_price - avg_range * 0.12:
                return index
        else:
            if bar.low_price <= target_price:
                return index
            if bar.high_price > invalidation_price + avg_range * 0.12:
                return index
    return limit


def build_background_direction_names(
    structure_phase_names: list[str],
    structure_contexts: list[StructureContext | None],
) -> list[str]:
    """按统一结构上下文生成方向标签。"""
    direction_names: list[str] = []
    for index, phase_name in enumerate(structure_phase_names):
        context = structure_contexts[index] if index < len(structure_contexts) else None
        if not context:
            direction_names.append("中性")
            continue
        direction_name = infer_context_direction(context)
        if phase_name == "震荡":
            direction_names.append("中性")
            continue
        if phase_name == "趋势交易区间":
            if abs(float(context.long_metrics["progress_ratio"])) < 0.14 and context.directional_swing_score < 0.22:
                direction_names.append("中性")
            else:
                direction_names.append(direction_name)
            continue
        direction_names.append(direction_name)
    return direction_names


def detect_breakout_start_direction(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
    structure_contexts: list[StructureContext | None] | None = None,
    higher_structure_phase_names: list[str] | None = None,
    higher_direction_names: list[str] | None = None,
) -> str:
    """识别突破起爆方向。"""
    if index < 8:
        return ""
    context = (
        structure_contexts[index]
        if structure_contexts is not None and index < len(structure_contexts)
        else calculate_structure_context(index, bars, ema_values, range_ma)
    )
    if not context:
        return ""

    if is_bull_breakout_phase(index, bars, ema_values, range_ma):
        if not passes_higher_timeframe_breakout_filter(
            index,
            "bull",
            bars,
            ema_values,
            range_ma,
            context,
            higher_structure_phase_names,
            higher_direction_names,
        ):
            return ""
        return "bull"
    if is_bear_breakout_phase(index, bars, ema_values, range_ma):
        if not passes_higher_timeframe_breakout_filter(
            index,
            "bear",
            bars,
            ema_values,
            range_ma,
            context,
            higher_structure_phase_names,
            higher_direction_names,
        ):
            return ""
        return "bear"
    return ""


def is_bull_breakout_phase(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
) -> bool:
    """判断是否属于 Brooks 语境下的多头突破起爆段。"""
    recent = bars[index - 2:index + 1]
    setup_window = bars[max(0, index - 14):index - 2]
    if len(recent) < 3 or len(setup_window) < 8:
        return False

    avg_range = max(range_ma[index], 1e-12)
    setup_high = max(bar.high_price for bar in setup_window)
    recent_high = max(bar.high_price for bar in recent)
    recent_move = recent[-1].close_price - recent[0].open_price
    bull_trend_bars = sum(1 for bar in recent if is_bull_trend_bar(bar))
    bull_closes_above_ema = count_recent_ema_side(index, bars, ema_values, "bull", 3)
    consecutive_bull_trend_bars = count_consecutive_trend_bars(index, bars, "bull")
    closes_above_setup = sum(1 for bar in recent if bar.close_price > setup_high + avg_range * 0.04)
    ema_slope_up = ema_values[index] >= ema_values[max(0, index - 3)]
    prior_bull_pressure = count_consecutive_trend_bars(max(0, index - 3), bars, "bull")
    has_balance = has_pre_breakout_balance(index, bars, ema_values, "bull")
    current_bar = bars[index]
    current_bar_broke_out = current_bar.close_price > setup_high + avg_range * 0.08
    surprise_breakout = is_surprise_breakout_bar(current_bar, "bull", avg_range) and current_bar.close_price > setup_high + avg_range * 0.12

    required_ema_side = 1 if surprise_breakout else 2
    if bull_closes_above_ema < required_ema_side or not ema_slope_up:
        return False

    breakout_pressure = bull_trend_bars >= 2 or consecutive_bull_trend_bars >= 3 or surprise_breakout
    broke_far_enough = recent_high >= setup_high + (avg_range * (0.18 if surprise_breakout else 0.25))
    moved_far_enough = recent_move >= avg_range * (1.05 if surprise_breakout else 1.55)
    required_setup_closes = 1 if surprise_breakout else 2
    if not breakout_pressure or not broke_far_enough or not moved_far_enough or closes_above_setup < required_setup_closes:
        return False

    if not current_bar_broke_out and not surprise_breakout:
        return False
    if prior_bull_pressure >= 2 and recent_move < avg_range * 1.95 and not surprise_breakout:
        return False
    if not has_balance:
        return False
    if not is_bull_trend_bar(current_bar) and consecutive_bull_trend_bars < 3 and not surprise_breakout:
        return False

    return not breakout_failed(index, bars, setup_high, "bull", avg_range)


def is_bear_breakout_phase(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
) -> bool:
    """判断是否属于 Brooks 语境下的空头突破起爆段。"""
    recent = bars[index - 2:index + 1]
    setup_window = bars[max(0, index - 14):index - 2]
    if len(recent) < 3 or len(setup_window) < 8:
        return False

    avg_range = max(range_ma[index], 1e-12)
    setup_low = min(bar.low_price for bar in setup_window)
    recent_low = min(bar.low_price for bar in recent)
    recent_move = recent[0].open_price - recent[-1].close_price
    bear_trend_bars = sum(1 for bar in recent if is_bear_trend_bar(bar))
    bear_closes_below_ema = count_recent_ema_side(index, bars, ema_values, "bear", 3)
    consecutive_bear_trend_bars = count_consecutive_trend_bars(index, bars, "bear")
    closes_below_setup = sum(1 for bar in recent if bar.close_price < setup_low - avg_range * 0.04)
    ema_slope_down = ema_values[index] <= ema_values[max(0, index - 3)]
    prior_bear_pressure = count_consecutive_trend_bars(max(0, index - 3), bars, "bear")
    has_balance = has_pre_breakout_balance(index, bars, ema_values, "bear")
    current_bar = bars[index]
    current_bar_broke_out = current_bar.close_price < setup_low - avg_range * 0.08
    surprise_breakout = is_surprise_breakout_bar(current_bar, "bear", avg_range) and current_bar.close_price < setup_low - avg_range * 0.12

    required_ema_side = 1 if surprise_breakout else 2
    if bear_closes_below_ema < required_ema_side or not ema_slope_down:
        return False

    breakout_pressure = bear_trend_bars >= 2 or consecutive_bear_trend_bars >= 3 or surprise_breakout
    broke_far_enough = recent_low <= setup_low - (avg_range * (0.18 if surprise_breakout else 0.25))
    moved_far_enough = recent_move >= avg_range * (1.05 if surprise_breakout else 1.55)
    required_setup_closes = 1 if surprise_breakout else 2
    if not breakout_pressure or not broke_far_enough or not moved_far_enough or closes_below_setup < required_setup_closes:
        return False

    if not current_bar_broke_out and not surprise_breakout:
        return False
    if prior_bear_pressure >= 2 and recent_move < avg_range * 1.95 and not surprise_breakout:
        return False
    if not has_balance:
        return False
    if not is_bear_trend_bar(current_bar) and consecutive_bear_trend_bars < 3 and not surprise_breakout:
        return False

    return not breakout_failed(index, bars, setup_low, "bear", avg_range)


def create_breakout_event_context(
    index: int,
    direction: str,
    bars: list[BarData],
    range_ma: list[float],
) -> BreakoutEventContext:
    """创建突破事件上下文。"""
    if direction == "bull":
        setup_window = bars[max(0, index - 14):index - 2]
        setup_level = max(bar.high_price for bar in setup_window) if setup_window else bars[index].high_price
    else:
        setup_window = bars[max(0, index - 14):index - 2]
        setup_level = min(bar.low_price for bar in setup_window) if setup_window else bars[index].low_price

    return BreakoutEventContext(
        direction=direction,
        start_index=index,
        setup_level=setup_level,
        avg_range=max(range_ma[index], 1e-12),
    )


def classify_breakout_event(
    index: int,
    context: BreakoutEventContext,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
) -> tuple[str, bool]:
    """按更严格边界分类突破起爆后的后续事件。"""
    if index <= context.start_index:
        return "", False

    if is_failed_breakout_event(index, context, bars, ema_values, range_ma):
        return "失败突破", False

    bars_since_start = index - context.start_index
    if bars_since_start > 8:
        return "", False

    if bars_since_start in {1, 2, 3} and is_breakout_followthrough_event(index, context, bars, ema_values, range_ma):
        context.followthrough_seen = True
        return "突破跟进", True

    if context.followthrough_seen and 2 <= bars_since_start <= 6 and is_breakout_test_event(index, context, bars, ema_values, range_ma):
        context.test_seen = True
        return "突破测试", True

    if context.followthrough_seen and bars_since_start <= 6:
        return "无事件", True

    if bars_since_start <= 4 and breakout_context_holds_level(index, context, bars, range_ma):
        return "无事件", True

    return "", False


def is_breakout_followthrough_event(
    index: int,
    context: BreakoutEventContext,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
) -> bool:
    """判断是否仍属于突破后的跟进阶段。"""
    bar = bars[index]
    prev_bar = bars[index - 1]
    avg_range = max(range_ma[index], context.avg_range)
    bar_range = get_bar_range(bar)
    body_ratio = get_bar_body(bar) / bar_range

    if context.direction == "bull":
        if bar.close_price < context.setup_level - avg_range * 0.05:
            return False
        if is_bear_trend_bar(bar):
            return False
        if bar.low_price <= context.setup_level + avg_range * 0.10:
            return False
        return (
            is_bull_trend_bar(bar)
            or (
                bar.close_price >= context.setup_level
                and body_ratio >= 0.35
                and bar.close_price >= prev_bar.close_price - avg_range * 0.18
                and bar.low_price >= prev_bar.low_price - avg_range * 0.22
            )
        )

    if bar.close_price > context.setup_level + avg_range * 0.05:
        return False
    if is_bull_trend_bar(bar):
        return False
    if bar.high_price >= context.setup_level - avg_range * 0.10:
        return False
    return (
        is_bear_trend_bar(bar)
        or (
            bar.close_price <= context.setup_level
            and body_ratio >= 0.35
            and bar.close_price <= prev_bar.close_price + avg_range * 0.18
            and bar.high_price <= prev_bar.high_price + avg_range * 0.22
        )
    )


def is_breakout_test_event(
    index: int,
    context: BreakoutEventContext,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
) -> bool:
    """判断是否进入突破测试阶段。"""
    bar = bars[index]
    avg_range = max(range_ma[index], context.avg_range)
    ema_value = ema_values[index]
    body_ratio = get_bar_body(bar) / get_bar_range(bar)

    if context.direction == "bull":
        test_zone = max(context.setup_level, ema_value)
        touched_zone = bar.low_price <= test_zone + avg_range * 0.12
        held_breakout = bar.close_price >= context.setup_level - avg_range * 0.04
        weak_pullback = body_ratio <= 0.55 or bar.close_price >= bar.open_price
        return touched_zone and held_breakout and weak_pullback and not is_bear_trend_bar(bar)

    test_zone = min(context.setup_level, ema_value)
    touched_zone = bar.high_price >= test_zone - avg_range * 0.12
    held_breakout = bar.close_price <= context.setup_level + avg_range * 0.04
    weak_pullback = body_ratio <= 0.55 or bar.close_price <= bar.open_price
    return touched_zone and held_breakout and weak_pullback and not is_bull_trend_bar(bar)


def is_failed_breakout_event(
    index: int,
    context: BreakoutEventContext,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
) -> bool:
    """判断是否属于失败突破。"""
    bar = bars[index]
    avg_range = max(range_ma[index], context.avg_range)
    ema_value = ema_values[index]

    if context.direction == "bull":
        returned_inside = bar.close_price <= context.setup_level - avg_range * 0.08
        strong_reversal = is_bear_trend_bar(bar) and bar.close_price <= ema_value
        return returned_inside or strong_reversal

    returned_inside = bar.close_price >= context.setup_level + avg_range * 0.08
    strong_reversal = is_bull_trend_bar(bar) and bar.close_price >= ema_value
    return returned_inside or strong_reversal


def breakout_context_holds_level(
    index: int,
    context: BreakoutEventContext,
    bars: list[BarData],
    range_ma: list[float],
) -> bool:
    """判断突破语境是否还保留在突破位外侧。"""
    bar = bars[index]
    avg_range = max(range_ma[index], context.avg_range)

    if context.direction == "bull":
        return bar.close_price >= context.setup_level - avg_range * 0.03
    return bar.close_price <= context.setup_level + avg_range * 0.03


def has_pre_breakout_balance(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    direction: str,
) -> bool:
    """判断突破前是否先出现 breakout mode/小平衡。"""
    start = max(0, index - 10)
    end = max(start, index - 2)
    window = bars[start:end]
    ema_window = ema_values[start:end]
    if len(window) < 6:
        return False

    overlap_count = 0
    for left, right in zip(window[:-1], window[1:]):
        overlap = min(left.high_price, right.high_price) - max(left.low_price, right.low_price)
        if overlap > 0:
            overlap_count += 1

    if direction == "bull":
        opposite_bars = sum(1 for bar in window if bar.close_price <= bar.open_price)
        touched_ema = any(bar.low_price <= ema for bar, ema in zip(window, ema_window))
    else:
        opposite_bars = sum(1 for bar in window if bar.close_price >= bar.open_price)
        touched_ema = any(bar.high_price >= ema for bar, ema in zip(window, ema_window))

    reversal_count = count_breakout_mode_reversals(window)
    return (
        reversal_count >= 2
        or overlap_count >= max(3, len(window) // 2)
        or opposite_bars >= 3
        or (touched_ema and overlap_count >= 2)
    )


def count_breakout_mode_reversals(bars: list[BarData]) -> int:
    """按 Brooks 的 BOM 语境，统计局部反转次数。"""
    if len(bars) < 3:
        return 0

    directions: list[int] = []
    for left, right in zip(bars[:-1], bars[1:]):
        if right.high_price > left.high_price and right.low_price >= left.low_price:
            directions.append(1)
        elif right.low_price < left.low_price and right.high_price <= left.high_price:
            directions.append(-1)
        else:
            directions.append(0)

    reversals = 0
    prev_direction = 0
    for direction in directions:
        if direction == 0:
            continue
        if prev_direction and direction != prev_direction:
            reversals += 1
        prev_direction = direction

    return reversals


def build_session_bar_counts(bars: list[BarData]) -> list[int]:
    """按会话生成逐 bar 计数。"""
    counts: list[int] = []
    current_date = None
    count = 0
    for bar in bars:
        bar_date = bar.datetime.date()
        if bar_date != current_date:
            current_date = bar_date
            count = 1
        else:
            count += 1
        counts.append(count)
    return counts


def is_opening_reversal_event(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
    session_bar_counts: list[int],
    bar_minutes: int,
) -> bool:
    """识别开盘反转事件。"""
    count = session_bar_counts[index]
    elapsed_minutes = count * bar_minutes
    if count < 4 or elapsed_minutes > 90:
        return False

    session_start = index - count + 1
    session = bars[session_start:index + 1]
    first_bar = session[0]
    current_bar = bars[index]
    avg_range = max(range_ma[index], 1e-6)

    prior_session = session[:-1]
    if not prior_session:
        return False

    broke_above_first = any(bar.high_price > first_bar.high_price + avg_range * 0.04 for bar in prior_session[1:])
    broke_below_first = any(bar.low_price < first_bar.low_price - avg_range * 0.04 for bar in prior_session[1:])

    bull_reversal = (
        broke_below_first
        and is_bull_trend_bar(current_bar)
        and current_bar.close_price > first_bar.high_price - avg_range * 0.04
        and current_bar.close_price >= ema_values[index]
    )
    bear_reversal = (
        broke_above_first
        and is_bear_trend_bar(current_bar)
        and current_bar.close_price < first_bar.low_price + avg_range * 0.04
        and current_bar.close_price <= ema_values[index]
    )
    return bull_reversal or bear_reversal


def is_midday_reversal_event(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
    session_bar_counts: list[int],
    bar_minutes: int,
) -> bool:
    """识别午间反转事件。"""
    count = session_bar_counts[index]
    elapsed_minutes = count * bar_minutes
    if bar_minutes <= 1:
        min_minutes = 30
        max_minutes = 180
    elif bar_minutes <= 5:
        min_minutes = 120
        max_minutes = 420
    else:
        min_minutes = 180
        max_minutes = 480
    if elapsed_minutes < min_minutes or elapsed_minutes > max_minutes or index < 4:
        return False

    session_start = index - count + 1
    session = bars[session_start:index + 1]
    prior_session = session[:-1]
    if len(prior_session) < 10:
        return False

    current_bar = bars[index]
    avg_range = max(range_ma[index], 1e-6)
    recent = bars[max(session_start, index - 4):index]
    context_window = bars[max(session_start, index - 12):index]
    recent_high = max(bar.high_price for bar in recent)
    recent_low = min(bar.low_price for bar in recent)
    context_high = max(bar.high_price for bar in context_window)
    context_low = min(bar.low_price for bar in context_window)
    recent_bear_bars = sum(1 for bar in recent if bar.close_price < bar.open_price)
    recent_bull_bars = sum(1 for bar in recent if bar.close_price > bar.open_price)

    bull_midday = (
        (
            recent_low <= context_low + avg_range * 0.25
            or recent_bear_bars >= 3
        )
        and is_bull_trend_bar(current_bar)
        and current_bar.close_price > recent_high - avg_range * 0.05
        and current_bar.close_price >= ema_values[index]
    )
    bear_midday = (
        (
            recent_high >= context_high - avg_range * 0.25
            or recent_bull_bars >= 3
        )
        and is_bear_trend_bar(current_bar)
        and current_bar.close_price < recent_low + avg_range * 0.05
        and current_bar.close_price <= ema_values[index]
    )
    return bull_midday or bear_midday


def is_inside_bar(bar: BarData, prior_bar: BarData) -> bool:
    """判断当前 bar 是否为内包线。"""
    return (
        bar.high_price <= prior_bar.high_price
        and bar.low_price >= prior_bar.low_price
        and (bar.high_price != prior_bar.high_price or bar.low_price != prior_bar.low_price)
    )


def is_outside_bar(bar: BarData, prior_bar: BarData) -> bool:
    """判断当前 bar 是否为外包线。"""
    return (
        bar.high_price >= prior_bar.high_price
        and bar.low_price <= prior_bar.low_price
        and (bar.high_price != prior_bar.high_price or bar.low_price != prior_bar.low_price)
    )


def breakout_failed(
    index: int,
    bars: list[BarData],
    setup_level: float,
    direction: str,
    avg_range: float,
) -> bool:
    """过滤掉在交易区间/宽幅通道里的失败突破或第二腿陷阱。"""
    if index + 1 >= len(bars):
        return False

    next_bar = bars[index + 1]
    if direction == "bull":
        if is_bear_trend_bar(next_bar) and next_bar.close_price <= setup_level:
            return True
        if index + 2 < len(bars):
            failed_closes = sum(1 for bar in bars[index + 1:index + 3] if bar.close_price <= setup_level)
            if failed_closes >= 2:
                return True
        return next_bar.close_price < setup_level - avg_range * 0.05

    if is_bull_trend_bar(next_bar) and next_bar.close_price >= setup_level:
        return True
    if index + 2 < len(bars):
        failed_closes = sum(1 for bar in bars[index + 1:index + 3] if bar.close_price >= setup_level)
        if failed_closes >= 2:
            return True
    return next_bar.close_price > setup_level + avg_range * 0.05


def calculate_structure_metrics(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
    lookback: int = 12,
) -> dict[str, float | int | str]:
    """计算结构层分类所需特征。"""
    start = max(0, index - lookback + 1)
    recent = bars[start:index + 1]
    ema_slice = ema_values[start:index + 1]
    if len(recent) < 6:
        return {
            "direction": "neutral",
            "overlap_ratio": 1.0,
            "crosses": 0,
            "dominance_ratio": 0.0,
            "efficiency": 0.0,
            "trend_bar_ratio": 0.0,
            "reversal_count": 0,
            "opposite_bar_ratio": 0.0,
            "slope_in_range": 0.0,
            "progress_ratio": 0.0,
            "pullback_depth_ratio": 0.0,
            "window_span_ratio": 0.0,
        }

    bull_side = sum(1 for bar, ema in zip(recent, ema_slice) if bar.close_price >= ema)
    bear_side = sum(1 for bar, ema in zip(recent, ema_slice) if bar.close_price <= ema)
    direction = "bull" if bull_side > bear_side else "bear" if bear_side > bull_side else "neutral"

    crosses = 0
    for left, right, left_ema, right_ema in zip(
        [bar.close_price for bar in recent[:-1]],
        [bar.close_price for bar in recent[1:]],
        ema_slice[:-1],
        ema_slice[1:],
    ):
        if (left - left_ema) * (right - right_ema) < 0:
            crosses += 1

    overlap_count = 0
    for left, right in zip(recent[:-1], recent[1:]):
        overlap = min(left.high_price, right.high_price) - max(left.low_price, right.low_price)
        smaller_range = max(min(get_bar_range(left), get_bar_range(right)), 1e-12)
        if overlap / smaller_range >= 0.45:
            overlap_count += 1

    close_changes = [abs(right.close_price - left.close_price) for left, right in zip(recent[:-1], recent[1:])]
    total_close_path = max(sum(close_changes), 1e-12)
    net_close_move = abs(recent[-1].close_price - recent[0].close_price)
    efficiency = net_close_move / total_close_path

    if direction == "bull":
        trend_bar_count = sum(1 for bar in recent if is_bull_trend_bar(bar))
        opposite_bar_count = sum(1 for bar in recent if bar.close_price < bar.open_price)
    elif direction == "bear":
        trend_bar_count = sum(1 for bar in recent if is_bear_trend_bar(bar))
        opposite_bar_count = sum(1 for bar in recent if bar.close_price > bar.open_price)
    else:
        trend_bar_count = 0
        opposite_bar_count = len(recent)

    avg_range = max(sum(range_ma[start:index + 1]) / len(recent), 1e-12)
    ema_slope = abs(ema_slice[-1] - ema_slice[0]) / avg_range
    reversal_count = count_breakout_mode_reversals(recent)
    window_high = max(bar.high_price for bar in recent)
    window_low = min(bar.low_price for bar in recent)
    window_span = max(window_high - window_low, 1e-12)

    if direction == "bull":
        directional_net_move = max(recent[-1].close_price - recent[0].close_price, 0.0)
        running_high = recent[0].high_price
        max_pullback = 0.0
        for bar in recent:
            running_high = max(running_high, bar.high_price)
            max_pullback = max(max_pullback, running_high - bar.close_price)
    elif direction == "bear":
        directional_net_move = max(recent[0].close_price - recent[-1].close_price, 0.0)
        running_low = recent[0].low_price
        max_pullback = 0.0
        for bar in recent:
            running_low = min(running_low, bar.low_price)
            max_pullback = max(max_pullback, bar.close_price - running_low)
    else:
        directional_net_move = 0.0
        max_pullback = window_span

    return {
        "direction": direction,
        "overlap_ratio": overlap_count / max(len(recent) - 1, 1),
        "crosses": crosses,
        "dominance_ratio": max(bull_side, bear_side) / len(recent),
        "efficiency": efficiency,
        "trend_bar_ratio": trend_bar_count / len(recent),
        "reversal_count": reversal_count,
        "opposite_bar_ratio": opposite_bar_count / len(recent),
        "slope_in_range": ema_slope,
        "progress_ratio": directional_net_move / window_span,
        "pullback_depth_ratio": max_pullback / avg_range,
        "window_span_ratio": window_span / avg_range,
    }


def calculate_structure_context(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
) -> StructureContext:
    """组合短窗、长窗与摆动结构特征。"""
    short_metrics = calculate_structure_metrics(index, bars, ema_values, range_ma, lookback=12)
    long_metrics = calculate_structure_metrics(index, bars, ema_values, range_ma, lookback=30)
    swing_metrics = calculate_swing_channel_metrics(index, bars, ema_values, range_ma, lookback=30)
    magnet_metrics = calculate_magnet_metrics(index, bars, range_ma, lookback=40)

    long_direction = str(long_metrics["direction"])
    short_direction = str(short_metrics["direction"])
    if long_direction != "neutral":
        direction = long_direction
    elif short_direction != "neutral":
        direction = short_direction
    else:
        direction = "neutral"

    return StructureContext(
        short_metrics=short_metrics,
        long_metrics=long_metrics,
        direction=direction,
        swing_point_count=int(swing_metrics["swing_point_count"]),
        leg_count=int(swing_metrics["leg_count"]),
        directional_swing_score=float(swing_metrics["directional_swing_score"]),
        counter_swing_score=float(swing_metrics["counter_swing_score"]),
        trendline_alignment=float(swing_metrics["trendline_alignment"]),
        ema_touch_ratio=float(swing_metrics["ema_touch_ratio"]),
        magnet_confluence_score=float(magnet_metrics["magnet_confluence_score"]),
        magnet_reaction_score=float(magnet_metrics["magnet_reaction_score"]),
        trend_touch_score=float(swing_metrics["trend_touch_score"]),
        channel_touch_score=float(swing_metrics["channel_touch_score"]),
        breach_ratio=float(swing_metrics["breach_ratio"]),
        channel_span_ratio=float(swing_metrics["channel_span_ratio"]),
        geometry_quality_score=float(swing_metrics["geometry_quality_score"]),
    )


def calculate_swing_channel_metrics(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
    lookback: int,
) -> dict[str, float | int]:
    """从摆动、通道线和 EMA 磁体角度补充结构信息。"""
    start = max(0, index - lookback + 1)
    recent = bars[start:index + 1]
    ema_slice = ema_values[start:index + 1]
    if len(recent) < 7:
        return {
            "swing_point_count": 0,
            "leg_count": 0,
            "directional_swing_score": 0.0,
            "counter_swing_score": 0.0,
            "trendline_alignment": 0.0,
            "ema_touch_ratio": 0.0,
            "trend_touch_score": 0.0,
            "channel_touch_score": 0.0,
            "breach_ratio": 1.0,
            "channel_span_ratio": 0.0,
            "geometry_quality_score": 0.0,
        }

    avg_range = max(sum(range_ma[start:index + 1]) / len(recent), 1e-12)
    swings = find_pivot_swings(recent, strength=2)
    highs = [(offset, price) for offset, kind, price in swings if kind == "H"]
    lows = [(offset, price) for offset, kind, price in swings if kind == "L"]

    direction = "neutral"
    bull_side = sum(1 for bar, ema in zip(recent, ema_slice) if bar.close_price >= ema)
    bear_side = sum(1 for bar, ema in zip(recent, ema_slice) if bar.close_price <= ema)
    if bull_side > bear_side:
        direction = "bull"
    elif bear_side > bull_side:
        direction = "bear"

    higher_high_ratio, lower_high_ratio = calculate_monotonic_swing_ratios(highs, rising=True)
    higher_low_ratio, lower_low_ratio = calculate_monotonic_swing_ratios(lows, rising=True)
    if direction == "bull":
        directional_swing_score = average_nonzero([higher_high_ratio, higher_low_ratio])
        counter_swing_score = average_nonzero([lower_high_ratio, lower_low_ratio])
    elif direction == "bear":
        directional_swing_score = average_nonzero([lower_high_ratio, lower_low_ratio])
        counter_swing_score = average_nonzero([higher_high_ratio, higher_low_ratio])
    else:
        directional_swing_score = 0.0
        counter_swing_score = 0.0

    geometry = select_channel_geometry(recent, direction, avg_range, strength=1)
    trendline_alignment = max(
        0.0,
        min(
            1.0,
            geometry.trend_touch_score * 0.55
            + geometry.channel_touch_score * 0.35
            + (1.0 - geometry.breach_ratio) * 0.10,
        ),
    )

    ema_touch_count = 0
    for bar, ema_value in zip(recent, ema_slice):
        if bar.low_price - avg_range * 0.08 <= ema_value <= bar.high_price + avg_range * 0.08:
            ema_touch_count += 1
        elif abs(bar.close_price - ema_value) <= avg_range * 0.12:
            ema_touch_count += 1

    return {
        "swing_point_count": len(swings),
        "leg_count": max(len(swings) - 1, 0),
        "directional_swing_score": directional_swing_score,
        "counter_swing_score": counter_swing_score,
        "trendline_alignment": trendline_alignment,
        "ema_touch_ratio": ema_touch_count / len(recent),
        "trend_touch_score": geometry.trend_touch_score,
        "channel_touch_score": geometry.channel_touch_score,
        "breach_ratio": geometry.breach_ratio,
        "channel_span_ratio": geometry.anchor_span_bars / max(len(recent), 1),
        "geometry_quality_score": geometry.quality_score,
    }


def select_channel_geometry(
    bars: list[BarData],
    direction: str,
    avg_range: float,
    strength: int = 1,
) -> ChannelGeometry:
    """选择最能解释当前节奏的趋势线与通道线。"""
    if direction not in {"bull", "bear"}:
        return ChannelGeometry(None, None, None, 0.0, 0.0, 1.0, 0, 0.0)

    best_geometry = ChannelGeometry(None, None, None, 0.0, 0.0, 1.0, 0, 0.0)
    strengths = sorted({max(1, strength), 2})
    for pivot_strength in strengths:
        geometry = _select_channel_geometry_for_strength(bars, direction, avg_range, pivot_strength)
        if geometry.quality_score > best_geometry.quality_score:
            best_geometry = geometry
    return best_geometry


def _select_channel_geometry_for_strength(
    bars: list[BarData],
    direction: str,
    avg_range: float,
    strength: int,
) -> ChannelGeometry:
    """按单一 pivot 强度挑选最佳线段。"""
    pivots = find_pivot_swings(bars, strength=max(1, strength))
    if direction == "bull":
        trend_pivots = [(index, price) for index, kind, price in pivots if kind == "L"]
        opposite_pivots = [(index, price) for index, kind, price in pivots if kind == "H"]
    else:
        trend_pivots = [(index, price) for index, kind, price in pivots if kind == "H"]
        opposite_pivots = [(index, price) for index, kind, price in pivots if kind == "L"]

    if len(trend_pivots) < 2:
        return ChannelGeometry(None, None, None, 0.0, 0.0, 1.0, 0, 0.0)

    candidate_pivots = trend_pivots[-8:]
    min_span = max(3, len(bars) // 7)
    best_geometry = ChannelGeometry(None, None, None, 0.0, 0.0, 1.0, 0, 0.0)

    for left_index in range(len(candidate_pivots) - 1):
        for right_index in range(left_index + 1, len(candidate_pivots)):
            anchor1 = candidate_pivots[left_index]
            anchor2 = candidate_pivots[right_index]
            span = anchor2[0] - anchor1[0]
            if span < min_span:
                continue

            slope = calculate_line_slope(anchor1, anchor2)
            if direction == "bull" and slope <= 0:
                continue
            if direction == "bear" and slope >= 0:
                continue

            touch_score = calculate_line_touch_score(trend_pivots, anchor1, anchor2, avg_range)
            breach_ratio = calculate_line_breach_ratio(bars, anchor1, anchor2, avg_range, direction)
            opposite_anchor = select_opposite_channel_anchor(opposite_pivots, anchor1, anchor2, direction)
            channel_touch_score = calculate_parallel_touch_score(opposite_pivots, anchor1, anchor2, opposite_anchor, avg_range)
            span_bonus = span / max(len(bars) - 1, 1)
            recency_bonus = anchor2[0] / max(len(bars) - 1, 1)
            quality_score = max(
                0.0,
                min(
                    1.0,
                    touch_score * 0.40
                    + channel_touch_score * 0.28
                    + span_bonus * 0.18
                    + recency_bonus * 0.08
                    + (1.0 - breach_ratio) * 0.06,
                ),
            )

            if quality_score <= best_geometry.quality_score:
                continue

            best_geometry = ChannelGeometry(
                trend_anchor1=anchor1,
                trend_anchor2=anchor2,
                opposite_anchor=opposite_anchor,
                trend_touch_score=touch_score,
                channel_touch_score=channel_touch_score,
                breach_ratio=breach_ratio,
                anchor_span_bars=span,
                quality_score=quality_score,
            )

    return best_geometry


def calculate_line_touch_score(
    pivots: list[tuple[int, float]],
    anchor1: tuple[int, float],
    anchor2: tuple[int, float],
    avg_range: float,
) -> float:
    """计算 pivot 对趋势线的贴合程度。"""
    if len(pivots) < 2:
        return 0.0

    touch_count = 0
    considered = 0
    for pivot in pivots:
        if pivot[0] < anchor1[0]:
            continue
        expected = project_line_value(anchor1, anchor2, pivot[0])
        considered += 1
        if abs(pivot[1] - expected) <= avg_range * 0.55:
            touch_count += 1
    if not considered:
        return 0.0
    return touch_count / considered


def calculate_line_breach_ratio(
    bars: list[BarData],
    anchor1: tuple[int, float],
    anchor2: tuple[int, float],
    avg_range: float,
    direction: str,
) -> float:
    """计算价格对趋势线的深度刺穿比例。"""
    if not bars:
        return 1.0

    breach_count = 0
    considered = 0
    for index, bar in enumerate(bars):
        if index < anchor1[0]:
            continue
        expected = project_line_value(anchor1, anchor2, index)
        considered += 1
        if direction == "bull" and bar.low_price < expected - avg_range * 0.35:
            breach_count += 1
        if direction == "bear" and bar.high_price > expected + avg_range * 0.35:
            breach_count += 1
    if not considered:
        return 1.0
    return breach_count / considered


def select_opposite_channel_anchor(
    pivots: list[tuple[int, float]],
    anchor1: tuple[int, float],
    anchor2: tuple[int, float],
    direction: str,
) -> tuple[int, float] | None:
    """选择最能代表通道外沿的对侧 pivot。"""
    if not pivots:
        return None

    selected: tuple[int, float] | None = None
    best_offset = float("-inf")
    for pivot in pivots:
        if pivot[0] < anchor1[0]:
            continue
        expected = project_line_value(anchor1, anchor2, pivot[0])
        offset = pivot[1] - expected
        if direction == "bear":
            offset = expected - pivot[1]
        if offset > best_offset:
            best_offset = offset
            selected = pivot
    return selected


def calculate_parallel_touch_score(
    pivots: list[tuple[int, float]],
    anchor1: tuple[int, float],
    anchor2: tuple[int, float],
    opposite_anchor: tuple[int, float] | None,
    avg_range: float,
) -> float:
    """计算对侧 pivot 对通道线的贴合程度。"""
    if not pivots or opposite_anchor is None:
        return 0.0

    offset = opposite_anchor[1] - project_line_value(anchor1, anchor2, opposite_anchor[0])
    touch_count = 0
    considered = 0
    for pivot in pivots:
        if pivot[0] < anchor1[0]:
            continue
        expected = project_line_value(anchor1, anchor2, pivot[0]) + offset
        considered += 1
        if abs(pivot[1] - expected) <= avg_range * 0.80:
            touch_count += 1
    if not considered:
        return 0.0
    return touch_count / considered


def calculate_line_slope(
    anchor1: tuple[int, float],
    anchor2: tuple[int, float],
) -> float:
    """计算两点连线斜率。"""
    delta_x = max(anchor2[0] - anchor1[0], 1)
    return (anchor2[1] - anchor1[1]) / delta_x


def project_line_value(
    anchor1: tuple[int, float],
    anchor2: tuple[int, float],
    target_index: int,
) -> float:
    """计算线段在目标索引的值。"""
    slope = calculate_line_slope(anchor1, anchor2)
    return anchor1[1] + slope * (target_index - anchor1[0])


def find_pivot_swings(
    bars: list[BarData],
    strength: int,
) -> list[tuple[int, str, float]]:
    """寻找局部摆动高低点。"""
    if len(bars) < strength * 2 + 1:
        return []

    candidates: list[tuple[int, str, float]] = []
    for index in range(strength, len(bars) - strength):
        high_price = bars[index].high_price
        low_price = bars[index].low_price

        if all(high_price >= bars[offset].high_price for offset in range(index - strength, index + strength + 1) if offset != index):
            candidates.append((index, "H", high_price))
        if all(low_price <= bars[offset].low_price for offset in range(index - strength, index + strength + 1) if offset != index):
            candidates.append((index, "L", low_price))

    candidates.sort(key=lambda item: item[0])
    swings: list[tuple[int, str, float]] = []
    for candidate in candidates:
        if swings and swings[-1][1] == candidate[1]:
            previous = swings[-1]
            if candidate[1] == "H" and candidate[2] >= previous[2]:
                swings[-1] = candidate
            elif candidate[1] == "L" and candidate[2] <= previous[2]:
                swings[-1] = candidate
            continue
        swings.append(candidate)
    return swings


def calculate_monotonic_swing_ratios(
    swings: list[tuple[int, float]],
    rising: bool,
) -> tuple[float, float]:
    """计算摆动序列上升与下降的占比。"""
    if len(swings) < 2:
        return 0.0, 0.0

    rising_count = 0
    falling_count = 0
    total = len(swings) - 1
    for (_, left_price), (_, right_price) in zip(swings[:-1], swings[1:]):
        if right_price > left_price:
            rising_count += 1
        elif right_price < left_price:
            falling_count += 1

    if rising:
        return rising_count / total, falling_count / total
    return falling_count / total, rising_count / total


def calculate_swing_slope(
    swings: list[tuple[int, float]],
    avg_range: float,
) -> float:
    """用主要摆动点估算趋势线斜率。"""
    if len(swings) < 2:
        return 0.0

    first_index, first_price = swings[0]
    last_index, last_price = swings[-1]
    bar_count = max(last_index - first_index, 1)
    return (last_price - first_price) / (avg_range * bar_count)


def calculate_trendline_alignment(
    direction: str,
    upper_slope: float,
    lower_slope: float,
) -> float:
    """衡量趋势线与通道线是否朝同一方向倾斜。"""
    if direction == "bull" and upper_slope > 0 and lower_slope > 0:
        return 1.0 - min(abs(upper_slope - lower_slope) / max(abs(upper_slope), abs(lower_slope), 1e-12), 1.0)
    if direction == "bear" and upper_slope < 0 and lower_slope < 0:
        return 1.0 - min(abs(abs(upper_slope) - abs(lower_slope)) / max(abs(upper_slope), abs(lower_slope), 1e-12), 1.0)
    return 0.0


def average_nonzero(values: list[float]) -> float:
    """对有效值求平均。"""
    filtered = [value for value in values if value > 0]
    if not filtered:
        return 0.0
    return sum(filtered) / len(filtered)


def calculate_magnet_metrics(
    index: int,
    bars: list[BarData],
    range_ma: list[float],
    lookback: int,
) -> dict[str, float]:
    """计算前高前低、昨日关键价和更高周期关键位的磁体作用。"""
    start = max(0, index - lookback + 1)
    recent = bars[start:index + 1]
    if len(recent) < 8:
        return {
            "magnet_confluence_score": 0.0,
            "magnet_reaction_score": 0.0,
        }

    avg_range = max(sum(range_ma[start:index + 1]) / len(recent), 1e-12)
    current_close = recent[-1].close_price
    current_bar = recent[-1]
    magnet_levels: list[float] = []

    swings = find_pivot_swings(recent, strength=2)
    swing_highs = [price for _offset, kind, price in swings if kind == "H"][-2:]
    swing_lows = [price for _offset, kind, price in swings if kind == "L"][-2:]
    magnet_levels.extend(swing_highs)
    magnet_levels.extend(swing_lows)

    session_groups = group_bars_by_session(recent)
    session_dates = sorted(session_groups.keys())
    if len(session_dates) >= 2:
        previous_session = session_groups[session_dates[-2]]
        magnet_levels.extend(
            [
                previous_session[0].open_price,
                previous_session[-1].close_price,
                max(bar.high_price for bar in previous_session),
                min(bar.low_price for bar in previous_session),
            ]
        )

    higher_levels = get_previous_higher_timeframe_levels(recent)
    magnet_levels.extend(higher_levels)

    valid_levels = deduplicate_levels(magnet_levels, avg_range * 0.12)
    if not valid_levels:
        return {
            "magnet_confluence_score": 0.0,
            "magnet_reaction_score": 0.0,
        }

    confluence_hits = sum(1 for level in valid_levels if abs(current_close - level) <= avg_range * 0.45)
    magnet_confluence_score = min(confluence_hits / 3, 1.0)

    reaction_hits = 0
    reaction_window = recent[-4:]
    for level in valid_levels:
        if any(bar.low_price <= level <= bar.high_price for bar in reaction_window):
            close_away = max(abs(bar.close_price - level) for bar in reaction_window)
            if close_away >= avg_range * 0.18:
                reaction_hits += 1
        elif (
            current_bar.low_price <= level + avg_range * 0.10
            and current_bar.high_price >= level - avg_range * 0.10
        ):
            reaction_hits += 1
    magnet_reaction_score = min(reaction_hits / 3, 1.0)

    return {
        "magnet_confluence_score": magnet_confluence_score,
        "magnet_reaction_score": magnet_reaction_score,
    }


def group_bars_by_session(
    bars: list[BarData],
) -> dict:
    """按自然日分组。"""
    grouped: dict = {}
    for bar in bars:
        grouped.setdefault(bar.datetime.date(), []).append(bar)
    return grouped


def infer_bar_minutes(
    bars: list[BarData],
) -> int:
    """估算当前 bars 的时间周期分钟数。"""
    if len(bars) < 2:
        return 1

    deltas: list[int] = []
    for left, right in zip(bars[:-1], bars[1:]):
        delta = int((right.datetime - left.datetime).total_seconds() // 60)
        if delta > 0:
            deltas.append(delta)
    if not deltas:
        return 1
    deltas.sort()
    return deltas[len(deltas) // 2]


def get_previous_higher_timeframe_levels(
    bars: list[BarData],
) -> list[float]:
    """提取上一根更高周期的高低收。"""
    current_minutes = infer_bar_minutes(bars)
    higher_minutes = resolve_logic_higher_timeframe_minutes(current_minutes)

    higher_bars = aggregate_logic_bars_to_minutes(bars, higher_minutes)
    if len(higher_bars) < 2:
        return []

    previous_bar = higher_bars[-2]
    return [
        previous_bar.high_price,
        previous_bar.low_price,
        previous_bar.close_price,
    ]


def resolve_logic_higher_timeframe_minutes(current_minutes: int) -> int:
    """按当前图表周期选择更高周期。"""
    if current_minutes <= 15:
        return 60
    return 24 * 60


def build_higher_timeframe_context_map(
    bars: list[BarData],
) -> tuple[list[str], list[str]]:
    """把更高周期结构映射回当前周期。"""
    if len(bars) < 20:
        return ["未就绪"] * len(bars), ["中性"] * len(bars)

    current_minutes = infer_bar_minutes(bars)
    higher_minutes = resolve_logic_higher_timeframe_minutes(current_minutes)
    if higher_minutes <= current_minutes:
        return ["未就绪"] * len(bars), ["中性"] * len(bars)

    higher_bars = aggregate_logic_bars_to_minutes(bars, higher_minutes)
    if len(higher_bars) < 8:
        return ["未就绪"] * len(bars), ["中性"] * len(bars)

    higher_analysis = analyze_brooks_context(higher_bars, enable_higher_timeframe_filter=False)
    bucket_index_map = {
        floor_logic_bar_datetime(bar.datetime, higher_minutes): index
        for index, bar in enumerate(higher_bars)
    }

    mapped_phase_names: list[str] = []
    mapped_direction_names: list[str] = []
    for bar in bars:
        bucket = floor_logic_bar_datetime(bar.datetime, higher_minutes)
        higher_index = bucket_index_map.get(bucket)
        if higher_index is None:
            mapped_phase_names.append("未就绪")
            mapped_direction_names.append("中性")
            continue
        mapped_phase_names.append(higher_analysis.structure_phase_names[higher_index])
        mapped_direction_names.append(higher_analysis.direction_names[higher_index])

    return mapped_phase_names, mapped_direction_names


def aggregate_logic_bars_to_minutes(
    bars: list[BarData],
    target_minutes: int,
) -> list[BarData]:
    """在逻辑层内聚合到更高分钟周期。"""
    if not bars:
        return []

    aggregated: list[BarData] = []
    current_bar: BarData | None = None
    current_bucket = None

    for bar in bars:
        bucket = floor_logic_bar_datetime(bar.datetime, target_minutes)
        if current_bucket != bucket or current_bar is None:
            if current_bar is not None:
                aggregated.append(current_bar)
            current_bucket = bucket
            current_bar = BarData(
                gateway_name=bar.gateway_name,
                symbol=bar.symbol,
                exchange=bar.exchange,
                datetime=bucket,
                interval=bar.interval,
                open_price=bar.open_price,
                high_price=bar.high_price,
                low_price=bar.low_price,
                close_price=bar.close_price,
                volume=bar.volume,
                turnover=bar.turnover,
                open_interest=bar.open_interest,
            )
            continue

        current_bar.high_price = max(current_bar.high_price, bar.high_price)
        current_bar.low_price = min(current_bar.low_price, bar.low_price)
        current_bar.close_price = bar.close_price
        current_bar.volume += bar.volume
        current_bar.turnover += bar.turnover
        current_bar.open_interest = bar.open_interest

    if current_bar is not None:
        aggregated.append(current_bar)
    return aggregated


def floor_logic_bar_datetime(
    dt: object,
    target_minutes: int,
) -> object:
    """按分钟数对齐时间。"""
    if target_minutes >= 24 * 60:
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if target_minutes >= 60:
        hour_window = max(target_minutes // 60, 1)
        hour = (dt.hour // hour_window) * hour_window
        return dt.replace(hour=hour, minute=0, second=0, microsecond=0)
    minute = (dt.minute // target_minutes) * target_minutes
    return dt.replace(minute=minute, second=0, microsecond=0)


def deduplicate_levels(
    levels: list[float],
    tolerance: float,
) -> list[float]:
    """去掉彼此太接近的重复关键位。"""
    unique_levels: list[float] = []
    for level in sorted(levels):
        if any(abs(level - existing) <= tolerance for existing in unique_levels):
            continue
        unique_levels.append(level)
    return unique_levels


def passes_higher_timeframe_breakout_filter(
    index: int,
    direction: str,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
    context: StructureContext,
    higher_structure_phase_names: list[str] | None,
    higher_direction_names: list[str] | None,
) -> bool:
    """让更高周期背景参与突破事件过滤。"""
    if not higher_structure_phase_names or index >= len(higher_structure_phase_names):
        return True

    higher_phase = higher_structure_phase_names[index]
    higher_direction = higher_direction_names[index] if higher_direction_names and index < len(higher_direction_names) else "中性"
    if higher_phase in {"未就绪", ""}:
        return True

    desired_direction = "多" if direction == "bull" else "空"
    recent = bars[max(0, index - 2):index + 1]
    if len(recent) < 3:
        return False

    avg_range = max(range_ma[index], 1e-12)
    current_bar = bars[index]
    if direction == "bull":
        recent_move = recent[-1].close_price - recent[0].open_price
        consecutive_trend_bars = count_consecutive_trend_bars(index, bars, "bull")
        ema_side_count = count_recent_ema_side(index, bars, ema_values, "bull", 3)
        directional_pressure = sum(1 for bar in recent if is_bull_trend_bar(bar))
        current_bar_is_trend = is_bull_trend_bar(current_bar)
    else:
        recent_move = recent[0].open_price - recent[-1].close_price
        consecutive_trend_bars = count_consecutive_trend_bars(index, bars, "bear")
        ema_side_count = count_recent_ema_side(index, bars, ema_values, "bear", 3)
        directional_pressure = sum(1 for bar in recent if is_bear_trend_bar(bar))
        current_bar_is_trend = is_bear_trend_bar(current_bar)

    raw_phase = infer_raw_structure_phase_from_context(context)
    surprise_breakout = (
        recent_move >= avg_range * 1.20
        and ema_side_count >= 2
        and (directional_pressure >= 2 or consecutive_trend_bars >= 2)
    )
    strong_breakout = (
        recent_move >= avg_range * 1.55
        and ema_side_count >= 2
        and consecutive_trend_bars >= 2
        and current_bar_is_trend
    )

    if higher_direction in {"多", "空"} and higher_direction != desired_direction:
        if higher_phase == "窄幅通道":
            return strong_breakout
        if higher_phase == "宽幅通道":
            return strong_breakout or raw_phase == "窄幅通道"
        if higher_phase in {"趋势交易区间", "震荡"}:
            return strong_breakout

    if higher_phase == "窄幅通道":
        return True
    if higher_phase == "宽幅通道":
        return (
            strong_breakout
            or (
                raw_phase == "窄幅通道"
                or (
                    float(context.short_metrics["progress_ratio"]) >= 0.28
                    and context.geometry_quality_score >= 0.22
                    and context.trend_touch_score >= 0.35
                )
            )
        )
    if higher_phase in {"趋势交易区间", "震荡"}:
        if raw_phase in {"震荡", "趋势交易区间"}:
            return surprise_breakout
        return surprise_breakout or raw_phase == "窄幅通道"
    return True


def is_signal_context_supported(
    analysis: BrooksAnalysis,
    index: int,
    direction: str,
    *,
    signal_family: str,
) -> bool:
    """统一判断 H1/H2/L1/L2 与 MAG 的背景是否支持。"""
    if index < 20 or index >= len(analysis.structure_phase_names):
        return False

    context = analysis.structure_contexts[index]
    if context is None:
        return False

    desired_direction = "bull" if direction == "bull" else "bear"
    if context.direction != desired_direction:
        return False

    structure_name = analysis.structure_phase_names[index]
    higher_phase = analysis.higher_structure_phase_names[index] if index < len(analysis.higher_structure_phase_names) else "未就绪"
    higher_direction = analysis.higher_direction_names[index] if index < len(analysis.higher_direction_names) else "中性"
    event_name = analysis.breakout_event_names[index] if index < len(analysis.breakout_event_names) else "无事件"

    if higher_direction in {"多", "空"}:
        higher_direction_key = "bull" if higher_direction == "多" else "bear"
        if higher_direction_key != desired_direction and structure_name != "窄幅通道":
            return False

    if structure_name in {"未就绪", "震荡"}:
        return False

    if signal_family == "mag":
        if context.ema_touch_ratio >= 0.58:
            return False
        if structure_name == "趋势交易区间":
            return (
                higher_phase in {"窄幅通道", "宽幅通道"}
                and context.geometry_quality_score >= 0.24
                and context.directional_swing_score >= 0.26
            )
        if structure_name == "宽幅通道":
            return context.geometry_quality_score >= 0.20 and context.channel_span_ratio >= 0.32
        return True

    if structure_name == "窄幅通道":
        return True
    if structure_name == "宽幅通道":
        return (
            context.geometry_quality_score >= 0.22
            and context.channel_span_ratio >= 0.28
            and (
                context.magnet_reaction_score >= 0.12
                or context.trend_touch_score >= 0.45
            )
        )
    if structure_name == "趋势交易区间":
        return (
            (
                event_name in {"突破跟进", "突破测试"}
                or float(context.long_metrics["progress_ratio"]) >= 0.18
            )
            and context.geometry_quality_score >= 0.26
            and context.trendline_alignment >= 0.22
            and higher_phase != "震荡"
        )
    return False


def is_trading_range_phase(metrics: dict[str, float | int | str]) -> bool:
    """判断是否属于震荡背景。"""
    if metrics["direction"] == "neutral":
        return True

    progress_ratio = float(metrics["progress_ratio"])
    pullback_depth_ratio = float(metrics["pullback_depth_ratio"])
    dominance_ratio = float(metrics["dominance_ratio"])
    slope_in_range = float(metrics["slope_in_range"])
    overlap_ratio = float(metrics["overlap_ratio"])
    reversal_count = int(metrics["reversal_count"])
    crosses = int(metrics["crosses"])

    if dominance_ratio >= 0.82 and slope_in_range >= 1.0 and progress_ratio >= 0.32:
        return False
    if progress_ratio >= 0.38 and pullback_depth_ratio <= 3.2 and float(metrics["window_span_ratio"]) >= 3.4:
        return False
    if progress_ratio <= 0.18:
        return True
    if progress_ratio <= 0.26 and reversal_count >= 3:
        return True

    score = 0
    if reversal_count >= 3:
        score += 1
    if crosses >= 3:
        score += 1
    if overlap_ratio >= 0.62:
        score += 1
    if float(metrics["efficiency"]) <= 0.33:
        score += 1
    if dominance_ratio <= 0.74:
        score += 1
    if slope_in_range <= 0.9:
        score += 1
    if progress_ratio <= 0.30:
        score += 1

    return score >= 4 or (score >= 3 and progress_ratio <= 0.32)


def is_narrow_channel_phase(metrics: dict[str, float | int | str]) -> bool:
    """判断是否属于窄幅通道。"""
    direction = metrics["direction"]
    if direction == "neutral":
        return False

    return (
        float(metrics["dominance_ratio"]) >= 0.72
        and float(metrics["progress_ratio"]) >= 0.58
        and float(metrics["pullback_depth_ratio"]) <= 1.35
        and float(metrics["trend_bar_ratio"]) >= 0.18
        and float(metrics["opposite_bar_ratio"]) <= 0.42
        and float(metrics["overlap_ratio"]) <= 0.78
        and int(metrics["reversal_count"]) <= 2
        and float(metrics["crosses"]) <= 2
        and float(metrics["slope_in_range"]) >= 0.85
        and float(metrics["window_span_ratio"]) >= 2.8
    )


def is_broad_channel_phase(metrics: dict[str, float | int | str]) -> bool:
    """判断是否属于宽幅通道。"""
    direction = metrics["direction"]
    if direction == "neutral":
        return False
    if is_narrow_channel_phase(metrics):
        return False

    return (
        float(metrics["dominance_ratio"]) >= 0.72
        and float(metrics["progress_ratio"]) >= 0.30
        and float(metrics["pullback_depth_ratio"]) >= 0.95
        and float(metrics["pullback_depth_ratio"]) <= 3.8
        and float(metrics["trend_bar_ratio"]) >= 0.14
        and float(metrics["slope_in_range"]) >= 0.75
        and int(metrics["reversal_count"]) <= 4
        and float(metrics["window_span_ratio"]) >= 3.0
        and float(metrics["overlap_ratio"]) >= 0.50
        and float(metrics["overlap_ratio"]) <= 0.95
    )


def is_trending_trading_range_phase_from_context(context: StructureContext) -> bool:
    """判断是否属于 Brooks 原文里的趋势交易区间。"""
    short_metrics = context.short_metrics
    long_metrics = context.long_metrics
    if context.direction == "neutral":
        return False
    if is_narrow_channel_phase(short_metrics):
        return False

    return (
        float(long_metrics["progress_ratio"]) >= 0.12
        and float(long_metrics["window_span_ratio"]) >= 3.2
        and (
            float(long_metrics["overlap_ratio"]) >= 0.58
            or context.ema_touch_ratio >= 0.32
        )
        and (
            int(long_metrics["reversal_count"]) >= 5
            or int(long_metrics["crosses"]) >= 4
            or context.leg_count >= 5
        )
        and context.directional_swing_score >= 0.22
        and (
            context.magnet_confluence_score >= 0.25
            or context.magnet_reaction_score >= 0.25
            or context.ema_touch_ratio >= 0.32
        )
        and context.geometry_quality_score >= 0.18
        and context.channel_span_ratio >= 0.22
    )


def is_broad_channel_phase_from_context(context: StructureContext) -> bool:
    """按 Brooks 的“倾斜交易区间”口径识别宽幅通道。"""
    short_metrics = context.short_metrics
    long_metrics = context.long_metrics
    if context.direction == "neutral":
        return False
    if is_narrow_channel_phase(short_metrics):
        return False

    return (
        float(long_metrics["progress_ratio"]) >= 0.18
        and float(long_metrics["window_span_ratio"]) >= 3.6
        and context.leg_count >= 4
        and context.directional_swing_score >= 0.32
        and context.trendline_alignment >= 0.18
        and context.geometry_quality_score >= 0.20
        and context.channel_span_ratio >= 0.26
        and (
            float(long_metrics["overlap_ratio"]) >= 0.50
            or context.ema_touch_ratio >= 0.24
        )
        and (
            float(short_metrics["pullback_depth_ratio"]) >= 0.90
            or float(long_metrics["pullback_depth_ratio"]) >= 2.2
        )
        and (
            context.magnet_reaction_score >= 0.12
            or context.trend_touch_score >= 0.50
        )
    )


def is_narrow_channel_phase_from_context(context: StructureContext) -> bool:
    """按短窗强单边、长窗仍顺向的口径识别紧密通道。"""
    short_metrics = context.short_metrics
    long_metrics = context.long_metrics
    if context.direction == "neutral":
        return False

    return (
        is_narrow_channel_phase(short_metrics)
        and float(long_metrics["progress_ratio"]) >= 0.18
        and context.ema_touch_ratio <= 0.44
        and context.counter_swing_score <= 0.62
        and context.magnet_confluence_score <= 0.55
        and context.breach_ratio <= 0.32
    )


def infer_raw_structure_phase(metrics: dict[str, float | int | str]) -> str:
    """把结构特征先映射成互斥的原始结构状态。"""
    if is_narrow_channel_phase(metrics):
        return "窄幅通道"
    if is_broad_channel_phase(metrics):
        return "宽幅通道"
    if is_trading_range_phase(metrics):
        return "震荡"

    if (
        metrics["direction"] != "neutral"
        and float(metrics["dominance_ratio"]) >= 0.80
        and float(metrics["slope_in_range"]) >= 0.90
        and float(metrics["progress_ratio"]) >= 0.28
    ):
        return "宽幅通道"
    return "震荡"


def infer_raw_structure_phase_from_context(context: StructureContext) -> str:
    """按多窗口与通道结构映射原始结构状态。"""
    if is_narrow_channel_phase_from_context(context):
        return "窄幅通道"
    if is_broad_channel_phase_from_context(context):
        return "宽幅通道"
    if is_trending_trading_range_phase_from_context(context):
        return "趋势交易区间"
    if is_trading_range_phase(context.short_metrics) and is_trading_range_phase(context.long_metrics):
        return "震荡"
    if (
        context.direction != "neutral"
        and float(context.long_metrics["progress_ratio"]) >= 0.16
        and context.directional_swing_score >= 0.20
        and context.geometry_quality_score >= 0.18
    ):
        return "趋势交易区间"
    return "震荡"


def required_structure_confirmation(
    current_state: str,
    proposed_state: str,
    event_name: str,
    context: StructureContext,
) -> int:
    """用最小确认根数减少结构层的一两根抖动。"""
    if proposed_state == current_state:
        return 0
    if event_name in {"突破起爆", "突破跟进"} and proposed_state == "窄幅通道":
        return 1
    if current_state == "震荡" and proposed_state == "宽幅通道":
        return 3
    if current_state == "震荡" and proposed_state == "趋势交易区间":
        return 2
    if current_state == "震荡" and proposed_state == "窄幅通道":
        return 2
    if current_state == "窄幅通道" and proposed_state == "宽幅通道":
        return 2
    if current_state == "窄幅通道" and proposed_state == "趋势交易区间":
        return 2
    if current_state == "宽幅通道" and proposed_state == "震荡":
        return 2
    if current_state == "宽幅通道" and proposed_state == "趋势交易区间":
        return 2
    if current_state == "趋势交易区间" and proposed_state == "宽幅通道":
        return 2
    if current_state == "趋势交易区间" and proposed_state == "震荡":
        return 2
    if current_state == "窄幅通道" and proposed_state == "震荡":
        return 2
    return 2


def infer_context_direction(context: StructureContext) -> str:
    """把多窗口上下文的方向映射成中文。"""
    if context.direction == "bull":
        return "多"
    if context.direction == "bear":
        return "空"
    return "中性"


def infer_metrics_direction(metrics: dict[str, float | int | str]) -> str:
    """把结构指标的方向映射成中文。"""
    direction = metrics["direction"]
    if direction == "bull":
        return "多"
    if direction == "bear":
        return "空"
    return "中性"


def count_recent_ema_side(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    direction: str,
    length: int,
) -> int:
    """统计最近若干根 K 线收盘在 EMA 优势侧的次数。"""
    start = max(0, index - length + 1)
    count = 0
    for offset in range(start, index + 1):
        bar = bars[offset]
        ema_value = ema_values[offset]
        if direction == "bull" and bar.close_price >= ema_value:
            count += 1
        elif direction == "bear" and bar.close_price <= ema_value:
            count += 1
    return count


def count_consecutive_gap_bars(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    direction: str,
) -> int:
    """统计当前信号柱之前连续未触及 EMA 的根数。"""
    if index <= 0:
        return 0

    gap_count = 0
    for cursor in range(index - 1, -1, -1):
        bar = bars[cursor]
        ema_value = ema_values[cursor]
        if direction == "bull":
            if bar.low_price > ema_value:
                gap_count += 1
                continue
        else:
            if bar.high_price < ema_value:
                gap_count += 1
                continue
        break
    return gap_count


def count_consecutive_trend_bars(index: int, bars: list[BarData], direction: str) -> int:
    """统计截至当前连续的趋势棒数量。"""
    count = 0
    cursor = index

    while cursor >= 0:
        bar = bars[cursor]
        if direction == "bull" and is_bull_trend_bar(bar):
            count += 1
            cursor -= 1
            continue
        if direction == "bear" and is_bear_trend_bar(bar):
            count += 1
            cursor -= 1
            continue
        break

    return count


def is_surprise_breakout_bar(bar: BarData, direction: str, avg_range: float) -> bool:
    """判断是否属于 surprise breakout bar。"""
    bar_range = get_bar_range(bar)
    body = get_bar_body(bar)
    if direction == "bull":
        return (
            is_bull_trend_bar(bar)
            and body >= avg_range * 0.55
            and bar_range >= avg_range * 0.95
        )
    return (
        is_bear_trend_bar(bar)
        and body >= avg_range * 0.55
        and bar_range >= avg_range * 0.95
    )


def is_bull_trend_bar(bar: BarData) -> bool:
    """判断是否为收在高位附近的强多头趋势棒。"""
    bar_range = get_bar_range(bar)
    close_position = (bar.close_price - bar.low_price) / bar_range
    body_ratio = get_bar_body(bar) / bar_range
    return (
        bar.close_price > bar.open_price
        and close_position >= 0.68
        and body_ratio >= 0.5
    )


def is_bear_trend_bar(bar: BarData) -> bool:
    """判断是否为收在低位附近的强空头趋势棒。"""
    bar_range = get_bar_range(bar)
    close_position = (bar.close_price - bar.low_price) / bar_range
    body_ratio = get_bar_body(bar) / bar_range
    return (
        bar.close_price < bar.open_price
        and close_position <= 0.32
        and body_ratio >= 0.5
    )


def get_bar_range(bar: BarData) -> float:
    """获取 K 线总波幅。"""
    return max(bar.high_price - bar.low_price, 1e-12)


def get_bar_body(bar: BarData) -> float:
    """获取 K 线实体大小。"""
    return abs(bar.close_price - bar.open_price)


def is_pullback_start_for_bull(index: int, bars: list[BarData], ema_values: list[float]) -> bool:
    """判断多头回调是否开始。"""
    bar: BarData = bars[index]
    prev_bar: BarData = bars[index - 1]
    return (
        bar.low_price < prev_bar.low_price
        or bar.close_price < prev_bar.close_price
        or bar.close_price < ema_values[index]
        or bar.close_price < bar.open_price
    )


def is_pullback_start_for_bear(index: int, bars: list[BarData], ema_values: list[float]) -> bool:
    """判断空头反弹是否开始。"""
    bar: BarData = bars[index]
    prev_bar: BarData = bars[index - 1]
    return (
        bar.high_price > prev_bar.high_price
        or bar.close_price > prev_bar.close_price
        or bar.close_price > ema_values[index]
        or bar.close_price > bar.open_price
    )


def is_first_bar_of_up_attempt(index: int, bars: list[BarData]) -> bool:
    """判断是否是一次新的向上尝试的起点。"""
    if bars[index].high_price <= bars[index - 1].high_price:
        return False

    return bars[index - 1].high_price <= bars[index - 2].high_price


def is_first_bar_of_down_attempt(index: int, bars: list[BarData]) -> bool:
    """判断是否是一次新的向下尝试的起点。"""
    if bars[index].low_price >= bars[index - 1].low_price:
        return False

    return bars[index - 1].low_price >= bars[index - 2].low_price


def is_near_ema_for_bull(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
) -> bool:
    """判断做多信号柱是否靠近 EMA20。"""
    threshold: float = max(range_ma[index] * 0.6, 1e-8)
    bar: BarData = bars[index]
    return abs(bar.low_price - ema_values[index]) <= threshold


def is_near_ema_for_bear(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
) -> bool:
    """判断做空信号柱是否靠近 EMA20。"""
    threshold: float = max(range_ma[index] * 0.6, 1e-8)
    bar: BarData = bars[index]
    return abs(bar.high_price - ema_values[index]) <= threshold


def evaluate_bull_signal_quality(bar: BarData) -> str:
    """评估多头 signal bar 的质量。"""
    bar_range: float = max(bar.high_price - bar.low_price, 1e-12)
    close_position: float = (bar.close_price - bar.low_price) / bar_range
    upper_tail: float = bar.high_price - max(bar.open_price, bar.close_price)

    if (
        bar.close_price > bar.open_price
        and close_position >= 0.7
        and upper_tail <= bar_range * 0.25
    ):
        return "强"

    if close_position >= 0.55:
        return "中"

    return "弱"


def evaluate_bear_signal_quality(bar: BarData) -> str:
    """评估空头 signal bar 的质量。"""
    bar_range: float = max(bar.high_price - bar.low_price, 1e-12)
    close_position: float = (bar.close_price - bar.low_price) / bar_range
    lower_tail: float = min(bar.open_price, bar.close_price) - bar.low_price

    if (
        bar.close_price < bar.open_price
        and close_position <= 0.3
        and lower_tail <= bar_range * 0.25
    ):
        return "强"

    if close_position <= 0.45:
        return "中"

    return "弱"


def confirm_buy_trigger(index: int, bars: list[BarData], entry: float, stop: float) -> int:
    """确认做多信号是否在 3 根 K 线内触发。"""
    max_index: int = min(len(bars), index + 4)
    for i in range(index + 1, max_index):
        if bars[i].low_price <= stop:
            return -1
        if bars[i].high_price >= entry:
            return i
    return -1


def confirm_sell_trigger(index: int, bars: list[BarData], entry: float, stop: float) -> int:
    """确认做空信号是否在 3 根 K 线内触发。"""
    max_index: int = min(len(bars), index + 4)
    for i in range(index + 1, max_index):
        if bars[i].high_price >= stop:
            return -1
        if bars[i].low_price <= entry:
            return i
    return -1


def choose_buy_target(prior_swing_high: float, entry: float, stop: float) -> float:
    """选择做多第一目标。"""
    actual_risk: float = max(entry - stop, 1e-12)
    if prior_swing_high > entry:
        return prior_swing_high
    return entry + actual_risk * 2


def choose_sell_target(prior_swing_low: float, entry: float, stop: float) -> float:
    """选择做空第一目标。"""
    actual_risk: float = max(stop - entry, 1e-12)
    if prior_swing_low < entry:
        return prior_swing_low
    return entry - actual_risk * 2


def find_recent_breakout_reference(
    index: int,
    bars: list[BarData],
    breakout_event_names: list[str],
    *,
    direction: str,
    lookback: int = 8,
) -> tuple[int, float] | None:
    """寻找最近仍有效的突破点。"""
    if index <= 0 or not breakout_event_names:
        return None

    breakout_index = -1
    search_start = max(0, index - lookback)
    for cursor in range(index, search_start - 1, -1):
        if cursor >= len(breakout_event_names):
            continue
        if breakout_event_names[cursor] == "突破起爆":
            breakout_index = cursor
            break
    if breakout_index < 0:
        return None

    prior_window = bars[max(0, breakout_index - 14):breakout_index]
    if len(prior_window) < 5:
        return None

    if direction == "bull":
        breakout_point = max(bar.high_price for bar in prior_window)
    else:
        breakout_point = min(bar.low_price for bar in prior_window)
    return breakout_index, breakout_point


def is_near_breakout_point(
    index: int,
    bars: list[BarData],
    range_ma: list[float],
    breakout_point: float,
    *,
    direction: str,
) -> bool:
    """判断当前 bar 是否回测到突破点附近。"""
    avg_range = max(range_ma[index], 1e-12)
    bar = bars[index]
    if direction == "bull":
        touched = bar.low_price <= breakout_point + avg_range * 0.30
        held = bar.close_price >= breakout_point - avg_range * 0.10
        return touched and held

    touched = bar.high_price >= breakout_point - avg_range * 0.30
    held = bar.close_price <= breakout_point + avg_range * 0.10
    return touched and held


def is_breakout_pullback_signal_bar(
    index: int,
    bars: list[BarData],
    ema_values: list[float],
    range_ma: list[float],
    breakout_point: float,
    *,
    direction: str,
) -> bool:
    """判断突破后的回测 bar 是否更像趋势恢复 signal bar。"""
    avg_range = max(range_ma[index], 1e-12)
    bar = bars[index]
    ema_value = ema_values[index]
    body_ratio = get_bar_body(bar) / get_bar_range(bar)
    prev_bar = bars[index - 1] if index > 0 else bar
    prior_test = index > 0 and is_near_breakout_point(index - 1, bars, range_ma, breakout_point, direction=direction)

    if direction == "bull":
        return (
            bar.close_price > bar.open_price
            and body_ratio >= 0.38
            and (
                is_near_breakout_point(index, bars, range_ma, breakout_point, direction=direction)
                or prior_test
            )
            and (
                bar.close_price >= prev_bar.close_price + avg_range * 0.04
                or bar.high_price >= prev_bar.high_price - avg_range * 0.08
            )
            and (bar.close_price >= ema_value or bar.low_price <= ema_value + avg_range * 0.18 or prior_test)
        )

    return (
        bar.close_price < bar.open_price
        and body_ratio >= 0.38
        and (
            is_near_breakout_point(index, bars, range_ma, breakout_point, direction=direction)
            or prior_test
        )
        and (
            bar.close_price <= prev_bar.close_price - avg_range * 0.04
            or bar.low_price <= prev_bar.low_price + avg_range * 0.08
        )
        and (bar.close_price <= ema_value or bar.high_price >= ema_value - avg_range * 0.18 or prior_test)
    )
