"""
EMA20 附近 H2 顺势多 / L2 顺势空策略。

说明：
1. 这是 Brooks 体系的程序化近似版，目标是先把最标准、最容易回测的一层落地。
2. 当前版本优先追求可回测、可解释、可优化，不追求一次覆盖全部价格行为细节。
"""

from __future__ import annotations

from dataclasses import dataclass

from brooks_chart_app.logic import BrooksAnalysis, analyze_brooks_context, is_signal_context_supported
from brooks_chart_app.setup_engine import SetupCandidate, build_setup_candidates
from vnpy.trader.constant import Direction, Interval, Offset, Status
from vnpy.trader.object import BarData, OrderData, TradeData, TickData
from vnpy.trader.utility import ArrayManager, BarGenerator
from vnpy_ctastrategy import CtaTemplate, StopOrder


@dataclass
class PendingSignal:
    """待触发信号。"""

    direction: int
    signal_count: int
    entry_price: float
    stop_price: float
    target_price: float
    kind: str


class Ema20H2L2TrendStrategy(CtaTemplate):
    """EMA20 附近 H2/L2 顺势策略。"""

    author: str = "Codex"

    signal_window: int = 5
    ema_window: int = 20
    am_window: int = 80
    init_days: int = 5

    fixed_size: float = 1.0
    max_pullback_bars: int = 12
    max_signal_wait_bars: int = 3
    ema_distance_factor: float = 0.6
    risk_reward_ratio: float = 2.0
    breakeven_r: float = 1.0
    stop_buffer_ticks: int = 1
    long_setup_kinds: tuple[str, ...] = ("H2",)
    short_setup_kinds: tuple[str, ...] = ("L2",)

    ema_value: float = 0.0
    pending_kind: str = ""
    active_stop_price: float = 0.0
    active_target_price: float = 0.0
    active_entry_price: float = 0.0
    active_risk: float = 0.0
    signal_bar_count: int = 0

    parameters: list[str] = [
        "signal_window",
        "ema_window",
        "am_window",
        "init_days",
        "fixed_size",
        "max_pullback_bars",
        "max_signal_wait_bars",
        "ema_distance_factor",
        "risk_reward_ratio",
        "breakeven_r",
        "stop_buffer_ticks",
    ]

    variables: list[str] = [
        "ema_value",
        "pending_kind",
        "active_stop_price",
        "active_target_price",
        "active_entry_price",
        "active_risk",
        "signal_bar_count",
    ]

    def on_init(self) -> None:
        """初始化策略。"""
        self.write_log("策略初始化")

        self.bg: BarGenerator = BarGenerator(self.on_bar, self.signal_window, self.on_signal_bar)
        self.am: ArrayManager = ArrayManager(self.am_window)

        self.pending_signal: PendingSignal | None = None
        self.signal_orderids: set[str] = set()
        self.exit_orderids: set[str] = set()

        self.signal_history: list[BarData] = []
        self.current_analysis: BrooksAnalysis | None = None

        self.load_bar(self.init_days, Interval.MINUTE, self.on_bar, use_database=True)

    def on_start(self) -> None:
        """启动策略。"""
        self.write_log("策略启动")
        self.put_event()

    def on_stop(self) -> None:
        """停止策略。"""
        self.write_log("策略停止")
        self.pending_signal = None
        self.signal_orderids.clear()
        self.exit_orderids.clear()
        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """不使用 Tick。"""
        return

    def on_bar(self, bar: BarData) -> None:
        """接收 1 分钟 K 线并管理持仓。"""
        self.bg.update_bar(bar)

        if self.pos > 0:
            self.manage_long_position()
        elif self.pos < 0:
            self.manage_short_position()

    def on_signal_bar(self, bar: BarData) -> None:
        """处理策略执行周期 K 线。"""
        self.signal_bar_count += 1
        self.signal_history.append(bar)
        if len(self.signal_history) > 120:
            self.signal_history = self.signal_history[-120:]

        self.am.update_bar(bar)
        if not self.am.inited:
            self.put_event()
            return

        self.current_analysis = analyze_brooks_context(self.signal_history)
        self.ema_value = self.current_analysis.ema_values[-1] if self.current_analysis.ema_values else 0.0

        self.update_pending_signal(bar)

        if self.pos == 0 and not self.pending_signal:
            self.detect_long_signal(bar)
            self.detect_short_signal(bar)

        self.put_event()

    def detect_long_signal(self, bar: BarData) -> None:
        """寻找 H2 顺势多。"""
        candidate = self.find_current_setup_candidate(self.long_setup_kinds)
        if not candidate:
            return

        self.pending_signal = PendingSignal(
            direction=1,
            signal_count=self.signal_bar_count,
            entry_price=candidate.entry_price,
            stop_price=candidate.stop_price,
            target_price=candidate.target_price,
            kind=f"{candidate.kind}-{candidate.quality}",
        )
        self.submit_pending_signal()

    def detect_short_signal(self, bar: BarData) -> None:
        """寻找 L2 顺势空。"""
        candidate = self.find_current_setup_candidate(self.short_setup_kinds)
        if not candidate:
            return

        self.pending_signal = PendingSignal(
            direction=-1,
            signal_count=self.signal_bar_count,
            entry_price=candidate.entry_price,
            stop_price=candidate.stop_price,
            target_price=candidate.target_price,
            kind=f"{candidate.kind}-{candidate.quality}",
        )
        self.submit_pending_signal()

    def update_pending_signal(self, bar: BarData) -> None:
        """更新待触发信号的有效性。"""
        if not self.pending_signal:
            return

        expired: bool = (self.signal_bar_count - self.pending_signal.signal_count) >= self.max_signal_wait_bars
        invalid: bool = False

        if self.pending_signal.direction > 0:
            invalid = bar.low_price <= self.pending_signal.stop_price
        else:
            invalid = bar.high_price >= self.pending_signal.stop_price

        if not invalid and self.current_analysis:
            latest_index = len(self.signal_history) - 1
            if latest_index >= 0:
                signal_family = "mag" if self.pending_signal.kind.startswith("MAG") else "pullback"
                direction = "bull" if self.pending_signal.direction > 0 else "bear"
                if not is_signal_context_supported(
                    self.current_analysis,
                    latest_index,
                    direction,
                    signal_family=signal_family,
                ):
                    invalid = True

        if expired or invalid:
            self.cancel_signal_orders()
            self.pending_signal = None
            self.pending_kind = ""
            return

        if not self.signal_orderids:
            self.submit_pending_signal()

    def submit_pending_signal(self) -> None:
        """发出待触发 stop 订单。"""
        if not self.pending_signal:
            return

        self.pending_kind = self.pending_signal.kind

        if self.pending_signal.direction > 0:
            vt_orderids: list[str] = self.buy(self.pending_signal.entry_price, self.fixed_size, stop=True)
        else:
            vt_orderids = self.short(self.pending_signal.entry_price, self.fixed_size, stop=True)

        self.signal_orderids = set(vt_orderids)

    def cancel_signal_orders(self) -> None:
        """撤销待触发信号订单。"""
        for vt_orderid in list(self.signal_orderids):
            self.cancel_order(vt_orderid)
        self.signal_orderids.clear()

    def manage_long_position(self) -> None:
        """管理多头持仓。"""
        if self.active_entry_price <= 0 or self.active_risk <= 0:
            return

        if self.am.close[-1] >= (self.active_entry_price + self.active_risk * self.breakeven_r):
            self.active_stop_price = max(self.active_stop_price, self.active_entry_price)

        self.cancel_exit_orders()

        volume: float = abs(self.pos)
        stop_ids: list[str] = self.sell(self.active_stop_price, volume, stop=True)
        target_ids: list[str] = self.sell(self.active_target_price, volume)
        self.exit_orderids.update(stop_ids)
        self.exit_orderids.update(target_ids)

    def manage_short_position(self) -> None:
        """管理空头持仓。"""
        if self.active_entry_price <= 0 or self.active_risk <= 0:
            return

        if self.am.close[-1] <= (self.active_entry_price - self.active_risk * self.breakeven_r):
            self.active_stop_price = min(self.active_stop_price, self.active_entry_price)

        self.cancel_exit_orders()

        volume: float = abs(self.pos)
        stop_ids: list[str] = self.cover(self.active_stop_price, volume, stop=True)
        target_ids: list[str] = self.cover(self.active_target_price, volume)
        self.exit_orderids.update(stop_ids)
        self.exit_orderids.update(target_ids)

    def cancel_exit_orders(self) -> None:
        """撤销退出订单。"""
        for vt_orderid in list(self.exit_orderids):
            self.cancel_order(vt_orderid)
        self.exit_orderids.clear()

    def on_order(self, order: OrderData) -> None:
        """更新订单状态。"""
        if not order.is_active():
            self.signal_orderids.discard(order.vt_orderid)
            self.exit_orderids.discard(order.vt_orderid)

    def on_trade(self, trade: TradeData) -> None:
        """处理成交回报。"""
        if trade.offset == Offset.OPEN and self.pending_signal:
            self.active_entry_price = trade.price or self.pending_signal.entry_price
            self.active_stop_price = self.pending_signal.stop_price
            self.active_target_price = self.pending_signal.target_price
            self.active_risk = abs(self.active_entry_price - self.active_stop_price)
            self.pending_signal = None
            self.pending_kind = ""
            self.signal_orderids.clear()

        if self.pos == 0:
            self.active_entry_price = 0.0
            self.active_stop_price = 0.0
            self.active_target_price = 0.0
            self.active_risk = 0.0
            self.cancel_exit_orders()

        self.put_event()

    def on_stop_order(self, stop_order: StopOrder) -> None:
        """处理本地 stop 订单状态。"""
        if stop_order.status in {Status.CANCELLED, Status.ALLTRADED, Status.REJECTED}:
            self.signal_orderids.discard(stop_order.stop_orderid)
            self.exit_orderids.discard(stop_order.stop_orderid)

    def is_context_supported(self, direction: str, *, signal_family: str) -> bool:
        """复用图表分析模块判断当前背景是否支持 setup。"""
        if not self.current_analysis or not self.signal_history:
            return False
        latest_index = len(self.signal_history) - 1
        return is_signal_context_supported(
            self.current_analysis,
            latest_index,
            direction,
            signal_family=signal_family,
        )

    def find_current_setup_candidate(self, allowed_kinds: tuple[str, ...]) -> SetupCandidate | None:
        """从共享 setup 模块中挑选当前 bar 的候选。"""
        if not self.current_analysis or not self.signal_history:
            return None

        pricetick = self.get_effective_pricetick()
        latest_index = len(self.signal_history) - 1
        candidates = build_setup_candidates(
            self.signal_history,
            self.current_analysis,
            pricetick,
            mag_min_gap_bars=getattr(self, "min_gap_bars", 20),
            mag_max_gap_bars=getattr(self, "max_gap_bars", 45),
        )
        current_bar_candidates = [
            item
            for item in candidates
            if item.signal_index == latest_index and item.kind in allowed_kinds
        ]
        if not current_bar_candidates:
            return None
        return current_bar_candidates[-1]

    def is_pullback_start_for_bull(self, bar: BarData) -> bool:
        """判断多头回调是否开始。"""
        if len(self.signal_history) < 2:
            return False

        prev_bar: BarData = self.signal_history[-2]
        return (
            bar.low_price < prev_bar.low_price
            or bar.close_price < prev_bar.close_price
            or bar.close_price < self.ema_value
            or bar.close_price < bar.open_price
        )

    def is_pullback_start_for_bear(self, bar: BarData) -> bool:
        """判断空头反弹是否开始。"""
        if len(self.signal_history) < 2:
            return False

        prev_bar: BarData = self.signal_history[-2]
        return (
            bar.high_price > prev_bar.high_price
            or bar.close_price > prev_bar.close_price
            or bar.close_price > self.ema_value
            or bar.close_price > bar.open_price
        )

    def is_first_bar_of_up_attempt(self) -> bool:
        """判断新的向上尝试是否开始。"""
        if len(self.signal_history) < 3:
            return False

        bar: BarData = self.signal_history[-1]
        prev_bar: BarData = self.signal_history[-2]
        prev_prev_bar: BarData = self.signal_history[-3]

        return (
            bar.high_price > prev_bar.high_price
            and prev_bar.high_price <= prev_prev_bar.high_price
        )

    def is_first_bar_of_down_attempt(self) -> bool:
        """判断新的向下尝试是否开始。"""
        if len(self.signal_history) < 3:
            return False

        bar: BarData = self.signal_history[-1]
        prev_bar: BarData = self.signal_history[-2]
        prev_prev_bar: BarData = self.signal_history[-3]

        return (
            bar.low_price < prev_bar.low_price
            and prev_bar.low_price >= prev_prev_bar.low_price
        )

    def is_near_ema_for_long(self, bar: BarData) -> bool:
        """判断做多信号是否靠近 EMA20。"""
        avg_range: float = max(self.get_recent_average_range(), self.get_effective_pricetick())
        threshold: float = avg_range * self.ema_distance_factor
        return abs(bar.low_price - self.ema_value) <= threshold

    def is_near_ema_for_short(self, bar: BarData) -> bool:
        """判断做空信号是否靠近 EMA20。"""
        avg_range: float = max(self.get_recent_average_range(), self.get_effective_pricetick())
        threshold: float = avg_range * self.ema_distance_factor
        return abs(bar.high_price - self.ema_value) <= threshold

    def evaluate_bull_signal_quality(self, bar: BarData) -> str:
        """评估多头 signal bar 质量。"""
        bar_range: float = max(bar.high_price - bar.low_price, self.get_effective_pricetick())
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

    def evaluate_bear_signal_quality(self, bar: BarData) -> str:
        """评估空头 signal bar 质量。"""
        bar_range: float = max(bar.high_price - bar.low_price, self.get_effective_pricetick())
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

    def get_recent_average_range(self) -> float:
        """获取最近几根信号 K 线的平均波动。"""
        sample: list[BarData] = self.signal_history[-min(len(self.signal_history), self.ema_window):]
        if not sample:
            return self.get_effective_pricetick()

        ranges: list[float] = [max(bar.high_price - bar.low_price, 0.0) for bar in sample]
        avg_range: float = float(sum(ranges) / len(ranges))
        return max(avg_range, self.get_effective_pricetick())

    def get_effective_pricetick(self) -> float:
        """获取有效价格跳动。"""
        pricetick: float = self.get_pricetick()
        if pricetick and pricetick > 0:
            return pricetick
        return 0.1
