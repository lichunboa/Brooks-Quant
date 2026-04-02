from datetime import datetime, timedelta
import unittest

from brooks_chart_app.logic import (
    build_opening_range_markers,
    build_brooks_annotations,
    calculate_ema,
    calculate_range_ma,
    calculate_structure_metrics,
    detect_bar_patterns,
    detect_measured_move_markers,
    detect_micro_gaps,
    is_broad_channel_phase,
    is_trading_range_phase,
    resolve_logic_higher_timeframe_minutes,
    select_channel_geometry,
)
from brooks_chart_app.ui import DISPLAY_INTERVAL_MAP, aggregate_bars_to_interval, resolve_higher_timeframe_option
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData


def make_bar(index: int, open_price: float, high_price: float, low_price: float, close_price: float) -> BarData:
    return BarData(
        gateway_name="TEST",
        symbol="TEST",
        exchange=Exchange.LOCAL,
        datetime=datetime(2024, 1, 1) + timedelta(minutes=index),
        interval=Interval.MINUTE,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
    )


def build_balanced_range(count: int) -> list[BarData]:
    bars: list[BarData] = []
    for index in range(count):
        base = 100.0 + (0.18 if index % 4 in {0, 1} else -0.18)
        if index % 2 == 0:
            open_price = base - 0.08
            close_price = base + 0.08
        else:
            open_price = base + 0.08
            close_price = base - 0.08
        high_price = max(open_price, close_price) + 0.15
        low_price = min(open_price, close_price) - 0.15
        bars.append(make_bar(index, open_price, high_price, low_price, close_price))
    return bars


def build_tight_bull_channel(count: int) -> list[BarData]:
    bars: list[BarData] = []
    price = 100.0
    for index in range(count):
        open_price = price + (0.04 if index % 3 == 0 else 0.08)
        close_price = open_price + (0.22 if index % 4 != 0 else -0.03)
        high_price = max(open_price, close_price) + 0.08
        low_price = min(open_price, close_price) - 0.05
        bars.append(make_bar(index, open_price, high_price, low_price, close_price))
        price = close_price + 0.06
    return bars


def build_broad_bull_channel(count: int) -> list[BarData]:
    bars: list[BarData] = []
    price = 100.0
    for index in range(count):
        swing = 0.55 if index % 5 in {0, 1} else -0.18 if index % 5 == 2 else 0.24
        open_price = price
        close_price = price + swing
        high_price = max(open_price, close_price) + 0.28
        low_price = min(open_price, close_price) - 0.24
        bars.append(make_bar(index, open_price, high_price, low_price, close_price))
        price = close_price + (0.04 if index % 2 == 0 else -0.02)
    return bars


def build_normal_cycle_to_broad_channel() -> list[BarData]:
    bars = build_balanced_range(20)
    bars.extend(
        [
            make_bar(20, 100.20, 101.60, 100.18, 101.40),
            make_bar(21, 101.35, 102.55, 101.20, 102.30),
            make_bar(22, 102.28, 103.10, 102.10, 103.00),
            make_bar(23, 103.02, 103.38, 102.62, 102.78),
            make_bar(24, 102.80, 103.85, 102.72, 103.46),
            make_bar(25, 103.42, 103.58, 102.74, 102.92),
            make_bar(26, 102.94, 104.02, 102.86, 103.74),
            make_bar(27, 103.70, 103.92, 102.98, 103.16),
            make_bar(28, 103.20, 104.18, 103.12, 103.96),
            make_bar(29, 103.94, 104.14, 103.18, 103.34),
            make_bar(30, 103.30, 104.32, 103.24, 104.08),
            make_bar(31, 104.02, 104.18, 103.32, 103.52),
            make_bar(32, 103.50, 104.45, 103.44, 104.22),
            make_bar(33, 104.20, 104.34, 103.56, 103.74),
        ]
    )
    return bars


def build_breakout_then_test() -> list[BarData]:
    bars = build_balanced_range(20)
    bars.extend(
        [
            make_bar(20, 100.20, 101.60, 100.18, 101.40),
            make_bar(21, 101.35, 102.55, 101.20, 102.30),
            make_bar(22, 102.00, 102.45, 101.90, 102.35),
            make_bar(23, 101.70, 101.95, 100.48, 101.00),
            make_bar(24, 100.95, 101.45, 100.88, 101.32),
        ]
    )
    return bars


