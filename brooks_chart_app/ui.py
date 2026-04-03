"""Brooks 图表标注界面。"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
import csv
import json
import re
import webbrowser

import pyqtgraph as pg

from vnpy.chart import ChartWidget, CandleItem, VolumeItem
from vnpy.chart.axis import DatetimeAxis
from vnpy.chart.base import BAR_WIDTH
from vnpy.trader.ui import QtCore, QtGui, QtWidgets
from vnpy.trader.engine import MainEngine, EventEngine
from vnpy.trader.constant import Interval
from vnpy.trader.database import BarOverview, DB_TZ
from vnpy.trader.object import BarData

from .catalog import (
    KNOWLEDGE_TOPICS,
    KNOWLEDGE_TOPIC_MAP,
    STRATEGY_BLUEPRINTS,
    STRATEGY_BLUEPRINT_MAP,
    KnowledgeTopic,
    StrategyBlueprint,
)
from .engine import APP_NAME, BrooksChartEngine
from .logic import (
    BackgroundPhase,
    MeasuredMoveMarker,
    MicroGapMarker,
    OpeningRangeMarker,
    PatternMarker,
    SignalAnnotation,
    build_brooks_annotations,
    build_opening_range_markers,
    detect_measured_move_markers,
    detect_bar_patterns,
    detect_micro_gaps,
    find_pivot_swings,
    group_bars_by_session,
    select_channel_geometry,
)
from .material_dates import MaterialDateRef, load_material_date_refs


INTERVAL_NAME_MAP: dict[Interval, str] = {
    Interval.MINUTE: "分钟线",
    Interval.HOUR: "小时线",
    Interval.DAILY: "日线",
}


@dataclass(frozen=True)
class DisplayIntervalOption:
    """图表显示周期配置。"""

    key: str
    label: str
    interval: Interval
    window: int
    minutes: int


DISPLAY_INTERVAL_OPTIONS: tuple[DisplayIntervalOption, ...] = (
    DisplayIntervalOption("1m", "1分钟", Interval.MINUTE, 1, 1),
    DisplayIntervalOption("5m", "5分钟", Interval.MINUTE, 5, 5),
    DisplayIntervalOption("15m", "15分钟", Interval.MINUTE, 15, 15),
    DisplayIntervalOption("1h", "1小时", Interval.HOUR, 1, 60),
)
DISPLAY_INTERVAL_MAP: dict[str, DisplayIntervalOption] = {
    option.key: option for option in DISPLAY_INTERVAL_OPTIONS
}
FOCUS_RANGE_OPTIONS: tuple[tuple[int, str], ...] = (
    (1, "当日"),
    (3, "近3天"),
    (5, "近5天"),
    (10, "近10天"),
    (20, "近20天"),
    (60, "近60天"),
)

ROOT_DIR: Path = Path(__file__).resolve().parent.parent
BACKTEST_OUTPUT_DIR: Path = ROOT_DIR / "backtests" / "output" / "ema20_h2_l2"
BACKTEST_MATRIX_ROOT: Path = ROOT_DIR / "backtests" / "output" / "brooks_matrix"
BACKTEST_OPT_ROOT: Path = ROOT_DIR / "backtests" / "output" / "brooks_opt"
CTA_GUI_OUTPUT_ROOT: Path = ROOT_DIR / "backtests" / "output" / "cta_gui_runs"
CTA_GUI_LATEST_ROOT: Path = ROOT_DIR / "backtests" / "output" / "cta_gui_latest"
REVIEW_PATH: Path = ROOT_DIR / ".vntrader" / "brooks_signal_reviews.json"
TOPIC_STAGE_PATH: Path = ROOT_DIR / ".vntrader" / "brooks_topic_stages.json"
TOPIC_STAGE_OPTIONS: tuple[str, ...] = (
    "未标记",
    "开发阶段",
    "已实现待验证",
    "截图验证通过",
    "已实现没问题",
)
BROOKS_FONT_MONO: str = "Menlo"
BROOKS_FONT_UI: str = "PingFang SC"
BROOKS_LABEL_SIZE_MICRO: int = 8
BROOKS_LABEL_SIZE_SMALL: int = 9
BROOKS_LABEL_SIZE_NORMAL: int = 10
BROOKS_LABEL_SIZE_TITLE: int = 12
BROOKS_LINE_WIDTH_THIN: float = 1.15
BROOKS_LINE_WIDTH_NORMAL: float = 1.45
BROOKS_LINE_WIDTH_STRONG: float = 1.9
BROOKS_BOX_ALPHA_LIGHT: int = 18
BROOKS_BOX_ALPHA_NORMAL: int = 26
BROOKS_BOX_ALPHA_STRONG: int = 34


def brooks_font(
    size: int,
    *,
    mono: bool = True,
    weight: QtGui.QFont.Weight = QtGui.QFont.Weight.Normal,
) -> QtGui.QFont:
    """统一 Brooks 图表字体，避免各处散落硬编码。"""
    family = BROOKS_FONT_MONO if mono else BROOKS_FONT_UI
    font = QtGui.QFont(family, size)
    font.setWeight(weight)
    return font


def brooks_pen(
    color: tuple[int, ...],
    *,
    width: float = BROOKS_LINE_WIDTH_NORMAL,
    style: QtCore.Qt.PenStyle = QtCore.Qt.PenStyle.SolidLine,
):
    """统一 Brooks 图表线条样式。"""
    return pg.mkPen(color=color, width=width, style=style)


@dataclass
class BacktestRecord:
    """可选回测记录。"""

    source: str
    source_label: str
    tag: str
    strategy_key: str
    strategy_label: str
    vt_symbol: str
    start: str
    end: str
    signal_window: str
    sharpe_ratio: float
    total_net_pnl: float
    total_trade_count: int
    setting_text: str = ""
    detail_path: Path | None = None
    meta_path: Path | None = None
    stats_path: Path | None = None
    trades_path: Path | None = None
    lifecycles_path: Path | None = None
    report_path: Path | None = None


class BrooksDatetimeAxis(DatetimeAxis):
    """Brooks 图表专用时间轴。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tickFont = brooks_font(BROOKS_LABEL_SIZE_SMALL)

    def tickStrings(self, values: list[int], scale: float, spacing: int) -> list[str]:
        if spacing < 1:
            return ["" for _ in values]

        strings: list[str] = []
        for ix in values:
            dt = self._manager.get_datetime(ix)
            if not dt:
                strings.append("")
                continue

            if dt.hour or dt.minute or dt.second:
                strings.append(dt.strftime("%m-%d\n%H:%M"))
            else:
                strings.append(dt.strftime("%Y-%m-%d"))

        return strings


