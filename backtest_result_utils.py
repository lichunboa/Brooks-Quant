"""回测结果导出与生命周期整理公共工具。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import csv
import json
import re


def write_json(path: Path, payload: dict) -> None:
    """写 JSON。"""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def sort_engine_trades(engine) -> list[tuple[str, object]]:
    """按成交时间而不是字符串编号排序。"""
    return sorted(
        engine.trades.items(),
        key=lambda item: (
            item[1].datetime or datetime.min,
            item[0],
        ),
    )


def write_trades_csv(path: Path, engine) -> None:
    """导出成交记录。"""
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["vt_tradeid", "datetime", "direction", "offset", "price", "volume"])
        for vt_tradeid, trade in sort_engine_trades(engine):
            writer.writerow([
                vt_tradeid,
                trade.datetime.isoformat(sep=" ") if trade.datetime else "",
                trade.direction.value if trade.direction else "",
                trade.offset.value if trade.offset else "",
                trade.price,
                trade.volume,
            ])


def build_lifecycle_rows(engine) -> list[list]:
    """把成交记录整理成生命周期。"""
    rows: list[list] = []

    current_direction: str = ""
    current_volume: float = 0.0
    entry_time: str = ""
    entry_price_sum: float = 0.0
    entry_volume_sum: float = 0.0
    lifecycle_id: int = 0

    for _, trade in sort_engine_trades(engine):
        direction = trade.direction.value if trade.direction else ""
        offset = trade.offset.value if trade.offset else ""

        is_open = offset in {"开", "OPEN"}
        is_close = offset in {"平", "CLOSE"}

        if is_open and current_volume == 0:
            current_direction = direction
            current_volume = float(trade.volume)
            entry_time = trade.datetime.isoformat(sep=" ") if trade.datetime else ""
            entry_price_sum = float(trade.price) * float(trade.volume)
            entry_volume_sum = float(trade.volume)
            continue

        if is_open and current_volume > 0:
            current_volume += float(trade.volume)
            entry_price_sum += float(trade.price) * float(trade.volume)
            entry_volume_sum += float(trade.volume)
            continue

        if is_close and current_volume > 0:
            exit_time = trade.datetime.isoformat(sep=" ") if trade.datetime else ""
            exit_price = float(trade.price)
            exit_volume = min(float(trade.volume), current_volume)
            avg_entry_price = entry_price_sum / entry_volume_sum if entry_volume_sum else 0.0

            if current_direction in {"多", "LONG"}:
                pnl_points = (exit_price - avg_entry_price) * exit_volume
            else:
                pnl_points = (avg_entry_price - exit_price) * exit_volume

            lifecycle_id += 1
            rows.append([lifecycle_id, current_direction, entry_time, avg_entry_price, exit_time, exit_price, exit_volume, pnl_points])

            current_volume -= exit_volume
            entry_price_sum -= avg_entry_price * exit_volume
            entry_volume_sum -= exit_volume
            if current_volume <= 1e-12 or entry_volume_sum <= 1e-12:
                current_direction = ""
                current_volume = 0.0
                entry_time = ""
                entry_price_sum = 0.0
                entry_volume_sum = 0.0

    return rows


def write_lifecycles_csv(path: Path, engine) -> None:
    """导出生命周期。"""
    rows = build_lifecycle_rows(engine)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["lifecycle_id", "direction", "entry_time", "entry_price", "exit_time", "exit_price", "volume", "pnl_points"])
        writer.writerows(rows)


def make_jsonable(data: dict) -> dict:
    """把 numpy 标量转为原生类型。"""
    converted: dict = {}
    for key, value in data.items():
        if hasattr(value, "item"):
            converted[key] = value.item()
        else:
            converted[key] = value
    return converted


def normalize_stats_payload(data: dict) -> dict:
    """把 CTA 回测输出中的格式化字符串转回可计算数值。"""
    converted = make_jsonable(data)
    normalized: dict = {}

    for key, value in converted.items():
        if isinstance(value, str):
            text = value.strip()
            if not text:
                normalized[key] = value
                continue

            cleaned = text.replace(",", "").replace("%", "")
            match = re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned)
            if match:
                number = float(cleaned)
                normalized[key] = number if "." in cleaned else int(number)
                continue

        normalized[key] = value

    return normalized