def build_surprise_bear_breakout() -> list[BarData]:
    bars = build_balanced_range(20)
    bars.extend(
        [
            make_bar(20, 100.10, 100.22, 99.92, 100.02),
            make_bar(21, 100.00, 100.08, 99.84, 99.90),
            make_bar(22, 99.88, 99.92, 98.72, 98.84),
            make_bar(23, 98.82, 98.90, 98.10, 98.22),
        ]
    )
    return bars


def build_bull_trending_trading_range() -> list[BarData]:
    bars = build_balanced_range(20)
    bars.extend(
        [
            make_bar(20, 100.20, 101.60, 100.10, 101.40),
            make_bar(21, 101.35, 102.60, 101.20, 102.30),
            make_bar(22, 102.28, 102.46, 101.55, 101.84),
            make_bar(23, 101.82, 102.32, 101.60, 102.14),
            make_bar(24, 102.12, 102.22, 101.22, 101.44),
            make_bar(25, 101.46, 102.04, 101.30, 101.88),
            make_bar(26, 101.86, 101.96, 101.02, 101.28),
            make_bar(27, 101.30, 101.92, 101.16, 101.72),
            make_bar(28, 101.70, 101.82, 100.92, 101.10),
            make_bar(29, 101.12, 101.84, 100.98, 101.64),
            make_bar(30, 101.62, 101.70, 100.88, 101.06),
            make_bar(31, 101.08, 101.86, 100.96, 101.74),
        ]
    )
    return bars


def build_linear_minute_bars(count: int) -> list[BarData]:
    bars: list[BarData] = []
    price = 100.0
    for index in range(count):
        open_price = price
        close_price = price + 0.2
        high_price = close_price + 0.05
        low_price = open_price - 0.05
        bars.append(make_bar(index, open_price, high_price, low_price, close_price))
        price = close_price
    return bars


def build_pattern_bars() -> list[BarData]:
    return [
        make_bar(0, 10.0, 20.0, 10.0, 18.0),
        make_bar(1, 12.0, 18.0, 12.0, 17.0),
        make_bar(2, 13.0, 17.0, 13.0, 16.0),
        make_bar(3, 15.0, 19.0, 12.0, 18.0),
        make_bar(4, 15.5, 18.0, 13.0, 14.0),
        make_bar(5, 14.0, 19.0, 12.0, 18.5),
        make_bar(6, 18.5, 20.0, 11.0, 11.5),
    ]


def build_micro_gap_bars() -> list[BarData]:
    return [
        make_bar(0, 100.0, 101.0, 99.8, 100.4),
        make_bar(1, 100.5, 102.0, 100.4, 101.9),
        make_bar(2, 101.7, 103.0, 101.3, 102.8),
        make_bar(3, 102.6, 102.8, 100.6, 100.8),
        make_bar(4, 100.7, 100.9, 99.2, 99.3),
    ]


def build_opening_range_bars() -> list[BarData]:
    bars: list[BarData] = []
    for index in range(18):
        high = 100.5 + (index % 4) * 0.05
        low = 99.5 - (index % 3) * 0.03
        bars.append(make_bar(index, 100.0, high, low, 100.0 + (index % 2) * 0.02))
    bars.append(make_bar(18, 100.2, 101.6, 100.1, 101.4))
    bars.append(make_bar(19, 101.4, 101.8, 101.1, 101.6))
    return bars


def build_open_bom_bars() -> list[BarData]:
    bars = [
        make_bar(0, 100.0, 100.8, 99.8, 100.6),
        make_bar(1, 100.6, 101.0, 100.2, 100.9),
        make_bar(2, 100.9, 101.1, 99.6, 99.8),
        make_bar(3, 99.8, 100.3, 99.4, 100.2),
    ]
    for index in range(4, 20):
        bars.append(make_bar(index, 100.0, 100.4, 99.7, 100.1))
    return bars