class InteractiveChartWidget(ChartWidget):
    """增强交互的图表组件。"""

    TRACKPAD_PIXEL_THRESHOLD: float = 36.0
    MOUSE_WHEEL_THRESHOLD: float = 120.0
    RIGHT_AXIS_WIDTH: int = 60
    BOTTOM_AXIS_HEIGHT: int = 42
    MIN_VERTICAL_RANGE_FACTOR: float = 0.75
    MAX_VERTICAL_RANGE_FACTOR: float = 4.0
    RANGE_FACTOR_STEP: float = 1.18
    AXIS_SCROLL_THRESHOLD: float = 60.0

    def __init__(self) -> None:
        super().__init__()
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.horizontal_scroll_buffer: float = 0
        self.vertical_scroll_buffer: float = 0
        self.price_axis_scroll_buffer: float = 0
        self.bottom_axis_scroll_buffer: float = 0
        self.vertical_range_factor: float = 1.0
        self.axis_drag_mode: str = ""
        self.last_axis_drag_pos: QtCore.QPointF | None = None

    def _get_new_x_axis(self) -> BrooksDatetimeAxis:
        return BrooksDatetimeAxis(self._manager, orientation="bottom")

    def visible_bar_count(self) -> int:
        if self._first_plot is None:
            return self._bar_count

        view = self._first_plot.getViewBox()
        x_range = view.viewRange()[0]
        width = int(max(1, x_range[1] - x_range[0]))
        return width

    def pan_bars(self, delta: int) -> None:
        if not self._manager.get_count():
            return

        self._right_ix += delta
        self._right_ix = max(self._bar_count, min(self._right_ix, self._manager.get_count()))
        self._update_x_range()
        self._update_y_range()
        if self._cursor:
            self._cursor.update_info()

    def pan_left(self) -> None:
        step = max(5, self.visible_bar_count() // 5)
        self.pan_bars(-step)

    def pan_right(self) -> None:
        step = max(5, self.visible_bar_count() // 5)
        self.pan_bars(step)

    def pan_steps(self, steps: int) -> None:
        if not steps:
            return
        step = max(3, self.visible_bar_count() // 12)
        self.pan_bars(step * steps)

    def zoom_in(self) -> None:
        self._on_key_up()
        self._update_y_range()
        self.refresh_bottom_axis_ticks()

    def zoom_out(self) -> None:
        self._on_key_down()
        self._update_y_range()
        self.refresh_bottom_axis_ticks()

    def compress_chart_height(self) -> None:
        self.vertical_range_factor = min(
            self.MAX_VERTICAL_RANGE_FACTOR,
            self.vertical_range_factor * self.RANGE_FACTOR_STEP,
        )
        self._update_y_range()

    def expand_chart_height(self) -> None:
        self.vertical_range_factor = max(
            self.MIN_VERTICAL_RANGE_FACTOR,
            self.vertical_range_factor / self.RANGE_FACTOR_STEP,
        )
        self._update_y_range()

    def refresh_axis_layout(self) -> None:
        """统一设置 Brooks 图表的坐标轴外观。"""
        for plot in self.get_all_plots():
            right_axis = plot.getAxis("right")
            bottom_axis = plot.getAxis("bottom")
            right_axis.setWidth(self.RIGHT_AXIS_WIDTH)
            bottom_axis.setHeight(self.BOTTOM_AXIS_HEIGHT)
            bottom_axis.setStyle(tickTextOffset=10)

        self.refresh_bottom_axis_ticks()
        self.updateGeometry()
        self.update()

    def refresh_bottom_axis_ticks(self) -> None:
        """根据当前可见宽度调整底部时间轴密度。"""
        plots = self.get_all_plots()
        if not plots:
            return

        bottom_axis = plots[-1].getAxis("bottom")
        visible_bars = max(1, self.visible_bar_count())
        major_spacing = max(1, visible_bars // 6)
        minor_spacing = max(1, major_spacing // 2)
        bottom_axis.setTickSpacing(major=major_spacing, minor=minor_spacing)
        bottom_axis.picture = None
        bottom_axis.update()

    def is_over_price_axis(self, pos: QtCore.QPointF) -> bool:
        """判断鼠标是否位于右侧价格轴区域。"""
        return pos.x() >= max(0, self.width() - self.RIGHT_AXIS_WIDTH)

    def is_over_time_axis(self, pos: QtCore.QPointF) -> bool:
        """判断鼠标是否位于底部时间轴区域。"""
        return pos.y() >= max(0, self.height() - self.BOTTOM_AXIS_HEIGHT)

    def handle_price_axis_scroll(self, delta_value: float) -> bool:
        """在价格轴区域滚动时，调图高。"""
        self.price_axis_scroll_buffer += delta_value
        steps = int(self.price_axis_scroll_buffer / self.AXIS_SCROLL_THRESHOLD)
        if not steps:
            return False

        for _ in range(abs(steps)):
            if steps > 0:
                self.expand_chart_height()
            else:
                self.compress_chart_height()
        self.price_axis_scroll_buffer -= steps * self.AXIS_SCROLL_THRESHOLD
        return True

    def handle_time_axis_scroll(self, delta_value: float) -> bool:
        """在时间轴区域滚动时，调图宽。"""
        self.bottom_axis_scroll_buffer += delta_value
        steps = int(self.bottom_axis_scroll_buffer / self.AXIS_SCROLL_THRESHOLD)
        if not steps:
            return False

        for _ in range(abs(steps)):
            if steps > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        self.bottom_axis_scroll_buffer -= steps * self.AXIS_SCROLL_THRESHOLD
        return True

    def _update_y_range(self) -> None:
        """支持独立纵向压缩/拉伸。"""
        if not self._first_plot:
            return

        view: pg.ViewBox = self._first_plot.getViewBox()
        view_range: list = view.viewRange()

        min_ix: int = max(0, int(view_range[0][0]))
        max_ix: int = min(self._manager.get_count(), int(view_range[0][1]))

        for item, plot in self._item_plot_map.items():
            min_value, max_value = item.get_y_range(min_ix, max_ix)
            if plot is self._first_plot:
                mid = (min_value + max_value) / 2
                half_range = max((max_value - min_value) / 2, 1e-6)
                scaled_half_range = half_range * self.vertical_range_factor
                padding = max(scaled_half_range * 0.05, 1e-6)
                y_range = (mid - scaled_half_range - padding, mid + scaled_half_range + padding)
            else:
                y_range = (min_value, max_value)
            plot.setRange(yRange=y_range, padding=0)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """兼容鼠标滚轮和 Mac 触摸板双指滑动。"""
        pixel_delta = event.pixelDelta()
        angle_delta = event.angleDelta()
        pos = event.position()

        horizontal = float(pixel_delta.x() or angle_delta.x())
        vertical = float(pixel_delta.y() or angle_delta.y())

        if event.inverted():
            horizontal = -horizontal
            vertical = -vertical

        if vertical and self.is_over_price_axis(pos):
            if self.handle_price_axis_scroll(vertical):
                event.accept()
                return

        if vertical and self.is_over_time_axis(pos):
            if self.handle_time_axis_scroll(vertical):
                event.accept()
                return

        threshold = self.TRACKPAD_PIXEL_THRESHOLD if not pixel_delta.isNull() else self.MOUSE_WHEEL_THRESHOLD

        if abs(horizontal) > abs(vertical) and horizontal:
            self.horizontal_scroll_buffer += horizontal
            steps = int(self.horizontal_scroll_buffer / threshold)
            if steps:
                self.pan_steps(steps)
                self.horizontal_scroll_buffer -= steps * threshold
            event.accept()
            return

        if vertical:
            self.vertical_scroll_buffer += vertical
            steps = int(self.vertical_scroll_buffer / threshold)
            if steps:
                for _ in range(abs(steps)):
                    if steps > 0:
                        self.zoom_in()
                    else:
                        self.zoom_out()
                self.vertical_scroll_buffer -= steps * threshold
            event.accept()
            return

        event.accept()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """支持在价格轴和时间轴上拖拽缩放。"""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            pos = event.position()
            if self.is_over_price_axis(pos):
                self.axis_drag_mode = "price"
                self.last_axis_drag_pos = pos
                self.setCursor(QtCore.Qt.CursorShape.SizeVerCursor)
                event.accept()
                return
            if self.is_over_time_axis(pos):
                self.axis_drag_mode = "time"
                self.last_axis_drag_pos = pos
                self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """处理坐标轴拖拽缩放。"""
        if self.axis_drag_mode and self.last_axis_drag_pos is not None:
            pos = event.position()
            delta = pos - self.last_axis_drag_pos
            if self.axis_drag_mode == "price" and delta.y():
                self.handle_price_axis_scroll(-delta.y() * 3)
            elif self.axis_drag_mode == "time" and delta.x():
                self.handle_time_axis_scroll(delta.x() * 3)
            self.last_axis_drag_pos = pos
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """结束坐标轴拖拽。"""
        if self.axis_drag_mode and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.axis_drag_mode = ""
            self.last_axis_drag_pos = None
            self.unsetCursor()
            event.accept()
            return

        super().mouseReleaseEvent(event)


class AdaptiveComboBox(QtWidgets.QComboBox):
    """自动扩展宽度并修正弹出列表尺寸。"""

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setMinimumContentsLength(10)
        self.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)

        view = QtWidgets.QListView()
        view.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        self.setView(view)

    def showPopup(self) -> None:
        popup = self.view()
        max_width = self.width()
        metrics = self.fontMetrics()
        for index in range(self.count()):
            max_width = max(max_width, metrics.horizontalAdvance(self.itemText(index)) + 52)
        popup.setMinimumWidth(max_width)
        super().showPopup()


class BrooksChartManager(QtWidgets.QWidget):
    """Brooks 图表标注主界面。"""

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.engine: BrooksChartEngine = main_engine.get_engine(APP_NAME)    # type: ignore

        self.overviews: list[BarOverview] = []
        self.current_overview: BarOverview | None = None
        self.current_bars: list[BarData] = []
        self.current_source_bars: list[BarData] = []
        self.current_datetimes: list[datetime] = []
        self.current_signals: list[SignalAnnotation] = []
        self.filtered_signals: list[SignalAnnotation] = []
        self.current_background: str = "无数据"
        self.current_display_interval: DisplayIntervalOption = DISPLAY_INTERVAL_MAP["1m"]
        self.current_structure_phase_names: list[str] = []
        self.current_structure_phases: list[BackgroundPhase] = []
        self.current_breakout_event_names: list[str] = []
        self.current_breakout_event_phases: list[BackgroundPhase] = []
        self.current_ema_values: list[float] = []
        self.current_compare_bars: list[BarData] = []
        self.current_compare_signals: list[SignalAnnotation] = []
        self.current_compare_ema_values: list[float] = []
        self.current_bar_counts: list[int] = []
        self.current_trades: list[dict] = []
        self.current_lifecycles: list[dict] = []
        self.overlay_items: list[object] = []
        self.compare_overlay_items: list[object] = []
        self.compare_focus_items: list[object] = []
        self.bar_count_items: list[object] = []
        self.signal_reviews: dict[str, dict] = self.load_signal_reviews()
        self.topic_stage_reviews: dict[str, str] = self.load_topic_stage_reviews()
        self.backtest_records: list[BacktestRecord] = []
        self.current_record: BacktestRecord | None = None
        self.active_topic: KnowledgeTopic | None = None
        self.active_strategy: StrategyBlueprint | None = None
        self.checked_topic_keys: set[str] = set()
        self.pending_focus_datetime: datetime | None = None
        self.material_date_refs: dict[str, list[MaterialDateRef]] = load_material_date_refs()

        self.init_ui()
        self.init_shortcuts()
        self.refresh_overviews()
        self.refresh_backtest_records()

    def init_ui(self) -> None:
        self.setWindowTitle("Brooks图表")

        self.dataset_combo: QtWidgets.QComboBox = AdaptiveComboBox()
        self.dataset_combo.currentIndexChanged.connect(self.on_dataset_changed)

        self.refresh_button: QtWidgets.QPushButton = QtWidgets.QPushButton("刷新数据集")
        self.refresh_button.clicked.connect(self.refresh_overviews)

        self.start_edit: QtWidgets.QDateTimeEdit = QtWidgets.QDateTimeEdit()
        self.start_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_edit.setCalendarPopup(True)

        self.end_edit: QtWidgets.QDateTimeEdit = QtWidgets.QDateTimeEdit()
        self.end_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.end_edit.setCalendarPopup(True)

        self.bar_limit_spin: QtWidgets.QSpinBox = QtWidgets.QSpinBox()
        self.bar_limit_spin.setRange(100, 200000)
        self.bar_limit_spin.setValue(7500)
        self.bar_limit_spin.setSingleStep(500)

        self.timeframe_combo: QtWidgets.QComboBox = AdaptiveComboBox()
        for option in DISPLAY_INTERVAL_OPTIONS:
            self.timeframe_combo.addItem(option.label, option.key)
        self.timeframe_combo.currentIndexChanged.connect(self.on_timeframe_changed)
        default_timeframe_index = self.timeframe_combo.findData("5m")
        if default_timeframe_index >= 0:
            self.timeframe_combo.setCurrentIndex(default_timeframe_index)

        self.focus_date_edit: QtWidgets.QDateEdit = QtWidgets.QDateEdit()
        self.focus_date_edit.setCalendarPopup(True)
        self.focus_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.focus_date_edit.setDate(QtCore.QDate.currentDate())
        self.focus_calendar: QtWidgets.QCalendarWidget = QtWidgets.QCalendarWidget()
        self.focus_calendar.clicked.connect(self.on_focus_calendar_clicked)
        self.focus_date_edit.setCalendarWidget(self.focus_calendar)
        self.focus_date_edit.dateChanged.connect(self.on_focus_date_changed)

        self.focus_range_combo: QtWidgets.QComboBox = AdaptiveComboBox()
        for days, label in FOCUS_RANGE_OPTIONS:
            self.focus_range_combo.addItem(label, days)
        default_focus_range_index = self.focus_range_combo.findData(3)
        if default_focus_range_index >= 0:
            self.focus_range_combo.setCurrentIndex(default_focus_range_index)

        self.apply_focus_range_button: QtWidgets.QPushButton = QtWidgets.QPushButton("按日期加载")
        self.apply_focus_range_button.clicked.connect(self.apply_focus_date_range)

        self.focus_current_date_button: QtWidgets.QPushButton = QtWidgets.QPushButton("跳到该日")
        self.focus_current_date_button.clicked.connect(self.focus_selected_date)

        self.kind_filter_combo: QtWidgets.QComboBox = AdaptiveComboBox()
        self.kind_filter_combo.addItems(["全部", "不检测", "H1", "H2", "L1", "L2", "MAG"])
        self.kind_filter_combo.currentIndexChanged.connect(self.apply_signal_filters)

        self.quality_filter_combo: QtWidgets.QComboBox = AdaptiveComboBox()
        self.quality_filter_combo.addItems(["全部", "强", "中"])
        self.quality_filter_combo.currentIndexChanged.connect(self.apply_signal_filters)

        self.compare_timeframe_combo: QtWidgets.QComboBox = AdaptiveComboBox()
        self.compare_timeframe_combo.addItem("自动", "auto")
        self.compare_timeframe_combo.addItem("5分钟", "5m")
        self.compare_timeframe_combo.addItem("15分钟", "15m")
        self.compare_timeframe_combo.addItem("1小时", "1h")
        self.compare_timeframe_combo.addItem("1日", "1d")
        self.compare_timeframe_combo.currentIndexChanged.connect(self.on_compare_timeframe_changed)

        self.review_filter_combo: QtWidgets.QComboBox = AdaptiveComboBox()
        self.review_filter_combo.addItems(["全部", "待处理", "已确认", "已忽略"])
        self.review_filter_combo.currentIndexChanged.connect(self.apply_signal_filters)

        self.show_bar_count_checkbox: QtWidgets.QCheckBox = QtWidgets.QCheckBox("显示Bar计数")
        self.show_bar_count_checkbox.setChecked(True)
        self.show_bar_count_checkbox.toggled.connect(self.on_bar_count_setting_changed)

        self.bar_count_interval_spin: QtWidgets.QSpinBox = QtWidgets.QSpinBox()
        self.bar_count_interval_spin.setRange(1, 20)
        self.bar_count_interval_spin.setValue(3)
        self.bar_count_interval_spin.valueChanged.connect(self.on_bar_count_setting_changed)

        self.load_button: QtWidgets.QPushButton = QtWidgets.QPushButton("加载图表")
        self.load_button.clicked.connect(self.load_chart)

        self.load_report_button: QtWidgets.QPushButton = QtWidgets.QPushButton("加载最近回测")
        self.load_report_button.clicked.connect(self.load_latest_backtest_report)

        self.open_report_button: QtWidgets.QPushButton = QtWidgets.QPushButton("打开HTML报告")
        self.open_report_button.clicked.connect(self.open_latest_report_html)

        self.prev_signal_button: QtWidgets.QPushButton = QtWidgets.QPushButton("上一信号")
        self.prev_signal_button.clicked.connect(lambda: self.navigate_signal(-1))

        self.next_signal_button: QtWidgets.QPushButton = QtWidgets.QPushButton("下一信号")
        self.next_signal_button.clicked.connect(lambda: self.navigate_signal(1))

        self.left_button: QtWidgets.QPushButton = QtWidgets.QPushButton("左移")
        self.left_button.clicked.connect(lambda: self.chart.pan_left())

        self.right_button: QtWidgets.QPushButton = QtWidgets.QPushButton("右移")
        self.right_button.clicked.connect(lambda: self.chart.pan_right())

        self.zoom_in_button: QtWidgets.QPushButton = QtWidgets.QPushButton("宽压")
        self.zoom_in_button.clicked.connect(lambda: self.chart.zoom_in())

        self.zoom_out_button: QtWidgets.QPushButton = QtWidgets.QPushButton("宽松")
        self.zoom_out_button.clicked.connect(lambda: self.chart.zoom_out())

        self.compress_height_button: QtWidgets.QPushButton = QtWidgets.QPushButton("高压")
        self.compress_height_button.clicked.connect(lambda: self.chart.compress_chart_height())

        self.expand_height_button: QtWidgets.QPushButton = QtWidgets.QPushButton("高松")
        self.expand_height_button.clicked.connect(lambda: self.chart.expand_chart_height())

        self.reset_view_button: QtWidgets.QPushButton = QtWidgets.QPushButton("重置视图")
        self.reset_view_button.clicked.connect(self.reset_chart_view)

        self.confirm_button: QtWidgets.QPushButton = QtWidgets.QPushButton("确认信号")
        self.confirm_button.clicked.connect(lambda: self.update_signal_review("已确认"))

        self.ignore_button: QtWidgets.QPushButton = QtWidgets.QPushButton("忽略信号")
        self.ignore_button.clicked.connect(lambda: self.update_signal_review("已忽略"))

        self.clear_review_button: QtWidgets.QPushButton = QtWidgets.QPushButton("清空状态")
        self.clear_review_button.clicked.connect(lambda: self.update_signal_review("待处理"))

        self.status_label: QtWidgets.QLabel = QtWidgets.QLabel("等待加载数据库中的 K 线数据")
        self.status_label.setWordWrap(True)
        self.material_refs_edit: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.material_refs_edit.setReadOnly(True)
        self.material_refs_edit.setPlaceholderText("这里显示当前日期命中的课程页、百科页和 Ali 卡。")
        self.material_refs_edit.setMinimumHeight(90)

        self.chart: InteractiveChartWidget = InteractiveChartWidget()
        self.chart.add_plot("candle", hide_x_axis=True)
        self.chart.add_plot("volume", maximum_height=180)
        self.chart.add_item(CandleItem, "candle", "candle")
        self.chart.add_item(VolumeItem, "volume", "volume")
        self.chart.add_cursor()
        self.chart.refresh_axis_layout()
        candle_plot = self.chart.get_plot("candle")
        if candle_plot is not None:
            candle_plot.getViewBox().sigXRangeChanged.connect(self.on_chart_view_changed)

        self.compare_title_label: QtWidgets.QLabel = QtWidgets.QLabel("更高周期对照：未加载")
        self.compare_title_label.setWordWrap(True)
        self.compare_chart: InteractiveChartWidget = InteractiveChartWidget()
        self.compare_chart.add_plot("candle", hide_x_axis=True)
        self.compare_chart.add_plot("volume", maximum_height=110)
        self.compare_chart.add_item(CandleItem, "candle", "candle")
        self.compare_chart.add_item(VolumeItem, "volume", "volume")
        self.compare_chart.add_cursor()
        self.compare_chart.refresh_axis_layout()
        compare_candle_plot = self.compare_chart.get_plot("candle")
        if compare_candle_plot is not None:
            compare_candle_plot.getViewBox().setMouseEnabled(x=False, y=False)

        self.signal_table: QtWidgets.QTableWidget = QtWidgets.QTableWidget()
        self.signal_table.setColumnCount(8)
        self.signal_table.setHorizontalHeaderLabels(["时间", "类型", "质量", "状态", "触发", "入场", "止损", "目标"])
        self.signal_table.verticalHeader().setVisible(False)
        self.signal_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.signal_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.signal_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.signal_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.signal_table.itemSelectionChanged.connect(self.on_signal_selected)
        self.signal_table.itemDoubleClicked.connect(lambda *_: self.on_signal_selected())

        self.detail_edit: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.detail_edit.setReadOnly(True)

        self.note_edit: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.note_edit.setPlaceholderText("输入你对该信号的备注，比如是否符合 Brooks 语境、是否想保留。")
        self.save_note_button: QtWidgets.QPushButton = QtWidgets.QPushButton("保存备注")
        self.save_note_button.clicked.connect(self.save_current_note)

        self.stats_edit: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.stats_edit.setReadOnly(True)
        self.stats_edit.setPlaceholderText("这里会显示最近一次回测的统计摘要。")

        self.record_table: QtWidgets.QTableWidget = QtWidgets.QTableWidget()
        self.record_table.setColumnCount(7)
        self.record_table.setHorizontalHeaderLabels(["来源", "周期", "策略", "合约", "Sharpe", "净利润", "成交笔数"])
        self.record_table.verticalHeader().setVisible(False)
        self.record_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.record_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.record_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.record_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.record_table.itemSelectionChanged.connect(self.on_backtest_record_selected)

        self.record_detail_edit: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.record_detail_edit.setReadOnly(True)
        self.record_detail_edit.setPlaceholderText("这里显示所选回测记录的参数和统计。")

        self.refresh_records_button: QtWidgets.QPushButton = QtWidgets.QPushButton("刷新回测记录")
        self.refresh_records_button.clicked.connect(self.refresh_backtest_records)

        self.load_selected_record_button: QtWidgets.QPushButton = QtWidgets.QPushButton("加载选中回测")
        self.load_selected_record_button.clicked.connect(self.load_selected_backtest_record)

        self.lifecycle_table: QtWidgets.QTableWidget = QtWidgets.QTableWidget()
        self.lifecycle_table.setColumnCount(6)
        self.lifecycle_table.setHorizontalHeaderLabels(["生命周期", "方向", "入场时间", "离场时间", "手数", "点数盈亏"])
        self.lifecycle_table.verticalHeader().setVisible(False)
        self.lifecycle_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lifecycle_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.lifecycle_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.lifecycle_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.lifecycle_table.itemSelectionChanged.connect(self.on_lifecycle_selected)

        self.trade_table: QtWidgets.QTableWidget = QtWidgets.QTableWidget()
        self.trade_table.setColumnCount(6)
        self.trade_table.setHorizontalHeaderLabels(["时间", "方向", "开平", "价格", "数量", "成交号"])
        self.trade_table.verticalHeader().setVisible(False)
        self.trade_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.trade_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.trade_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.trade_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.trade_table.itemSelectionChanged.connect(self.on_trade_selected)
        self.trade_table.itemDoubleClicked.connect(lambda *_: self.on_trade_selected())

        self.topic_tree: QtWidgets.QTreeWidget = QtWidgets.QTreeWidget()
        self.topic_tree.setColumnCount(4)
        self.topic_tree.setHeaderLabels(["模块/章节", "知识点", "状态", "开发状态"])
        self.topic_tree.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.topic_tree.itemSelectionChanged.connect(self.on_topic_selected)
        self.topic_tree.itemChanged.connect(self.on_topic_check_changed)

        self.topic_detail_edit: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.topic_detail_edit.setReadOnly(True)
        self.topic_detail_edit.setPlaceholderText("这里显示公用知识体系的目录、资料来源和当前接入状态。")
        self.topic_stage_button: QtWidgets.QPushButton = QtWidgets.QPushButton()
        self.topic_stage_button.setEnabled(False)
        self.topic_stage_menu: QtWidgets.QMenu = QtWidgets.QMenu(self.topic_stage_button)
        self.topic_stage_actions: dict[str, QtGui.QAction] = {}
        for stage in TOPIC_STAGE_OPTIONS:
            action = self.topic_stage_menu.addAction(stage)
            action.triggered.connect(lambda checked=False, value=stage: self.on_topic_stage_changed(value))
            self.topic_stage_actions[stage] = action
        self.topic_stage_button.clicked.connect(self.show_topic_stage_menu)
        self.topic_stage_button.setText(f"{TOPIC_STAGE_OPTIONS[0]} ▼")
        self.populate_topic_tree()

        self.strategy_combo: QtWidgets.QComboBox = AdaptiveComboBox()
        self.strategy_combo.currentIndexChanged.connect(self.on_strategy_changed)

        self.strategy_tree: QtWidgets.QTreeWidget = QtWidgets.QTreeWidget()
        self.strategy_tree.setColumnCount(3)
        self.strategy_tree.setHeaderLabels(["流程环节", "当前策略口径", "状态"])
        self.strategy_tree.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        self.strategy_detail_edit: QtWidgets.QTextEdit = QtWidgets.QTextEdit()
        self.strategy_detail_edit.setReadOnly(True)
        self.strategy_detail_edit.setPlaceholderText("这里显示策略蓝图、公共知识点引用和当前微调方向。")
        self.populate_strategy_selector()

        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow("数据集", self.dataset_combo)
        form.addRow("开始时间", self.start_edit)
        form.addRow("结束时间", self.end_edit)
        form.addRow("目标日期", self.focus_date_edit)
        form.addRow("日期范围", self.focus_range_combo)
        form.addRow("图表周期", self.timeframe_combo)
        form.addRow("更高周期", self.compare_timeframe_combo)
        form.addRow("最近K线数", self.bar_limit_spin)
        form.addRow("建仓信号", self.kind_filter_combo)
        form.addRow("最低质量", self.quality_filter_combo)
        form.addRow("审核状态", self.review_filter_combo)
        form.addRow("Bar计数", self.show_bar_count_checkbox)
        form.addRow("计数间隔", self.bar_count_interval_spin)

        button_box1 = QtWidgets.QHBoxLayout()
        button_box1.addWidget(self.refresh_button)
        button_box1.addWidget(self.load_button)
        button_box1.addWidget(self.apply_focus_range_button)
        button_box1.addWidget(self.focus_current_date_button)

        button_box2 = QtWidgets.QHBoxLayout()
        button_box2.addWidget(self.load_report_button)
        button_box2.addWidget(self.open_report_button)

        button_box3 = QtWidgets.QHBoxLayout()
        button_box3.addWidget(self.prev_signal_button)
        button_box3.addWidget(self.next_signal_button)
        button_box3.addWidget(self.reset_view_button)

        button_box4 = QtWidgets.QHBoxLayout()
        button_box4.addWidget(self.left_button)
        button_box4.addWidget(self.right_button)
        button_box4.addWidget(self.zoom_in_button)
        button_box4.addWidget(self.zoom_out_button)

        button_box6 = QtWidgets.QHBoxLayout()
        button_box6.addWidget(self.compress_height_button)
        button_box6.addWidget(self.expand_height_button)

        button_box5 = QtWidgets.QHBoxLayout()
        button_box5.addWidget(self.confirm_button)
        button_box5.addWidget(self.ignore_button)
        button_box5.addWidget(self.clear_review_button)
        button_box5.addWidget(self.save_note_button)

        signal_tab = QtWidgets.QWidget()
        signal_layout = QtWidgets.QVBoxLayout(signal_tab)
        signal_layout.addWidget(self.signal_table)
        signal_layout.addWidget(self.detail_edit)
        signal_layout.addWidget(self.note_edit)
        signal_layout.addLayout(button_box5)

        report_tab = QtWidgets.QWidget()
        report_layout = QtWidgets.QVBoxLayout(report_tab)
        report_layout.addWidget(self.stats_edit)
        report_layout.addWidget(self.lifecycle_table)
        report_layout.addWidget(self.trade_table)

        record_tab = QtWidgets.QWidget()
        record_layout = QtWidgets.QVBoxLayout(record_tab)
        record_buttons = QtWidgets.QHBoxLayout()
        record_buttons.addWidget(self.refresh_records_button)
        record_buttons.addWidget(self.load_selected_record_button)
        record_layout.addLayout(record_buttons)
        record_layout.addWidget(self.record_table)
        record_layout.addWidget(self.record_detail_edit)

        topic_tab = QtWidgets.QWidget()
        topic_layout = QtWidgets.QVBoxLayout(topic_tab)
        topic_layout.addWidget(self.topic_tree)
        topic_stage_layout = QtWidgets.QHBoxLayout()
        topic_stage_layout.addWidget(QtWidgets.QLabel("开发状态"))
        topic_stage_layout.addWidget(self.topic_stage_button)
        topic_layout.addLayout(topic_stage_layout)
        topic_layout.addWidget(self.topic_detail_edit)

        strategy_tab = QtWidgets.QWidget()
        strategy_layout = QtWidgets.QVBoxLayout(strategy_tab)
        strategy_layout.addWidget(self.strategy_combo)
        strategy_layout.addWidget(self.strategy_tree)
        strategy_layout.addWidget(self.strategy_detail_edit)

        self.info_tabs: QtWidgets.QTabWidget = QtWidgets.QTabWidget()
        self.info_tabs.addTab(signal_tab, "信号")
        self.info_tabs.addTab(report_tab, "回测")
        self.info_tabs.addTab(record_tab, "记录")
        self.info_tabs.addTab(topic_tab, "知识点")
        self.info_tabs.addTab(strategy_tab, "策略开发")

        left_layout = QtWidgets.QVBoxLayout()
        left_layout.addLayout(form)
        left_layout.addLayout(button_box1)
        left_layout.addLayout(button_box2)
        left_layout.addLayout(button_box3)
        left_layout.addLayout(button_box4)
        left_layout.addLayout(button_box6)
        left_layout.addWidget(self.status_label)
        left_layout.addWidget(self.material_refs_edit)
        left_layout.addWidget(self.info_tabs)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        left_widget = QtWidgets.QWidget()
        left_widget.setLayout(left_layout)
        splitter.addWidget(left_widget)

        right_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        right_splitter.addWidget(self.chart)
        compare_widget = QtWidgets.QWidget()
        compare_layout = QtWidgets.QVBoxLayout(compare_widget)
        compare_layout.setContentsMargins(0, 0, 0, 0)
        compare_layout.addWidget(self.compare_title_label)
        compare_layout.addWidget(self.compare_chart)
        right_splitter.addWidget(compare_widget)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 1)
        right_splitter.setSizes([960, 320])
        splitter.addWidget(right_splitter)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([460, 1300])

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(splitter)
        self.setLayout(layout)
        self.apply_material_calendar_marks()
        self.refresh_material_reference_panel()

    def init_shortcuts(self) -> None:
        QtGui.QShortcut(QtGui.QKeySequence("Left"), self, activated=self.chart.pan_left)
        QtGui.QShortcut(QtGui.QKeySequence("Right"), self, activated=self.chart.pan_right)
        QtGui.QShortcut(QtGui.QKeySequence("Up"), self, activated=self.chart.zoom_in)
        QtGui.QShortcut(QtGui.QKeySequence("Down"), self, activated=self.chart.zoom_out)

    def refresh_overviews(self) -> None:
        self.overviews = self.engine.get_bar_overview()
        self.overviews.sort(key=lambda item: (item.exchange.value if item.exchange else "", item.symbol, item.interval.value if item.interval else ""))

        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        for overview in self.overviews:
            self.dataset_combo.addItem(build_dataset_label(overview), overview)
        self.dataset_combo.blockSignals(False)

        if self.overviews:
            self.dataset_combo.setCurrentIndex(0)
            self.on_dataset_changed(0)
            self.status_label.setText(f"共发现 {len(self.overviews)} 组本地 K 线数据")
        else:
            self.status_label.setText("数据库里没有可用的 K 线数据")

    def on_dataset_changed(self, index: int) -> None:
        if index < 0:
            return

        overview: BarOverview | None = self.dataset_combo.itemData(index)
        if not overview or not overview.start or not overview.end:
            return

        self.current_overview = overview
        if overview.interval == Interval.HOUR:
            hour_index = self.timeframe_combo.findData("1h")
            if hour_index >= 0:
                self.timeframe_combo.blockSignals(True)
                self.timeframe_combo.setCurrentIndex(hour_index)
                self.timeframe_combo.blockSignals(False)
        self.start_edit.setDateTime(to_qdatetime(get_recent_start(overview, self.bar_limit_spin.value(), self.get_selected_display_interval())))
        self.end_edit.setDateTime(to_qdatetime(overview.end))
        self.focus_date_edit.setDate(QtCore.QDate(overview.end.year, overview.end.month, overview.end.day))

    def on_timeframe_changed(self, _index: int) -> None:
        if self.current_overview:
            self.start_edit.setDateTime(
                to_qdatetime(get_recent_start(self.current_overview, self.bar_limit_spin.value(), self.get_selected_display_interval()))
            )

    def get_selected_display_interval(self) -> DisplayIntervalOption:
        key = self.timeframe_combo.currentData()
        return DISPLAY_INTERVAL_MAP.get(str(key), DISPLAY_INTERVAL_MAP["1m"])

    def get_selected_compare_interval(self) -> DisplayIntervalOption:
        key = self.compare_timeframe_combo.currentData()
        if key == "auto":
            return resolve_higher_timeframe_option(self.get_selected_display_interval())
        if key == "1d":
            return DisplayIntervalOption("1d", "1日", Interval.DAILY, 1, 1440)
        return DISPLAY_INTERVAL_MAP.get(str(key), resolve_higher_timeframe_option(self.get_selected_display_interval()))

    def on_compare_timeframe_changed(self, _index: int) -> None:
        if self.current_source_bars:
            self.load_compare_chart(self.current_source_bars, self.current_display_interval)

    def set_display_interval_key(self, key: str) -> None:
        index = self.timeframe_combo.findData(key)
        if index < 0:
            return
        self.timeframe_combo.blockSignals(True)
        self.timeframe_combo.setCurrentIndex(index)
        self.timeframe_combo.blockSignals(False)

    def get_selected_focus_days(self) -> int:
        value = self.focus_range_combo.currentData()
        return int(value or 1)

    def apply_focus_date_range(self) -> None:
        if not self.current_overview or not self.current_overview.start or not self.current_overview.end:
            self.status_label.setText("当前没有可定位的数据集")
            return

        target_date = self.focus_date_edit.date().toPython()
        start, end = build_focus_date_window(target_date, self.get_selected_focus_days())
        overview_start = self.current_overview.start.astimezone(DB_TZ)
        overview_end = self.current_overview.end.astimezone(DB_TZ)
        start = max(start, overview_start)
        end = min(end, overview_end)
        if start > end:
            self.pending_focus_datetime = None
            self.status_label.setText("目标日期超出当前数据集范围")
            return

        self.start_edit.setDateTime(to_qdatetime(start))
        self.end_edit.setDateTime(to_qdatetime(end))
        self.pending_focus_datetime = datetime(target_date.year, target_date.month, target_date.day, 12, 0, tzinfo=DB_TZ)
        self.load_chart()

    def focus_selected_date(self) -> None:
        if not self.current_bars:
            self.status_label.setText("请先加载图表后再定位日期")
            return

        target_date = self.focus_date_edit.date().toPython()
        target_dt = datetime(target_date.year, target_date.month, target_date.day, 12, 0, tzinfo=DB_TZ)
        display_minutes = max(self.current_display_interval.minutes, 1)
        window = max(80, min(1600, (self.get_selected_focus_days() * 24 * 60) // display_minutes))
        self.focus_on_datetime(target_dt, window=window)

    def apply_material_calendar_marks(self) -> None:
        """在资料日历里高亮高置信度页面日期。"""
        default_format = QtGui.QTextCharFormat()
        for year in range(2010, 2036):
            for month in range(1, 13):
                self.focus_calendar.setDateTextFormat(QtCore.QDate(year, month, 1), default_format)

        marked_format = QtGui.QTextCharFormat()
        marked_format.setFontWeight(QtGui.QFont.Weight.Bold)
        marked_format.setBackground(QtGui.QColor(255, 241, 118))
        marked_format.setForeground(QtGui.QColor(51, 51, 51))

        for date_text in self.material_date_refs:
            ref_date = date.fromisoformat(date_text)
            qdate = QtCore.QDate(ref_date.year, ref_date.month, ref_date.day)
            self.focus_calendar.setDateTextFormat(qdate, marked_format)

    def on_focus_date_changed(self, qdate: QtCore.QDate) -> None:
        self.refresh_material_reference_panel(qdate.toPython())

    def on_focus_calendar_clicked(self, qdate: QtCore.QDate) -> None:
        self.focus_date_edit.setDate(qdate)
        if qdate.toPython().isoformat() in self.material_date_refs:
            self.apply_focus_date_range()

    def refresh_material_reference_panel(self, target_date: date | None = None) -> None:
        """显示当前日期命中的资料页。"""
        if target_date is None:
            target_date = self.focus_date_edit.date().toPython()

        refs = self.material_date_refs.get(target_date.isoformat(), [])
        if not refs:
            self.material_refs_edit.setPlainText("当前日期没有已建立的高置信度资料索引。")
            return

        lines = [f"{target_date:%Y-%m-%d} 命中 {len(refs)} 页资料：", ""]
        for ref in refs:
            lines.append(f"[{ref.source}] {ref.title}")
            lines.append(f"置信度：{ref.confidence}")
            lines.append(f"依据：{ref.evidence}")
            lines.append(ref.page_path)
            lines.append("")
        self.material_refs_edit.setPlainText("\n".join(lines).strip())

    def load_chart(self) -> None:
        overview: BarOverview | None = self.dataset_combo.currentData()
        if not overview or not overview.exchange or not overview.interval:
            self.status_label.setText("没有可加载的数据集")
            return

        start = self.start_edit.dateTime().toPython().astimezone(DB_TZ)
        end = self.end_edit.dateTime().toPython().astimezone(DB_TZ)
        display_interval = self.get_selected_display_interval()
        source_bars = self.load_chart_source_bars(overview, start, end, display_interval)
        bars = aggregate_bars_to_display_interval(source_bars, display_interval)

        if not bars:
            self.status_label.setText("选定区间内没有 K 线数据")
            self.chart.clear_all()
            self.clear_overlays()
            self.compare_chart.clear_all()
            self.clear_compare_overlays()
            self.clear_bar_count_items()
            self.current_ema_values = []
            self.current_source_bars = []
            self.pending_focus_datetime = None
            return

        limit = self.bar_limit_spin.value()
        if len(bars) > limit:
            bars = bars[-limit:]
            source_bars = [bar for bar in source_bars if bar.datetime >= bars[0].datetime]

        pricetick = self.engine.get_pricetick(overview.symbol, overview.exchange, bars)
        (
            ema_values,
            signals,
            background,
            structure_phase_names,
            structure_phases,
            breakout_event_names,
            breakout_event_phases,
        ) = build_brooks_annotations(bars, pricetick)

        self.chart.clear_all()
        self.clear_overlays()
        self.chart.update_history(bars)

        self.current_bars = bars
        self.current_source_bars = source_bars
        self.current_datetimes = [bar.datetime for bar in bars]
        self.current_signals = signals
        self.current_background = background
        self.current_display_interval = display_interval
        self.current_structure_phase_names = structure_phase_names
        self.current_structure_phases = structure_phases
        self.current_breakout_event_names = breakout_event_names
        self.current_breakout_event_phases = breakout_event_phases
        self.current_ema_values = ema_values
        self.current_bar_counts = build_bar_count_values(bars)
        self.chart.refresh_axis_layout()
        self.draw_ema_line(ema_values)
        self.draw_background_label(background)
        self.draw_topic_overlay()
        if self.kind_filter_combo.currentText() != "不检测":
            self.draw_signal_annotations(bars, signals)
        self.draw_trade_annotations(self.current_trades)
        self.apply_signal_filters(select_first=True)
        self.refresh_bar_count_overlay()
        self.load_compare_chart(source_bars, display_interval)

        self.status_label.setText(
            f"已加载 {len(bars)} 根K线（{display_interval.label}），识别到 {len(signals)} 个程序化信号，背景：{background}。"
        )
        if self.pending_focus_datetime is not None:
            display_minutes = max(display_interval.minutes, 1)
            window = max(80, min(1600, (self.get_selected_focus_days() * 24 * 60) // display_minutes))
            self.focus_on_datetime(self.pending_focus_datetime, window=window)
            self.pending_focus_datetime = None

    def load_chart_source_bars(
        self,
        overview: BarOverview,
        start: datetime,
        end: datetime,
        display_interval: DisplayIntervalOption,
    ) -> list[BarData]:
        """按显示周期决定底层读取的原始 K 线。"""
        if overview.interval == Interval.MINUTE:
            return self.engine.load_bar_data(overview.symbol, overview.exchange, Interval.MINUTE, start, end)

        if overview.interval == Interval.HOUR and display_interval.interval == Interval.HOUR and display_interval.window == 1:
            return self.engine.load_bar_data(overview.symbol, overview.exchange, Interval.HOUR, start, end)

        if overview.interval == Interval.DAILY and display_interval.interval == Interval.DAILY:
            return self.engine.load_bar_data(overview.symbol, overview.exchange, Interval.DAILY, start, end)

        self.status_label.setText("当前数据集不支持向更小周期切换，请选择分钟线数据集。")
        return []

    def clear_overlays(self) -> None:
        plot = self.chart.get_plot("candle")
        if plot is None:
            self.overlay_items.clear()
            return
        for item in self.overlay_items:
            try:
                plot.removeItem(item)
            except Exception:
                pass
        self.overlay_items.clear()

    def clear_compare_overlays(self) -> None:
        plot = self.compare_chart.get_plot("candle")
        if plot is None:
            self.compare_overlay_items.clear()
            return
        for item in self.compare_overlay_items:
            try:
                plot.removeItem(item)
            except Exception:
                pass
        self.compare_overlay_items.clear()

    def clear_compare_focus_items(self) -> None:
        plot = self.compare_chart.get_plot("candle")
        if plot is None:
            self.compare_focus_items.clear()
            return
        for item in self.compare_focus_items:
            try:
                plot.removeItem(item)
            except Exception:
                pass
        self.compare_focus_items.clear()

    def clear_bar_count_items(self) -> None:
        plot = self.chart.get_plot("candle")
        if plot is None:
            self.bar_count_items.clear()
            return
        for item in self.bar_count_items:
            try:
                plot.removeItem(item)
            except Exception:
                pass
        self.bar_count_items.clear()

    def redraw_chart_overlays(self) -> None:
        """统一重绘图表附加层。"""
        if not self.current_bars:
            return

        self.clear_overlays()
        self.clear_bar_count_items()
        self.draw_ema_line(self.current_ema_values)
        self.draw_background_label(self.current_background)
        self.draw_topic_overlay()
        if self.kind_filter_combo.currentText() != "不检测":
            self.draw_signal_annotations(self.current_bars, self.current_signals)
        self.draw_trade_annotations(self.current_trades)
        self.refresh_bar_count_overlay()

    def load_compare_chart(
        self,
        source_bars: list[BarData],
        display_interval: DisplayIntervalOption,
    ) -> None:
        """同步加载更高周期对照图。"""
        compare_option = self.get_selected_compare_interval()
        compare_bars = aggregate_bars_to_interval(source_bars, compare_option.interval, compare_option.window)
        if not compare_bars:
            self.compare_chart.clear_all()
            self.clear_compare_overlays()
            self.compare_title_label.setText("更高周期对照：暂无数据")
            self.current_compare_bars = []
            self.current_compare_signals = []
            self.current_compare_ema_values = []
            return

        if len(compare_bars) > 400:
            compare_bars = compare_bars[-400:]

        compare_tick = self.engine.get_pricetick(self.current_overview.symbol if self.current_overview else "", self.current_overview.exchange if self.current_overview and self.current_overview.exchange else Exchange.LOCAL, compare_bars)
        compare_ema, compare_signals, compare_background, _compare_structure_names, _compare_structure_phases, _compare_event_names, _compare_event_phases = build_brooks_annotations(compare_bars, compare_tick)

        self.compare_chart.clear_all()
        self.clear_compare_overlays()
        self.compare_chart.update_history(compare_bars)
        self.current_compare_bars = compare_bars
        self.current_compare_signals = compare_signals
        self.current_compare_ema_values = compare_ema
        self.compare_chart.refresh_axis_layout()
        self.draw_ema_line_on_chart(self.compare_chart, self.compare_overlay_items, compare_ema)
        self.draw_background_label_on_chart(self.compare_chart, self.compare_overlay_items, f"更高周期背景: {compare_background}", compare_bars)
        self.draw_signal_annotations_on_plot(self.compare_chart, self.compare_overlay_items, compare_bars, compare_signals)
        self.compare_title_label.setText(f"更高周期对照：{compare_option.label} | {len(compare_bars)} 根")
        self.sync_compare_chart_view()

    def refresh_bar_count_overlay(self) -> None:
        self.clear_bar_count_items()

        if not self.show_bar_count_checkbox.isChecked():
            return
        if not self.current_bars or not self.current_bar_counts:
            return

        plot = self.chart.get_plot("candle")
        if plot is None:
            return

        first_plot = self.chart.get_plot("candle")
        if first_plot is None:
            return
        x_range = first_plot.getViewBox().viewRange()[0]
        min_ix = max(0, int(x_range[0]) - 2)
        max_ix = min(len(self.current_bars) - 1, int(x_range[1]) + 2)
        interval = self.bar_count_interval_spin.value()

        visible_bars = self.current_bars[min_ix:max_ix + 1]
        avg_range = 0.0
        if visible_bars:
            avg_range = sum(max(bar.high_price - bar.low_price, 0.0) for bar in visible_bars) / len(visible_bars)
        avg_range = max(avg_range, 1e-6)

        for index in range(min_ix, max_ix + 1):
            count = self.current_bar_counts[index]
            if count != 1 and count % interval != 0:
                continue

            bar = self.current_bars[index]
            if count == 18:
                color = (0, 255, 255)
            elif count % 12 == 0:
                color = (228, 0, 127)
            else:
                color = (160, 160, 160)

            label = pg.TextItem(text=str(count), color=color, anchor=(0.5, 0))
            label.setFont(brooks_font(BROOKS_LABEL_SIZE_SMALL))
            label.setPos(index, bar.low_price - avg_range * 0.18)
            plot.addItem(label)
            self.bar_count_items.append(label)

    def on_chart_view_changed(self, *_args) -> None:
        self.chart.refresh_bottom_axis_ticks()
        if any(topic.overlay_group in {"背景", "关键位置", "辅助"} for topic in self.get_overlay_topics()):
            self.redraw_chart_overlays()
        else:
            self.refresh_bar_count_overlay()
        self.sync_compare_chart_view()

    def on_bar_count_setting_changed(self, *_args) -> None:
        self.refresh_bar_count_overlay()

    def draw_ema_line(self, ema_values: list[float]) -> None:
        self.draw_ema_line_on_chart(self.chart, self.overlay_items, ema_values)

    def draw_ema_line_on_chart(
        self,
        chart_widget: InteractiveChartWidget,
        overlay_items: list[object],
        ema_values: list[float],
    ) -> None:
        plot = chart_widget.get_plot("candle")
        if plot is None or not ema_values:
            return
        pen = brooks_pen((255, 215, 0), width=BROOKS_LINE_WIDTH_STRONG + 0.35)
        item = pg.PlotCurveItem(list(range(len(ema_values))), ema_values, pen=pen)
        item.setZValue(4)
        plot.addItem(item)
        overlay_items.append(item)

        label = pg.TextItem(text="EMA20", color=(255, 215, 0), anchor=(1, 1))
        label.setFont(brooks_font(BROOKS_LABEL_SIZE_NORMAL))
        label.setPos(len(ema_values) - 1, ema_values[-1])
        plot.addItem(label)
        overlay_items.append(label)

    def draw_background_label(self, background: str) -> None:
        self.draw_background_label_on_chart(self.chart, self.overlay_items, f"背景: {background}", self.current_bars)

    def draw_background_label_on_chart(
        self,
        chart_widget: InteractiveChartWidget,
        overlay_items: list[object],
        text: str,
        bars: list[BarData],
    ) -> None:
        plot = chart_widget.get_plot("candle")
        if plot is None or not bars:
            return
        label = pg.TextItem(text=text, color=(255, 255, 255), anchor=(0, 0))
        label.setFont(brooks_font(BROOKS_LABEL_SIZE_TITLE, mono=False, weight=QtGui.QFont.Weight.Bold))
        label.setPos(1, max(bar.high_price for bar in bars))
        plot.addItem(label)
        overlay_items.append(label)

    def draw_topic_overlay(self) -> None:
        """根据知识点选择绘制附加图层。"""
        topics = self.get_overlay_topics()
        if not topics:
            return

        topic_keys = {topic.key for topic in topics}
        if "bg_all" in topic_keys:
            topics = [topic for topic in topics if topic.overlay_group != "背景" or topic.key == "bg_all"]
        if "key_all" in topic_keys:
            topics = [topic for topic in topics if topic.overlay_group != "关键位置" or topic.key == "key_all"]

        for topic in topics:
            if topic.overlay_group == "背景":
                if topic.key in {"bg_all", "bg_narrow_channel", "bg_broad_channel", "bg_trading_range", "bg_trending_tr"}:
                    self.draw_structure_phase_overlay(topic.key)
                if topic.key in {"bg_all", "bg_breakout", "bg_opening_reversal", "bg_midday_reversal"}:
                    self.draw_breakout_event_overlay(topic.key)
                continue
            if topic.overlay_group == "关键位置":
                self.draw_key_level_overlay(topic.key)
                continue
            if topic.overlay_group == "辅助":
                self.draw_auxiliary_overlay(topic.key)

    def draw_key_level_overlay(self, topic_key: str) -> None:
        """绘制关键位置图层。"""
        if topic_key in {"key_all", "key_magnets", "key_prior_swing"}:
            self.draw_prior_swing_overlay()
        if topic_key in {"key_all", "key_magnets", "key_trendline"}:
            self.draw_trendline_overlay()
        if topic_key in {"key_all", "key_magnets", "key_higher_timeframe"}:
            self.draw_higher_timeframe_levels()
        if topic_key in {"key_all", "key_magnets", "key_session_levels"}:
            self.draw_session_levels()
        measured_move_labels: tuple[str, ...] = ()
        if topic_key in {"key_all", "key_magnets", "key_measured_move"}:
            measured_move_labels = (
                "Leg1=Leg2↑", "Leg1=Leg2↓",
                "TR MM↑", "TR MM↓",
                "BO MM↑", "BO MM↓",
                "MG MM↑", "MG MM↓",
            )
        elif topic_key == "key_mm_leg_equal":
            measured_move_labels = ("Leg1=Leg2↑", "Leg1=Leg2↓")
        elif topic_key == "key_mm_leg_equal_deep_pb":
            measured_move_labels = ("Leg1=Leg2↑", "Leg1=Leg2↓")
        elif topic_key == "key_mm_leg_equal_tr_context":
            measured_move_labels = ("Leg1=Leg2↑", "Leg1=Leg2↓")
        elif topic_key == "key_mm_leg_equal_ema":
            measured_move_labels = ("Leg1=Leg2↑", "Leg1=Leg2↓")
        elif topic_key == "key_mm_tr_height":
            measured_move_labels = ("TR MM↑", "TR MM↓")
        elif topic_key == "key_mm_bo_height":
            measured_move_labels = ("BO MM↑", "BO MM↓")
        elif topic_key == "key_mm_measuring_gap":
            measured_move_labels = ("MG MM↑", "MG MM↓", "Neg MG↑", "Neg MG↓", "MG Mid1↑", "MG Mid1↓", "MG Mid2↑", "MG Mid2↓")
        elif topic_key == "key_mm_negative_measuring_gap":
            measured_move_labels = ("Neg MG↑", "Neg MG↓")
        elif topic_key == "key_mm_measuring_gap_midline":
            measured_move_labels = ("MG Mid1↑", "MG Mid1↓", "MG Mid2↑", "MG Mid2↓")
        if measured_move_labels:
            allowed_categories: tuple[str, ...] = ()
            if topic_key == "key_mm_leg_equal_deep_pb":
                allowed_categories = ("强趋势深回调",)
            elif topic_key == "key_mm_leg_equal_tr_context":
                allowed_categories = ("交易区间内部",)
            elif topic_key == "key_mm_leg_equal_ema":
                allowed_categories = ("EMA配合",)
            elif topic_key == "key_mm_measuring_gap":
                allowed_categories = ("测量缺口",)
            elif topic_key == "key_mm_negative_measuring_gap":
                allowed_categories = ("负测量缺口",)
            elif topic_key == "key_mm_measuring_gap_midline":
                allowed_categories = ("测量缺口中线/标准", "测量缺口中线/较小")
            self.draw_measured_move_overlay(measured_move_labels, allowed_categories)

    def draw_auxiliary_overlay(self, topic_key: str) -> None:
        """绘制形态与审计辅助图层。"""
        if topic_key == "aux_bom_patterns":
            self.draw_bar_pattern_overlay()
        elif topic_key == "aux_micro_gap":
            self.draw_micro_gap_overlay()
        elif topic_key == "aux_opening_range":
            self.draw_opening_range_overlay()

    def draw_prior_swing_overlay(self) -> None:
        """绘制前高前低磁体。"""
        plot = self.chart.get_plot("candle")
        if plot is None or len(self.current_bars) < 8:
            return

        min_ix, max_ix = self.get_visible_index_range()
        start_ix = max(0, min_ix - 40)
        segment = self.current_bars[start_ix:max_ix + 1]
        swings = find_pivot_swings(segment, strength=2)
        highs = [(start_ix + index, price) for index, kind, price in swings if kind == "H"][-3:]
        lows = [(start_ix + index, price) for index, kind, price in swings if kind == "L"][-3:]

        for order, (index, price) in enumerate(reversed(highs), start=1):
            self.draw_horizontal_key_line(plot, index, max_ix, price, f"前高{order}", (255, 183, 77))
        for order, (index, price) in enumerate(reversed(lows), start=1):
            self.draw_horizontal_key_line(plot, index, max_ix, price, f"前低{order}", (129, 199, 132))

    def draw_trendline_overlay(self) -> None:
        """绘制趋势线与通道线。"""
        plot = self.chart.get_plot("candle")
        if plot is None or len(self.current_bars) < 12 or not self.current_structure_phases:
            return

        min_ix, max_ix = self.get_visible_index_range()
        for phase in self.current_structure_phases:
            if phase.name not in {"窄幅通道", "宽幅通道", "趋势交易区间"}:
                continue
            if phase.end_index < min_ix or phase.start_index > max_ix:
                continue

            segment_start = max(0, phase.start_index - 6)
            segment_end = min(len(self.current_bars) - 1, phase.end_index + 2)
            if segment_end - segment_start < 8:
                continue

            segment = self.current_bars[segment_start:segment_end + 1]
            direction = "bull" if phase.direction == "多" else "bear"
            avg_range = max(sum(max(bar.high_price - bar.low_price, 0.0) for bar in segment) / len(segment), 1e-12)
            geometry = select_channel_geometry(segment, direction, avg_range, strength=1)
            if not geometry.trend_anchor1 or not geometry.trend_anchor2 or not geometry.opposite_anchor:
                continue
            phase_span = phase.end_index - phase.start_index + 1
            min_anchor_span = max(4, phase_span // 3)
            min_quality = 0.18 if phase.name == "宽幅通道" and phase_span >= 12 else 0.22
            if geometry.anchor_span_bars < min_anchor_span:
                continue
            if geometry.quality_score < min_quality:
                continue

            anchor1 = (segment_start + geometry.trend_anchor1[0], geometry.trend_anchor1[1])
            anchor2 = (segment_start + geometry.trend_anchor2[0], geometry.trend_anchor2[1])
            opposite_anchor = (segment_start + geometry.opposite_anchor[0], geometry.opposite_anchor[1])
            color = (80, 200, 255) if direction == "bull" else (255, 138, 128)
            self.draw_parallel_channel_lines(plot, anchor1, anchor2, opposite_anchor, segment_end, color)

    def draw_higher_timeframe_levels(self) -> None:
        """绘制更高时间周期的前一根高低收。"""
        plot = self.chart.get_plot("candle")
        if plot is None or not self.current_source_bars:
            return

        option = self.get_selected_compare_interval()
        higher_bars = aggregate_bars_to_interval(self.current_source_bars, option.interval, option.window)
        if len(higher_bars) < 2:
            return

        ref_bar = higher_bars[-2]
        end_ix = len(self.current_bars) - 1
        self.draw_horizontal_key_line(plot, 0, end_ix, ref_bar.high_price, f"前{option.label}高", (255, 213, 79))
        self.draw_horizontal_key_line(plot, 0, end_ix, ref_bar.low_price, f"前{option.label}低", (77, 182, 172))
        self.draw_horizontal_key_line(plot, 0, end_ix, ref_bar.close_price, f"前{option.label}收", (176, 190, 197))

    def draw_session_levels(self) -> None:
        """绘制当日开盘和昨日关键价。"""
        plot = self.chart.get_plot("candle")
        if plot is None or not self.current_source_bars or not self.current_bars:
            return

        latest_date = self.current_bars[-1].datetime.date()
        session_map = group_bars_by_session(self.current_source_bars)
        dates = sorted(session_map.keys())
        if latest_date not in session_map:
            return

        end_ix = len(self.current_bars) - 1
        current_session = session_map[latest_date]
        self.draw_horizontal_key_line(plot, 0, end_ix, current_session[0].open_price, "当日开盘", (144, 202, 249))

        latest_index = dates.index(latest_date)
        if latest_index <= 0:
            return

        previous_session = session_map[dates[latest_index - 1]]
        self.draw_horizontal_key_line(plot, 0, end_ix, previous_session[-1].close_price, "昨日收盘", (255, 241, 118))
        self.draw_horizontal_key_line(plot, 0, end_ix, max(bar.high_price for bar in previous_session), "昨日高点", (255, 204, 128))
        self.draw_horizontal_key_line(plot, 0, end_ix, min(bar.low_price for bar in previous_session), "昨日低点", (165, 214, 167))

    def draw_measured_move_overlay(
        self,
        allowed_labels: tuple[str, ...],
        allowed_categories: tuple[str, ...] = (),
    ) -> None:
        """绘制可见区间内的 Brooks 测量走势。"""
        plot = self.chart.get_plot("candle")
        if plot is None or len(self.current_bars) < 12:
            return

        min_ix, max_ix = self.get_visible_index_range()
        segment_start = max(0, min_ix - 160)
        segment = self.current_bars[segment_start:max_ix + 1]
        segment_ema = self.current_ema_values[segment_start:max_ix + 1]
        segment_structure = self.current_structure_phase_names[segment_start:max_ix + 1]
        markers: list[MeasuredMoveMarker] = detect_measured_move_markers(
            segment,
            ema_values=segment_ema,
            structure_phase_names=segment_structure,
            breakout_event_names=self.current_breakout_event_names[segment_start:max_ix + 1],
        )
        if not markers:
            return

        visible_markers = [
            marker
            for marker in markers
            if (min_ix - segment_start - 8) <= marker.projection_start_index <= (max_ix - segment_start + 8)
            and marker.label in allowed_labels
            and (not allowed_categories or marker.category in allowed_categories)
        ]
        if not visible_markers:
            visible_markers = [
                marker
                for marker in markers
                if marker.label in allowed_labels and (not allowed_categories or marker.category in allowed_categories)
            ][-8:]

        color_map = {
            "Leg1=Leg2↑": (102, 187, 106),
            "Leg1=Leg2↓": (239, 83, 80),
            "TR MM↑": (41, 182, 246),
            "TR MM↓": (255, 167, 38),
            "BO MM↑": (171, 71, 188),
            "BO MM↓": (255, 112, 67),
            "MG MM↑": (255, 241, 118),
            "MG MM↓": (255, 171, 64),
            "Neg MG↑": (255, 138, 128),
            "Neg MG↓": (255, 112, 67),
            "MG Mid1↑": (255, 245, 157),
            "MG Mid1↓": (255, 204, 128),
            "MG Mid2↑": (255, 249, 196),
            "MG Mid2↓": (255, 224, 178),
        }

        for marker in visible_markers[:20]:
            projection_start = segment_start + marker.projection_start_index
            leg_start = segment_start + marker.leg_start_index
            leg_end = segment_start + marker.leg_end_index
            end_index = segment_start + marker.end_index
            color = color_map.get(marker.label, (102, 187, 106) if marker.direction == "bull" else (239, 83, 80))
            self.draw_horizontal_key_line(plot, projection_start, end_index, marker.target_price, marker.label, color)

            if leg_start == leg_end:
                guide = pg.PlotCurveItem(
                    [leg_start, end_index],
                    [marker.leg_start_price, marker.target_price],
                    pen=brooks_pen(color, width=BROOKS_LINE_WIDTH_THIN, style=QtCore.Qt.PenStyle.DashLine),
                )
            else:
                guide = pg.PlotCurveItem(
                    [leg_start, leg_end],
                    [marker.leg_start_price, marker.leg_end_price],
                    pen=brooks_pen(color, width=BROOKS_LINE_WIDTH_THIN, style=QtCore.Qt.PenStyle.DashLine),
                )
            guide.setZValue(-5)
            plot.addItem(guide)
            self.overlay_items.append(guide)

    def draw_horizontal_key_line(
        self,
        plot,
        start_index: int,
        end_index: int,
        price: float,
        label_text: str,
        color: tuple[int, int, int],
    ) -> None:
        """绘制水平关键位。"""
        line = pg.PlotCurveItem(
            [start_index - 0.3, end_index + 0.3],
            [price, price],
            pen=brooks_pen(color, width=BROOKS_LINE_WIDTH_NORMAL, style=QtCore.Qt.PenStyle.DotLine),
        )
        line.setZValue(-6)
        plot.addItem(line)
        self.overlay_items.append(line)

        label = pg.TextItem(text=label_text, color=color, anchor=(1, 1))
        label.setFont(brooks_font(BROOKS_LABEL_SIZE_SMALL))
        label.setPos(end_index + 0.2, price)
        plot.addItem(label)
        self.overlay_items.append(label)

    def draw_bar_pattern_overlay(self) -> None:
        """绘制 ii / ioi / oo 压缩形态。"""
        plot = self.chart.get_plot("candle")
        if plot is None or len(self.current_bars) < 3:
            return

        min_ix, max_ix = self.get_visible_index_range()
        markers: list[PatternMarker] = [
            marker
            for marker in detect_bar_patterns(self.current_bars)
            if min_ix - 3 <= marker.anchor_index <= max_ix + 3
        ]
        visible_bars = self.current_bars[max(0, min_ix):max_ix + 1]
        avg_range = max(
            sum(max(bar.high_price - bar.low_price, 0.0) for bar in visible_bars) / max(len(visible_bars), 1),
            1e-6,
        )
        color_map = {
            "ii": (66, 165, 245),
            "ioi": (255, 112, 67),
            "oo": (171, 71, 188),
        }

        for marker in markers:
            anchor_bar = self.current_bars[marker.anchor_index]
            color = color_map.get(marker.label, (200, 200, 200))
            label = pg.TextItem(text=marker.label, color=color, anchor=(0.5, 1.0))
            label.setFont(brooks_font(BROOKS_LABEL_SIZE_SMALL, weight=QtGui.QFont.Weight.Bold))
            label.setPos(marker.anchor_index, anchor_bar.high_price + avg_range * 0.22)
            plot.addItem(label)
            self.overlay_items.append(label)

    def draw_micro_gap_overlay(self) -> None:
        """绘制微缺口矩形。"""
        plot = self.chart.get_plot("candle")
        if plot is None or len(self.current_bars) < 3:
            return

        min_ix, max_ix = self.get_visible_index_range()
        markers: list[MicroGapMarker] = [
            marker
            for marker in detect_micro_gaps(self.current_bars)
            if min_ix - 3 <= marker.center_index <= max_ix + 3
        ]

        for marker in markers:
            rect = QtWidgets.QGraphicsRectItem(
                marker.left_index + 0.15,
                marker.bottom_price,
                (marker.right_index - marker.left_index) - 0.3,
                marker.top_price - marker.bottom_price,
            )
            if marker.direction == "bull":
                border = (76, 175, 80)
                fill = (76, 175, 80, 80)
            else:
                border = (229, 57, 53)
                fill = (229, 57, 53, 80)
            rect.setPen(brooks_pen(border, width=BROOKS_LINE_WIDTH_THIN))
            rect.setBrush(pg.mkBrush(fill))
            rect.setZValue(-3)
            plot.addItem(rect)
            self.overlay_items.append(rect)

            label = pg.TextItem(text="MG", color=border, anchor=(0.5, 1.0))
            label.setFont(brooks_font(BROOKS_LABEL_SIZE_MICRO, weight=QtGui.QFont.Weight.Bold))
            label.setPos(marker.center_index, marker.top_price)
            plot.addItem(label)
            self.overlay_items.append(label)

    def draw_opening_range_overlay(self) -> None:
        """绘制开盘区间、Bar 18 与 ORBO。"""
        plot = self.chart.get_plot("candle")
        if plot is None or not self.current_bars or self.current_display_interval.minutes > 15:
            return

        min_ix, max_ix = self.get_visible_index_range()
        markers: list[OpeningRangeMarker] = [
            marker
            for marker in build_opening_range_markers(self.current_bars)
            if marker.opening_end_index >= min_ix - 3 and marker.start_index <= max_ix + 3
        ]

        for marker in markers:
            start_ix = marker.start_index
            end_ix = len(self.current_bars) - 1
            first_bar_end = marker.bom_index or marker.opening_end_index
            self.draw_horizontal_key_line(plot, start_ix, first_bar_end, marker.first_bar_high, "首根高", (186, 104, 200))
            self.draw_horizontal_key_line(plot, start_ix, first_bar_end, marker.first_bar_low, "首根低", (186, 104, 200))
            self.draw_horizontal_key_line(plot, start_ix, end_ix, marker.high_price, "OR高", (79, 195, 247))
            self.draw_horizontal_key_line(plot, start_ix, end_ix, marker.low_price, "OR低", (129, 199, 132))

            if marker.bom_index is not None:
                bom_bar = self.current_bars[marker.bom_index]
                label = pg.TextItem(text="Open BOM", color=(186, 104, 200), anchor=(0.5, 1.0))
                label.setFont(brooks_font(BROOKS_LABEL_SIZE_SMALL, weight=QtGui.QFont.Weight.Bold))
                label.setPos(marker.bom_index, bom_bar.high_price)
                plot.addItem(label)
                self.overlay_items.append(label)

            if marker.bar18_index is not None:
                line = pg.PlotCurveItem(
                    [marker.bar18_index, marker.bar18_index],
                    [marker.low_price, marker.high_price],
                    pen=brooks_pen((0, 255, 255), width=BROOKS_LINE_WIDTH_THIN, style=QtCore.Qt.PenStyle.DashLine),
                )
                line.setZValue(-5)
                plot.addItem(line)
                self.overlay_items.append(line)

                label = pg.TextItem(text="18", color=(0, 255, 255), anchor=(0.5, 1.0))
                label.setFont(brooks_font(BROOKS_LABEL_SIZE_SMALL, weight=QtGui.QFont.Weight.Bold))
                label.setPos(marker.bar18_index, marker.high_price)
                plot.addItem(label)
                self.overlay_items.append(label)

            if marker.breakout_index is not None:
                breakout_bar = self.current_bars[marker.breakout_index]
                text = "ORBO↑" if marker.breakout_direction == "bull" else "ORBO↓"
                color = (33, 150, 243) if marker.breakout_direction == "bull" else (239, 83, 80)
                anchor = (0.5, 1.0 if marker.breakout_direction == "bull" else 0.0)
                label_y = breakout_bar.high_price if marker.breakout_direction == "bull" else breakout_bar.low_price
                label = pg.TextItem(text=text, color=color, anchor=anchor)
                label.setFont(brooks_font(BROOKS_LABEL_SIZE_SMALL, weight=QtGui.QFont.Weight.Bold))
                label.setPos(marker.breakout_index, label_y)
                plot.addItem(label)
                self.overlay_items.append(label)

    def sync_compare_chart_view(self) -> None:
        """让更高周期图与主图的时间范围同步。"""
        if not self.current_bars or not self.current_compare_bars:
            return

        min_ix, max_ix = self.get_visible_index_range()
        start_dt = self.current_bars[min_ix].datetime
        end_dt = self.current_bars[max_ix].datetime
        compare_datetimes = [bar.datetime for bar in self.current_compare_bars]
        start_compare_ix = find_nearest_datetime_index(compare_datetimes, start_dt)
        end_compare_ix = find_nearest_datetime_index(compare_datetimes, end_dt)
        if start_compare_ix is None or end_compare_ix is None:
            return

        left_ix = min(start_compare_ix, end_compare_ix)
        right_ix = max(start_compare_ix, end_compare_ix)
        visible_count = max(12, (right_ix - left_ix) + 8)
        self.compare_chart._bar_count = min(max(visible_count, 12), len(self.current_compare_bars))
        self.compare_chart._right_ix = min(
            len(self.current_compare_bars),
            max(self.compare_chart._bar_count, right_ix + max(2, visible_count // 3)),
        )
        self.compare_chart._update_x_range()
        self.compare_chart._update_y_range()
        self.draw_compare_focus_range(left_ix, right_ix, start_dt, end_dt)

    def draw_compare_focus_range(
        self,
        start_index: int,
        end_index: int,
        start_dt: datetime,
        end_dt: datetime,
    ) -> None:
        """在更高周期图上标注主图当前关注的时间范围。"""
        plot = self.compare_chart.get_plot("candle")
        if plot is None or not self.current_compare_bars:
            return

        self.clear_compare_focus_items()
        top_price, bottom_price, pad = get_phase_price_range(self.current_compare_bars, max(0, start_index), min(len(self.current_compare_bars) - 1, end_index))
        rect = QtWidgets.QGraphicsRectItem(
            start_index - 0.4,
            bottom_price - pad * 0.6,
            max((end_index - start_index) + 0.8, 0.8),
            (top_price - bottom_price) + pad * 1.2,
        )
        rect.setPen(brooks_pen((255, 235, 59), width=BROOKS_LINE_WIDTH_THIN, style=QtCore.Qt.PenStyle.DashLine))
        rect.setBrush(pg.mkBrush((255, 235, 59, BROOKS_BOX_ALPHA_NORMAL)))
        rect.setZValue(-3)
        plot.addItem(rect)
        self.compare_focus_items.append(rect)

        label = pg.TextItem(
            text=f"主图范围\n{start_dt:%m-%d %H:%M} -> {end_dt:%m-%d %H:%M}",
            color=(255, 235, 59),
            anchor=(0, 1),
        )
        label.setFont(brooks_font(BROOKS_LABEL_SIZE_SMALL))
        label.setPos(start_index, top_price + pad * 0.15)
        plot.addItem(label)
        self.compare_focus_items.append(label)

    def draw_parallel_channel_lines(
        self,
        plot,
        anchor1: tuple[int, float],
        anchor2: tuple[int, float],
        opposite_anchor: tuple[int, float],
        end_index: int,
        color: tuple[int, int, int],
    ) -> None:
        """绘制趋势线和与之平行的通道线。"""
        slope = calculate_line_slope(anchor1, anchor2)
        start_x = anchor1[0]
        end_x = max(end_index, anchor2[0])
        trend_y_start = anchor1[1]
        trend_y_end = anchor1[1] + slope * (end_x - start_x)
        line1 = pg.PlotCurveItem([start_x, end_x], [trend_y_start, trend_y_end], pen=brooks_pen(color, width=BROOKS_LINE_WIDTH_STRONG))
        line1.setZValue(-4)
        plot.addItem(line1)
        self.overlay_items.append(line1)

        offset = opposite_anchor[1] - (anchor1[1] + slope * (opposite_anchor[0] - start_x))
        channel_y_start = trend_y_start + offset
        channel_y_end = trend_y_end + offset
        line2 = pg.PlotCurveItem(
            [start_x, end_x],
            [channel_y_start, channel_y_end],
            pen=brooks_pen(color, width=BROOKS_LINE_WIDTH_NORMAL, style=QtCore.Qt.PenStyle.DashLine),
        )
        line2.setZValue(-4)
        plot.addItem(line2)
        self.overlay_items.append(line2)

    def get_visible_index_range(self) -> tuple[int, int]:
        """返回当前可见索引范围。"""
        plot = self.chart.get_plot("candle")
        if plot is None or not self.current_bars:
            return 0, max(len(self.current_bars) - 1, 0)
        x_range = plot.getViewBox().viewRange()[0]
        min_ix = int(max(0, x_range[0] - 1))
        max_ix = int(min(len(self.current_bars) - 1, x_range[1] + 1))
        return min_ix, max_ix

    def draw_structure_phase_overlay(self, topic_key: str) -> None:
        """绘制底层结构背景。"""
        plot = self.chart.get_plot("candle")
        if plot is None or not self.current_structure_phases:
            return

        phase_mapping = {
            "bg_all": {"窄幅通道", "宽幅通道", "趋势交易区间", "震荡"},
            "bg_narrow_channel": {"窄幅通道"},
            "bg_broad_channel": {"宽幅通道"},
            "bg_trending_tr": {"趋势交易区间"},
            "bg_trading_range": {"震荡"},
        }
        allowed = phase_mapping.get(topic_key, set())
        if not allowed:
            return

        view = plot.getViewBox()
        x_range = view.viewRange()[0]
        min_ix = int(max(0, x_range[0] - 1))
        max_ix = int(min(len(self.current_bars) - 1, x_range[1] + 1))

        color_map = {
            "窄幅通道": (0, 188, 212, BROOKS_BOX_ALPHA_LIGHT),
            "宽幅通道": (76, 175, 80, BROOKS_BOX_ALPHA_LIGHT),
            "趋势交易区间": (121, 134, 203, BROOKS_BOX_ALPHA_NORMAL),
            "震荡": (158, 158, 158, BROOKS_BOX_ALPHA_LIGHT),
        }

        for phase in self.current_structure_phases:
            if phase.name not in allowed:
                continue
            if phase.end_index < min_ix or phase.start_index > max_ix:
                continue
            segment_start = max(phase.start_index, min_ix)
            segment_end = min(phase.end_index, max_ix)
            if topic_key == "bg_all":
                self.draw_structure_badge(plot, phase, segment_start, segment_end)
            else:
                self.draw_phase_box(
                    plot,
                    phase,
                    segment_start,
                    segment_end,
                    color_map.get(phase.name, (128, 128, 128, 18)),
                    outline_color=(190, 190, 190),
                    label_text=build_structure_short_label(phase),
                    dashed=True,
                    z_value=-8,
                )

    def draw_breakout_event_overlay(self, topic_key: str) -> None:
        """绘制突破事件层。"""
        plot = self.chart.get_plot("candle")
        if plot is None or not self.current_breakout_event_phases:
            return

        phase_mapping = {
            "bg_all": {"突破起爆", "突破跟进", "突破测试", "失败突破", "开盘反转", "午间反转"},
            "bg_breakout": {"突破起爆", "突破跟进", "突破测试", "失败突破"},
            "bg_opening_reversal": {"开盘反转"},
            "bg_midday_reversal": {"午间反转"},
        }
        allowed = phase_mapping.get(topic_key, set())
        if not allowed:
            return

        view = plot.getViewBox()
        x_range = view.viewRange()[0]
        min_ix = int(max(0, x_range[0] - 1))
        max_ix = int(min(len(self.current_bars) - 1, x_range[1] + 1))

        color_map = {
            "突破起爆": (255, 193, 7, BROOKS_BOX_ALPHA_STRONG),
            "突破跟进": (255, 152, 0, BROOKS_BOX_ALPHA_NORMAL),
            "突破测试": (33, 150, 243, BROOKS_BOX_ALPHA_NORMAL),
            "失败突破": (244, 67, 54, BROOKS_BOX_ALPHA_NORMAL),
            "开盘反转": (186, 104, 200, BROOKS_BOX_ALPHA_NORMAL),
            "午间反转": (0, 188, 212, BROOKS_BOX_ALPHA_NORMAL),
        }

        for phase in self.current_breakout_event_phases:
            if phase.name not in allowed:
                continue
            if phase.name in {"无事件", "未就绪"}:
                continue
            if phase.end_index < min_ix or phase.start_index > max_ix:
                continue
            self.draw_phase_box(
                plot,
                phase,
                max(phase.start_index, min_ix),
                min(phase.end_index, max_ix),
                color_map.get(phase.name, (255, 152, 0, 30)),
                outline_color=get_event_outline_color(phase.name),
                label_text=build_event_short_label(phase),
                dashed=False,
                z_value=-5,
            )

    def draw_structure_badge(
        self,
        plot,
        phase: BackgroundPhase,
        start_index: int,
        end_index: int,
    ) -> None:
        """总览模式下，用 Brooks 风格的简短结构标签代替整块底色。"""
        phase_label = build_structure_short_label(phase)
        top_price, _bottom_price, pad = get_phase_price_range(self.current_bars, start_index, end_index)

        line = pg.PlotCurveItem(
            [start_index - 0.35, end_index + 0.35],
            [top_price + pad * 0.45, top_price + pad * 0.45],
            pen=brooks_pen(get_structure_outline_color(phase.name), width=BROOKS_LINE_WIDTH_NORMAL, style=QtCore.Qt.PenStyle.DashLine),
        )
        line.setZValue(-7)
        plot.addItem(line)
        self.overlay_items.append(line)

        label = pg.TextItem(text=phase_label, color=get_structure_outline_color(phase.name), anchor=(0, 1))
        label.setFont(brooks_font(BROOKS_LABEL_SIZE_SMALL))
        label.setPos(start_index, top_price + pad * 0.4)
        plot.addItem(label)
        self.overlay_items.append(label)

    def draw_phase_box(
        self,
        plot,
        phase: BackgroundPhase,
        start_index: int,
        end_index: int,
        fill_color: tuple[int, int, int, int],
        outline_color: tuple[int, int, int],
        label_text: str,
        dashed: bool,
        z_value: int,
    ) -> None:
        """用局部框标注结构或事件，更接近 Brooks 图示。"""
        top_price, bottom_price, pad = get_phase_price_range(self.current_bars, start_index, end_index)
        rect = QtWidgets.QGraphicsRectItem(
            start_index - 0.45,
            bottom_price - pad,
            (end_index - start_index) + 0.9,
            (top_price - bottom_price) + pad * 2,
        )
        line_style = QtCore.Qt.PenStyle.DashLine if dashed else QtCore.Qt.PenStyle.SolidLine
        rect.setPen(brooks_pen(outline_color, width=BROOKS_LINE_WIDTH_NORMAL if dashed else BROOKS_LINE_WIDTH_STRONG, style=line_style))
        rect.setBrush(pg.mkBrush(fill_color))
        rect.setZValue(z_value)
        plot.addItem(rect)
        self.overlay_items.append(rect)

        label = pg.TextItem(text=label_text, color=outline_color, anchor=(0, 1))
        label.setFont(brooks_font(BROOKS_LABEL_SIZE_SMALL))
        label.setPos(start_index, top_price + pad * 0.15)
        plot.addItem(label)
        self.overlay_items.append(label)

    def draw_signal_annotations(self, bars: list[BarData], signals: list[SignalAnnotation]) -> None:
        self.draw_signal_annotations_on_plot(self.chart, self.overlay_items, bars, signals)

    def draw_signal_annotations_on_plot(
        self,
        chart_widget: InteractiveChartWidget,
        overlay_items: list[object],
        bars: list[BarData],
        signals: list[SignalAnnotation],
    ) -> None:
        plot = chart_widget.get_plot("candle")
        if plot is None:
            return

        for signal in signals:
            signal_bar = bars[signal.signal_index]
            pen_color, brush_color = get_signal_colors(signal.kind, signal.quality)
            rect = QtWidgets.QGraphicsRectItem(
                signal.signal_index - BAR_WIDTH - 0.08,
                signal_bar.low_price,
                BAR_WIDTH * 2 + 0.16,
                signal_bar.high_price - signal_bar.low_price,
            )
            rect.setPen(brooks_pen(pen_color, width=BROOKS_LINE_WIDTH_STRONG))
            rect.setBrush(pg.mkBrush(brush_color))
            plot.addItem(rect)
            overlay_items.append(rect)

            is_long_signal = signal.kind.startswith("H") or signal.kind == "MAG多"
            label_y = signal_bar.low_price - (signal_bar.high_price - signal_bar.low_price) * 0.8 if is_long_signal else signal_bar.high_price + (signal_bar.high_price - signal_bar.low_price) * 0.8
            text = pg.TextItem(text=f"{signal.kind}\n{signal.quality}", color=pen_color, anchor=(0.5, 0.5))
            text.setFont(brooks_font(BROOKS_LABEL_SIZE_NORMAL, mono=False, weight=QtGui.QFont.Weight.Medium))
            text.setPos(signal.signal_index, label_y)
            plot.addItem(text)
            overlay_items.append(text)

            self.add_price_line(plot, signal.signal_index, signal.entry_price, "入场", (44, 123, 229))
            self.add_price_line(plot, signal.signal_index, signal.stop_price, "止损", (220, 53, 69))
            self.add_price_line(plot, signal.signal_index, signal.target_price, "目标", (0, 150, 136))

    def draw_trade_annotations(self, trades: list[dict]) -> None:
        plot = self.chart.get_plot("candle")
        if plot is None or not self.current_bars or not trades:
            return

        for trade in trades:
            dt_text = trade.get("datetime", "")
            if not dt_text:
                continue
            dt = datetime.fromisoformat(dt_text)
            idx = find_nearest_datetime_index(self.current_datetimes, dt)
            if idx is None:
                continue

            price = float(trade.get("price", 0) or 0)
            direction = trade.get("direction", "")
            color = (46, 204, 113) if direction in {"多", "LONG"} else (231, 76, 60)

            marker = pg.ScatterPlotItem([idx], [price], size=11, brush=pg.mkBrush(color), pen=brooks_pen(color, width=BROOKS_LINE_WIDTH_THIN))
            plot.addItem(marker)
            self.overlay_items.append(marker)

            nearest_signal = min(self.current_signals, key=lambda s: abs(s.trigger_index - idx), default=None)
            if nearest_signal:
                line = pg.PlotCurveItem([nearest_signal.signal_index, idx], [nearest_signal.entry_price, price], pen=brooks_pen(color, width=BROOKS_LINE_WIDTH_THIN, style=QtCore.Qt.PenStyle.DotLine))
                plot.addItem(line)
                self.overlay_items.append(line)

    def add_price_line(self, plot, signal_index: int, price: float, title: str, color: tuple[int, int, int]) -> None:
        end_index = signal_index + 8
        line = pg.PlotCurveItem([signal_index - 0.2, end_index], [price, price], pen=brooks_pen(color, width=BROOKS_LINE_WIDTH_NORMAL, style=QtCore.Qt.PenStyle.DashLine))
        plot.addItem(line)
        self.overlay_items.append(line)

        text = pg.TextItem(text=title, color=color, anchor=(0, 1))
        text.setFont(brooks_font(BROOKS_LABEL_SIZE_SMALL, mono=False, weight=QtGui.QFont.Weight.Medium))
        text.setPos(end_index + 0.2, price)
        plot.addItem(text)
        self.overlay_items.append(text)

    def apply_signal_filters(self, select_first: bool = False) -> None:
        kind_filter = self.kind_filter_combo.currentText()
        quality_filter = self.quality_filter_combo.currentText()
        review_filter = self.review_filter_combo.currentText()
        topic_kinds = self.get_active_filter_kinds()

        signals: list[SignalAnnotation] = []
        if kind_filter == "不检测":
            self.filtered_signals = []
            self.update_signal_table([], select_first)
            self.redraw_chart_overlays()
            return

        for signal in self.current_signals:
            if topic_kinds and signal.kind not in topic_kinds:
                continue
            if kind_filter == "MAG" and not signal.kind.startswith("MAG"):
                continue
            if kind_filter not in {"全部", "MAG"} and signal.kind != kind_filter:
                continue
            if quality_filter == "强" and signal.quality != "强":
                continue
            if quality_filter == "中" and signal.quality == "弱":
                continue
            review = self.get_signal_review(signal)
            status = review.get("status", "待处理")
            if review_filter != "全部" and status != review_filter:
                continue
            signals.append(signal)

        self.filtered_signals = signals
        self.update_signal_table(signals, select_first)
        self.redraw_chart_overlays()

    def update_signal_table(self, signals: list[SignalAnnotation], select_first: bool = False) -> None:
        self.signal_table.setRowCount(len(signals))
        for row, signal in enumerate(signals):
            signal_bar = self.current_bars[signal.signal_index]
            trigger_bar = self.current_bars[signal.trigger_index]
            review = self.get_signal_review(signal)
            values = [
                signal_bar.datetime.strftime("%Y-%m-%d %H:%M"),
                signal.kind,
                signal.quality,
                review.get("status", "待处理"),
                trigger_bar.datetime.strftime("%m-%d %H:%M"),
                fmt_price(signal.entry_price),
                fmt_price(signal.stop_price),
                fmt_price(signal.target_price),
            ]
            for column, value in enumerate(values):
                self.signal_table.setItem(row, column, QtWidgets.QTableWidgetItem(value))

        if signals and (select_first or self.signal_table.currentRow() < 0):
            self.signal_table.selectRow(0)
            self.on_signal_selected()
        elif not signals:
            self.detail_edit.setPlainText("当前过滤条件下没有信号。")
            self.note_edit.clear()

    def on_signal_selected(self) -> None:
        row = self.signal_table.currentRow()
        if row < 0 or row >= len(self.filtered_signals):
            return

        signal = self.filtered_signals[row]
        self.info_tabs.setCurrentIndex(0)
        self.focus_on_signal(signal)
        self.update_signal_detail(signal)
        self.load_signal_note(signal)

    def focus_on_signal(self, signal: SignalAnnotation) -> None:
        self.focus_on_index(signal.signal_index, preserve_window=True)

    def navigate_signal(self, step: int) -> None:
        total = self.signal_table.rowCount()
        if not total:
            return
        row = self.signal_table.currentRow()
        if row < 0:
            row = 0
        else:
            row = max(0, min(total - 1, row + step))
        self.signal_table.selectRow(row)
        self.on_signal_selected()

    def focus_on_index(self, index: int, preserve_window: bool = True, override_window: int | None = None) -> None:
        if not self.current_bars:
            return

        visible = self.chart.visible_bar_count()
        if override_window is not None:
            window = override_window
        elif preserve_window and 80 <= visible <= 1200:
            window = visible
        else:
            window = min(max(240, len(self.current_bars) // 20), 600)

        right_ix = min(len(self.current_bars), index + window // 2)
        right_ix = max(window, right_ix)
        self.chart._bar_count = window
        self.chart._right_ix = right_ix
        self.chart._update_x_range()
        self.chart._update_y_range()
        if getattr(self.chart, "_cursor", None):
            self.chart._cursor._x = index
            self.chart._cursor.update_info()
        self.chart.setFocus()

    def focus_on_datetime(self, dt: datetime, window: int = 180) -> None:
        idx = find_nearest_datetime_index(self.current_datetimes, dt)
        if idx is None:
            return
        self.focus_on_index(idx, preserve_window=False, override_window=window)

    def reset_chart_view(self) -> None:
        if not self.current_bars:
            return
        window = min(max(500, self.bar_limit_spin.value() // 2), len(self.current_bars))
        self.chart._bar_count = max(window, 100)
        self.chart.move_to_right()
        self.chart._update_y_range()
        self.chart.setFocus()

    def update_signal_detail(self, signal: SignalAnnotation) -> None:
        signal_bar = self.current_bars[signal.signal_index]
        trigger_bar = self.current_bars[signal.trigger_index]
        review = self.get_signal_review(signal)
        text = (
            f"建仓信号：{signal.kind}\n"
            f"质量：{signal.quality}\n"
            f"背景：{signal.background}\n"
            f"审核：{review.get('status', '待处理')}\n"
            f"信号时间：{signal_bar.datetime:%Y-%m-%d %H:%M}\n"
            f"触发时间：{trigger_bar.datetime:%Y-%m-%d %H:%M}\n"
            f"EMA20：{signal.ema_value:.4f}\n"
            f"入场：{fmt_price(signal.entry_price)}\n"
            f"止损：{fmt_price(signal.stop_price)}\n"
            f"目标：{fmt_price(signal.target_price)}\n"
            f"说明：{signal.reason}\n"
            f"回调起点序号：{signal.pullback_start_index}\n"
            f"信号柱序号：{signal.signal_index}\n"
            f"触发柱序号：{signal.trigger_index}"
        )
        self.detail_edit.setPlainText(text)

    def load_latest_backtest_report(self) -> None:
        meta_path = BACKTEST_OUTPUT_DIR / "latest_meta.json"
        stats_path = BACKTEST_OUTPUT_DIR / "latest_stats.json"
        trades_path = BACKTEST_OUTPUT_DIR / "latest_trades.csv"
        lifecycle_path = BACKTEST_OUTPUT_DIR / "latest_lifecycles.csv"

        if not meta_path.exists() or not stats_path.exists():
            self.stats_edit.setPlainText("还没有找到最近一次回测输出，请先运行回测脚本。")
            self.trade_table.setRowCount(0)
            return

        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        with stats_path.open("r", encoding="utf-8") as f:
            stats = json.load(f)

        self.stats_edit.setPlainText(format_stats_text(meta, stats))
        self.set_display_interval_key(meta.get("signal_window", "1m"))
        vt_symbol = meta.get("vt_symbol", "")
        symbol, exchange_value = vt_symbol.split(".") if "." in vt_symbol else ("", "")

        matched_index = -1
        for i, overview in enumerate(self.overviews):
            if overview.symbol == symbol and overview.exchange and overview.exchange.value == exchange_value:
                matched_index = i
                break

        if matched_index >= 0:
            self.dataset_combo.setCurrentIndex(matched_index)
            self.start_edit.setDateTime(to_qdatetime(datetime.fromisoformat(meta["start"])))
            self.end_edit.setDateTime(to_qdatetime(datetime.fromisoformat(meta["end"])))
            self.load_chart()

        self.current_trades = []
        self.current_lifecycles = []
        self.trade_table.setRowCount(0)
        self.lifecycle_table.setRowCount(0)
        if lifecycle_path.exists():
            with lifecycle_path.open("r", encoding="utf-8-sig") as f:
                self.current_lifecycles = list(csv.DictReader(f))
            self.update_lifecycle_table(self.current_lifecycles)

        if trades_path.exists():
            with trades_path.open("r", encoding="utf-8-sig") as f:
                self.current_trades = list(csv.DictReader(f))
            self.update_trade_table(self.current_trades)
            self.draw_trade_annotations(self.current_trades)

        self.info_tabs.setCurrentIndex(1)

    def open_latest_report_html(self) -> None:
        html_path = BACKTEST_OUTPUT_DIR / "latest_report.html"
        if not html_path.exists():
            self.status_label.setText("还没有生成 HTML 回测报告，请先运行回测脚本。")
            return
        webbrowser.open(html_path.as_uri())


    def update_lifecycle_table(self, lifecycles: list[dict]) -> None:
        self.lifecycle_table.setRowCount(len(lifecycles))
        for row, item in enumerate(lifecycles):
            values = [
                item.get("lifecycle_id", ""),
                item.get("direction", ""),
                item.get("entry_time", ""),
                item.get("exit_time", ""),
                item.get("volume", ""),
                item.get("pnl_points", ""),
            ]
            for column, value in enumerate(values):
                self.lifecycle_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
        if lifecycles:
            self.lifecycle_table.selectRow(0)
            self.on_lifecycle_selected()

    def on_lifecycle_selected(self) -> None:
        row = self.lifecycle_table.currentRow()
        if row < 0 or row >= len(self.current_lifecycles):
            return
        lifecycle = self.current_lifecycles[row]
        entry_dt = lifecycle.get("entry_time", "")
        exit_dt = lifecycle.get("exit_time", "")
        if not entry_dt or not exit_dt:
            return
        entry = datetime.fromisoformat(entry_dt)
        exit_ = datetime.fromisoformat(exit_dt)
        entry_index = find_nearest_datetime_index(self.current_datetimes, entry)
        exit_index = find_nearest_datetime_index(self.current_datetimes, exit_)
        if entry_index is None or exit_index is None:
            return
        left = min(entry_index, exit_index)
        right = max(entry_index, exit_index)
        span = max(180, (right - left) + 120)
        self.focus_on_index(right, preserve_window=False, override_window=span)
        self.detail_edit.setPlainText(
            f"生命周期：{lifecycle.get('lifecycle_id', '')}\n"
            f"方向：{lifecycle.get('direction', '')}\n"
            f"入场时间：{entry_dt}\n"
            f"入场价格：{lifecycle.get('entry_price', '')}\n"
            f"离场时间：{exit_dt}\n"
            f"离场价格：{lifecycle.get('exit_price', '')}\n"
            f"手数：{lifecycle.get('volume', '')}\n"
            f"点数盈亏：{lifecycle.get('pnl_points', '')}"
        )

    def update_trade_table(self, trades: list[dict]) -> None:
        self.trade_table.setRowCount(len(trades))
        for row, trade in enumerate(trades):
            values = [
                trade.get("datetime", ""),
                trade.get("direction", ""),
                trade.get("offset", ""),
                trade.get("price", ""),
                trade.get("volume", ""),
                trade.get("vt_tradeid", ""),
            ]
            for column, value in enumerate(values):
                self.trade_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
        if trades:
            self.trade_table.selectRow(0)
            self.on_trade_selected()

    def on_trade_selected(self) -> None:
        row = self.trade_table.currentRow()
        if row < 0 or row >= len(self.current_trades):
            return
        trade = self.current_trades[row]
        dt_text = trade.get("datetime", "")
        if not dt_text:
            return
        dt = datetime.fromisoformat(dt_text)
        self.focus_on_datetime(dt, window=180)
        self.info_tabs.setCurrentIndex(1)
        self.detail_edit.setPlainText(
            f"成交时间：{trade.get('datetime', '')}\n"
            f"方向：{trade.get('direction', '')}\n"
            f"开平：{trade.get('offset', '')}\n"
            f"价格：{trade.get('price', '')}\n"
            f"数量：{trade.get('volume', '')}\n"
            f"成交号：{trade.get('vt_tradeid', '')}"
        )

    def load_signal_reviews(self) -> dict[str, dict]:
        if REVIEW_PATH.exists():
            with REVIEW_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_signal_reviews(self) -> None:
        REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
        with REVIEW_PATH.open("w", encoding="utf-8") as f:
            json.dump(self.signal_reviews, f, ensure_ascii=False, indent=2)

    def get_signal_key(self, signal: SignalAnnotation) -> str:
        if not self.current_overview or not self.current_bars:
            return ""
        dt = self.current_bars[signal.signal_index].datetime.strftime("%Y-%m-%d %H:%M")
        return f"{self.current_overview.symbol}.{self.current_overview.exchange.value}.{self.current_display_interval.key}|{signal.kind}|{dt}"

    def get_signal_review(self, signal: SignalAnnotation) -> dict:
        return self.signal_reviews.get(self.get_signal_key(signal), {})

    def load_topic_stage_reviews(self) -> dict[str, str]:
        if TOPIC_STAGE_PATH.exists():
            with TOPIC_STAGE_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {str(key): str(value) for key, value in data.items()}
        return {}

    def save_topic_stage_reviews(self) -> None:
        TOPIC_STAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TOPIC_STAGE_PATH.open("w", encoding="utf-8") as f:
            json.dump(self.topic_stage_reviews, f, ensure_ascii=False, indent=2)

    def get_topic_stage(self, topic: KnowledgeTopic) -> str:
        return self.topic_stage_reviews.get(topic.key, TOPIC_STAGE_OPTIONS[0])

    def format_topic_status_text(self, topic: KnowledgeTopic) -> str:
        return topic.status

    def load_signal_note(self, signal: SignalAnnotation) -> None:
        review = self.get_signal_review(signal)
        self.note_edit.setPlainText(review.get("note", ""))

    def save_current_note(self) -> None:
        row = self.signal_table.currentRow()
        if row < 0 or row >= len(self.filtered_signals):
            return
        signal = self.filtered_signals[row]
        key = self.get_signal_key(signal)
        review = self.signal_reviews.get(key, {"status": "待处理", "note": ""})
        review["note"] = self.note_edit.toPlainText().strip()
        self.signal_reviews[key] = review
        self.save_signal_reviews()
        self.apply_signal_filters()

    def update_signal_review(self, status: str) -> None:
        row = self.signal_table.currentRow()
        if row < 0 or row >= len(self.filtered_signals):
            return
        signal = self.filtered_signals[row]
        key = self.get_signal_key(signal)
        review = self.signal_reviews.get(key, {"status": "待处理", "note": ""})
        review["status"] = status
        self.signal_reviews[key] = review
        self.save_signal_reviews()
        self.apply_signal_filters()

    def populate_topic_tree(self) -> None:
        self.topic_tree.blockSignals(True)
        self.topic_tree.clear()
        track_items: dict[str, QtWidgets.QTreeWidgetItem] = {}
        module_items: dict[tuple[str, ...], QtWidgets.QTreeWidgetItem] = {}

        for topic in KNOWLEDGE_TOPICS:
            if topic.track not in track_items:
                track_item = QtWidgets.QTreeWidgetItem([topic.track, "", "", ""])
                track_items[topic.track] = track_item
                self.topic_tree.addTopLevelItem(track_item)
            else:
                track_item = track_items[topic.track]

            parent_item = track_item
            path_parts = [part.strip() for part in topic.module.split(" / ") if part.strip()]
            path_accum: list[str] = [topic.track]
            for part in path_parts:
                path_accum.append(part)
                module_key = tuple(path_accum)
                if module_key not in module_items:
                    module_item = QtWidgets.QTreeWidgetItem([part, "", "", ""])
                    module_items[module_key] = module_item
                    parent_item.addChild(module_item)
                parent_item = module_items[module_key]

            item = QtWidgets.QTreeWidgetItem(
                [
                    topic.lesson_code,
                    topic.name,
                    self.format_topic_status_text(topic),
                    self.get_topic_stage(topic),
                ]
            )
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, topic.key)
            if topic.implemented and topic.overlay_group:
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(1, QtCore.Qt.CheckState.Checked if topic.key in self.checked_topic_keys else QtCore.Qt.CheckState.Unchecked)
            parent_item.addChild(item)

        self.topic_tree.expandAll()
        self.topic_tree.blockSignals(False)

    def on_topic_selected(self) -> None:
        items = self.topic_tree.selectedItems()
        if not items:
            return

        item = items[0]
        topic_key = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not topic_key:
            self.active_topic = None
            self.topic_stage_button.setEnabled(False)
            self.topic_stage_button.setText(f"{TOPIC_STAGE_OPTIONS[0]} ▼")
            return

        topic = KNOWLEDGE_TOPIC_MAP.get(topic_key)
        if not topic:
            self.active_topic = None
            self.topic_stage_button.setEnabled(False)
            self.topic_stage_button.setText(f"{TOPIC_STAGE_OPTIONS[0]} ▼")
            return

        self.active_topic = topic
        self.topic_stage_button.setEnabled(True)
        self.topic_stage_button.setText(f"{self.get_topic_stage(topic)} ▼")
        self.update_topic_detail(topic)
        self.apply_signal_filters(select_first=True)
        self.redraw_chart_overlays()
        self.info_tabs.setCurrentIndex(3)

    def on_topic_check_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        if column != 1:
            return

        topic_key = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not topic_key:
            return

        state = item.checkState(1)
        if state == QtCore.Qt.CheckState.Checked:
            self.checked_topic_keys.add(topic_key)
        else:
            self.checked_topic_keys.discard(topic_key)

        self.apply_signal_filters(select_first=True)
        self.redraw_chart_overlays()

    def get_checked_topics(self) -> list[KnowledgeTopic]:
        return [topic for topic in KNOWLEDGE_TOPICS if topic.key in self.checked_topic_keys]

    def get_overlay_topics(self) -> list[KnowledgeTopic]:
        topics = {topic.key: topic for topic in self.get_checked_topics()}
        if self.active_topic and self.active_topic.implemented:
            topics[self.active_topic.key] = self.active_topic
        return list(topics.values())

    def get_active_filter_kinds(self) -> set[str] | None:
        kinds: set[str] = set()
        for topic in self.get_overlay_topics():
            kinds.update(topic.filter_kinds)
        return kinds or None

    def update_topic_detail(self, topic: KnowledgeTopic) -> None:
        kind_text = "、".join(topic.filter_kinds) if topic.filter_kinds else "无"
        refs_text = "、".join(topic.course_refs) if topic.course_refs else "未标注"
        source_text = "\n".join(topic.source_refs) if topic.source_refs else "未标注"
        stage_text = self.get_topic_stage(topic)
        text = (
            f"知识点：{topic.name}\n"
            f"体系：{topic.track}\n"
            f"模块：{topic.module}\n"
            f"章节：{topic.lesson_code or '未标注'}\n"
            f"状态：{topic.status}\n"
            f"开发状态：{stage_text}\n"
            f"关联信号：{kind_text}\n"
            f"课程章节：{refs_text}\n"
            f"说明：{topic.description}\n"
            f"\n资料来源：\n{source_text}\n"
        )
        if topic.implementation_notes:
            text += f"\n当前程序口径：\n{topic.implementation_notes}\n"
        self.topic_detail_edit.setPlainText(text)
        if not topic.implemented:
            self.status_label.setText(f"知识点 {topic.name} 当前还未接入图表，仅提供公用目录与资料来源。")

    def on_topic_stage_changed(self, stage: str) -> None:
        if not self.active_topic:
            return
        self.topic_stage_reviews[self.active_topic.key] = stage
        self.save_topic_stage_reviews()
        self.update_topic_detail(self.active_topic)
        self.topic_stage_button.setText(f"{stage} ▼")
        items = self.topic_tree.selectedItems()
        if items:
            items[0].setText(2, self.format_topic_status_text(self.active_topic))
            items[0].setText(3, self.get_topic_stage(self.active_topic))

    def show_topic_stage_menu(self) -> None:
        if not self.topic_stage_button.isEnabled():
            return
        pos = self.topic_stage_button.mapToGlobal(QtCore.QPoint(0, self.topic_stage_button.height()))
        self.topic_stage_menu.popup(pos)

    def populate_strategy_selector(self) -> None:
        self.strategy_combo.blockSignals(True)
        self.strategy_combo.clear()
        for blueprint in STRATEGY_BLUEPRINTS:
            label = f"[{blueprint.family}] {blueprint.name}"
            self.strategy_combo.addItem(label, blueprint.key)
        self.strategy_combo.blockSignals(False)

        if self.strategy_combo.count():
            self.strategy_combo.setCurrentIndex(0)
            self.on_strategy_changed(0)

    def on_strategy_changed(self, index: int) -> None:
        if index < 0:
            return

        strategy_key = self.strategy_combo.itemData(index)
        if not strategy_key:
            return

        blueprint = STRATEGY_BLUEPRINT_MAP.get(strategy_key)
        if not blueprint:
            return

        self.active_strategy = blueprint
        self.update_strategy_flow_tree(blueprint)
        self.update_strategy_detail(blueprint)
        if hasattr(self, "info_tabs"):
            self.info_tabs.setCurrentIndex(4)

    def update_strategy_flow_tree(self, blueprint: StrategyBlueprint) -> None:
        self.strategy_tree.clear()
        for step in blueprint.steps:
            step_item = QtWidgets.QTreeWidgetItem([step.name, step.summary, step.status])
            self.strategy_tree.addTopLevelItem(step_item)
            for topic_key in step.topic_keys:
                topic = KNOWLEDGE_TOPIC_MAP.get(topic_key)
                if not topic:
                    continue
                child = QtWidgets.QTreeWidgetItem(
                    [
                        f"[{topic.lesson_code}]",
                        topic.name,
                        topic.status,
                    ]
                )
                step_item.addChild(child)
            if step.notes:
                note_item = QtWidgets.QTreeWidgetItem(["说明", step.notes, ""])
                step_item.addChild(note_item)

        self.strategy_tree.expandAll()

    def update_strategy_detail(self, blueprint: StrategyBlueprint) -> None:
        seen: set[str] = set()
        topic_lines = []
        for step in blueprint.steps:
            for topic_key in step.topic_keys:
                if topic_key in seen:
                    continue
                seen.add(topic_key)
                topic = KNOWLEDGE_TOPIC_MAP.get(topic_key)
                if not topic:
                    continue
                topic_lines.append(f"- [{topic.lesson_code}] {topic.name} | {topic.status}")

        code_lines = "\n".join(blueprint.code_refs) if blueprint.code_refs else "暂未接入代码"
        source_lines = "\n".join(blueprint.source_refs) if blueprint.source_refs else "未标注"
        topic_text = "\n".join(topic_lines) if topic_lines else "暂未绑定公用知识点。"
        text = (
            f"策略：{blueprint.name}\n"
            f"策略族：{blueprint.family}\n"
            f"状态：{blueprint.status}\n"
            f"概要：{blueprint.summary}\n"
            f"\n引用的公用知识点：\n{topic_text}\n"
            f"\n当前微调方向：\n{blueprint.tuning_notes or '未填写'}\n"
            f"\n代码路径：\n{code_lines}\n"
            f"\n理论来源：\n{source_lines}\n"
        )
        self.strategy_detail_edit.setPlainText(text)

    def refresh_backtest_records(self) -> None:
        self.backtest_records = []
        self.backtest_records.extend(load_latest_single_backtest_record())
        self.backtest_records.extend(load_latest_cta_gui_record())
        self.backtest_records.extend(load_cta_gui_run_records())
        self.backtest_records.extend(load_batch_backtest_records(BACKTEST_MATRIX_ROOT, "矩阵"))
        self.backtest_records.extend(load_batch_backtest_records(BACKTEST_OPT_ROOT, "优化"))
        self.update_record_table()

    def update_record_table(self) -> None:
        self.record_table.setRowCount(len(self.backtest_records))
        for row, record in enumerate(self.backtest_records):
            values = [
                record.source_label,
                record.signal_window,
                record.strategy_label,
                record.vt_symbol,
                f"{record.sharpe_ratio:.3f}",
                f"{record.total_net_pnl:.3f}",
                str(record.total_trade_count),
            ]
            for column, value in enumerate(values):
                self.record_table.setItem(row, column, QtWidgets.QTableWidgetItem(value))

        if self.backtest_records:
            self.record_table.selectRow(0)
            self.on_backtest_record_selected()
        else:
            self.record_detail_edit.setPlainText("还没有找到可选的回测记录。")

    def on_backtest_record_selected(self) -> None:
        row = self.record_table.currentRow()
        if row < 0 or row >= len(self.backtest_records):
            return
        record = self.backtest_records[row]
        self.current_record = record
        self.record_detail_edit.setPlainText(format_backtest_record_text(record))

    def load_selected_backtest_record(self) -> None:
        if not self.current_record:
            return

        record = self.current_record
        vt_symbol = record.vt_symbol
        self.set_display_interval_key(record.signal_window)
        symbol, exchange_value = vt_symbol.split(".") if "." in vt_symbol else ("", "")

        matched_index = -1
        for index, overview in enumerate(self.overviews):
            if overview.symbol == symbol and overview.exchange and overview.exchange.value == exchange_value:
                matched_index = index
                break

        if matched_index >= 0:
            self.dataset_combo.setCurrentIndex(matched_index)
            self.start_edit.setDateTime(to_qdatetime(datetime.fromisoformat(record.start)))
            self.end_edit.setDateTime(to_qdatetime(datetime.fromisoformat(record.end)))
            self.load_chart()

        self.stats_edit.setPlainText(format_backtest_record_text(record))
        self.current_trades = []
        self.current_lifecycles = []
        self.trade_table.setRowCount(0)
        self.lifecycle_table.setRowCount(0)

        if record.trades_path and record.trades_path.exists():
            with record.trades_path.open("r", encoding="utf-8-sig") as file:
                self.current_trades = list(csv.DictReader(file))
            self.update_trade_table(self.current_trades)
            self.draw_trade_annotations(self.current_trades)

        if record.lifecycles_path and record.lifecycles_path.exists():
            with record.lifecycles_path.open("r", encoding="utf-8-sig") as file:
                self.current_lifecycles = list(csv.DictReader(file))
            self.update_lifecycle_table(self.current_lifecycles)

        self.info_tabs.setCurrentIndex(1)
        self.status_label.setText(
            f"已加载回测记录：{record.strategy_label} | {record.vt_symbol} | 周期 {record.signal_window}"
        )


def build_dataset_label(overview: BarOverview) -> str:
    interval_name = INTERVAL_NAME_MAP.get(overview.interval, overview.interval.value if overview.interval else "")
    start_text = overview.start.strftime("%Y-%m-%d") if overview.start else ""
    end_text = overview.end.strftime("%Y-%m-%d") if overview.end else ""
    exchange_text = overview.exchange.value if overview.exchange else ""
    return f"{overview.symbol}.{exchange_text} | {interval_name} | {start_text} -> {end_text} | {overview.count}"


def fmt_price(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def get_phase_price_range(
    bars: list[BarData],
    start_index: int,
    end_index: int,
) -> tuple[float, float, float]:
    """计算某段价格区间，用于局部框标注。"""
    segment = bars[start_index:end_index + 1]
    top_price = max(bar.high_price for bar in segment)
    bottom_price = min(bar.low_price for bar in segment)
    span = max(top_price - bottom_price, 1e-6)
    pad = span * 0.18
    return top_price, bottom_price, pad


def build_structure_short_label(phase: BackgroundPhase) -> str:
    """结构层缩写，贴近 Brooks 课件风格。"""
    name_map = {
        "震荡": "TR",
        "窄幅通道": "Tight CH",
        "宽幅通道": "Broad CH",
        "趋势交易区间": "Trend TR",
    }
    return f"{name_map.get(phase.name, phase.name)}/{phase.direction}"


def build_event_short_label(phase: BackgroundPhase) -> str:
    """事件层缩写，贴近 Brooks 课件风格。"""
    name_map = {
        "突破起爆": "BO",
        "突破跟进": "FT",
        "突破测试": "Test",
        "失败突破": "FBO",
        "开盘反转": "Open Rev",
        "午间反转": "Mid Rev",
    }
    return f"{name_map.get(phase.name, phase.name)}/{phase.direction}"


def get_structure_outline_color(name: str) -> tuple[int, int, int]:
    color_map = {
        "震荡": (180, 180, 180),
        "窄幅通道": (56, 189, 248),
        "宽幅通道": (74, 222, 128),
        "趋势交易区间": (129, 140, 248),
    }
    return color_map.get(name, (180, 180, 180))


def get_event_outline_color(name: str) -> tuple[int, int, int]:
    color_map = {
        "突破起爆": (255, 214, 10),
        "突破跟进": (249, 115, 22),
        "突破测试": (59, 130, 246),
        "失败突破": (239, 68, 68),
        "开盘反转": (186, 104, 200),
        "午间反转": (0, 188, 212),
    }
    return color_map.get(name, (255, 255, 255))


def parse_metric_number(value, *, default: float = 0.0) -> float:
    """兼容带千分位和百分号的数字文本。"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return default

    text = text.replace(",", "").replace("%", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return default
    return float(match.group(0))


def to_qdatetime(dt: datetime) -> QtCore.QDateTime:
    aware_dt = dt.replace(tzinfo=DB_TZ) if dt.tzinfo is None else dt.astimezone(DB_TZ)
    naive_local = aware_dt.astimezone().replace(tzinfo=None)
    return QtCore.QDateTime(naive_local.year, naive_local.month, naive_local.day, naive_local.hour, naive_local.minute, naive_local.second)


def build_focus_date_window(target_date: date, days: int) -> tuple[datetime, datetime]:
    """按目标日期生成快速截图用的时间范围。"""
    span_days = max(1, days)
    start_date = target_date - timedelta(days=span_days - 1)
    start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=DB_TZ)
    end_dt = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, tzinfo=DB_TZ)
    return start_dt, end_dt


def get_recent_start(
    overview: BarOverview,
    bar_limit: int,
    display_interval: DisplayIntervalOption,
) -> datetime:
    if not overview.start or not overview.end or not overview.interval:
        return overview.start or datetime.now()
    if display_interval.interval == Interval.MINUTE:
        delta = timedelta(minutes=bar_limit * display_interval.window * 2)
    elif display_interval.interval == Interval.HOUR:
        delta = timedelta(hours=bar_limit * 2)
    else:
        delta = timedelta(days=bar_limit * 2)
    recent_start = overview.end - delta
    return overview.start if recent_start < overview.start else recent_start


def aggregate_bars_to_display_interval(
    bars: list[BarData],
    display_interval: DisplayIntervalOption,
) -> list[BarData]:
    """把原始 K 线转换到当前显示周期。"""
    return aggregate_bars_to_interval(bars, display_interval.interval, display_interval.window)


def aggregate_bars_to_interval(
    bars: list[BarData],
    interval: Interval,
    window: int,
) -> list[BarData]:
    """按分钟/小时窗口聚合 K 线。"""
    if not bars:
        return []
    if interval == Interval.MINUTE and window == 1:
        return list(bars)

    aggregated: list[BarData] = []
    current_bar: BarData | None = None
    current_bucket: datetime | None = None

    for bar in bars:
        bucket = floor_bar_datetime(bar.datetime, interval, window)
        if current_bucket != bucket or current_bar is None:
            if current_bar is not None:
                aggregated.append(current_bar)
            current_bucket = bucket
            current_bar = BarData(
                gateway_name=bar.gateway_name,
                symbol=bar.symbol,
                exchange=bar.exchange,
                datetime=bucket,
                interval=interval,
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


def floor_bar_datetime(dt: datetime, interval: Interval, window: int) -> datetime:
    """把时间下取整到目标周期。"""
    if interval == Interval.MINUTE:
        minute = (dt.minute // window) * window
        return dt.replace(minute=minute, second=0, microsecond=0)

    if interval == Interval.HOUR:
        hour = (dt.hour // window) * window
        return dt.replace(hour=hour, minute=0, second=0, microsecond=0)

    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def resolve_higher_timeframe_option(display_interval: DisplayIntervalOption) -> DisplayIntervalOption:
    """为关键位选择更高一级周期。"""
    if display_interval.minutes <= 15:
        return DISPLAY_INTERVAL_MAP["1h"]
    if display_interval.minutes <= 60:
        return DisplayIntervalOption("1d", "1日", Interval.DAILY, 1, 1440)
    return DisplayIntervalOption("1d", "1日", Interval.DAILY, 1, 1440)


def calculate_line_slope(anchor1: tuple[int, float], anchor2: tuple[int, float]) -> float:
    """计算两点连线斜率。"""
    delta_x = max(anchor2[0] - anchor1[0], 1)
    return (anchor2[1] - anchor1[1]) / delta_x


def get_signal_colors(kind: str, quality: str) -> tuple[tuple[int, int, int], tuple[int, int, int, int]]:
    if kind.startswith("H") or kind == "MAG多":
        pen = (40, 167, 69)
        brush = (40, 167, 69, 55) if quality == "强" else (40, 167, 69, 28)
        return pen, brush
    pen = (220, 53, 69)
    brush = (220, 53, 69, 55) if quality == "强" else (220, 53, 69, 28)
    return pen, brush


def find_nearest_datetime_index(datetimes: list[datetime], target: datetime) -> int | None:
    if not datetimes:
        return None
    idx = bisect_left(datetimes, target)
    if idx >= len(datetimes):
        return len(datetimes) - 1
    if idx > 0:
        left_dt = datetimes[idx - 1]
        right_dt = datetimes[idx]
        if abs((target - left_dt).total_seconds()) <= abs((right_dt - target).total_seconds()):
            return idx - 1
    return idx


def format_stats_text(meta: dict, stats: dict) -> str:
    rows = [
        ("合约", meta.get("vt_symbol", "")),
        ("策略", meta.get("strategy_key", meta.get("strategy", ""))),
        ("执行周期", meta.get("signal_window", "")),
        ("开始时间", meta.get("start", "")),
        ("结束时间", meta.get("end", "")),
        ("总天数", stats.get("total_days", "")),
        ("盈利天数", stats.get("profit_days", "")),
        ("亏损天数", stats.get("loss_days", "")),
        ("总收益", stats.get("total_return", "")),
        ("净利润", stats.get("total_net_pnl", "")),
        ("最大回撤", stats.get("max_drawdown", "")),
        ("Sharpe", stats.get("sharpe_ratio", "")),
        ("EWM Sharpe", stats.get("ewm_sharpe", "")),
        ("收益回撤比", stats.get("return_drawdown_ratio", "")),
        ("成交笔数", stats.get("total_trade_count", "")),
        ("总滑点", stats.get("total_slippage", "")),
        ("总成交额", stats.get("total_turnover", "")),
    ]
    return "\n".join(f"{key}: {value}" for key, value in rows)


def build_bar_count_values(bars: list[BarData]) -> list[int]:
    """按自然日为单位生成 bar count。"""
    counts: list[int] = []
    current_date = None
    current_count = 0

    for bar in bars:
        bar_date = bar.datetime.date()
        if current_date != bar_date:
            current_date = bar_date
            current_count = 1
        else:
            current_count += 1
        counts.append(current_count)

    return counts


def strategy_label_from_key(strategy_key: str) -> str:
    """把策略键转成可读名称。"""
    mapping = {
        "ema20_h2_l2": "EMA20_H2_L2",
        "h1_l1": "H1_L1_FIRST_PULLBACK",
        "mag20": "MAG20_GAP",
    }
    return mapping.get(strategy_key, strategy_key.upper())


def load_latest_single_backtest_record() -> list[BacktestRecord]:
    """读取旧的单次回测输出。"""
    meta_path = BACKTEST_OUTPUT_DIR / "latest_meta.json"
    stats_path = BACKTEST_OUTPUT_DIR / "latest_stats.json"
    trades_path = BACKTEST_OUTPUT_DIR / "latest_trades.csv"
    lifecycles_path = BACKTEST_OUTPUT_DIR / "latest_lifecycles.csv"
    report_path = BACKTEST_OUTPUT_DIR / "latest_report.html"

    if not meta_path.exists() or not stats_path.exists():
        return []

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    setting = meta.get("setting", {})

    return [
        BacktestRecord(
            source="single",
            source_label="单次回测",
            tag="latest",
            strategy_key=meta.get("strategy_key", "ema20_h2_l2"),
            strategy_label=strategy_label_from_key(meta.get("strategy_key", "ema20_h2_l2")),
            vt_symbol=meta.get("vt_symbol", ""),
            start=meta.get("start", ""),
            end=meta.get("end", ""),
            signal_window=str(setting.get("signal_window", "")),
            sharpe_ratio=float(stats.get("sharpe_ratio", 0) or 0),
            total_net_pnl=float(stats.get("total_net_pnl", 0) or 0),
            total_trade_count=int(stats.get("total_trade_count", 0) or 0),
            setting_text=json.dumps(setting, ensure_ascii=False, sort_keys=True),
            meta_path=meta_path,
            stats_path=stats_path,
            trades_path=trades_path,
            lifecycles_path=lifecycles_path,
            report_path=report_path,
        )
    ]


def load_batch_backtest_records(root: Path, source_label: str) -> list[BacktestRecord]:
    """读取矩阵和优化输出记录。"""
    records: list[BacktestRecord] = []
    if not root.exists():
        return records

    for summary_path in sorted(root.glob("*/matrix_summary.json")) + sorted(root.glob("*/optimization_summary.json")):
        tag = summary_path.parent.name
        rows = json.loads(summary_path.read_text(encoding="utf-8"))
        is_optimization = summary_path.name == "optimization_summary.json"
        for row in rows:
            vt_symbol = str(row.get("vt_symbol", ""))
            strategy_key = str(row.get("strategy_key", ""))
            signal_window = str(row.get("signal_window", ""))
            detail_path: Path | None = None

            safe_symbol = vt_symbol.replace(".", "_")
            if not is_optimization:
                candidate = summary_path.parent / "details" / f"{strategy_key}__{safe_symbol}.json"
                if candidate.exists():
                    detail_path = candidate

            records.append(
                BacktestRecord(
                    source=source_label,
                    source_label=source_label,
                    tag=tag,
                    strategy_key=strategy_key,
                    strategy_label=strategy_label_from_key(strategy_key),
                    vt_symbol=vt_symbol,
                    start=str(row.get("start", "")),
                    end=str(row.get("end", "")),
                    signal_window=signal_window,
                    sharpe_ratio=float(row.get("sharpe_ratio", 0) or 0),
                    total_net_pnl=float(row.get("total_net_pnl", 0) or 0),
                    total_trade_count=int(row.get("total_trade_count", 0) or 0),
                    setting_text=str(row.get("setting", "")),
                    detail_path=detail_path,
                )
            )

    records.sort(key=lambda item: (item.source_label, item.tag, item.strategy_key, -item.sharpe_ratio), reverse=True)
    return records


def load_latest_cta_gui_record() -> list[BacktestRecord]:
    """读取 CTA GUI 最近一次回测。"""
    meta_path = CTA_GUI_LATEST_ROOT / "latest_meta.json"
    stats_path = CTA_GUI_LATEST_ROOT / "latest_stats.json"
    trades_path = CTA_GUI_LATEST_ROOT / "latest_trades.csv"
    lifecycles_path = CTA_GUI_LATEST_ROOT / "latest_lifecycles.csv"
    report_path = CTA_GUI_LATEST_ROOT / "latest_report.html"

    if not meta_path.exists() or not stats_path.exists():
        return []

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    stats = json.loads(stats_path.read_text(encoding="utf-8"))

    return [
        BacktestRecord(
            source="cta_gui_latest",
            source_label="CTA回测",
            tag="latest",
            strategy_key=meta.get("strategy_key", meta.get("strategy", "")),
            strategy_label=meta.get("strategy", meta.get("strategy_key", "")),
            vt_symbol=meta.get("vt_symbol", ""),
            start=meta.get("start", ""),
            end=meta.get("end", ""),
            signal_window=str(meta.get("signal_window", "")),
            sharpe_ratio=parse_metric_number(stats.get("sharpe_ratio", 0)),
            total_net_pnl=parse_metric_number(stats.get("total_net_pnl", 0)),
            total_trade_count=int(stats.get("total_trade_count", 0) or 0),
            setting_text=json.dumps(meta.get("setting", {}), ensure_ascii=False, sort_keys=True),
            meta_path=meta_path,
            stats_path=stats_path,
            trades_path=trades_path,
            lifecycles_path=lifecycles_path,
            report_path=report_path,
        )
    ]


def load_cta_gui_run_records() -> list[BacktestRecord]:
    """读取 CTA GUI 历史回测记录。"""
    records: list[BacktestRecord] = []
    if not CTA_GUI_OUTPUT_ROOT.exists():
        return records

    for run_dir in sorted(CTA_GUI_OUTPUT_ROOT.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue

        meta_path = run_dir / "meta.json"
        stats_path = run_dir / "stats.json"
        trades_path = run_dir / "trades.csv"
        lifecycles_path = run_dir / "lifecycles.csv"
        report_path = run_dir / "report.html"
        if not meta_path.exists() or not stats_path.exists():
            continue

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        stats = json.loads(stats_path.read_text(encoding="utf-8"))

        records.append(
            BacktestRecord(
                source="cta_gui",
                source_label="CTA回测",
                tag=run_dir.name,
                strategy_key=meta.get("strategy_key", meta.get("strategy", "")),
                strategy_label=meta.get("strategy", meta.get("strategy_key", "")),
                vt_symbol=meta.get("vt_symbol", ""),
                start=meta.get("start", ""),
                end=meta.get("end", ""),
                signal_window=str(meta.get("signal_window", "")),
                sharpe_ratio=parse_metric_number(stats.get("sharpe_ratio", 0)),
                total_net_pnl=parse_metric_number(stats.get("total_net_pnl", 0)),
                total_trade_count=int(stats.get("total_trade_count", 0) or 0),
                setting_text=json.dumps(meta.get("setting", {}), ensure_ascii=False, sort_keys=True),
                meta_path=meta_path,
                stats_path=stats_path,
                trades_path=trades_path,
                lifecycles_path=lifecycles_path,
                report_path=report_path,
            )
        )

    return records


def format_backtest_record_text(record: BacktestRecord) -> str:
    """格式化所选回测记录说明。"""
    lines = [
        f"来源：{record.source_label}",
        f"标签：{record.tag}",
        f"策略：{record.strategy_label}",
        f"合约：{record.vt_symbol}",
        f"执行周期：{record.signal_window}",
        f"开始：{record.start}",
        f"结束：{record.end}",
        f"Sharpe：{record.sharpe_ratio:.6f}",
        f"净利润：{record.total_net_pnl:.6f}",
        f"成交笔数：{record.total_trade_count}",
    ]

    if record.detail_path and record.detail_path.exists():
        payload = json.loads(record.detail_path.read_text(encoding="utf-8"))
        setting = payload.get("setting", {})
        stats = payload.get("stats", {})
        engine_parameters = payload.get("engine_parameters", {})
        lines.append("")
        lines.append(f"参数：{json.dumps(setting, ensure_ascii=False, sort_keys=True)}")
        lines.append(f"回测参数：{json.dumps(engine_parameters, ensure_ascii=False, sort_keys=True)}")
        lines.append(f"收益回撤比：{stats.get('return_drawdown_ratio', '')}")
        lines.append(f"EWM Sharpe：{stats.get('ewm_sharpe', '')}")
        lines.append(f"总滑点：{stats.get('total_slippage', '')}")
        lines.append(f"总成交额：{stats.get('total_turnover', '')}")
    elif record.meta_path and record.meta_path.exists() and record.stats_path and record.stats_path.exists():
        meta = json.loads(record.meta_path.read_text(encoding="utf-8"))
        stats = json.loads(record.stats_path.read_text(encoding="utf-8"))
        lines.append("")
        lines.append(format_stats_text(meta, stats))
    else:
        lines.append("")
        if record.setting_text:
            lines.append(f"参数：{record.setting_text}")
        lines.append("该记录来自批量回测摘要，当前没有逐笔成交与生命周期文件。")

    return "\n".join(lines)
