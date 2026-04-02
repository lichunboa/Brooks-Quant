from pathlib import Path
import unittest

from brooks_chart_app.catalog import KNOWLEDGE_TOPIC_MAP, STRATEGY_BLUEPRINTS


class TestBrooksCatalog(unittest.TestCase):
    def test_course_outline_topics_loaded(self) -> None:
        for key in ("course_01", "course_15A", "course_16A", "course_41A", "course_48K", "course_52B"):
            self.assertIn(key, KNOWLEDGE_TOPIC_MAP)

    def test_chart_mapping_topics_preserved(self) -> None:
        for key in (
            "bg_all",
            "bg_breakout",
            "bg_opening_reversal",
            "bg_midday_reversal",
            "bg_narrow_channel",
            "bg_broad_channel",
            "bg_trending_tr",
            "bg_trading_range",
            "key_all",
            "key_magnets",
            "key_ema20",
            "key_trendline",
            "key_measured_move",
            "key_mm_leg_equal",
            "key_mm_tr_height",
            "key_mm_bo_height",
            "key_mm_measuring_gap",
            "key_mm_negative_measuring_gap",
            "key_mm_measuring_gap_midline",
            "aux_bom_patterns",
            "aux_micro_gap",
            "aux_opening_range",
        ):
            topic = KNOWLEDGE_TOPIC_MAP[key]
            self.assertTrue(topic.implemented)
            self.assertTrue(topic.track.startswith("公用知识体系"))

    def test_course_topics_referenced_by_chart_mapping_mark_partially_implemented(self) -> None:
        self.assertEqual(KNOWLEDGE_TOPIC_MAP["course_20A"].status, "已接入图表（部分）")
        self.assertEqual(KNOWLEDGE_TOPIC_MAP["course_20B"].status, "已接入图表（部分）")
        self.assertEqual(KNOWLEDGE_TOPIC_MAP["course_11B"].status, "已接入图表（部分）")
        self.assertEqual(KNOWLEDGE_TOPIC_MAP["course_48A"].status, "已接入图表（部分）")

    def test_supplement_topics_include_public_theme_groups(self) -> None:
        for key in (
            "supp_signal_entries",
            "supp_ema_gap_measured_move",
            "supp_double_top_bottom",
            "supp_wedge_exhaustion",
            "supp_channel_spike",
        ):
            topic = KNOWLEDGE_TOPIC_MAP[key]
            self.assertEqual(topic.module, "百科/Ali 实战补充")
            self.assertFalse(topic.implemented)
            self.assertTrue(topic.source_refs)

    def test_supplement_source_refs_exist(self) -> None:
        for topic in KNOWLEDGE_TOPIC_MAP.values():
            if topic.module != "百科/Ali 实战补充":
                continue
            for ref in topic.source_refs:
                self.assertTrue(Path(ref).exists(), ref)

    def test_strategy_blueprints_only_reference_existing_topics(self) -> None:
        for blueprint in STRATEGY_BLUEPRINTS:
            self.assertGreaterEqual(len(blueprint.steps), 14)
            for step in blueprint.steps:
                self.assertTrue(step.name)
                for topic_key in step.topic_keys:
                    self.assertIn(topic_key, KNOWLEDGE_TOPIC_MAP)

    def test_strategy_blueprints_include_taifei_mapped_setups(self) -> None:
        names = {blueprint.name for blueprint in STRATEGY_BLUEPRINTS}
        expected = {
            "收线试驾 / BUYNOW",
            "逆 1 失败、顺 1 成功",
            "旗形回调（双重顶底 / 楔形作持续）",
            "双重顶 / 双重底",
            "楔形顶 / 楔形底",
            "看衰突破（Fade Breakout in TR）",
            "急赴磁体（Magnet Rush）",
            "区间突破回调",
            "极速与通道反转（Spike & Channel）",
            "末端旗形（Final Flag）",
            "20 均线缺口",
            "第一均线缺口",
        }
        self.assertTrue(expected.issubset(names))


if __name__ == "__main__":
    unittest.main()