def build_measured_move_bars() -> list[BarData]:
    return [
        make_bar(0, 100.0, 100.4, 99.8, 100.2),
        make_bar(1, 100.2, 100.6, 99.6, 100.0),
        make_bar(2, 100.5, 101.0, 100.4, 100.9),
        make_bar(3, 100.9, 102.2, 100.8, 102.0),
        make_bar(4, 102.0, 101.8, 101.0, 101.2),
        make_bar(5, 101.2, 101.4, 100.2, 100.4),
        make_bar(6, 100.4, 100.8, 100.0, 100.6),
        make_bar(7, 100.6, 101.0, 100.5, 100.9),
        make_bar(8, 100.9, 101.3, 100.8, 101.1),
        make_bar(9, 101.1, 101.8, 101.0, 101.7),
    ]


def build_tr_measured_move_bars() -> list[BarData]:
    return [
        make_bar(0, 100.0, 100.6, 99.7, 100.3),
        make_bar(1, 100.3, 100.7, 99.8, 100.0),
        make_bar(2, 100.0, 100.8, 99.9, 100.4),
        make_bar(3, 100.4, 100.75, 99.85, 100.1),
        make_bar(4, 100.1, 100.7, 99.9, 100.5),
        make_bar(5, 100.5, 100.78, 99.88, 100.2),
        make_bar(6, 100.25, 101.6, 100.2, 101.45),
        make_bar(7, 101.4, 101.7, 101.1, 101.55),
    ]


def build_bo_measured_move_bars() -> list[BarData]:
    return [
        make_bar(0, 100.0, 100.3, 99.8, 100.1),
        make_bar(1, 100.1, 100.4, 99.9, 100.2),
        make_bar(2, 100.2, 100.45, 100.0, 100.1),
        make_bar(3, 100.1, 100.35, 99.95, 100.15),
        make_bar(4, 100.15, 100.4, 100.0, 100.2),
        make_bar(5, 100.2, 102.0, 100.15, 101.9),
        make_bar(6, 101.9, 102.1, 101.6, 101.8),
    ]


def build_measuring_gap_bars() -> list[BarData]:
    return [
        make_bar(0, 100.0, 100.3, 99.8, 100.1),
        make_bar(1, 100.1, 100.35, 99.9, 100.0),
        make_bar(2, 100.0, 100.4, 99.95, 100.2),
        make_bar(3, 100.2, 100.38, 100.0, 100.1),
        make_bar(4, 100.1, 100.45, 99.98, 100.25),
        make_bar(5, 100.25, 102.1, 100.2, 101.95),
        make_bar(6, 101.95, 102.2, 101.2, 101.35),
        make_bar(7, 101.35, 101.9, 101.1, 101.75),
        make_bar(8, 101.75, 102.5, 101.7, 102.35),
    ]


def build_opening_reversal_bars() -> list[BarData]:
    bars: list[BarData] = [
        make_bar(0, 100.0, 100.4, 99.8, 100.2),
        make_bar(1, 100.2, 100.3, 99.4, 99.5),
        make_bar(2, 99.5, 99.7, 99.1, 99.2),
        make_bar(3, 99.2, 100.55, 99.1, 100.45),
    ]
    for index in range(4, 24):
        bars.append(make_bar(index, 100.2, 100.45, 99.95, 100.15))
    return bars


def build_negative_measuring_gap_bars() -> list[BarData]:
    return [
        make_bar(0, 100.0, 100.3, 99.8, 100.1),
        make_bar(1, 100.1, 100.35, 99.9, 100.0),
        make_bar(2, 100.0, 100.4, 99.95, 100.2),
        make_bar(3, 100.2, 100.38, 100.0, 100.1),
        make_bar(4, 100.1, 100.45, 99.98, 100.25),
        make_bar(5, 100.25, 102.1, 100.2, 101.95),
        make_bar(6, 101.95, 102.0, 100.35, 100.55),
        make_bar(7, 100.55, 101.3, 100.45, 101.1),
        make_bar(8, 101.1, 101.8, 101.0, 101.7),
    ]


