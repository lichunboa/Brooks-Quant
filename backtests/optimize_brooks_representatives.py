"""基于回测矩阵结果，对三套策略的代表品种做快速优化。"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime
from itertools import product
from pathlib import Path
import csv
import json

from brooks_backtest_common import (
    OUTPUT_ROOT,
    STRATEGY_SPECS,
    fetch_symbol_window,
    infer_engine_parameters,
    prepare_backtest_snapshot,
    run_single_backtest,
    save_run_detail,
)


def load_matrix_rows(matrix_dir: Path) -> list[dict]:
    """读取矩阵结果。"""
    json_path = matrix_dir / "matrix_summary.json"
    return json.loads(json_path.read_text(encoding="utf-8"))


def choose_representative(rows: list[dict], strategy_key: str) -> dict:
    """为单个策略挑选代表品种。"""
    candidates = [row for row in rows if row["strategy_key"] == strategy_key]
    traded = [row for row in candidates if int(row["total_trade_count"]) >= 20]

    if traded:
        traded.sort(
            key=lambda row: (
                float(row["sharpe_ratio"]),
                float(row["return_drawdown_ratio"]),
                float(row["total_net_pnl"]),
            ),
            reverse=True,
        )
        return traded[0]

    candidates.sort(
        key=lambda row: (
            int(row["total_trade_count"]),
            float(row["sharpe_ratio"]),
            float(row["total_net_pnl"]),
        ),
        reverse=True,
    )
    return candidates[0]


def build_grid(strategy_key: str) -> list[dict]:
    """构建快速优化参数网格。"""
    if strategy_key == "ema20_h2_l2":
        return [
            {
                "signal_window": signal_window,
                "max_signal_wait_bars": max_signal_wait_bars,
                "risk_reward_ratio": risk_reward_ratio,
                "ema_distance_factor": ema_distance_factor,
            }
            for signal_window, max_signal_wait_bars, risk_reward_ratio, ema_distance_factor in product(
                [5, 10],
                [2, 3],
                [1.6, 2.0, 2.4],
                [0.4, 0.6, 0.8],
            )
        ]

    if strategy_key == "h1_l1":
        return [
            {
                "signal_window": signal_window,
                "risk_reward_ratio": risk_reward_ratio,
                "ema_distance_factor": ema_distance_factor,
                "max_pullback_bars": max_pullback_bars,
            }
            for signal_window, risk_reward_ratio, ema_distance_factor, max_pullback_bars in product(
                [5, 10],
                [1.4, 1.8, 2.2],
                [0.4, 0.6],
                [8, 12],
            )
        ]

    return [
        {
            "min_gap_bars": min_gap_bars,
            "max_gap_bars": max_gap_bars,
            "risk_reward_ratio": risk_reward_ratio,
            "ema_distance_factor": ema_distance_factor,
            "stop_buffer_ticks": stop_buffer_ticks,
        }
        for min_gap_bars, max_gap_bars, risk_reward_ratio, ema_distance_factor, stop_buffer_ticks in product(
            [18, 20, 24],
            [36, 45],
            [1.2, 1.6, 2.0],
            [0.4, 0.6],
            [1, 2],
        )
    ]


def main() -> None:
    """执行三套策略的代表品种快速优化。"""
    parser = ArgumentParser(description="对 Brooks 策略代表品种执行快速优化。")
    parser.add_argument("--matrix-tag", required=True, help="矩阵回测输出目录标签。")
    parser.add_argument(
        "--output-tag",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="优化输出目录标签。",
    )
    args = parser.parse_args()

    matrix_dir = OUTPUT_ROOT / "brooks_matrix" / args.matrix_tag
    rows = load_matrix_rows(matrix_dir)
    snapshot_path = prepare_backtest_snapshot("brooks_opt_snapshot")
    output_dir = OUTPUT_ROOT / "brooks_opt" / args.output_tag
    detail_dir = output_dir / "details"
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_dir.mkdir(parents=True, exist_ok=True)

    optimization_rows: list[dict[str, object]] = []

    try:
        for spec in STRATEGY_SPECS:
            representative = choose_representative(rows, spec.key)
            vt_symbol = str(representative["vt_symbol"])
            start = datetime.fromisoformat(str(representative["start"]))
            end = datetime.fromisoformat(str(representative["end"]))
            _, _, _ = fetch_symbol_window(snapshot_path, vt_symbol)
            engine_parameters = infer_engine_parameters(snapshot_path, vt_symbol)
            grid = build_grid(spec.key)

            print(f"开始优化 {spec.display_name}，代表品种：{vt_symbol}，共 {len(grid)} 组参数")

            for index, setting in enumerate(grid, start=1):
                print(f"[{spec.display_name} {index}/{len(grid)}] {setting}")
                stats, _, _, merged_setting = run_single_backtest(
                    vt_symbol=vt_symbol,
                    spec=spec,
                    snapshot_path=snapshot_path,
                    start=start,
                    end=end,
                    strategy_setting=setting,
                )

                row = {
                    "strategy_key": spec.key,
                    "vt_symbol": vt_symbol,
                    "start": start.isoformat(sep=" "),
                    "end": end.isoformat(sep=" "),
                    "setting": json.dumps(setting, ensure_ascii=False, sort_keys=True),
                    "total_net_pnl": float(stats.get("total_net_pnl", 0) or 0),
                    "sharpe_ratio": float(stats.get("sharpe_ratio", 0) or 0),
                    "return_drawdown_ratio": float(stats.get("return_drawdown_ratio", 0) or 0),
                    "max_drawdown": float(stats.get("max_drawdown", 0) or 0),
                    "total_trade_count": int(stats.get("total_trade_count", 0) or 0),
                }
                optimization_rows.append(row)

                save_run_detail(
                    output_dir=detail_dir,
                    strategy_key=f"{spec.key}__opt_{index:03d}",
                    vt_symbol=vt_symbol,
                    start=start,
                    end=end,
                    stats=stats,
                    setting=merged_setting,
                    engine_parameters=engine_parameters,
                )

        optimization_rows.sort(
            key=lambda row: (str(row["strategy_key"]), float(row["sharpe_ratio"])),
            reverse=True,
        )

        csv_path = output_dir / "optimization_summary.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(optimization_rows[0].keys()))
            writer.writeheader()
            writer.writerows(optimization_rows)

        json_path = output_dir / "optimization_summary.json"
        json_path.write_text(json.dumps(optimization_rows, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"优化完成：{csv_path}")
        print(f"优化完成：{json_path}")
    finally:
        if snapshot_path.exists():
            snapshot_path.unlink()


if __name__ == "__main__":
    main()
