"""CTA 界面补丁。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

from vnpy.trader.constant import Interval
from vnpy.trader.database import get_database
from vnpy.trader.ui import QtCore, QtWidgets


ROOT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from market_data_common import SYMBOL_CONFIG_MAP
from brooks_chart_app.engine import estimate_pricetick

LOCAL_CTA_CLASS_NAMES: tuple[str, ...] = (
    "Ema20H2L2TrendStrategy",
    "H1L1FirstPullbackStrategy",
    "Mag20GapStrategy",
)


def patch_vnpy_ui() -> None:
    """统一应用 CTA UI 补丁。"""
    patch_cta_backtester_ui()
    patch_cta_strategy_ui()


def get_local_dataset_entries() -> list[tuple[str, str, object]]:
    """读取本地分钟线数据集，供下拉框使用。"""
    database = get_database()
    overviews = [item for item in database.get_bar_overview() if item.interval == Interval.MINUTE and item.exchange]
    overviews.sort(key=lambda item: (item.exchange.value, item.symbol))

    entries: list[tuple[str, str, object]] = []
    seen: set[str] = set()
    for overview in overviews:
        vt_symbol = f"{overview.symbol}.{overview.exchange.value}"
        if vt_symbol in seen:
            continue
        seen.add(vt_symbol)
        label = (
            f"{vt_symbol} | "
            f"{overview.start.strftime('%Y-%m-%d') if overview.start else ''} -> "
            f"{overview.end.strftime('%Y-%m-%d') if overview.end else ''} | "
            f"{overview.count}"
        )
        entries.append((label, vt_symbol, overview))
    return entries


def infer_dataset_defaults(vt_symbol: str, overview) -> dict[str, object]:
    """根据品种推断回测默认参数。"""
    symbol = vt_symbol.split(".")[0]
    config = SYMBOL_CONFIG_MAP.get(symbol)
    if not config or not overview or not overview.start or not overview.end or not overview.exchange:
        return {}

    database = get_database()
    end_dt = overview.start + (overview.end - overview.start) / 100 if overview.end > overview.start else overview.end
    bars = database.load_bar_data(symbol, overview.exchange, Interval.MINUTE, overview.start, end_dt)
    pricetick = estimate_pricetick(bars) if bars else 0.01

    if config.exchange.value == "GLOBAL":
        rate = 0.0005
    else:
        rate = 0.0

    start_date = max(overview.start.date(), date(2025, 1, 1))
    return {
        "rate": rate,
        "slippage": pricetick,
        "size": 1.0,
        "pricetick": pricetick,
        "capital": 100000.0,
        "start_date": start_date,
    }


def patch_cta_backtester_ui() -> None:
    """给 CTA 回测界面加本地数据集下拉框。"""
    from vnpy_ctabacktester.ui.widget import BacktesterManager

    if getattr(BacktesterManager, "_dataset_patch_applied", False):
        return

    original_init_ui = BacktesterManager.init_ui
    original_init_strategy_settings = BacktesterManager.init_strategy_settings
    original_load_backtesting_setting = BacktesterManager.load_backtesting_setting

    def init_ui(self) -> None:
        original_init_ui(self)

        self.dataset_combo = QtWidgets.QComboBox()
        self.dataset_combo.setMinimumWidth(280)
        self.dataset_refresh_button = QtWidgets.QPushButton("刷新数据集")
        self.dataset_refresh_button.clicked.connect(lambda: self.refresh_dataset_combo())
        self.dataset_combo.currentIndexChanged.connect(self.on_dataset_selected)

        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.dataset_combo)
        row_layout.addWidget(self.dataset_refresh_button)

        left_widget = self.layout().itemAt(0).widget()
        left_hbox = left_widget.layout()
        left_vbox = left_hbox.itemAt(0).layout()
        form = left_vbox.itemAt(0).layout()
        form.insertRow(2, "本地数据集", row_widget)

    def refresh_dataset_combo(self) -> None:
        entries = get_local_dataset_entries()
        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        for label, vt_symbol, overview in entries:
            self.dataset_combo.addItem(label, (vt_symbol, overview))
        self.dataset_combo.blockSignals(False)

        current_symbol = self.symbol_line.text().strip()
        if current_symbol:
            for index in range(self.dataset_combo.count()):
                vt_symbol, _overview = self.dataset_combo.itemData(index)
                if vt_symbol == current_symbol:
                    self.dataset_combo.setCurrentIndex(index)
                    break

    def on_dataset_selected(self, index: int) -> None:
        if index < 0:
            return
        payload = self.dataset_combo.itemData(index)
        if not payload:
            return
        vt_symbol, overview = payload
        self.symbol_line.setText(vt_symbol)
        defaults = infer_dataset_defaults(vt_symbol, overview)
        if not defaults:
            return

        self.rate_line.setText(str(defaults["rate"]))
        self.slippage_line.setText(str(defaults["slippage"]))
        self.size_line.setText(str(defaults["size"]))
        self.pricetick_line.setText(str(defaults["pricetick"]))
        self.capital_line.setText(str(defaults["capital"]))
        self.start_date_edit.setDate(QtCore.QDate(defaults["start_date"].year, defaults["start_date"].month, defaults["start_date"].day))
        self.interval_combo.setCurrentText("1m")

    def init_strategy_settings(self) -> None:
        original_init_strategy_settings(self)
        filter_strategy_combo(self.class_combo)
        self.refresh_dataset_combo()

    def load_backtesting_setting(self) -> None:
        original_load_backtesting_setting(self)
        filter_strategy_combo(self.class_combo)
        self.refresh_dataset_combo()

    BacktesterManager.init_ui = init_ui
    BacktesterManager.refresh_dataset_combo = refresh_dataset_combo
    BacktesterManager.on_dataset_selected = on_dataset_selected
    BacktesterManager.init_strategy_settings = init_strategy_settings
    BacktesterManager.load_backtesting_setting = load_backtesting_setting
    BacktesterManager._dataset_patch_applied = True


def patch_cta_strategy_ui() -> None:
    """给 CTA 策略界面加本地数据集下拉框。"""
    from vnpy_ctastrategy.ui.widget import CtaManager, SettingEditor

    if getattr(CtaManager, "_dataset_patch_applied", False):
        return

    original_init_ui = CtaManager.init_ui
    original_update_class_combo = CtaManager.update_class_combo
    original_add_strategy = CtaManager.add_strategy

    def init_ui(self) -> None:
        original_init_ui(self)
        self.dataset_combo = QtWidgets.QComboBox()
        self.dataset_combo.setMinimumWidth(280)
        self.dataset_refresh_button = QtWidgets.QPushButton("刷新数据集")
        self.dataset_refresh_button.clicked.connect(lambda: self.refresh_dataset_combo())

        root_vbox = self.layout()
        hbox1 = root_vbox.itemAt(0).layout()
        hbox1.insertWidget(1, self.dataset_combo)
        hbox1.insertWidget(2, self.dataset_refresh_button)

    def refresh_dataset_combo(self) -> None:
        entries = get_local_dataset_entries()
        self.dataset_combo.clear()
        for label, vt_symbol, _overview in entries:
            self.dataset_combo.addItem(label, vt_symbol)

    def update_class_combo(self) -> None:
        original_update_class_combo(self)
        filter_strategy_combo(self.class_combo)
        self.refresh_dataset_combo()

    def add_strategy(self) -> None:
        class_name = str(self.class_combo.currentText())
        if not class_name:
            return

        parameters = self.cta_engine.get_strategy_class_parameters(class_name)
        editor = SettingEditor(parameters, class_name=class_name)

        if self.dataset_combo.count():
            vt_symbol = str(self.dataset_combo.currentData())
            if "vt_symbol" in editor.edits:
                editor.edits["vt_symbol"][0].setText(vt_symbol)

        n = editor.exec_()
        if n == editor.DialogCode.Accepted:
            setting = editor.get_setting()
            vt_symbol = setting.pop("vt_symbol")
            strategy_name = setting.pop("strategy_name")
            self.cta_engine.add_strategy(class_name, strategy_name, vt_symbol, setting)

    CtaManager.init_ui = init_ui
    CtaManager.refresh_dataset_combo = refresh_dataset_combo
    CtaManager.update_class_combo = update_class_combo
    CtaManager.add_strategy = add_strategy
    CtaManager._dataset_patch_applied = True


def filter_strategy_combo(combo: QtWidgets.QComboBox) -> None:
    """只保留本项目自己的 CTA 策略类。"""
    keep_texts = set(LOCAL_CTA_CLASS_NAMES)
    remove_indexes: list[int] = []
    for index in range(combo.count()):
        text = combo.itemText(index)
        if text not in keep_texts:
            remove_indexes.append(index)
    for index in reversed(remove_indexes):
        combo.removeItem(index)
