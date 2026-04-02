"""
桌面本地量化交易终端启动脚本。
"""

from __future__ import annotations

from argparse import ArgumentParser
from importlib import import_module
import sys
from pathlib import Path

REPO_DIR: Path = Path(__file__).resolve().parent
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp

from vnpy_binance import BinanceLinearGateway, BinanceSpotGateway
from vnpy_okx import OkxGateway
from vnpy_bybit import BybitGateway
from vnpy_mt5 import Mt5Gateway

from brooks_chart_app import BrooksChartApp
from cta_backtester_sync import patch_cta_backtester_sync
from mt5_compat import patch_mt5_timezone_compat
from vnpy_ui_patches import patch_vnpy_ui


GATEWAY_SPECS: list[tuple[type, str]] = [
    (BinanceLinearGateway, "BINANCE_LINEAR"),
    (BinanceSpotGateway, "BINANCE_SPOT"),
    (OkxGateway, "OKX"),
    (BybitGateway, "BYBIT"),
    (Mt5Gateway, "MT5"),
]

APP_SPECS: list[tuple[str, str]] = [
    ("vnpy_ctastrategy", "CtaStrategyApp"),
    ("vnpy_ctabacktester", "CtaBacktesterApp"),
    ("vnpy_datamanager", "DataManagerApp"),
    ("vnpy_riskmanager", "RiskManagerApp"),
    ("vnpy_portfoliostrategy", "PortfolioStrategyApp"),
    ("vnpy_portfoliomanager", "PortfolioManagerApp"),
    ("vnpy_chartwizard", "ChartWizardApp"),
    ("vnpy_algotrading", "AlgoTradingApp"),
    ("vnpy_paperaccount", "PaperAccountApp"),
    ("vnpy_spreadtrading", "SpreadTradingApp"),
    ("vnpy_datarecorder", "DataRecorderApp"),
]


def build_main_engine() -> tuple[MainEngine, EventEngine]:
    """创建主引擎并注册网关和应用。"""
    patch_mt5_timezone_compat()
    patch_cta_backtester_sync()
    patch_vnpy_ui()

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)

    for gateway_class, gateway_name in GATEWAY_SPECS:
        main_engine.add_gateway(gateway_class, gateway_name)

    for module_name, class_name in APP_SPECS:
        add_optional_app(main_engine, module_name, class_name)

    main_engine.add_app(BrooksChartApp)

    return main_engine, event_engine


def add_optional_app(main_engine: MainEngine, module_name: str, class_name: str) -> None:
    """按需加载可选应用模块。"""
    try:
        module = import_module(module_name)
        app_class = getattr(module, class_name)
        main_engine.add_app(app_class)
    except Exception as exc:
        main_engine.write_log(f"加载插件失败：{module_name}.{class_name} -> {exc}")


def run_check() -> int:
    """无界面检查。"""
    main_engine, _ = build_main_engine()
    print("vn.py 图形终端检查通过")
    print(f"已加载网关：{main_engine.get_all_gateway_names()}")
    print(f"已加载应用：{[app.app_name for app in main_engine.get_all_apps()]}")
    main_engine.close()
    return 0


def run_gui() -> int:
    """启动本地 vn.py 图形界面。"""
    qapp = create_qapp("量化交易 vn.py")
    main_engine, event_engine = build_main_engine()

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()
    return 0


def main() -> int:
    """命令行入口。"""
    parser = ArgumentParser(description="启动本地量化交易 vn.py 终端。")
    parser.add_argument("--check", action="store_true", help="仅检查环境，不启动图形界面。")
    args = parser.parse_args()

    if args.check:
        return run_check()

    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
