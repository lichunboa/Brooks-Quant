"""从 Dukascopy 下载重点 OTC 品种并导入 DuckDB。"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import csv
import subprocess
import tempfile

from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData

from market_data_common import (
    DEFAULT_STAGING_DB_FILE,
    OTC_FOCUS_SYMBOLS,
    SymbolConfig,
    configure_database,
    iso_date,
    month_chunks,
    parse_symbol_list,
    resolve_database_path,
)


INTERVAL_MAP: dict[str, tuple[str, Interval]] = {
    "1m": ("m1", Interval.MINUTE),
    "1h": ("h1", Interval.HOUR),
    "1d": ("d1", Interval.DAILY),
}


def download_csv(
    config: SymbolConfig,
    start_text: str,
    end_text: str,
    timeframe: str,
    output_dir: Path,
    *,
    price_type: str,
    include_volume: bool,
    retries: int,
    batch_size: int,
    batch_pause_ms: int,
) -> Path:
    """调用 dukascopy-node 下载单个分段 CSV。"""
    command = [
        "npx",
        "-y",
        "dukascopy-node",
        "-i",
        config.source_symbol,
        "-from",
        start_text,
        "-to",
        end_text,
        "-t",
        timeframe,
        "-p",
        price_type,
        "-f",
        "csv",
        "-dir",
        str(output_dir),
        "-bs",
        str(batch_size),
        "-bp",
        str(batch_pause_ms),
        "-r",
        str(retries),
        "-re",
    ]

    if include_volume:
        command.extend(["-v", "-vu", "units"])

    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, check=True)

    files = sorted(output_dir.glob("*.csv"))
    if not files:
        raise RuntimeError(f"没有下载到 CSV 文件：{config.symbol} {start_text} -> {end_text}")

    return files[-1]


def load_csv_as_bars(csv_path: Path, config: SymbolConfig, interval: Interval) -> list[BarData]:
    """把 Dukascopy CSV 转成 vn.py 的 BarData。"""
    bars: list[BarData] = []

    with csv_path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            timestamp_ms = int(row["timestamp"])
            dt = datetime.fromtimestamp(timestamp_ms / 1000, timezone.utc)

            bars.append(
                BarData(
                    symbol=config.symbol,
                    exchange=config.exchange,
                    datetime=dt,
                    interval=interval,
                    open_price=float(row["open"]),
                    high_price=float(row["high"]),
                    low_price=float(row["low"]),
                    close_price=float(row["close"]),
                    volume=float(row.get("volume", 0) or 0),
                    gateway_name="DUKASCOPY",
                )
            )

    return bars


def parse_date(text: str) -> date:
    """解析命令行日期。"""
    return datetime.strptime(text, "%Y-%m-%d").date()


def import_symbol(
    config: SymbolConfig,
    *,
    start_date: date,
    end_date: date,
    months_per_chunk: int,
    min_days_per_chunk: int,
    timeframe: str,
    interval: Interval,
    price_type: str,
    include_volume: bool,
    retries: int,
    batch_size: int,
    batch_pause_ms: int,
    db,
    temp_root: Path,
) -> int:
    """按月导入单个 Dukascopy 品种。"""
    total_count = 0

    for chunk_start, chunk_end in month_chunks(start_date, end_date, months_per_chunk):
        total_count += import_span_with_fallback(
            config,
            span_start=chunk_start,
            span_end=chunk_end,
            min_days_per_chunk=min_days_per_chunk,
            timeframe=timeframe,
            interval=interval,
            price_type=price_type,
            include_volume=include_volume,
            retries=retries,
            batch_size=batch_size,
            batch_pause_ms=batch_pause_ms,
            db=db,
            temp_root=temp_root,
        )

    return total_count


def import_span_with_fallback(
    config: SymbolConfig,
    *,
    span_start: date,
    span_end: date,
    min_days_per_chunk: int,
    timeframe: str,
    interval: Interval,
    price_type: str,
    include_volume: bool,
    retries: int,
    batch_size: int,
    batch_pause_ms: int,
    db,
    temp_root: Path,
) -> int:
    """下载失败时自动拆小区间重试。"""
    print(
        f"开始下载 {config.symbol} | {config.description} | "
        f"{iso_date(span_start)} -> {iso_date(span_end)}"
    )

    try:
        csv_path = download_csv(
            config,
            iso_date(span_start),
            iso_date(span_end),
            timeframe,
            temp_root / config.symbol.lower(),
            price_type=price_type,
            include_volume=include_volume,
            retries=retries,
            batch_size=batch_size,
            batch_pause_ms=batch_pause_ms,
        )
    except subprocess.CalledProcessError:
        span_days = (span_end - span_start).days
        if span_days <= min_days_per_chunk:
            print(
                f"下载失败且区间已缩到 {span_days} 天，跳过 {config.symbol} "
                f"{iso_date(span_start)} -> {iso_date(span_end)}"
            )
            return 0

        split_days = max(1, span_days // 2)
        midpoint = span_start + timedelta(days=split_days)
        if midpoint >= span_end:
            midpoint = span_start + timedelta(days=1)

        print(
            f"下载失败，自动拆分 {config.symbol} "
            f"{iso_date(span_start)} -> {iso_date(midpoint)} 和 "
            f"{iso_date(midpoint)} -> {iso_date(span_end)}"
        )
        left_count = import_span_with_fallback(
            config,
            span_start=span_start,
            span_end=midpoint,
            min_days_per_chunk=min_days_per_chunk,
            timeframe=timeframe,
            interval=interval,
            price_type=price_type,
            include_volume=include_volume,
            retries=retries,
            batch_size=batch_size,
            batch_pause_ms=batch_pause_ms,
            db=db,
            temp_root=temp_root,
        )
        right_count = import_span_with_fallback(
            config,
            span_start=midpoint,
            span_end=span_end,
            min_days_per_chunk=min_days_per_chunk,
            timeframe=timeframe,
            interval=interval,
            price_type=price_type,
            include_volume=include_volume,
            retries=retries,
            batch_size=batch_size,
            batch_pause_ms=batch_pause_ms,
            db=db,
            temp_root=temp_root,
        )
        return left_count + right_count

    bars = load_csv_as_bars(csv_path, config, interval)
    print(f"解析完成 {config.symbol}，本段 {len(bars)} 根 K 线")

    if bars:
        db.save_bar_data(bars)
        print(f"已写入 {config.symbol}，本段写入 {len(bars)} 根")
        return len(bars)

    print(f"本段为空 {config.symbol}，通常是周末或停盘时段")
    return 0


def main() -> None:
    parser = ArgumentParser(description="下载 Dukascopy 数据并导入 DuckDB。")
    parser.add_argument("--symbols", default=",".join(OTC_FOCUS_SYMBOLS))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=(date.today() + timedelta(days=1)).strftime("%Y-%m-%d"))
    parser.add_argument("--interval", default="1m", choices=sorted(INTERVAL_MAP))
    parser.add_argument("--months-per-chunk", type=int, default=1, help="每次下载覆盖的月份数，正式回填可适当调大。")
    parser.add_argument("--min-days-per-chunk", type=int, default=1, help="下载失败后自动拆分时允许的最小天数。")
    parser.add_argument("--price-type", default="bid", choices=("bid", "ask"))
    parser.add_argument("--with-volume", action="store_true", help="下载 Dukascopy 自带的成交量列。")
    parser.add_argument("--retries", type=int, default=2, help="单个分段下载重试次数。")
    parser.add_argument("--batch-size", type=int, default=100, help="dukascopy-node 批量下载分片数。")
    parser.add_argument("--batch-pause-ms", type=int, default=50, help="批次之间的暂停毫秒数。")
    parser.add_argument(
        "--database-file",
        default="database.duckdb",
        help=(
            "目标 DuckDB 文件名，位于 .vntrader 下。"
            f"若主界面正在运行，可改用 {DEFAULT_STAGING_DB_FILE}。"
        ),
    )
    args = parser.parse_args()

    start_date = parse_date(args.start)
    end_date = parse_date(args.end)
    if end_date <= start_date:
        raise SystemExit("结束日期必须晚于开始日期，且结束日期采用开区间。")

    configs = parse_symbol_list(args.symbols, source="dukascopy")
    timeframe, interval = INTERVAL_MAP[args.interval]

    try:
        db = configure_database(args.database_file)
    except Exception as exc:  # noqa: BLE001
        db_path = resolve_database_path(args.database_file)
        raise SystemExit(
            "打开数据库失败："
            f"{db_path}\n"
            f"{exc}\n"
            f"如果正式库正在被 vn.py 占用，请改用 --database-file {DEFAULT_STAGING_DB_FILE}"
        ) from exc

    print(f"目标数据库：{resolve_database_path(args.database_file)}")
    print(f"准备导入 {len(configs)} 个 Dukascopy 品种：{', '.join(config.symbol for config in configs)}")

    with tempfile.TemporaryDirectory(prefix="dukascopy_") as temp_dir:
        temp_root = Path(temp_dir)
        total_written = 0
        for config in configs:
            written = import_symbol(
                config,
                start_date=start_date,
                end_date=end_date,
                months_per_chunk=args.months_per_chunk,
                min_days_per_chunk=args.min_days_per_chunk,
                timeframe=timeframe,
                interval=interval,
                price_type=args.price_type,
                include_volume=args.with_volume,
                retries=args.retries,
                batch_size=args.batch_size,
                batch_pause_ms=args.batch_pause_ms,
                db=db,
                temp_root=temp_root,
            )
            total_written += written

    print(f"全部完成，本次累计写入 {total_written} 根 K 线。")


if __name__ == "__main__":
    main()
