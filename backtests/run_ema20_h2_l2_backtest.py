"""
运行 EMA20_H2_L2 顺势策略单次回测。
"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
import json
import sys

from vnpy.trader.constant import Interval
from vnpy_ctastrategy.backtesting import BacktestingEngine

ROOT_DIR: Path = Path(__file__).resolve().parent.parent
OUTPUT_DIR: Path = Path(__file__).resolve().parent / "output" / "ema20_h2_l2"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtest_result_utils import make_jsonable, write_json, write_lifecycles_csv, write_trades_csv
from brooks_backtest_common import infer_engine_parameters, prepare_backtest_snapshot
from strategies.ema20_h2_l2_trend_strategy import Ema20H2L2TrendStrategy


def run_backtest(
    vt_symbol: str,
    start: datetime,
    end: datetime,
    setting: dict,
) -> tuple[dict, object, BacktestingEngine, Path]:
    """执行一次回测。"""
    snapshot_path = prepare_backtest_snapshot("single_backtest_snapshot")
    try:
        engine_parameters = infer_engine_parameters(snapshot_path, vt_symbol)

        engine = BacktestingEngine()
        engine.set_parameters(
            vt_symbol=vt_symbol,
            interval=Interval.MINUTE,
            start=start,
            end=end,
            rate=engine_parameters["rate"],
            slippage=engine_parameters["slippage"],
            size=engine_parameters["size"],
            pricetick=engine_parameters["pricetick"],
            capital=engine_parameters["capital"],
        )
        engine.add_strategy(Ema20H2L2TrendStrategy, setting)
        engine.load_data()
        engine.run_backtesting()
        daily_df = engine.calculate_result()
        stats = engine.calculate_statistics()
        return stats, daily_df, engine, snapshot_path
    except Exception:
        if snapshot_path.exists():
            snapshot_path.unlink()
        raise


def save_outputs(vt_symbol: str, start: datetime, end: datetime, setting: dict, stats: dict, daily_df, engine: BacktestingEngine) -> None:
    """保存统计结果和逐日结果。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats_path = OUTPUT_DIR / "latest_stats.json"
    write_json(stats_path, make_jsonable(stats))

    meta_path = OUTPUT_DIR / "latest_meta.json"
    write_json(
        meta_path,
        {
            "vt_symbol": vt_symbol,
            "start": start.isoformat(sep=" "),
            "end": end.isoformat(sep=" "),
            "setting": setting,
        },
    )

    if daily_df is not None and not daily_df.empty:
        csv_path = OUTPUT_DIR / "latest_daily.csv"
        daily_df.to_csv(csv_path, encoding="utf-8-sig")

    write_trades_csv(OUTPUT_DIR / "latest_trades.csv", engine)
    write_lifecycles_csv(OUTPUT_DIR / "latest_lifecycles.csv", engine)

    figure = engine.show_chart()
    if figure:
        html_path = OUTPUT_DIR / "latest_report.html"
        figure.write_html(html_path, include_plotlyjs="cdn")


def main() -> None:
    """命令行入口。"""
    parser = ArgumentParser(description="运行 EMA20_H2_L2 顺势策略单次回测。")
    parser.add_argument("--symbol", default="BTCUSDT.GLOBAL")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-12-07")
    parser.add_argument("--signal-window", type=int, default=5)
    parser.add_argument("--risk-reward-ratio", type=float, default=2.0)
    args = parser.parse_args()

    setting: dict = {
        "signal_window": args.signal_window,
        "ema_window": 20,
        "am_window": 80,
        "init_days": 5,
        "fixed_size": 1.0,
        "max_pullback_bars": 12,
        "max_signal_wait_bars": 3,
        "ema_distance_factor": 0.6,
        "risk_reward_ratio": args.risk_reward_ratio,
        "breakeven_r": 1.0,
        "stop_buffer_ticks": 1,
    }

    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)

    stats = {}
    snapshot_path: Path | None = None
    try:
        stats, daily_df, engine, snapshot_path = run_backtest(args.symbol, start, end, setting)
        save_outputs(args.symbol, start, end, setting, stats, daily_df, engine)
    finally:
        if snapshot_path and snapshot_path.exists():
            snapshot_path.unlink()

    print("回测完成")
    print(json.dumps({
        "vt_symbol": args.symbol,
        "total_net_pnl": stats.get("total_net_pnl"),
        "total_return": stats.get("total_return"),
        "max_drawdown": stats.get("max_drawdown"),
        "sharpe_ratio": stats.get("sharpe_ratio"),
        "return_drawdown_ratio": stats.get("return_drawdown_ratio"),
        "total_trade_count": stats.get("total_trade_count"),
    }, ensure_ascii=False, indent=2, default=str))
if __name__ == "__main__":
    main()
