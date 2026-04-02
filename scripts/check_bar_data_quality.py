"""检查重点品种 K 线数据质量。"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
import csv
import json
import shutil
import tempfile

import duckdb

from market_data_common import FOCUS_SYMBOLS, SYMBOL_CONFIG_MAP, parse_symbol_list, resolve_database_path


GAP_THRESHOLD_MINUTES: dict[str, int] = {
    "crypto_24x7": 2,
    "forex_otc": 180,
    "metals_otc": 180,
    "index_cfd": 240,
    "futures_cme": 90,
    "us_equity_intraday_sparse": 120,
}
IGNORED_LARGE_GAP_MINUTES: dict[str, int] = {
    "crypto_24x7": 0,
    "forex_otc": 2000,
    "metals_otc": 2000,
    "index_cfd": 2000,
    "futures_cme": 4000,
    "us_equity_intraday_sparse": 360,
}
FRESHNESS_THRESHOLD_DAYS: dict[str, int] = {
    "crypto_24x7": 3,
    "forex_otc": 14,
    "metals_otc": 14,
    "index_cfd": 14,
    "futures_cme": 14,
    "us_equity_intraday_sparse": 21,
}


def open_connection(database_file: str) -> tuple[duckdb.DuckDBPyConnection, Path]:
    """尽量打开数据库，若正式库被锁则复制临时副本只读检查。"""
    source_path = resolve_database_path(database_file)
    try:
        return duckdb.connect(str(source_path), read_only=True), source_path
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "Conflicting lock" not in message:
            raise

        temp_dir = Path(tempfile.mkdtemp(prefix="quality_db_copy_"))
        temp_path = temp_dir / source_path.name
        shutil.copy2(source_path, temp_path)
        return duckdb.connect(str(temp_path), read_only=True), temp_path


def fetch_overview(con: duckdb.DuckDBPyConnection, symbol: str, exchange: str, interval: str) -> tuple | None:
    """读取单个品种的概览。"""
    row = con.execute(
        """
        SELECT symbol, exchange, interval, count, start, "end"
        FROM bar_overview
        WHERE symbol = ? AND exchange = ? AND interval = ?
        """,
        [symbol, exchange, interval],
    ).fetchone()
    return row


def fetch_quality_metrics(
    con: duckdb.DuckDBPyConnection,
    *,
    symbol: str,
    exchange: str,
    interval: str,
    gap_threshold_minutes: int,
    ignored_large_gap_minutes: int,
) -> dict[str, int | float]:
    """读取单个品种的质量指标。"""
    invalid_price_count, invalid_ohlc_count, duplicate_count = con.execute(
        """
        WITH base AS (
            SELECT *
            FROM bar_data
            WHERE symbol = ? AND exchange = ? AND interval = ?
        ),
        duplicates AS (
            SELECT COUNT(*) - COUNT(DISTINCT datetime) AS duplicate_count
            FROM base
        )
        SELECT
            SUM(
                CASE
                    WHEN open_price <= 0 OR high_price <= 0 OR low_price <= 0 OR close_price <= 0
                    THEN 1 ELSE 0
                END
            ) AS invalid_price_count,
            SUM(
                CASE
                    WHEN high_price < GREATEST(open_price, close_price, low_price)
                         OR low_price > LEAST(open_price, close_price, high_price)
                    THEN 1 ELSE 0
                END
            ) AS invalid_ohlc_count,
            (SELECT duplicate_count FROM duplicates) AS duplicate_count
        FROM base
        """,
        [symbol, exchange, interval],
    ).fetchone()

    max_gap_minutes, suspicious_gap_count = con.execute(
        """
        WITH ordered AS (
            SELECT
                datetime,
                LAG(datetime) OVER (ORDER BY datetime) AS prev_dt
            FROM bar_data
            WHERE symbol = ? AND exchange = ? AND interval = ?
        ),
        gaps AS (
            SELECT
                DATE_DIFF('minute', prev_dt, datetime) AS gap_minutes
            FROM ordered
            WHERE prev_dt IS NOT NULL
        )
        SELECT
            COALESCE(MAX(gap_minutes), 0) AS max_gap_minutes,
            COALESCE(
                SUM(
                    CASE
                        WHEN gap_minutes > ?
                             AND (? = 0 OR gap_minutes < ?)
                        THEN 1 ELSE 0
                    END
                ),
                0
            ) AS suspicious_gap_count
        FROM gaps
        """,
        [symbol, exchange, interval, gap_threshold_minutes, ignored_large_gap_minutes, ignored_large_gap_minutes],
    ).fetchone()

    return {
        "invalid_price_count": int(invalid_price_count or 0),
        "invalid_ohlc_count": int(invalid_ohlc_count or 0),
        "duplicate_count": int(duplicate_count or 0),
        "max_gap_minutes": int(max_gap_minutes or 0),
        "suspicious_gap_count": int(suspicious_gap_count or 0),
    }


def classify_status(
    *,
    overview_exists: bool,
    invalid_price_count: int,
    invalid_ohlc_count: int,
    duplicate_count: int,
    suspicious_gap_count: int,
    last_bar_age_days: int | None,
    freshness_limit_days: int,
) -> str:
    """把指标转成可读状态。"""
    if not overview_exists:
        return "缺失"
    if invalid_price_count or invalid_ohlc_count or duplicate_count:
        return "异常"
    if last_bar_age_days is not None and last_bar_age_days > freshness_limit_days:
        return "关注"
    if suspicious_gap_count:
        return "关注"
    return "通过"


def main() -> None:
    parser = ArgumentParser(description="检查 DuckDB 中重点品种的 K 线质量。")
    parser.add_argument("--symbols", default=",".join(FOCUS_SYMBOLS))
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--database-file", default="database.duckdb")
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="输出目录，默认写到仓库根目录下的 reports。",
    )
    args = parser.parse_args()

    con, opened_path = open_connection(args.database_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    configs = parse_symbol_list(args.symbols)
    now = datetime.now()
    report_rows: list[dict[str, str | int]] = []

    for config in configs:
        overview = fetch_overview(con, config.symbol, config.exchange.value, args.interval)
        if overview is None:
            row = {
                "symbol": config.symbol,
                "exchange": config.exchange.value,
                "source": config.source,
                "market_group": config.market_group,
                "status": "缺失",
                "count": 0,
                "start": "",
                "end": "",
                "last_bar_age_days": "",
                "invalid_price_count": 0,
                "invalid_ohlc_count": 0,
                "duplicate_count": 0,
                "max_gap_minutes": 0,
                "suspicious_gap_count": 0,
            }
            report_rows.append(row)
            print(f"{config.symbol:<8} 缺失")
            continue

        metrics = fetch_quality_metrics(
            con,
            symbol=config.symbol,
            exchange=config.exchange.value,
            interval=args.interval,
            gap_threshold_minutes=GAP_THRESHOLD_MINUTES[config.market_group],
            ignored_large_gap_minutes=IGNORED_LARGE_GAP_MINUTES[config.market_group],
        )
        start_dt = overview[4]
        end_dt = overview[5]
        age_days = (now - end_dt).days if end_dt else None
        status = classify_status(
            overview_exists=True,
            invalid_price_count=metrics["invalid_price_count"],
            invalid_ohlc_count=metrics["invalid_ohlc_count"],
            duplicate_count=metrics["duplicate_count"],
            suspicious_gap_count=metrics["suspicious_gap_count"],
            last_bar_age_days=age_days,
            freshness_limit_days=FRESHNESS_THRESHOLD_DAYS[config.market_group],
        )

        row = {
            "symbol": config.symbol,
            "exchange": config.exchange.value,
            "source": config.source,
            "market_group": config.market_group,
            "status": status,
            "count": int(overview[3]),
            "start": start_dt.isoformat(sep=" "),
            "end": end_dt.isoformat(sep=" "),
            "last_bar_age_days": age_days if age_days is not None else "",
            "invalid_price_count": metrics["invalid_price_count"],
            "invalid_ohlc_count": metrics["invalid_ohlc_count"],
            "duplicate_count": metrics["duplicate_count"],
            "max_gap_minutes": metrics["max_gap_minutes"],
            "suspicious_gap_count": metrics["suspicious_gap_count"],
        }
        report_rows.append(row)
        print(
            f"{config.symbol:<8} {status:<2} | "
            f"count={row['count']} | end={row['end']} | "
            f"异常价={row['invalid_price_count']} | 异常高低={row['invalid_ohlc_count']} | "
            f"重复={row['duplicate_count']} | 可疑缺口={row['suspicious_gap_count']}"
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"focus_data_quality_{stamp}.json"
    csv_path = output_dir / f"focus_data_quality_{stamp}.csv"

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database_file": args.database_file,
        "opened_path": str(opened_path),
        "interval": args.interval,
        "rows": report_rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(report_rows[0].keys()))
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"JSON 报告已输出：{json_path}")
    print(f"CSV 报告已输出：{csv_path}")


if __name__ == "__main__":
    main()
