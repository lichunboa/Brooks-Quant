"""
Brooks 图表应用引擎。
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from statistics import median

from vnpy.trader.database import BaseDatabase, BarOverview, get_database
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, ContractData


APP_NAME: str = "BrooksChart"


class BrooksChartEngine(BaseEngine):
    """负责加载历史 K 线和合约参数。"""

    def __init__(self, main_engine: MainEngine, event_engine) -> None:
        super().__init__(main_engine, event_engine, APP_NAME)
        self.database: BaseDatabase = get_database()

    def get_bar_overview(self) -> list[BarOverview]:
        """读取数据库中的 K 线概览。"""
        return self.database.get_bar_overview()

    def load_bar_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> list[BarData]:
        """读取指定区间的历史 K 线。"""
        return self.database.load_bar_data(symbol, exchange, interval, start, end)

    def get_pricetick(self, symbol: str, exchange: Exchange, bars: list[BarData]) -> float:
        """优先从合约信息读取价格跳动，否则根据 K 线价格估算。"""
        vt_symbol: str = f"{symbol}.{exchange.value}"
        contract: ContractData | None = self.main_engine.get_contract(vt_symbol)
        if contract and contract.pricetick:
            return float(contract.pricetick)

        return estimate_pricetick(bars)


def estimate_pricetick(bars: list[BarData]) -> float:
    """根据价格小数位估算价格跳动。"""
    if not bars:
        return 0.01

    median_price: float = median([bar.close_price for bar in bars])
    decimals: int = 0
    sample_size: int = min(len(bars), 200)

    for bar in bars[:sample_size]:
        for price in (bar.open_price, bar.high_price, bar.low_price, bar.close_price):
            text: str = format(price, "f").rstrip("0").rstrip(".")
            if "." in text:
                decimals = max(decimals, len(text.split(".")[1]))

    if decimals <= 0:
        return 1.0

    estimated_tick: float = float(Decimal("1").scaleb(-decimals))

    # 某些历史数据来自 float32/float64 存储，可能出现过度细碎的小数位。
    # 这里做一次价格级别上的修正，优先给图表标注一个更可读的跳动值。
    if median_price >= 10000 and estimated_tick < 0.1:
        return 0.1
    if median_price >= 1000 and estimated_tick < 0.01:
        return 0.01
    if median_price >= 100 and estimated_tick < 0.01:
        return 0.01
    if median_price >= 1 and estimated_tick < 0.0001:
        return 0.0001
    if median_price >= 0.01 and estimated_tick < 0.00001:
        return 0.00001

    return estimated_tick
