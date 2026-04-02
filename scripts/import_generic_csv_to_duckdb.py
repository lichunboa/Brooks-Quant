"""把外部 CSV K 线导入 DuckDB，优先用于 ES 等期货数据。"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import csv
from typing import Iterator

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

from market_data_common import DEFAULT_STAGING_DB_FILE, configure_database, resolve_database_path


INTERVAL_MAP: dict[str, Interval] = {
    "1m": Interval.MINUTE,
    "1h": Interval.HOUR,
    "1d": Interval.DAILY,
}


def parse_datetime(raw_text: str, *, fmt: str, timezone_name: str) -> datetime:
    """解析 CSV 时间列。"""
    text = raw_text.strip()
    if not text:
        raise ValueError("时间列为空")

    if fmt:
        dt = datetime.strptime(text, fmt)
    else:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(timezone_name))
    return dt


def normalize_datetime_timezone(dt: datetime, output_timezone_name: str) -> datetime:
    """统一把时间转换到输出时区，默认建议写入 UTC。"""
    return dt.astimezone(ZoneInfo(output_timezone_name))


def parse_float(raw_text: str, *, default: float = 0.0) -> float:
    """把 CSV 文本转成浮点数。"""
    text = raw_text.strip()
    if not text:
        return default
    return float(text.replace(",", ""))


def iter_csv_bars(
    csv_path: Path,
    *,
    symbol: str,
    exchange: Exchange,
    interval: Interval,
    gateway_name: str,
    datetime_column: str,
    open_column: str,
    high_column: str,
    low_column: str,
    close_column: str,
    volume_column: str,
    turnover_column: str,
    datetime_format: str,
    timezone_name: str,
    output_timezone_name: str,
) -> Iterator[BarData]:
    """流式读取 CSV 并转成 vn.py 的 BarData。"""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required_columns = {datetime_column, open_column, high_column, low_column, close_column}
        if not reader.fieldnames:
            raise ValueError("CSV 没有表头。")
        missing_columns = [column for column in required_columns if column not in reader.fieldnames]
        if missing_columns:
            raise ValueError(f"CSV 缺少必要列：{', '.join(missing_columns)}")

        for row in reader:
            dt = parse_datetime(
                row[datetime_column],
                fmt=datetime_format,
                timezone_name=timezone_name,
            )
            yield BarData(
                symbol=symbol,
                exchange=exchange,
                datetime=normalize_datetime_timezone(dt, output_timezone_name),
                interval=interval,
                volume=parse_float(row.get(volume_column, "")),
                turnover=parse_float(row.get(turnover_column, "")),
                open_price=parse_float(row[open_column]),
                high_price=parse_float(row[high_column]),
                low_price=parse_float(row[low_column]),
                close_price=parse_float(row[close_column]),
                gateway_name=gateway_name,
            )


def load_csv_bars(
    csv_path: Path,
    *,
    symbol: str,
    exchange: Exchange,
    interval: Interval,
    gateway_name: str,
    datetime_column: str,
    open_column: str,
    high_column: str,
    low_column: str,
    close_column: str,
    volume_column: str,
    turnover_column: str,
    datetime_format: str,
    timezone_name: str,
    output_timezone_name: str,
) -> list[BarData]:
    """读取 CSV 并转成 vn.py 的 BarData。"""
    return list(
        iter_csv_bars(
            csv_path,
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            gateway_name=gateway_name,
            datetime_column=datetime_column,
            open_column=open_column,
            high_column=high_column,
            low_column=low_column,
            close_column=close_column,
            volume_column=volume_column,
            turnover_column=turnover_column,
            datetime_format=datetime_format,
            timezone_name=timezone_name,
            output_timezone_name=output_timezone_name,
        )
    )


def save_in_batches(db, bars: Iterator[BarData], batch_size: int) -> int:
    """分批写入，避免一次性内存过大。"""
    batch: list[BarData] = []
    total_count = 0
    first_dt: datetime | None = None
    last_dt: datetime | None = None
    for bar in bars:
        batch.append(bar)
        if first_dt is None:
            first_dt = bar.datetime
        last_dt = bar.datetime
        if len(batch) < batch_size:
            continue
        db.save_bar_data(batch)
        total_count += len(batch)
        print(f"已写入 {len(batch)} 根，累计 {total_count} 根，区间 {batch[0].datetime} -> {batch[-1].datetime}")
        batch = []

    if batch:
        db.save_bar_data(batch)
        total_count += len(batch)
        print(f"已写入 {len(batch)} 根，累计 {total_count} 根，区间 {batch[0].datetime} -> {batch[-1].datetime}")

    if total_count == 0 or first_dt is None or last_dt is None:
        raise SystemExit("CSV 中没有可导入的 K 线。")
    return total_count


def main() -> None:
    """命令行入口。"""
    parser = ArgumentParser(description="把外部 CSV K 线导入 DuckDB。")
    parser.add_argument("--csv", required=True, help="待导入 CSV 的绝对路径。")
    parser.add_argument("--symbol", required=True, help="仓库内部统一符号，例如 ES。")
    parser.add_argument("--exchange", default="CME", help="交易所，例如 CME、OTC、GLOBAL。")
    parser.add_argument("--interval", default="1m", choices=sorted(INTERVAL_MAP))
    parser.add_argument("--datetime-column", default="datetime")
    parser.add_argument("--open-column", default="open")
    parser.add_argument("--high-column", default="high")
    parser.add_argument("--low-column", default="low")
    parser.add_argument("--close-column", default="close")
    parser.add_argument("--volume-column", default="volume")
    parser.add_argument("--turnover-column", default="turnover")
    parser.add_argument(
        "--datetime-format",
        default="",
        help="若不是 ISO 时间，可传入 strptime 格式，例如 %%Y-%%m-%%d %%H:%%M:%%S。",
    )
    parser.add_argument(
        "--timezone",
        default="UTC",
        help="当 CSV 时间列不带时区时，按这个时区解释，例如 UTC 或 America/New_York。",
    )
    parser.add_argument(
        "--output-timezone",
        default="UTC",
        help="写入数据库前统一转换到这个时区，默认 UTC。",
    )
    parser.add_argument("--gateway-name", default="CSV_IMPORT")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument(
        "--database-file",
        default="database.duckdb",
        help=(
            "目标 DuckDB 文件名，位于 .vntrader 下。"
            f"若主界面正在运行，可改用 {DEFAULT_STAGING_DB_FILE}。"
        ),
    )
    args = parser.parse_args()

    csv_path = Path(args.csv).expanduser().resolve()
    if not csv_path.exists():
        raise SystemExit(f"CSV 文件不存在：{csv_path}")

    try:
        exchange = Exchange(args.exchange.upper())
    except ValueError as exc:
        raise SystemExit(f"不支持的交易所：{args.exchange}") from exc

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

    bars = iter_csv_bars(
        csv_path,
        symbol=args.symbol,
        exchange=exchange,
        interval=INTERVAL_MAP[args.interval],
        gateway_name=args.gateway_name,
        datetime_column=args.datetime_column,
        open_column=args.open_column,
        high_column=args.high_column,
        low_column=args.low_column,
        close_column=args.close_column,
        volume_column=args.volume_column,
        turnover_column=args.turnover_column,
        datetime_format=args.datetime_format,
        timezone_name=args.timezone,
        output_timezone_name=args.output_timezone,
    )

    print(f"目标数据库：{resolve_database_path(args.database_file)}")
    print(f"CSV 路径：{csv_path}")
    print(
        f"准备导入：{args.symbol}.{exchange.value} {args.interval}，"
        f"源时区 {args.timezone} -> 写入时区 {args.output_timezone}"
    )
    total_count = save_in_batches(db, bars, args.batch_size)
    print(f"总写入根数：{total_count}")
    print("导入完成。")


if __name__ == "__main__":
    main()
