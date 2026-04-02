"""通过 Binance 公共 K 线接口导入重点加密品种到 DuckDB。"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import date, datetime, time as dt_time, timedelta, timezone
from time import sleep
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData

from market_data_common import (
    CRYPTO_FOCUS_SYMBOLS,
    DEFAULT_STAGING_DB_FILE,
    SymbolConfig,
    configure_database,
    parse_symbol_list,
    resolve_database_path,
)


BINANCE_KLINE_URL: str = "https://api.binance.com/api/v3/klines"
INTERVAL_MAP: dict[str, tuple[str, Interval]] = {
    "1m": ("1m", Interval.MINUTE),
    "1h": ("1h", Interval.HOUR),
    "1d": ("1d", Interval.DAILY),
}


def parse_date(text: str) -> date:
    """解析命令行日期。"""
    return datetime.strptime(text, "%Y-%m-%d").date()


def to_utc_ms(target: datetime) -> int:
    """把 UTC 时间转换为毫秒时间戳。"""
    return int(target.timestamp() * 1000)


def request_klines(
    config: SymbolConfig,
    *,
    interval_text: str,
    start_ms: int,
    end_ms: int,
    limit: int = 1000,
) -> list[list]:
    """请求 Binance 公共 K 线。"""
    params = urlencode(
        {
            "symbol": config.source_symbol,
            "interval": interval_text,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": limit,
        }
    )
    request = Request(
        f"{BINANCE_KLINE_URL}?{params}",
        headers={"User-Agent": "quant-vnpy-data-import/1.0"},
    )

    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def rows_to_bars(rows: list[list], config: SymbolConfig, interval: Interval) -> list[BarData]:
    """把 Binance 返回值转为 BarData。"""
    now_ms = to_utc_ms(datetime.now(timezone.utc))
    bars: list[BarData] = []

    for row in rows:
        open_time = int(row[0])
        close_time = int(row[6])

        # 未收盘 K 线不写入数据库。
        if close_time >= now_ms:
            continue

        bars.append(
            BarData(
                symbol=config.symbol,
                exchange=config.exchange,
                datetime=datetime.fromtimestamp(open_time / 1000, timezone.utc),
                interval=interval,
                volume=float(row[5]),
                turnover=float(row[7]),
                open_price=float(row[1]),
                high_price=float(row[2]),
                low_price=float(row[3]),
                close_price=float(row[4]),
                gateway_name="BINANCE_SPOT",
            )
        )

    return bars


def import_symbol(
    config: SymbolConfig,
    *,
    start_dt: datetime,
    end_dt: datetime,
    interval_text: str,
    interval: Interval,
    sleep_seconds: float,
    db,
) -> int:
    """循环导入单个加密品种。"""
    start_ms = to_utc_ms(start_dt)
    end_ms = to_utc_ms(end_dt)
    total_count = 0

    while start_ms < end_ms:
        rows = request_klines(
            config,
            interval_text=interval_text,
            start_ms=start_ms,
            end_ms=end_ms,
        )

        if not rows:
            print(f"{config.symbol} 在 {datetime.fromtimestamp(start_ms / 1000, timezone.utc)} 之后没有更多数据")
            break

        bars = rows_to_bars(rows, config, interval)
        if bars:
            db.save_bar_data(bars)
            total_count += len(bars)
            print(
                f"已写入 {config.symbol} {len(bars)} 根，累计 {total_count} 根，"
                f"区间 {bars[0].datetime} -> {bars[-1].datetime}"
            )
        else:
            print(f"{config.symbol} 本批只有未收盘 K 线，已跳过")

        last_open_ms = int(rows[-1][0])
        next_start_ms = last_open_ms + 1
        if next_start_ms <= start_ms:
            break
        start_ms = next_start_ms
        sleep(sleep_seconds)

    return total_count


def main() -> None:
    parser = ArgumentParser(description="通过 Binance 公共接口导入重点加密品种到 DuckDB。")
    parser.add_argument("--symbols", default=",".join(CRYPTO_FOCUS_SYMBOLS))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=(date.today() + timedelta(days=1)).strftime("%Y-%m-%d"))
    parser.add_argument("--interval", default="1m", choices=sorted(INTERVAL_MAP))
    parser.add_argument("--sleep-seconds", type=float, default=0.15, help="每次请求后的等待时间。")
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

    configs = parse_symbol_list(args.symbols, source="binance_spot")
    interval_text, interval = INTERVAL_MAP[args.interval]

    start_dt = datetime.combine(start_date, dt_time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, dt_time.min, tzinfo=timezone.utc)

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
    print(f"准备导入 {len(configs)} 个 Binance 重点品种：{', '.join(config.symbol for config in configs)}")

    total_written = 0
    for config in configs:
        written = import_symbol(
            config,
            start_dt=start_dt,
            end_dt=end_dt,
            interval_text=interval_text,
            interval=interval,
            sleep_seconds=args.sleep_seconds,
            db=db,
        )
        total_written += written

    print(f"全部完成，本次累计写入 {total_written} 根 K 线。")


if __name__ == "__main__":
    main()
