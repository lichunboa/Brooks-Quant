"""
对 EMA20_H2_L2 顺势策略执行参数优化。
"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import csv
import shutil

from vnpy.trader.optimize import OptimizationSetting
from vnpy.trader.constant import Interval
from vnpy.trader.setting import SETTINGS
from vnpy_ctastrategy.backtesting import BacktestingEngine

from strategies.ema20_h2_l2_trend_strategy import Ema20H2L2TrendStrategy


ROOT_DIR: Path = Path(__file__).resolve().parent.parent
OUTPUT_DIR: Path = Path(__file__).resolve().parent / "output" / "ema20_h2_l2"
SOURCE_DB_PATH: Path = ROOT_DIR / ".vntrader" / "database.duckdb"


def prepare_backtest_snapshot() -> Path:
    """复制数据库快照，避免 DuckDB 锁冲突。"""
    if not SOURCE_DB_PATH.exists():
        raise RuntimeError(f"找不到数据库文件：{SOURCE_DB_PATH}")

    snapshot_path: Path = ROOT_DIR / ".vntrader" / f"database_opt_snapshot_{uuid4().hex}.duckdb"
    shutil.copy2(SOURCE_DB_PATH, snapshot_path)
    SETTINGS["database.database"] = snapshot_path.name
    return snapshot_path


def build_optimization_setting(quick: bool, target_name: str, base_signal_window: int) -> OptimizationSetting:
    """创建优化参数集合。"""
    optimization = OptimizationSetting()
    optimization.set_target(target_name)

    if quick:
        optimization.add_parameter("signal_window", max(5, base_signal_window), max(10, base_signal_window + 5), 5)
        optimization.add_parameter("max_signal_wait_bars", 2, 3, 1)
        optimization.add_parameter("risk_reward_ratio", 1.6, 2.0, 0.4)
        return optimization

    optimization.add_parameter("signal_window", max(5, base_signal_window - 5), max(15, base_signal_window + 10), 5)
    optimization.add_parameter("max_pullback_bars", 8, 14, 2)
    optimization.add_parameter("max_signal_wait_bars", 2, 4, 1)
    optimization.add_parameter("ema_distance_factor", 0.4, 0.8, 0.2)
    optimization.add_parameter("risk_reward_ratio", 1.4, 2.6, 0.4)
    optimization.add_parameter("breakeven_r", 0.8, 1.6, 0.4)
    return optimization


def main() -> None:
    """执行穷举优化。"""
    parser = ArgumentParser(description="优化 EMA20_H2_L2 顺势策略参数。")
    parser.add_argument("--symbol", default="BTCUSDT.GLOBAL")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-12-07")
    parser.add_argument("--target", default="sharpe_ratio")
    parser.add_argument("--base-signal-window", type=int, default=5)
    parser.add_argument("--quick", action="store_true", help="只跑快速参数烟雾测试。")
    args = parser.parse_args()

    snapshot_path: Path = prepare_backtest_snapshot()

    try:
        optimization = build_optimization_setting(args.quick, args.target, args.base_signal_window)
        settings = optimization.generate_settings()
        results: list[tuple[dict, float, dict]] = []

        print(f"开始顺序优化，共 {len(settings)} 组参数")

        for index, setting in enumerate(settings, start=1):
            print(f"[{index}/{len(settings)}] 测试参数：{setting}")
            target, stats = run_single_optimization(
                vt_symbol=args.symbol,
                start=datetime.fromisoformat(args.start),
                end=datetime.fromisoformat(args.end),
                setting=setting,
                target_name=optimization.target_name,
            )
            print(f"目标值({optimization.target_name})：{target}")
            results.append((setting, target, make_jsonable(stats)))

        results.sort(key=lambda item: item[1], reverse=True)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = OUTPUT_DIR / "optimization_results.csv"

        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["参数", "目标", "统计"])
            for params, target, stats in results:
                writer.writerow([params, target, stats])

        print(f"优化完成，结果已写入：{csv_path}")
        print("前十组结果：")
        for row in results[:10]:
            print(row)
    finally:
        if snapshot_path.exists():
            snapshot_path.unlink()


def run_single_optimization(
    vt_symbol: str,
    start: datetime,
    end: datetime,
    setting: dict,
    target_name: str,
) -> tuple[float, dict]:
    """顺序执行单组参数回测。"""
    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vt_symbol,
        interval=Interval.MINUTE,
        start=start,
        end=end,
        rate=0.0005,
        slippage=0.1,
        size=1,
        pricetick=0.1,
        capital=100000,
    )

    engine.add_strategy(Ema20H2L2TrendStrategy, setting)
    engine.load_data()
    engine.run_backtesting()
    engine.calculate_result()
    stats = engine.calculate_statistics()

    target = stats.get(target_name, 0)
    if hasattr(target, "item"):
        target = target.item()

    return float(target), stats


def make_jsonable(data: dict) -> dict:
    """把 numpy 标量转换为原生 Python 类型。"""
    converted: dict = {}
    for key, value in data.items():
        if hasattr(value, "item"):
            converted[key] = value.item()
        else:
            converted[key] = value
    return converted


if __name__ == "__main__":
    main()
