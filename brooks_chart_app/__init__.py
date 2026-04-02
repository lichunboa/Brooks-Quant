"""
Brooks 图表标注应用。
"""

from pathlib import Path

from vnpy.trader.app import BaseApp

from .engine import APP_NAME, BrooksChartEngine


class BrooksChartApp(BaseApp):
    """Brooks 图表标注应用入口。"""

    app_name: str = APP_NAME
    app_module: str = __module__
    app_path: Path = Path(__file__).parent
    display_name: str = "Brooks图表"
    engine_class: type[BrooksChartEngine] = BrooksChartEngine
    widget_name: str = "BrooksChartManager"
    icon_name: str = str(Path(__file__).resolve().parent.parent / "vnpy" / "trader" / "ui" / "ico" / "database.ico")
