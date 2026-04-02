"""三套 Brooks 策略的全量回测矩阵。"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
import csv
import json

from brooks_backtest_common import (
    OUTPUT_ROOT,
    STRATEGY_SPECS,
    fetch_symbol_window,
    infer_engine_parameters,
    iter_focus_vt_symbols,
    prepare_backtest_snapshot,
    run_single_backtest,
    save_run_detail,
)
from market_data_common import SYMBOL_CONFIG_MAP, normalize_symbol


def build_summary_row(
    *,
    strategy_key: str,
    signal_window: int,
    vt_symbol: str,
    start: datetime,
    end: datetime,
    count: int,
    stats: dict,
    engine_parameters: dict,
) -> dict[str, object]:
    """构建摘要行。"""
    trade_count = int(stats.get("total_trade_count", 0) or 0)
    total_days = int(stats.get("total_days", 0) or 0)
    pnl_per_trade = float(stats.get("total_net_pnl", 0) or 0) / trade_count if trade_count else 0.0

    return {
        "strategy_key": strategy_key,
        "signal_window": signal_window,
        "vt_symbol": vt_symbol,
        "start": start.isoformat(sep=" "),
        "end": end.isoformat(sep=" "),
        "bar_count": count,
        "rate": engine_parameters["rate"],
        "slippage": engine_parameters["slippage"],
        "pricetick": engine_parameters["pricetick"],
        "capital": engine_parameters["capital"],
        "total_days": total_days,
        "profit_days": int(stats.get("profit_days", 0) or 0),
        "loss_days": int(stats.get("loss_days", 0) or 0),
        "total_net_pnl": float(stats.get("total_net_pnl", 0) or 0),
        "total_return": float(stats.get("total_return", 0) or 0),
        "max_drawdown": float(stats.get("max_drawdown", 0) or 0),
        "max_ddpercent": float(stats.get("max_ddpercent", 0) or 0),
        "sharpe_ratio": float(stats.get("sharpe_ratio", 0) or 0),
        "ewm_sharpe": float(stats.get("ewm_sharpe", 0) or 0),
        "return_drawdown_ratio": float(stats.get("return_drawdown_ratio", 0) or 0),
        "rgr_ratio": float(stats.get("rgr_ratio", 0) or 0),
        "total_trade_count": trade_count,
        "daily_trade_count": float(stats.get("daily_trade_count", 0) or 0),
        "pnl_per_trade": pnl_per_trade,
    }


def flush_summary(output_dir: Path, rows: list[dict[str, object]]) -> None:
    """把当前摘要增量写盘。"""
    if not rows:
        return

    sorted_rows = sorted(rows, key=lambda item: (str(item["strategy_key"]), -float(item["sharpe_ratio"])))

    csv_path = output_dir / "matrix_summary.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(sorted_rows[0].keys()))
        writer.writeheader()
        writer.writerows(sorted_rows)

    json_path = output_dir / "matrix_summary.json"
    json_path.write_text(json.dumps(sorted_rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> None:
    """运行三套策略的回测矩阵。"""
    parser = ArgumentParser(description="运行三套 Brooks 策略的全量回测矩阵。")
    parser.add_argument("--symbols", default="all", help="默认 all，使用重点品种全集。")
    parser.add_argument(
        "--output-tag",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="输出目录标签。",
    )
    parser.add_argument("--start", default="2025-01-01", help="统一研究窗口开始时间。")
    parser.add_argument("--end", default="2026-03-31 23:59:00", help="统一研究窗口结束时间。")
    parser.add_argument("--signal-window", type=int, default=5, help="统一覆盖三套策略的执行周期，单位为分钟。")
    args = parser.parse_args()

    if args.symbols.strip().lower() == "all":
        vt_symbols = iter_focus_vt_symbols()
    else:
        vt_symbols = []
        for item in args.symbols.split(","):
            symbol_text = item.strip()
            if not symbol_text:
                continue
            if "." in symbol_text:
                vt_symbols.append(symbol_text)
            else:
                symbol = normalize_symbol(symbol_text)
                config = SYMBOL_CONFIG_MAP[symbol]
                vt_symbols.append(f"{symbol}.{config.exchange.value}")
    snapshot_path = prepare_backtest_snapshot("brooks_matrix_snapshot")
    output_dir = OUTPUT_ROOT / "brooks_matrix" / args.output_tag
    detail_dir = output_dir / "details"
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_dir.mkdir(parents=True, exist_ok=True)
    user_start = datetime.fromisoformat(args.start)
    user_end = datetime.fromisoformat(args.end)

    summary_rows: list[dict[str, object]] = []

    try:
        total_runs = len(STRATEGY_SPECS) * len(vt_symbols)
        run_index = 0

        for spec in STRATEGY_SPECS:
            for vt_symbol in vt_symbols:
                run_index += 1
                symbol_start, symbol_end, count = fetch_symbol_window(snapshot_path, vt_symbol)
                start = max(symbol_start, user_start)
                end = min(symbol_end, user_end)
                if end <= start:
                    print(f"[{run_index}/{total_runs}] 跳过 {spec.display_name} | {vt_symbol}，统一窗口内没有可用数据")
                    continue
                engine_parameters = infer_engine_parameters(snapshot_path, vt_symbol)
                print(
                    f"[{run_index}/{total_runs}] 开始回测 "
                    f"{spec.display_name} | {vt_symbol} | "
                    f"{start} -> {end} | bars={count}"
                )

                stats, _, _, merged_setting = run_single_backtest(
                    vt_symbol=vt_symbol,
                    spec=spec,
                    snapshot_path=snapshot_path,
                    start=start,
                    end=end,
                    strategy_setting={"signal_window": args.signal_window},
                )

                row = build_summary_row(
                    strategy_key=spec.key,
                    signal_window=args.signal_window,
                    vt_symbol=vt_symbol,
                    start=start,
                    end=end,
                    count=count,
                    stats=stats,
                    engine_parameters=engine_parameters,
                )
                summary_rows.append(row)
                save_run_detail(
                    output_dir=detail_dir,
                    strategy_key=spec.key,
                    vt_symbol=vt_symbol,
                    start=start,
                    end=end,
                    stats=stats,
                    setting=merged_setting,
                    engine_parameters=engine_parameters,
                )
                flush_summary(output_dir, summary_rows)

                print(
                    json.dumps(
                        {
                            "strategy": spec.display_name,
                            "vt_symbol": vt_symbol,
                            "signal_window": args.signal_window,
                            "total_net_pnl": row["total_net_pnl"],
                            "sharpe_ratio": row["sharpe_ratio"],
                            "max_drawdown": row["max_drawdown"],
                            "total_trade_count": row["total_trade_count"],
                        },
                        ensure_ascii=False,
                    )
                )

        flush_summary(output_dir, summary_rows)
        csv_path = output_dir / "matrix_summary.csv"
        json_path = output_dir / "matrix_summary.json"

        print(f"矩阵回测完成：{csv_path}")
        print(f"矩阵回测完成：{json_path}")
    finally:
        if snapshot_path.exists():
            snapshot_path.unlink()


if __name__ == "__main__":
    main()
