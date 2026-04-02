"""
修正 vnpy_mt5 在 zoneinfo 环境下的时区兼容问题。
"""

from __future__ import annotations

from datetime import datetime


def patch_mt5_timezone_compat() -> None:
    """补丁化 MT5 网关里依赖 pytz 的时间转换。"""
    try:
        import vnpy_mt5.mt5_gateway as mt5_gateway
    except Exception:
        return

    def generate_china_datetime(timestamp: int) -> datetime:
        dt = datetime.strptime(str(timestamp), "%Y.%m.%d %H:%M")
        utc_dt = dt.replace(tzinfo=mt5_gateway.UTC_TZ)
        return utc_dt.astimezone(mt5_gateway.CHINA_TZ)

    def generate_utc_datetime(dt: datetime) -> str:
        utc_dt = dt.astimezone(mt5_gateway.UTC_TZ).replace(tzinfo=None)
        return utc_dt.isoformat().replace("T", " ")

    mt5_gateway.generate_china_datetime = generate_china_datetime
    mt5_gateway.generate_utc_datetime = generate_utc_datetime
