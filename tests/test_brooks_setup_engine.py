import unittest

from brooks_chart_app.logic import analyze_brooks_context, build_brooks_annotations
from brooks_chart_app.setup_engine import build_setup_candidates, confirm_setup_candidates
from tests.test_brooks_chart_logic import (
    build_bull_trending_trading_range,
    build_normal_cycle_to_broad_channel,
)


class TestBrooksSetupEngine(unittest.TestCase):
    def test_confirmed_setup_signals_match_chart_output(self) -> None:
        for bars in (build_normal_cycle_to_broad_channel(), build_bull_trending_trading_range()):
            analysis = analyze_brooks_context(bars)
            candidates = build_setup_candidates(bars, analysis, 0.01)
            confirmed = confirm_setup_candidates(bars, candidates)
            _ema, chart_signals, _bg, _spn, _sp, _epn, _ep = build_brooks_annotations(bars, 0.01)

            left = [
                (item.kind, item.signal_index, item.trigger_index, item.entry_price, item.stop_price, item.target_price)
                for item in confirmed
            ]
            right = [
                (item.kind, item.signal_index, item.trigger_index, item.entry_price, item.stop_price, item.target_price)
                for item in chart_signals
            ]
            self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
