"""从 Databento 下载历史数据并导入 DuckDB。"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
import json
import os
import re

import databento as db
import pandas as pd
from databento.common.error import BentoClientError

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

from market_data_common import DEFAULT_STAGING_DB_FILE, configure_database, resolve_database_path


ROOT_DIR: Path = Path(__file__).resolve().parent.parent
DATABENTO_CACHE_DIR: Path = ROOT_DIR / ".vntrader" / "databento"
FREE_CREDIT_USD: float = 125.0
INTERVAL_MAP: dict[str, Interval] = {
    "ohlcv-1m": Interval.MINUTE,
    "ohlcv-1h": Interval.HOUR,
    "ohlcv-1d": Interval.DAILY,
}
LICENSE_END_RE = re.compile(r"Try again with an end time before (?P<end>\S+)\.")


def resolve_api_key(cli_api_key: str) -> str:
    """优先读取命令行参数，其次读取环境变量。"""
    if cli_api_key.strip():
        return cli_api_key.strip()
    env_api_key = os.environ.get("DATABENTO_API_KEY", "").strip()
    if env_api_key:
        return env_api_key
    raise SystemExit("没有找到 Databento API Key。请传入 --api-key，或先设置环境变量 DATABENTO_API_KEY。")


def normalize_ohlcv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """把 Databento 返回的 OHLCV DataFrame 统一成仓库内部列名。"""
    normalized = frame.copy()
    if isinstance(normalized.index, pd.DatetimeIndex):
        index_name = normalized.index.name or "datetime"
        normalized = normalized.reset_index().rename(columns={index_name: "datetime"})
    elif "ts_event" in normalized.columns:
        normalized = normalized.rename(columns={"ts_event": "datetime"})
    elif "datetime" not in normalized.columns:
        first_column = str(normalized.columns[0])
        normalized = normalized.rename(columns={first_column: "datetime"})

    column_map = {
        "open_price": "open",
        "high_price": "high",
        "low_price": "low",
        "close_price": "close",
    }
    normalized = normalized.rename(columns=column_map)

    required = {"datetime", "open", "high", "low", "close", "volume"}
    missing = [column for column in required if column not in normalized.columns]
    if missing:
        raise ValueError(f"Databento OHLCV 数据缺少必要列：{', '.join(missing)}")

    normalized["datetime"] = pd.to_datetime(normalized["datetime"], utc=True)
    normalized["datetime"] = normalized["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    ordered_columns = ["datetime", "open", "high", "low", "close", "volume"]
    return normalized.loc[:, ordered_columns]


def build_bars_from_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    exchange: Exchange,
    interval: Interval,
    gateway_name: str,
) -> list[BarData]:
    """把标准 OHLCV DataFrame 转成 vn.py BarData。"""
    bars: list[BarData] = []
    for row in frame.itertuples(index=False):
        bars.append(
            BarData(
                symbol=symbol,
                exchange=exchange,
                datetime=datetime.fromisoformat(row.datetime + "+00:00"),
                interval=interval,
                volume=float(row.volume),
                turnover=0.0,
                open_price=float(row.open),
                high_price=float(row.high),
                low_price=float(row.low),
                close_price=float(row.close),
                gateway_name=gateway_name,
            )
        )
    return bars


def estimate_request(
    client: db.Historical,
    *,
    dataset: str,
    start: str,
    end: str,
    symbols: str,
    schema: str,
    stype_in: str,
) -> dict[str, float | int]:
    """估算请求成本、体积和记录数。"""
    cost = client.metadata.get_cost(
        dataset=dataset,
        start=start,
        end=end,
        symbols=symbols,
        schema=schema,
        stype_in=stype_in,
    )
    billable_size = client.metadata.get_billable_size(
        dataset=dataset,
        start=start,
        end=end,
        symbols=symbols,
        schema=schema,
        stype_in=stype_in,
    )
    record_count = client.metadata.get_record_count(
        dataset=dataset,
        start=start,
        end=end,
        symbols=symbols,
        schema=schema,
        stype_in=stype_in,
    )
    return {
        "estimated_cost_usd": float(cost),
        "billable_size_bytes": int(billable_size),
        "record_count": int(record_count),
    }


def resolve_schema_available_end(client: db.Historical, dataset: str, schema: str) -> str:
    """读取指定 dataset/schema 当前公开可见的结束时间。"""
    dataset_range = client.metadata.get_dataset_range(dataset)
    schema_range = dataset_range.get("schema", {}).get(schema, {})
    end = schema_range.get("end") or dataset_range.get("end")
    if not end:
        raise SystemExit(f"无法读取 {dataset} / {schema} 的可用结束时间。")
    return str(end)


def parse_license_limited_end(error_text: str) -> str | None:
    """从 Databento 的许可报错中提取建议结束时间。"""
    match = LICENSE_END_RE.search(error_text)
    if not match:
        return None
    return match.group("end")


def safe_estimate_request(
    client: db.Historical,
    *,
    dataset: str,
    start: str,
    end: str | None,
    symbols: str,
    schema: str,
    stype_in: str,
) -> tuple[dict[str, float | int], str]:
    """估算请求成本，并在可恢复的 Databento 边界错误时自动收窄结束时间。"""
    effective_end = end or resolve_schema_available_end(client, dataset, schema)
    try:
        estimate = estimate_request(
            client,
            dataset=dataset,
            start=start,
            end=effective_end,
            symbols=symbols,
            schema=schema,
            stype_in=stype_in,
        )
        return estimate, effective_end
    except BentoClientError as exc:
        message = str(exc)
        limited_end = parse_license_limited_end(message)
        if not limited_end:
            raise
        estimate = estimate_request(
            client,
            dataset=dataset,
            start=start,
            end=limited_end,
            symbols=symbols,
            schema=schema,
            stype_in=stype_in,
        )
        return estimate, limited_end


def write_metadata_json(path: Path, payload: dict) -> None:
    """把本次下载的元信息写到本地。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    """命令行入口。"""
    parser = ArgumentParser(description="从 Databento 下载历史数据并导入 DuckDB。")
    parser.add_argument("--api-key", default="", help="Databento API Key，若不传则读取 DATABENTO_API_KEY。")
    parser.add_argument("--dataset", default="GLBX.MDP3")
    parser.add_argument("--symbols", default="ES.c.0", help="Databento 查询符号，例如 ES.c.0。")
    parser.add_argument("--schema", default="ohlcv-1m", choices=sorted(INTERVAL_MAP))
    parser.add_argument("--stype-in", default="continuous", help="Databento 输入符号类型，例如 continuous、raw_symbol。")
    parser.add_argument("--start", default="2018-01-01T00:00:00Z")
    parser.add_argument("--end", default="", help="结束时间，留空则由 Databento 按 schema 分辨率前向填充。")
    parser.add_argument("--output-symbol", default="ES", help="写入 DuckDB 时使用的内部统一符号。")
    parser.add_argument("--exchange", default="CME")
    parser.add_argument("--gateway-name", default="DATABENTO")
    parser.add_argument("--dbn-dir", default=str(DATABENTO_CACHE_DIR))
    parser.add_argument("--estimate-only", action="store_true", help="只估算成本，不下载。")
    parser.add_argument("--frame-chunk-size", type=int, default=50000, help="DBN 转 DataFrame 时的分块大小。")
    parser.add_argument(
        "--database-file",
        default=DEFAULT_STAGING_DB_FILE,
        help="目标 DuckDB 文件名，默认先写暂存库。",
    )
    args = parser.parse_args()

    api_key = resolve_api_key(args.api_key)
    requested_end = args.end.strip() or None

    try:
        exchange = Exchange(args.exchange.upper())
    except ValueError as exc:
        raise SystemExit(f"不支持的交易所：{args.exchange}") from exc

    client = db.Historical(api_key)
    estimate, effective_end = safe_estimate_request(
        client,
        dataset=args.dataset,
        start=args.start,
        end=requested_end,
        symbols=args.symbols,
        schema=args.schema,
        stype_in=args.stype_in,
    )
    if requested_end and effective_end != requested_end:
        print(f"请求结束时间已自动收窄到许可范围：{effective_end}")
    elif not requested_end:
        print(f"未传 --end，已自动使用当前可用结束时间：{effective_end}")
    print(f"Databento 估算成本：${estimate['estimated_cost_usd']:.6f}")
    print(f"计费体积：{estimate['billable_size_bytes']} 字节")
    print(f"记录数：{estimate['record_count']}")
    if estimate["estimated_cost_usd"] <= FREE_CREDIT_USD:
        print(f"按官方公开口径，这次请求低于新账号的 ${FREE_CREDIT_USD:.2f} 免费历史额度。")
    else:
        print(f"这次请求高于 ${FREE_CREDIT_USD:.2f} 免费历史额度，需要账户里还有剩余额度或付费。")

    metadata_path = Path(args.dbn_dir).expanduser().resolve() / "last_request.json"
    write_metadata_json(
        metadata_path,
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "dataset": args.dataset,
            "symbols": args.symbols,
            "schema": args.schema,
            "stype_in": args.stype_in,
            "start": args.start,
            "requested_end": requested_end,
            "effective_end": effective_end,
            **estimate,
        },
    )
    print(f"请求元信息已写入：{metadata_path}")

    if args.estimate_only:
        return

    dbn_dir = Path(args.dbn_dir).expanduser().resolve()
    dbn_dir.mkdir(parents=True, exist_ok=True)
    suffix = args.symbols.replace(".", "_").replace("/", "_")
    dbn_path = dbn_dir / f"{args.dataset}_{suffix}_{args.schema}.dbn.zst"
    print(f"开始下载 DBN：{dbn_path}")
    store = client.timeseries.get_range(
        dataset=args.dataset,
        start=args.start,
        end=effective_end,
        symbols=args.symbols,
        schema=args.schema,
        stype_in=args.stype_in,
        path=str(dbn_path),
    )
    print("下载完成，开始写入 DuckDB。")

    try:
        database = configure_database(args.database_file)
    except Exception as exc:  # noqa: BLE001
        db_path = resolve_database_path(args.database_file)
        raise SystemExit(
            "打开数据库失败："
            f"{db_path}\n"
            f"{exc}\n"
            f"如果正式库正在被 vn.py 占用，请改用 --database-file {DEFAULT_STAGING_DB_FILE}"
        ) from exc

    total_count = 0
    interval = INTERVAL_MAP[args.schema]
    frames = store.to_df(schema=args.schema, tz="UTC", count=args.frame_chunk_size)
    if isinstance(frames, pd.DataFrame):
        frames = [frames]

    for frame in frames:
        normalized = normalize_ohlcv_frame(frame)
        bars = build_bars_from_frame(
            normalized,
            symbol=args.output_symbol,
            exchange=exchange,
            interval=interval,
            gateway_name=args.gateway_name,
        )
        if not bars:
            continue
        database.save_bar_data(bars)
        total_count += len(bars)
        print(f"已写入 {len(bars)} 根，累计 {total_count} 根，区间 {bars[0].datetime} -> {bars[-1].datetime}")

    print(f"导入完成，总写入 {total_count} 根。")


if __name__ == "__main__":
    main()
