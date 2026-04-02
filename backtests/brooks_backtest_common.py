"""Brooks 策略回测公共工具。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import json
import shutil
import sys

import duckdb

ROOT_DIR: Path = Path(__file__).resolve().parent.parent
SCRIPTS_DIR: Path = ROOT_DIR / "scripts"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from backtest_result_utils import make_jsonable
import vnpy.trader.database as database_module
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.setting import SETTINGS
from vnpy.trader.object import BarData
from vnpy_ctastrategy.backtesting import BacktestingEngine

from brooks_chart_app.engine import estimate_pricetick
from market_data_common import FOCUS_SYMBOLS, SYMBOL_CONFIG_MAP
from strategies.ema20_h2_l2_trend_strategy import Ema20H2L2TrendStrategy
from strategies.h1_l1_first_pullback_strategy import H1L1FirstPullbackStrategy
from strategies.mag_20_gap_strategy import Mag20GapStrategy


SOURCE_DB_PATH: Path = ROOT_DIR / ".vntrader" / "database.duckdb"
OUTPUT_ROOT: Path = ROOT_DIR / "backtests" / "output"


@dataclass(frozen=True)
class StrategySpec:
    """策略注册信息。"""

    key: str
    display_name: str
    strategy_class: type
    default_setting: dict


STRATEGY_SPECS: tuple[StrategySpec, ...] = (
    StrategySpec(
        key="ema20_h2_l2",
        display_name="EMA20_H2_L2",
        strategy_class=Ema20H2L2TrendStrategy,
        default_setting={
            "signal_window": 5,
            "ema_window": 20,
            "am_window": 80,
            "init_days": 5,
            "fixed_size": 1.0,
            "max_pullback_bars": 12,
            "max_signal_wait_bars": 3,
            "ema_distance_factor": 0.6,
            "risk_reward_ratio": 2.0,
            "breakeven_r": 1.0,
            "stop_buffer_ticks": 1,
        },
    ),
    StrategySpec(
        key="h1_l1",
        display_name="H1_L1_FIRST_PULLBACK",
        strategy_class=H1L1FirstPullbackStrategy,
        default_setting={
            "signal_window": 5,
            "ema_window": 20,
            "am_window": 80,
            "init_days": 5,
            "fixed_size": 1.0,
            "max_pullback_bars": 12,
            "max_signal_wait_bars": 3,
            "ema_distance_factor": 0.6,
            "risk_reward_ratio": 2.0,
            "breakeven_r": 1.0,
            "stop_buffer_ticks": 1,
        },
    ),
    StrategySpec(
        key="mag20",
        display_name="MAG20_GAP",
        strategy_class=Mag20GapStrategy,
        default_setting={
            "signal_window": 5,
            "ema_window": 20,
            "am_window": 80,
            "init_days": 5,
            "fixed_size": 1.0,
            "max_pullback_bars": 12,
            "max_signal_wait_bars": 3,
            "ema_distance_factor": 0.6,
            "risk_reward_ratio": 2.0,
            "breakeven_r": 1.0,
            "stop_buffer_ticks": 1,
            "min_gap_bars": 20,
            "max_gap_bars": 45,
        },
    ),
)


def prepare_backtest_snapshot(tag: str) -> Path:
    """复制 DuckDB 快照，避免锁冲突。"""
    if not SOURCE_DB_PATH.exists():
        raise RuntimeError(f"找不到数据库文件：{SOURCE_DB_PATH}")

    snapshot_path = ROOT_DIR / ".vntrader" / f"{tag}_{uuid4().hex}.duckdb"
    shutil.copy2(SOURCE_DB_PATH, snapshot_path)
    SETTINGS["database.name"] = "duckdb"
    SETTINGS["database.database"] = snapshot_path.name
    database_module.database = None
    return snapshot_path


def fetch_symbol_window(snapshot_path: Path, vt_symbol: str) -> tuple[datetime, datetime, int]:
    """读取单个品种的可用时间区间。"""
    symbol, exchange_text = vt_symbol.split(".")
    con = duckdb.connect(str(snapshot_path))
    row = con.execute(
        """
        SELECT start, "end", count
        FROM bar_overview
        WHERE symbol = ? AND exchange = ? AND interval = '1m'
        """,
        [symbol, exchange_text],
    ).fetchone()
    con.close()
    if not row:
        raise RuntimeError(f"快照中找不到 {vt_symbol} 的分钟线概览")
    return row[0], row[1], int(row[2])


def load_sample_bars(snapshot_path: Path, vt_symbol: str, limit: int = 500) -> list[BarData]:
    """读取估算最小跳动所需的样本。"""
    symbol, exchange_text = vt_symbol.split(".")
    exchange = Exchange(exchange_text)
    con = duckdb.connect(str(snapshot_path))
    rows = con.execute(
        """
        SELECT datetime, open_price, high_price, low_price, close_price, volume
        FROM bar_data
        WHERE symbol = ? AND exchange = ? AND interval = '1m'
        ORDER BY datetime
        LIMIT ?
        """,
        [symbol, exchange_text, limit],
    ).fetchall()
    con.close()

    bars: list[BarData] = []
    for row in rows:
        bars.append(
            BarData(
                symbol=symbol,
                exchange=exchange,
                datetime=row[0],
                interval=Interval.MINUTE,
                open_price=float(row[1]),
                high_price=float(row[2]),
                low_price=float(row[3]),
                close_price=float(row[4]),
                volume=float(row[5]),
                gateway_name="DB",
            )
        )
    return bars


def infer_engine_parameters(snapshot_path: Path, vt_symbol: str) -> dict:
    """为不同品种推断回测参数。"""
    symbol = vt_symbol.split(".")[0]
    config = SYMBOL_CONFIG_MAP[symbol]
    sample_bars = load_sample_bars(snapshot_path, vt_symbol)
    pricetick = estimate_pricetick(sample_bars)

    if config.market_group == "crypto_24x7":
        rate = 0.0005
    else:
        rate = 0.0

    return {
        "rate": rate,
        "slippage": pricetick,
        "size": 1,
        "pricetick": pricetick,
        "capital": 100000,
    }


def run_single_backtest(
    *,
    vt_symbol: str,
    spec: StrategySpec,
    snapshot_path: Path,
    start: datetime,
    end: datetime,
    strategy_setting: dict | None = None,
) -> tuple[dict, object, BacktestingEngine, dict]:
    """执行单次策略回测。"""
    engine = BacktestingEngine()
    engine_setting = infer_engine_parameters(snapshot_path, vt_symbol)
    engine.set_parameters(
        vt_symbol=vt_symbol,
        interval=Interval.MINUTE,
        start=start,
        end=end,
        rate=engine_setting["rate"],
        slippage=engine_setting["slippage"],
        size=engine_setting["size"],
        pricetick=engine_setting["pricetick"],
        capital=engine_setting["capital"],
    )

    merged_setting = dict(spec.default_setting)
    if strategy_setting:
        merged_setting.update(strategy_setting)

    engine.add_strategy(spec.strategy_class, merged_setting)
    engine.load_data()
    engine.run_backtesting()
    daily_df = engine.calculate_result()
    stats = make_jsonable(engine.calculate_statistics())
    return stats, daily_df, engine, merged_setting
def save_run_detail(
    *,
    output_dir: Path,
    strategy_key: str,
    vt_symbol: str,
    start: datetime,
    end: datetime,
    stats: dict,
    setting: dict,
    engine_parameters: dict,
) -> None:
    """保存单次回测详情。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_symbol = vt_symbol.replace(".", "_")
    detail_path = output_dir / f"{strategy_key}__{safe_symbol}.json"
    detail_path.write_text(
        json.dumps(
            {
                "strategy_key": strategy_key,
                "vt_symbol": vt_symbol,
                "start": start.isoformat(sep=" "),
                "end": end.isoformat(sep=" "),
                "setting": setting,
                "engine_parameters": engine_parameters,
                "stats": stats,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )


def iter_focus_vt_symbols() -> list[str]:
    """返回重点品种的 vt_symbol 列表。"""
    vt_symbols: list[str] = []
    for symbol in FOCUS_SYMBOLS:
        config = SYMBOL_CONFIG_MAP[symbol]
        vt_symbols.append(f"{symbol}.{config.exchange.value}")
    return vt_symbols
