from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from import_databento_to_duckdb import normalize_ohlcv_frame, parse_license_limited_end
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
                output_timezone_name="UTC",
            )

        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].symbol, "ES")
        self.assertEqual(bars[0].exchange, Exchange.CME)
        self.assertEqual(bars[0].interval, Interval.MINUTE)
        self.assertEqual(bars[0].datetime, datetime(2026, 4, 1, 13, 30, tzinfo=timezone.utc))
        self.assertEqual(bars[1].close_price, 5601.75)
        self.assertEqual(bars[1].volume, 256)

    def test_normalize_databento_ohlcv_frame(self) -> None:
        frame = pd.DataFrame(
            {
                "open": [5600.25, 5600.50],
                "high": [5601.00, 5602.00],
                "low": [5599.75, 5600.25],
                "close": [5600.50, 5601.75],
                "volume": [128, 256],
            },
            index=pd.to_datetime(["2026-04-01T13:30:00Z", "2026-04-01T13:31:00Z"], utc=True),
        )
        frame.index.name = "ts_event"

        normalized = normalize_ohlcv_frame(frame)

        self.assertEqual(
            list(normalized.columns),
            ["datetime", "open", "high", "low", "close", "volume"],
        )
        self.assertEqual(normalized.iloc[0]["datetime"], "2026-04-01 13:30:00")
        self.assertEqual(float(normalized.iloc[1]["close"]), 5601.75)

    def test_parse_databento_license_limited_end(self) -> None:
        message = (
            "422 dataset_unavailable_range "
            "Part or all of your request for dataset 'GLBX.MDP3' requires a subscription "
            "and/or license to access. Try again with an end time before "
            "2026-04-02T08:36:14.380325000Z."
        )
        self.assertEqual(
            parse_license_limited_end(message),
            "2026-04-02T08:36:14.380325000Z",
        )


if __name__ == "__main__":
    unittest.main()
