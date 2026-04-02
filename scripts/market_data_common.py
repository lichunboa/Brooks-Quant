"""重点品种数据源配置和数据库辅助。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import vnpy.trader.database as database_module

from vnpy.trader.constant import Exchange
from vnpy.trader.setting import SETTINGS


DEFAULT_STAGING_DB_FILE: str = "database_import_staging.duckdb"


@dataclass(frozen=True)
class SymbolConfig:
    """单个重点品种的数据源配置。"""

    symbol: str
    aliases: tuple[str, ...]
    source: str
    source_symbol: str
    exchange: Exchange
    market_group: str
    description: str


SYMBOL_CONFIGS: tuple[SymbolConfig, ...] = (
    SymbolConfig(
        symbol="BTCUSDT",
        aliases=("BTCUSDT", "BTC/USDT", "BTC USDT"),
        source="binance_spot",
        source_symbol="BTCUSDT",
        exchange=Exchange.GLOBAL,
        market_group="crypto_24x7",
        description="比特币现货",
    ),
    SymbolConfig(
        symbol="ETHUSDT",
        aliases=("ETHUSDT", "ETH/USDT", "ETH USDT"),
        source="binance_spot",
        source_symbol="ETHUSDT",
        exchange=Exchange.GLOBAL,
        market_group="crypto_24x7",
        description="以太坊现货",
    ),
    SymbolConfig(
        symbol="BNBUSDT",
        aliases=("BNBUSDT", "BNB/USDT", "BNB USDT"),
        source="binance_spot",
        source_symbol="BNBUSDT",
        exchange=Exchange.GLOBAL,
        market_group="crypto_24x7",
        description="BNB 现货",
    ),
    SymbolConfig(
        symbol="SOLUSDT",
        aliases=("SOLUSDT", "SOL/USDT", "SOL USDT"),
        source="binance_spot",
        source_symbol="SOLUSDT",
        exchange=Exchange.GLOBAL,
        market_group="crypto_24x7",
        description="SOL 现货",
    ),
    SymbolConfig(
        symbol="XRPUSDT",
        aliases=("XRPUSDT", "XRP/USDT", "XRP USDT"),
        source="binance_spot",
        source_symbol="XRPUSDT",
        exchange=Exchange.GLOBAL,
        market_group="crypto_24x7",
        description="XRP 现货",
    ),
    SymbolConfig(
        symbol="ADAUSDT",
        aliases=("ADAUSDT", "ADA/USDT", "ADA USDT"),
        source="binance_spot",
        source_symbol="ADAUSDT",
        exchange=Exchange.GLOBAL,
        market_group="crypto_24x7",
        description="ADA 现货",
    ),
    SymbolConfig(
        symbol="EURUSD",
        aliases=("EURUSD", "EUR/USD"),
        source="dukascopy",
        source_symbol="eurusd",
        exchange=Exchange.OTC,
        market_group="forex_otc",
        description="欧元兑美元",
    ),
    SymbolConfig(
        symbol="GBPUSD",
        aliases=("GBPUSD", "GBP/USD"),
        source="dukascopy",
        source_symbol="gbpusd",
        exchange=Exchange.OTC,
        market_group="forex_otc",
        description="英镑兑美元",
    ),
    SymbolConfig(
        symbol="USDJPY",
        aliases=("USDJPY", "USD/JPY"),
        source="dukascopy",
        source_symbol="usdjpy",
        exchange=Exchange.OTC,
        market_group="forex_otc",
        description="美元兑日元",
    ),
    SymbolConfig(
        symbol="AUDUSD",
        aliases=("AUDUSD", "AUD/USD"),
        source="dukascopy",
        source_symbol="audusd",
        exchange=Exchange.OTC,
        market_group="forex_otc",
        description="澳元兑美元",
    ),
    SymbolConfig(
        symbol="USDCHF",
        aliases=("USDCHF", "USD/CHF"),
        source="dukascopy",
        source_symbol="usdchf",
        exchange=Exchange.OTC,
        market_group="forex_otc",
        description="美元兑瑞郎",
    ),
    SymbolConfig(
        symbol="USDCAD",
        aliases=("USDCAD", "USD/CAD"),
        source="dukascopy",
        source_symbol="usdcad",
        exchange=Exchange.OTC,
        market_group="forex_otc",
        description="美元兑加元",
    ),
    SymbolConfig(
        symbol="XAUUSD",
        aliases=("XAUUSD", "XAU/USD", "GOLD"),
        source="dukascopy",
        source_symbol="xauusd",
        exchange=Exchange.OTC,
        market_group="metals_otc",
        description="现货黄金",
    ),
    SymbolConfig(
        symbol="XAGUSD",
        aliases=("XAGUSD", "XAG/USD", "SILVER"),
        source="dukascopy",
        source_symbol="xagusd",
        exchange=Exchange.OTC,
        market_group="metals_otc",
        description="现货白银",
    ),
    SymbolConfig(
        symbol="US500",
        aliases=("US500", "US 500", "USA500", "SPX500"),
        source="dukascopy",
        source_symbol="usa500idxusd",
        exchange=Exchange.OTC,
        market_group="index_cfd",
        description="美国 500 指数 CFD",
    ),
    SymbolConfig(
        symbol="NAS100",
        aliases=("NAS100", "US TECH 100", "US TECH100", "USA100", "USTECH100"),
        source="dukascopy",
        source_symbol="usatechidxusd",
        exchange=Exchange.OTC,
        market_group="index_cfd",
        description="美国科技 100 指数 CFD",
    ),
    SymbolConfig(
        symbol="GER40",
        aliases=("GER40", "DE40", "GER 40"),
        source="dukascopy",
        source_symbol="deuidxeur",
        exchange=Exchange.OTC,
        market_group="index_cfd",
        description="德国 40 指数 CFD",
    ),
)


SYMBOL_CONFIG_MAP: dict[str, SymbolConfig] = {config.symbol: config for config in SYMBOL_CONFIGS}
FOCUS_SYMBOLS: tuple[str, ...] = tuple(
    symbol
    for symbol in (
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "AUDUSD",
        "USDCHF",
        "USDCAD",
        "XAUUSD",
        "XAGUSD",
        "US500",
        "NAS100",
    )
)
OTC_FOCUS_SYMBOLS: tuple[str, ...] = tuple(
    symbol for symbol in FOCUS_SYMBOLS if SYMBOL_CONFIG_MAP[symbol].source == "dukascopy"
)
CRYPTO_FOCUS_SYMBOLS: tuple[str, ...] = tuple(
    symbol for symbol in FOCUS_SYMBOLS if SYMBOL_CONFIG_MAP[symbol].source == "binance_spot"
)


def _normalize_key(value: str) -> str:
    """把用户输入归一化成稳定键。"""
    compact = value.strip().upper().replace("-", " ").replace("_", " ")
    compact = " ".join(compact.split())
    return compact.replace("/", "")


ALIAS_TO_SYMBOL: dict[str, str] = {}
for config in SYMBOL_CONFIGS:
    for alias in (config.symbol, *config.aliases):
        ALIAS_TO_SYMBOL[_normalize_key(alias)] = config.symbol


def normalize_symbol(raw_symbol: str) -> str:
    """把别名转换为仓库内部统一符号。"""
    key = _normalize_key(raw_symbol)
    symbol = ALIAS_TO_SYMBOL.get(key)
    if symbol:
        return symbol
    raise KeyError(f"未配置的重点品种：{raw_symbol}")


def parse_symbol_list(symbols_text: str, *, source: str | None = None) -> list[SymbolConfig]:
    """解析命令行里的品种列表。"""
    normalized = symbols_text.strip().lower()
    if normalized in {"all", "focus"}:
        symbols = list(FOCUS_SYMBOLS)
    elif normalized in {"all_otc", "focus_otc", "otc"}:
        symbols = list(OTC_FOCUS_SYMBOLS)
    elif normalized in {"all_crypto", "focus_crypto", "crypto"}:
        symbols = list(CRYPTO_FOCUS_SYMBOLS)
    else:
        symbols = [normalize_symbol(item) for item in symbols_text.split(",") if item.strip()]

    configs = [SYMBOL_CONFIG_MAP[symbol] for symbol in symbols]
    if source:
        configs = [config for config in configs if config.source == source]
    return configs


def configure_database(database_file: str):
    """根据给定文件名创建 DuckDB 适配器。"""
    SETTINGS["database.name"] = "duckdb"
    SETTINGS["database.database"] = database_file
    database_module.database = None
    return database_module.get_database()


def resolve_database_path(database_file: str) -> Path:
    """把数据库文件名映射到 .vntrader 目录下的真实路径。"""
    return Path.cwd().joinpath(".vntrader", database_file)


def month_chunks(start: date, end_exclusive: date, months_per_chunk: int = 1) -> Iterable[tuple[date, date]]:
    """按月份块切分日期区间，结束日期采用开区间。"""
    if months_per_chunk < 1:
        raise ValueError("months_per_chunk 必须大于等于 1")

    current = start
    while current < end_exclusive:
        next_year = current.year
        next_month = current.month
        for _ in range(months_per_chunk):
            if next_month == 12:
                next_year += 1
                next_month = 1
            else:
                next_month += 1
        chunk_end = date(next_year, next_month, 1)
        yield current, min(chunk_end, end_exclusive)
        current = chunk_end


def iso_date(value: date | datetime) -> str:
    """输出 Dukascopy 和脚本统一使用的日期文本。"""
    return value.strftime("%Y-%m-%d")
