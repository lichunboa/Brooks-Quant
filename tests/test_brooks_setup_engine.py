import unittest

from brooks_chart_app.logic import analyze_brooks_context, build_brooks_annotations
from brooks_chart_app.setup_engine import build_setup_candidates, confirm_setup_candidates
from tests.test_brooks_chart_logic import (
    build_breakout_then_test,
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

    def test_build_setup_candidates_marks_breakout_pullback_continuation(self) -> None:
        bars = build_breakout_then_test()
        analysis = analyze_brooks_context(bars)
        candidates = build_setup_candidates(bars, analysis, 0.01)

        pullback_kinds = [(item.kind, item.signal_index, item.reason) for item in candidates]
        self.assertIn(("H1", 24, "窄幅通道 + 突破后小回调延续 + 第1次尝试"), pullback_kinds)


if __name__ == "__main__":
    unittest.main()