def build_midday_reversal_bars() -> list[BarData]:
    bars: list[BarData] = []
    price = 100.0
    for index in range(40):
        if index < 30:
            open_price = price
            close_price = price + 0.18
            high_price = close_price + 0.08
            low_price = open_price - 0.04
        elif index < 35:
            open_price = price
            close_price = price - 0.12
            high_price = open_price + 0.06
            low_price = close_price - 0.18
        else:
            open_price = price
            close_price = price + (0.55 if index == 35 else 0.12)
            high_price = close_price + 0.08
            low_price = open_price - 0.04
        bars.append(make_bar(index, open_price, high_price, low_price, close_price))
        price = close_price
    return bars


class TestBrooksChartLogic(unittest.TestCase):
    def test_calculate_ema_uses_sma_seed_and_brooks_20_bar_definition(self) -> None:
        values = [1, 2, 3, 4, 5]
        ema_values = calculate_ema(values, 3)
        self.assertEqual(ema_values, [1.0, 1.5, 2.0, 3.0, 4.0])

    def test_breakout_phase_marks_strong_bull_burst(self) -> None:
        bars = build_balanced_range(20)
        bars.extend(
            [
                make_bar(20, 100.25, 101.80, 100.20, 101.65),
                make_bar(21, 101.55, 103.20, 101.40, 103.00),
                make_bar(22, 102.95, 104.60, 102.80, 104.35),
                make_bar(23, 104.20, 104.90, 104.00, 104.75),
            ]
        )

        (
            _ema_values,
            _signals,
            background,
            structure_phase_names,
            _structure_phases,
            breakout_event_names,
            _breakout_event_phases,
        ) = build_brooks_annotations(bars, 0.01)

        self.assertIn("结构:", background)
        self.assertIn("事件:", background)
        self.assertIn("突破起爆", breakout_event_names)
        self.assertIn("突破跟进", breakout_event_names)
        self.assertIn(structure_phase_names[22], {"窄幅通道", "宽幅通道", "震荡"})

    def test_breakout_phase_filters_failed_second_leg_trap(self) -> None:
        bars = build_balanced_range(20)
        bars.extend(
            [
                make_bar(20, 100.25, 101.80, 100.20, 101.65),
                make_bar(21, 101.55, 103.20, 101.40, 103.00),
                make_bar(22, 102.95, 104.60, 102.80, 104.35),
                make_bar(23, 104.20, 104.30, 100.10, 100.25),
            ]
        )

        (
            _ema_values,
            _signals,
            _background,
            _structure_phase_names,
            _structure_phases,
            breakout_event_names,
            _breakout_event_phases,
        ) = build_brooks_annotations(bars, 0.01)

        self.assertIn("失败突破", breakout_event_names[20:24])

    def test_structure_layer_marks_tight_channel(self) -> None:
        bars = build_tight_bull_channel(40)
        (
            _ema_values,
            _signals,
            _background,
            structure_phase_names,
            _structure_phases,
            _breakout_event_names,
            _breakout_event_phases,
        ) = build_brooks_annotations(bars, 0.01)

        self.assertEqual(structure_phase_names[-1], "窄幅通道")

    def test_structure_layer_marks_broad_channel(self) -> None:
        bars = build_normal_cycle_to_broad_channel()
        (
            _ema_values,
            _signals,
            _background,
            structure_phase_names,
            _structure_phases,
            _breakout_event_names,
            _breakout_event_phases,
        ) = build_brooks_annotations(bars, 0.01)

        self.assertEqual(structure_phase_names[21], "窄幅通道")
        self.assertIn(structure_phase_names[-1], {"宽幅通道", "趋势交易区间"})
        self.assertNotEqual(structure_phase_names[-1], "震荡")

    def test_directional_broad_channel_metrics_do_not_collapse_into_trading_range(self) -> None:
        bars = build_normal_cycle_to_broad_channel()
        ema_values = calculate_ema([bar.close_price for bar in bars], 20)
        range_ma = calculate_range_ma(bars, 20)
        metrics = calculate_structure_metrics(26, bars, ema_values, range_ma)

        self.assertTrue(is_broad_channel_phase(metrics))
        self.assertFalse(is_trading_range_phase(metrics))
        self.assertGreater(float(metrics["progress_ratio"]), 0.30)
        self.assertGreater(float(metrics["pullback_depth_ratio"]), 1.0)

    def test_breakout_event_marks_first_pullback_test(self) -> None:
        bars = build_breakout_then_test()
        (
            _ema_values,
            _signals,
            _background,
            _structure_phase_names,
            _structure_phases,
            breakout_event_names,
            _breakout_event_phases,
        ) = build_brooks_annotations(bars, 0.01)

        self.assertEqual(breakout_event_names[20], "突破起爆")
        self.assertEqual(breakout_event_names[21], "突破跟进")
        self.assertEqual(breakout_event_names[23], "突破测试")

    def test_surprise_breakout_bar_can_start_breakout_event(self) -> None:
        bars = build_surprise_bear_breakout()
        (
            _ema_values,
            _signals,
            _background,
            _structure_phase_names,
            _structure_phases,
            breakout_event_names,
            _breakout_event_phases,
        ) = build_brooks_annotations(bars, 0.01)

        self.assertEqual(breakout_event_names[22], "突破起爆")

    def test_structure_layer_marks_trending_trading_range(self) -> None:
        bars = build_bull_trending_trading_range()
        (
            _ema_values,
            _signals,
            _background,
            structure_phase_names,
            _structure_phases,
            _breakout_event_names,
            _breakout_event_phases,
        ) = build_brooks_annotations(bars, 0.01)

        self.assertEqual(structure_phase_names[21], "窄幅通道")
        self.assertEqual(structure_phase_names[-1], "趋势交易区间")

    def test_aggregate_bars_to_five_minutes(self) -> None:
        bars = build_linear_minute_bars(12)
        aggregated = aggregate_bars_to_interval(bars, Interval.MINUTE, 5)

        self.assertEqual(len(aggregated), 3)
        self.assertEqual(aggregated[0].datetime.minute, 0)
        self.assertEqual(aggregated[1].datetime.minute, 5)
        self.assertEqual(aggregated[0].open_price, bars[0].open_price)
        self.assertEqual(aggregated[0].close_price, bars[4].close_price)

    def test_aggregate_bars_to_one_hour(self) -> None:
        bars = build_linear_minute_bars(70)
        aggregated = aggregate_bars_to_interval(bars, Interval.HOUR, 1)

        self.assertEqual(len(aggregated), 2)
        self.assertEqual(aggregated[0].datetime.minute, 0)
        self.assertEqual(aggregated[1].datetime.hour, 1)

    def test_resolve_higher_timeframe_option_uses_one_hour_for_intraday_minute_charts(self) -> None:
        self.assertEqual(resolve_higher_timeframe_option(DISPLAY_INTERVAL_MAP["1m"]).key, "1h")
        self.assertEqual(resolve_higher_timeframe_option(DISPLAY_INTERVAL_MAP["5m"]).key, "1h")
        self.assertEqual(resolve_higher_timeframe_option(DISPLAY_INTERVAL_MAP["15m"]).key, "1h")
        self.assertEqual(resolve_higher_timeframe_option(DISPLAY_INTERVAL_MAP["1h"]).key, "1d")

    def test_logic_higher_timeframe_minutes_matches_intraday_workflow(self) -> None:
        self.assertEqual(resolve_logic_higher_timeframe_minutes(1), 60)
        self.assertEqual(resolve_logic_higher_timeframe_minutes(5), 60)
        self.assertEqual(resolve_logic_higher_timeframe_minutes(15), 60)
        self.assertEqual(resolve_logic_higher_timeframe_minutes(60), 1440)

    def test_channel_geometry_prefers_longer_explanatory_span(self) -> None:
        bars = build_broad_bull_channel(40)
        avg_range = sum(bar.high_price - bar.low_price for bar in bars) / len(bars)
        geometry = select_channel_geometry(bars, "bull", avg_range, strength=1)

        self.assertIsNotNone(geometry.trend_anchor1)
        self.assertIsNotNone(geometry.trend_anchor2)
        self.assertGreaterEqual(geometry.anchor_span_bars, 5)
        self.assertGreaterEqual(geometry.quality_score, 0.15)

    def test_detect_bar_patterns_marks_ii_ioi_and_oo(self) -> None:
        bars = build_pattern_bars()
        markers = detect_bar_patterns(bars)
        labels = {(marker.label, marker.anchor_index) for marker in markers}

        self.assertIn(("ii", 2), labels)
        self.assertIn(("ioi", 4), labels)
        self.assertIn(("oo", 6), labels)

    def test_detect_micro_gaps_marks_bull_and_bear_cases(self) -> None:
        bars = build_micro_gap_bars()
        markers = detect_micro_gaps(bars)
        directions = {(marker.direction, marker.center_index) for marker in markers}

        self.assertIn(("bull", 1), directions)
        self.assertIn(("bear", 3), directions)

    def test_build_opening_range_markers_marks_bar18_and_orbo(self) -> None:
        bars = build_opening_range_bars()
        markers = build_opening_range_markers(bars)

        self.assertEqual(len(markers), 1)
        marker = markers[0]
        self.assertEqual(marker.bar18_index, 17)
        self.assertEqual(marker.breakout_index, 18)
        self.assertEqual(marker.breakout_direction, "bull")

    def test_build_opening_range_markers_marks_open_bom(self) -> None:
        bars = build_open_bom_bars()
        markers = build_opening_range_markers(bars)

        self.assertEqual(len(markers), 1)
        marker = markers[0]
        self.assertEqual(marker.bom_index, 2)

    def test_detect_measured_move_markers_marks_abcd_target(self) -> None:
        bars = build_measured_move_bars()
        markers = detect_measured_move_markers(bars, strength=1)

        self.assertTrue(markers)
        last = [marker for marker in markers if marker.label == "Leg1=Leg2↑"][-1]
        self.assertEqual(last.direction, "bull")
        self.assertEqual(last.label, "Leg1=Leg2↑")
        self.assertGreater(last.target_price, bars[last.projection_start_index].high_price)
        self.assertGreaterEqual(last.end_index, last.projection_start_index)

    def test_detect_measured_move_markers_marks_tr_height_target(self) -> None:
        bars = build_tr_measured_move_bars()
        markers = detect_measured_move_markers(bars, strength=1)
        labels = {marker.label for marker in markers}

        self.assertIn("TR MM↑", labels)

    def test_detect_measured_move_markers_marks_breakout_body_target(self) -> None:
        bars = build_bo_measured_move_bars()
        markers = detect_measured_move_markers(bars, strength=1)
        labels = {marker.label for marker in markers}

        self.assertIn("BO MM↑", labels)

    def test_detect_measured_move_markers_marks_measuring_gap_target(self) -> None:
        bars = build_measuring_gap_bars()
        ema_values = calculate_ema([bar.close_price for bar in bars], 20)
        markers = detect_measured_move_markers(
            bars,
            strength=1,
            ema_values=ema_values,
        )
        labels = {marker.label for marker in markers}

        self.assertIn("MG MM↑", labels)
        self.assertIn("MG Mid1↑", labels)
        self.assertIn("MG Mid2↑", labels)

    def test_detect_measured_move_markers_marks_negative_measuring_gap(self) -> None:
        bars = build_negative_measuring_gap_bars()
        ema_values = calculate_ema([bar.close_price for bar in bars], 20)
        markers = detect_measured_move_markers(
            bars,
            strength=1,
            ema_values=ema_values,
        )
        labels = {marker.label for marker in markers}

        self.assertIn("Neg MG↑", labels)

    def test_breakout_event_marks_opening_reversal(self) -> None:
        bars = build_opening_reversal_bars()
        (
            _ema_values,
            _signals,
            _background,
            _structure_phase_names,
            _structure_phases,
            breakout_event_names,
            _breakout_event_phases,
        ) = build_brooks_annotations(bars, 0.01)

        self.assertIn("开盘反转", breakout_event_names[:18])

    def test_breakout_event_marks_midday_reversal(self) -> None:
        bars = build_midday_reversal_bars()
        (
            _ema_values,
            _signals,
            _background,
            _structure_phase_names,
            _structure_phases,
            breakout_event_names,
            _breakout_event_phases,
        ) = build_brooks_annotations(bars, 0.01)

        self.assertIn("午间反转", breakout_event_names)


if __name__ == "__main__":
    unittest.main()
