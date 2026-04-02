"""
从 MT5 网关导入历史 K 线到本地 DuckDB。
"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
import json
from time import sleep

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.object import HistoryRequest
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.database import get_database
from vnpy_mt5 import Mt5Gateway
from mt5_compat import patch_mt5_timezone_compat


ROOT_DIR: Path = Path(__file__).resolve().parent.parent
CONFIG_PATH: Path = ROOT_DIR / ".vntrader" / "connect_mt5.json"


def main() -> None:
    """命令行入口。"""
    parser = ArgumentParser(description="从 MT5 导入外汇/指数历史 K 线到 DuckDB。")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--start", default="2025-10-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--interval", default="1m", choices=["1m", "1h", "d"])
    parser.add_argument("--discover-only", action="store_true", help="仅列出当前 MT5 可用合约，不导入。")
    args = parser.parse_args()

    interval: Interval = Interval(args.interval)
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)

    patch_mt5_timezone_compat()

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(Mt5Gateway, "MT5")

    if not CONFIG_PATH.exists():
        raise RuntimeError("没有找到 .vntrader/connect_mt5.json 配置。")
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        setting = json.load(f)

    main_engine.connect(setting, "MT5")
    sleep(1.5)

    contracts = main_engine.get_all_contracts()
    symbols = [contract.symbol for contract in contracts if contract.gateway_name == "MT5"]
    print(f"当前 MT5 可用合约：{symbols}")

    if args.discover_only:
        main_engine.close()
        return

    if args.symbols.strip():
        target_symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    else:
        target_symbols = symbols

    db = get_database()

    for symbol in target_symbols:
        req = HistoryRequest(
            symbol=symbol,
            exchange=Exchange.OTC,
            interval=interval,
            start=start,
            end=end,
        )
        print(f"开始导入：{symbol} {interval.value} {start} -> {end}")
        bars = main_engine.query_history(req, "MT5")
        print(f"获取到 {len(bars)} 根 K 线")

        if bars:
            db.save_bar_data(bars)
            print(f"已写入数据库：{symbol}")
        else:
            print(f"没有获取到数据：{symbol}")

    main_engine.close()


if __name__ == "__main__":
    main()
