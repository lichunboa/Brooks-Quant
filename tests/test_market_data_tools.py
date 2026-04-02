from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from import_generic_csv_to_duckdb import load_csv_bars
from market_data_common import normalize_symbol
from vnpy.trader.constant import Exchange, Interval


class MarketDataToolsTestCase(unittest.TestCase):
    def test_es_alias_is_normalized(self) -> None:
        self.assertEqual(normalize_symbol("ES1!"), "ES")
        self.assertEqual(normalize_symbol("E-mini S&P 500"), "ES")

    def test_generic_csv_loader_builds_bars(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "es.csv"
            csv_path.write_text(
                "datetime,open,high,low,close,volume\n"
                "2026-04-01 13:30:00,5600.25,5601.00,5599.75,5600.50,128\n"
                "2026-04-01 13:31:00,5600.50,5602.00,5600.25,5601.75,256\n",
                encoding="utf-8",
            )

            bars = load_csv_bars(
                csv_path,
                symbol="ES",
                exchange=Exchange.CME,
                interval=Interval.MINUTE,
                gateway_name="CSV_IMPORT",
                datetime_column="datetime",
                open_column="open",
                high_column="high",
                low_column="low",
                close_column="close",
                volume_column="volume",
                turnover_column="turnover",
                datetime_format="%Y-%m-%d %H:%M:%S",
                timezone_name="UTC",
            )

        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].symbol, "ES")
        self.assertEqual(bars[0].exchange, Exchange.CME)
        self.assertEqual(bars[0].interval, Interval.MINUTE)
        self.assertEqual(bars[0].datetime, datetime(2026, 4, 1, 13, 30, tzinfo=timezone.utc))
        self.assertEqual(bars[1].close_price, 5601.75)
        self.assertEqual(bars[1].volume, 256)


if __name__ == "__main__":
    unittest.main()
