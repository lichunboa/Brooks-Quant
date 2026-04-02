"""Brooks 公用知识体系与策略开发目录。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


REPO_DIR: Path = Path(__file__).resolve().parent.parent
KNOWLEDGE_ROOT: Path = REPO_DIR / "策略资料" / "al brooks参考资料agent专用版 "
FOUNDATION_INDEX_PATH: Path = KNOWLEDGE_ROOT / "1.《价格行为学》（基础篇1-36章）" / "章节索引.md"
ADVANCED_INDEX_PATH: Path = KNOWLEDGE_ROOT / "2.《价格行为学》（进阶篇37-52章）" / "章节索引.md"
PRACTICAL_INDEX_PATH: Path = KNOWLEDGE_ROOT / "实战主题总索引.md"
ALI_INDEX_PATH: Path = KNOWLEDGE_ROOT / "Ali Flash Cards - 完美裁切A3宽(4K屏推荐)" / "主题索引.md"
BEST10_INDEX_PATH: Path = KNOWLEDGE_ROOT / "阿布10种最佳价格行为交易模式" / "主题索引.md"
OUTLINE_PATH: Path = KNOWLEDGE_ROOT / "AL brooks原课程大纲.md"

STATUS_IMPLEMENTED: str = "已接入图表"
STATUS_IMPLEMENTED_PARTIAL: str = "已接入图表（部分）"
STATUS_CATALOGED: str = "已整理待接入"
STATUS_PLANNED: str = "待整理"
STRATEGY_STATUS_CODED: str = "已接入代码"
STRATEGY_STATUS_DESIGNED: str = "已建立蓝图"
STRATEGY_STATUS_PLANNED: str = "待开发"
STEP_STATUS_CODED: str = "已接入代码"
STEP_STATUS_DESIGNED: str = "已建立蓝图"
STEP_STATUS_PLANNED: str = "待补充"


@dataclass(frozen=True)
class KnowledgeTopic:
    """单个 Brooks 知识点。"""

    key: str
    track: str
    module: str
    lesson_code: str
    name: str
    status: str
    implemented: bool = False
    overlay_group: str = ""
    filter_kinds: tuple[str, ...] = ()
    description: str = ""
    course_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    implementation_notes: str = ""


@dataclass(frozen=True)
class StrategyBlueprint:
    """单个策略开发蓝图。"""

    key: str
    family: str
    name: str
    status: str
    summary: str
    steps: tuple["StrategyTemplateStep", ...]
    tuning_notes: str = ""
    code_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategyTemplateStep:
    """策略开发流程模板中的单个环节。"""

    key: str
    name: str
    status: str
    summary: str
    topic_keys: tuple[str, ...] = ()
    notes: str = ""


SECTION_RE = re.compile(r"^- \*\*(?P<title>[^*]+)\*\* \| 入口：\[第 (?P<page>\d{4}) 页\]\((?P<entry>[^)]+)\)")
LESSON_RE = re.compile(r"^(?P<code>\d{2}[A-Z]?)\s+(?P<name>.+)$")

FLOW_STEP_DEFS: tuple[tuple[str, str], ...] = (
    ("background", "背景"),
    ("key_levels", "关键位置"),
    ("setup_context", "setup 前提"),
    ("signal_bar", "signal bar 类型"),
    ("entry_trigger", "entry trigger"),
    ("trigger_invalidation", "触发失效"),
    ("initial_stop", "初始止损类型"),
    ("actual_risk", "实际风险"),
    ("position_leverage", "仓位与杠杆"),
    ("first_target", "第一目标"),
    ("management", "partial / scalp / swing"),
    ("breakeven", "BE 条件"),
    ("early_exit", "提前离场"),
    ("reentry_addon", "re-entry / add-on"),
)
FLOW_STEP_NAME_MAP: dict[str, str] = {key: name for key, name in FLOW_STEP_DEFS}


def _knowledge_ref(*parts: str) -> str:
    """生成策略资料内的绝对路径引用。"""
    return str((KNOWLEDGE_ROOT.joinpath(*parts)).resolve())


def _parse_course_index(index_path: Path, volume_name: str) -> list[KnowledgeTopic]:
    """从章节索引解析课程知识点。"""
    if not index_path.exists():
        return []

    topics: list[KnowledgeTopic] = []
    module_name: str = ""
    current_title: str = ""
    current_entry: str = ""
    current_page: str = ""
    current_description_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_title, current_entry, current_page, current_description_lines
        if not current_title:
            return

        lesson_match = LESSON_RE.match(current_title)
        if lesson_match:
            lesson_code = lesson_match.group("code")
            lesson_name = lesson_match.group("name")
        else:
            lesson_code = current_title
            lesson_name = current_title

        description = "；".join(current_description_lines) if current_description_lines else f"{lesson_name}。"
        entry_path = (index_path.parent / current_entry).resolve() if current_entry else index_path.resolve()
        topics.append(
            KnowledgeTopic(
                key=f"course_{lesson_code}",
                track="公用知识体系",
                module=module_name or volume_name,
                lesson_code=lesson_code,
                name=lesson_name,
                status=STATUS_CATALOGED,
                implemented=False,
                description=description,
                course_refs=(lesson_code,),
                source_refs=(
                    str(index_path.resolve()),
                    str(entry_path),
                ),
            )
        )

        current_title = ""
        current_entry = ""
        current_page = ""
        current_description_lines = []

    for raw_line in index_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            flush_current()
            module_name = line[3:].strip()
            continue

        match = SECTION_RE.match(line)
        if match:
            flush_current()
            current_title = match.group("title").strip()
            current_page = match.group("page")
            current_entry = match.group("entry").strip()
            continue

        if current_title and line.strip().startswith("说明："):
            current_description_lines.append(line.strip())
            continue

        if current_title and line.strip().startswith("要点："):
            current_description_lines.append(line.strip())

    flush_current()
    return topics


def _build_chart_mapping_topics() -> list[KnowledgeTopic]:
    """当前图表已接入的公用概念映射。"""
    return [
        KnowledgeTopic(
            key="bg_all",
            track="公用知识体系",
            module="图表映射 / 背景",
            lesson_code="映射",
            name="背景总览",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="背景",
            description="当前图表用双层模型表达背景：结构层负责 TR / Tight CH / Broad CH / 趋势交易区间，事件层负责突破起爆、跟进、测试和失败突破。",
            course_refs=("12A", "12B", "14A", "14E", "15A", "16A", "18A", "43A", "45A", "47A"),
            source_refs=(str(OUTLINE_PATH), str(FOUNDATION_INDEX_PATH), str(ADVANCED_INDEX_PATH)),
            implementation_notes=(
                "1. 当前背景采用“结构层 + 事件层”双层模型。\n"
                "2. 结构层输出 TR、Tight CH、Broad CH、趋势交易区间；事件层输出 BO、FT、Test、FBO。\n"
                "3. 结构层同时参考短窗、长窗、摆动腿数、趋势线/通道线几何质量、EMA 接触与磁体反应。\n"
                "4. 总览只负责把这些公共概念放到一张图上，不再把它们组织成策略执行流程。"
            ),
        ),
        KnowledgeTopic(
            key="bg_breakout",
            track="公用知识体系",
            module="图表映射 / 背景",
            lesson_code="15A-15H / 41A-42B",
            name="突破",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="背景",
            description="公共概念里的突破事件层，对应 BO / FT / Test / FBO。",
            course_refs=("15A", "15B", "15C", "15D", "15E", "15F", "15G", "15H", "41A", "41B", "42A", "42B"),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(ADVANCED_INDEX_PATH)),
            implementation_notes=(
                "1. 当前突破是单独事件层，不与结构层互斥。\n"
                "2. 起爆允许 surprise breakout bar，也要求突破前先有 breakout mode / 小平衡。\n"
                "3. 更高周期背景只做过滤，不再把所有宽通道里的强 surprise breakout 都压掉。\n"
                "4. 图上勾选“背景总览”和“突破”时，事件层不会重复叠加。"
            ),
        ),
        KnowledgeTopic(
            key="bg_opening_reversal",
            track="公用知识体系",
            module="图表映射 / 背景",
            lesson_code="02 / 48A-48C / Ali-OR",
            name="开盘反转",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="背景",
            description="把开盘早段的双向测试、BOM 与反向夺回接进共同事件层，辅助识别 Opening Reversal。",
            course_refs=("02A", "02B", "48A", "48B", "48C"),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                str(ADVANCED_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-0528.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0178.md"),
            ),
            implementation_notes=(
                "1. 当前把 Opening Reversal 并入共同事件层，不再单独起一套日内状态机。\n"
                "2. 主要参考 Open BOM、首段方向失败、反向夺回与 OR 位置。"
            ),
        ),
        KnowledgeTopic(
            key="bg_midday_reversal",
            track="公用知识体系",
            module="图表映射 / 背景",
            lesson_code="48D-48I / 百科",
            name="午间反转",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="背景",
            description="把午间时段接近日内极值后的反向夺回并入共同事件层，辅助识别 Midday Reversal。",
            course_refs=("48D", "48E", "48F", "48G", "48H", "48I"),
            source_refs=(
                str(ADVANCED_INDEX_PATH),
                str(PRACTICAL_INDEX_PATH),
            ),
            implementation_notes=(
                "1. 当前按日内中后段、接近会话极值、反向强趋势棒夺回来识别。\n"
                "2. 仍属于审计层近似，不直接下单。"
            ),
        ),
        KnowledgeTopic(
            key="bg_narrow_channel",
            track="公用知识体系",
            module="图表映射 / 背景",
            lesson_code="14E / 17A-17B / 43A-44D",
            name="窄幅通道",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="背景",
            description="公共概念里的紧密通道，强调趋势延续、小回调和更高时间周期上的突破属性。",
            course_refs=("14E", "17A", "17B", "43A", "43B", "43D", "44A", "44B", "44D"),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(ADVANCED_INDEX_PATH)),
            implementation_notes=(
                "1. 当前紧密通道要求短窗单边推进明显、EMA 优势侧占优、几何刺穿少。\n"
                "2. 它对应 Brooks 的“tight channel is breakout on higher time frame”。\n"
                "3. 图表显示只画质量达标且跨度足够的线，不再每个小波动都重画一条。"
            ),
        ),
        KnowledgeTopic(
            key="bg_broad_channel",
            track="公用知识体系",
            module="图表映射 / 背景",
            lesson_code="14D / 16D-16F / 45A-46E",
            name="宽幅通道",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="背景",
            description="公共概念里的宽幅通道，按 Brooks 口径视为倾斜的交易区间，而不是干净单边趋势。",
            course_refs=("14D", "16D", "16E", "16F", "45A", "45B", "45C", "45D", "45E", "46A", "46B", "46C", "46D", "46E"),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(ADVANCED_INDEX_PATH), str(PRACTICAL_INDEX_PATH)),
            implementation_notes=(
                "1. 当前宽幅通道结合长窗方向漂移、摆动腿数、趋势线/通道线质量和磁体反应判断。\n"
                "2. 起爆事件允许发生在宽幅通道里，但只接受真实突破，不接受普通摆动腿。\n"
                "3. 这部分目前仍是最需要继续打磨的边界。"
            ),
        ),
        KnowledgeTopic(
            key="bg_trending_tr",
            track="公用知识体系",
            module="图表映射 / 背景",
            lesson_code="45A-47D / 百科补充",
            name="趋势交易区间",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="背景",
            description="Brooks 原文里的 Trending Trading Range，作为 Broad CH 与 TR 之间的桥接背景。",
            course_refs=("45A", "45B", "46A", "46B", "47A", "47B", "47C", "47D"),
            source_refs=(str(PRACTICAL_INDEX_PATH), str(ADVANCED_INDEX_PATH)),
            implementation_notes=(
                "1. 这里不是第五个独立市场大周期，而是公共背景里的桥接态。\n"
                "2. 当前程序把它单列出来，是为了减少 Broad CH 与 TR 之间的硬切换。\n"
                "3. 它本质上仍然是带方向漂移的区间环境。"
            ),
        ),
        KnowledgeTopic(
            key="bg_trading_range",
            track="公用知识体系",
            module="图表映射 / 背景",
            lesson_code="12C / 18A-18F / 47A-47D",
            name="震荡",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="背景",
            description="公共概念里的交易区间，强调重叠、穿 EMA、边界突破大多失败。",
            course_refs=("12C", "18A", "18B", "18C", "18D", "18E", "18F", "47A", "47B", "47C", "47D"),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(ADVANCED_INDEX_PATH), str(PRACTICAL_INDEX_PATH)),
            implementation_notes=(
                "1. 当前震荡判定要求长窗和短窗都明显双边化。\n"
                "2. 它会压制一部分突破事件，但不会再把所有 surprise breakout 一概取消。"
            ),
        ),
        KnowledgeTopic(
            key="key_all",
            track="公用知识体系",
            module="图表映射 / 关键位置",
            lesson_code="19A-20B / 48A-48K",
            name="关键位置总览",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="把公共磁体与关键位置汇总到一张图上，方便与背景联动判断。",
            course_refs=("19A", "19B", "19C", "19D", "19E", "20A", "20B", "48A", "48C", "48E", "48K"),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(ADVANCED_INDEX_PATH)),
            implementation_notes=(
                "1. 当前会叠加 EMA、前高前低、趋势线/通道线、更高周期高低收、当日开盘和昨日关键价。\n"
                "2. 这些公共概念会参与结构判定，不只是显示层。"
            ),
        ),
        KnowledgeTopic(
            key="key_magnets",
            track="公用知识体系",
            module="图表映射 / 关键位置",
            lesson_code="19A-20B / Ali / 百科",
            name="磁体总览",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="按照 Brooks 最常用磁体组织：EMA20、前高前低、趋势线/通道线、更高周期关键位、测量走势和会话价位。",
            course_refs=("19A", "19B", "19C", "19D", "19E", "20A", "20B"),
            source_refs=(str(PRACTICAL_INDEX_PATH), str(ALI_INDEX_PATH)),
            implementation_notes=(
                "1. 当前已经把磁体接触比例和磁体反应分数接进结构层。\n"
                "2. 下一步最值得补的是更多水平磁体与 measured move 的直接联动。"
            ),
        ),
        KnowledgeTopic(
            key="key_ema20",
            track="公用知识体系",
            module="图表映射 / 关键位置",
            lesson_code="11B / 17B / Ali-EMA",
            name="EMA20 关键均值",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="Brooks 默认的 20 bar EMA，用作均值、优势侧与均线缺口语境。",
            course_refs=("11B", "17B"),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(ALI_INDEX_PATH)),
            implementation_notes="当前按 20 bar EMA 计算，并作为背景、突破测试和 MAG 语境的公共均值。 ",
        ),
        KnowledgeTopic(
            key="key_prior_swing",
            track="公用知识体系",
            module="图表映射 / 关键位置",
            lesson_code="19A-19E",
            name="前高前低 / 波段极值",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="最近 swing high / swing low，对应 Brooks 的前高前低和重要波段极值。",
            course_refs=("19A", "19B", "19C", "19D", "19E"),
            source_refs=(str(FOUNDATION_INDEX_PATH),),
            implementation_notes="当前会在可见区间提取最近几组 swing high / swing low，并接入磁体评分。 ",
        ),
        KnowledgeTopic(
            key="key_trendline",
            track="公用知识体系",
            module="图表映射 / 关键位置",
            lesson_code="16A-16F / 24A-24E",
            name="趋势线 / 通道线",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="公共概念里的趋势线与通道线，用来解释当前节奏和通道外沿。",
            course_refs=("16A", "16B", "16C", "16D", "16E", "16F", "24A", "24B", "24C", "24D", "24E"),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(PRACTICAL_INDEX_PATH)),
            implementation_notes=(
                "1. 当前会在最近一组 pivot 里挑最能解释当前节奏的线段。\n"
                "2. 评分同时看贴线、对侧通道贴合、刺穿比例、跨度和时效性。\n"
                "3. 只画质量达标的线。"
            ),
        ),
        KnowledgeTopic(
            key="key_higher_timeframe",
            track="公用知识体系",
            module="图表映射 / 关键位置",
            lesson_code="09C / 16C / 48K / Ali-TopDown",
            name="更高时间周期关键位",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="分钟级默认参考 1 小时，1 小时参考 1 日；同时绘制上一根更高周期高低收。",
            course_refs=("09C", "16C", "48K"),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(ALI_INDEX_PATH)),
            implementation_notes="当前默认 1m/5m/15m -> 1h，1h -> 1d，并允许手动覆盖。 ",
        ),
        KnowledgeTopic(
            key="key_session_levels",
            track="公用知识体系",
            module="图表映射 / 关键位置",
            lesson_code="19C / 48A-48K",
            name="开盘价 / 昨收 / 昨高低",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="公共概念里的会话价位与前一日关键价。",
            course_refs=("19C", "48A", "48C", "48E", "48K"),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(ADVANCED_INDEX_PATH)),
            implementation_notes="当前会绘制当日开盘、昨日收盘、昨日高点和昨日低点，并用于磁体评分。 ",
        ),
        KnowledgeTopic(
            key="key_measured_move",
            track="公用知识体系",
            module="图表映射 / 关键位置 / 测量走势",
            lesson_code="20A-20B / 11B / Ali-MM",
            name="测量走势 / AB=CD",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="当前图表按 Brooks 常见口径绘制 Leg1=Leg2、交易区间高度 MM、突破实体高度 MM，作为目标位与磁体。",
            course_refs=("20A", "20B"),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1724.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1726.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1747.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1757.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1762.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-0655.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-0705.md"),
                _knowledge_ref("阿布10种最佳价格行为交易模式", "pages", "page-0008.md"),
            ),
            implementation_notes=(
                "1. 当前显示 Leg1=Leg2、TR 高度 MM、BO 实体高度 MM，并把历史上可计算的目标一起画出来。\n"
                "2. 还没有把 breakout gap 到 BO point 的 measuring gap 单独画出来。"
            ),
        ),
        KnowledgeTopic(
            key="key_mm_leg_equal",
            track="公用知识体系",
            module="图表映射 / 关键位置 / 测量走势 / Leg1=Leg2",
            lesson_code="20A / Ali-MM",
            name="Leg1=Leg2 / AB=CD",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="基于前一波走势段高度的 Leg1=Leg2 测量走势。",
            course_refs=("20A",),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1724.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1726.md"),
                _knowledge_ref("阿布10种最佳价格行为交易模式", "pages", "page-0008.md"),
            ),
            implementation_notes="当前按最近摆点序列识别 Leg1=Leg2，并为历史与当前区间都绘制边界。",
        ),
        KnowledgeTopic(
            key="key_mm_leg_equal_deep_pb",
            track="公用知识体系",
            module="图表映射 / 关键位置 / 测量走势 / Leg1=Leg2",
            lesson_code="20A",
            name="Leg1=Leg2：强趋势深回调",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="对应原文里“趋势很强但回调较深（约50%）时，Leg1=Leg2 是最小目标”的子情形。",
            course_refs=("20A",),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1726.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1727.md"),
            ),
            implementation_notes="当前按回调深度与结构背景把 Leg1=Leg2 细分为强趋势深回调子情形。",
        ),
        KnowledgeTopic(
            key="key_mm_leg_equal_tr_context",
            track="公用知识体系",
            module="图表映射 / 关键位置 / 测量走势 / Leg1=Leg2",
            lesson_code="20A-20B",
            name="Leg1=Leg2：交易区间内部",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="对应原文里“趋势较弱或位于交易区间内部时，Leg1=Leg2 常是反弹末端”的子情形。",
            course_refs=("20A", "20B"),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1726.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1751.md"),
            ),
            implementation_notes="当前按结构层的震荡 / 趋势交易区间背景来细分这类 Leg1=Leg2。",
        ),
        KnowledgeTopic(
            key="key_mm_leg_equal_ema",
            track="公用知识体系",
            module="图表映射 / 关键位置 / 测量走势 / Leg1=Leg2",
            lesson_code="20A / 17A-17B / Ali-EMA",
            name="Leg1=Leg2：与 EMA 配合",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="把 Leg1=Leg2 与 EMA20 附近回调语境结合，用来过滤更有均值回归色彩的子情形。",
            course_refs=("20A", "17A", "17B"),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1726.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0039.md"),
            ),
            implementation_notes="这是用 Leg1=Leg2 原文与 EMA 回调语境合成的程序口径，会明确标成 EMA 配合子情形。",
        ),
        KnowledgeTopic(
            key="key_mm_tr_height",
            track="公用知识体系",
            module="图表映射 / 关键位置 / 测量走势",
            lesson_code="20B",
            name="交易区间高度 MM",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="基于交易区间高度推导的测量走势目标。",
            course_refs=("20B",),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1747.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1749.md"),
            ),
            implementation_notes="当前按局部紧密区间后的突破识别 TR 高度 MM，并为历史目标补结束边界。",
        ),
        KnowledgeTopic(
            key="key_mm_bo_height",
            track="公用知识体系",
            module="图表映射 / 关键位置 / 测量走势",
            lesson_code="20B / 11B",
            name="突破高度 / 实体高度 MM",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="基于突破高度或突破实体高度推导的测量走势目标。",
            course_refs=("20B", "11B"),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1757.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-1762.md"),
            ),
            implementation_notes="当前先按强突破实体高度识别 BO MM，还没把 measuring gap 目标单独拆出来。",
        ),
        KnowledgeTopic(
            key="key_mm_measuring_gap",
            track="公用知识体系",
            module="图表映射 / 关键位置 / 测量走势 / Measuring Gap",
            lesson_code="11B / Ali-MG",
            name="Measuring Gap MM",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="基于 breakout point 与 pullback 之间保持开放的 gap 推导 Measuring Gap MM。",
            course_refs=("11B",),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-0655.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-0656.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-0705.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0487.md"),
            ),
            implementation_notes="当前把 Measuring Gap MM 单独接进 MM 协同计算，并用背景层/突破层共同过滤。",
        ),
        KnowledgeTopic(
            key="key_mm_negative_measuring_gap",
            track="公用知识体系",
            module="图表映射 / 关键位置 / 测量走势 / Measuring Gap",
            lesson_code="Ali-NegMG",
            name="Negative Measuring Gap",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="回调略微跌破或涨破突破点后形成的负测量缺口，目标可靠性下降，但仍值得记录。",
            course_refs=("11B",),
            source_refs=(
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0487.md"),
            ),
            implementation_notes="当前把 Negative Measuring Gap 作为 Measuring Gap 的低可靠性分支单独画出。",
        ),
        KnowledgeTopic(
            key="key_mm_measuring_gap_midline",
            track="公用知识体系",
            module="图表映射 / 关键位置 / 测量走势 / Measuring Gap",
            lesson_code="11B / MM-middle",
            name="Measuring Gap middle line 多口径",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="关键位置",
            description="同一段 Measuring Gap 可能存在标准中线和较小中线两种口径，程序会并列画出。",
            course_refs=("11B",),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-2253.md"),
            ),
            implementation_notes="当前按较大 gap 与较小 gap 两种中线口径并列绘制，方便后续截图核对。 ",
        ),
        KnowledgeTopic(
            key="bar_count",
            track="公用知识体系",
            module="图表映射 / 辅助",
            lesson_code="09A / 48A",
            name="Bar Count",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            description="日内 bar count 辅助读图，帮助定位开盘区间、bar 18 与日内节奏。",
            course_refs=("09A", "48A", "48B", "48C"),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(ADVANCED_INDEX_PATH)),
            implementation_notes="当前图表支持局部 bar count，可按固定间隔显示。 ",
        ),
        KnowledgeTopic(
            key="aux_bom_patterns",
            track="公用知识体系",
            module="图表映射 / 辅助",
            lesson_code="08B-08D",
            name="ii / ioi / oo 与突破模式",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="辅助",
            description="在图表上标出 ii、ioi、oo 这类压缩形态，辅助识别 breakout mode、小型紧密区间和第二个信号语境。",
            course_refs=("08B", "08C", "08D"),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-0457.md"),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-0470.md"),
            ),
            implementation_notes=(
                "1. 当前只做图表审计叠加，不把 ii / ioi / oo 直接当 CTA 触发条件。\n"
                "2. 重点是辅助看 breakout mode、小平衡和第二个信号。"
            ),
        ),
        KnowledgeTopic(
            key="aux_micro_gap",
            track="公用知识体系",
            module="图表映射 / 辅助",
            lesson_code="11C",
            name="微缺口（Micro Gap）",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="辅助",
            description="按 Brooks 的口径，检查趋势棒前后一根是否不重叠，并把微缺口直接标在图上。",
            course_refs=("11C",),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                _knowledge_ref("1.《价格行为学》（基础篇1-36章）", "pages", "page-0686.md"),
            ),
            implementation_notes=(
                "1. 当前按“中间必须是趋势棒，且前后一根不重叠”识别微缺口。\n"
                "2. 这部分用于审计突破后续跟进强弱，不直接替代 MAG。"
            ),
        ),
        KnowledgeTopic(
            key="aux_opening_range",
            track="公用知识体系",
            module="图表映射 / 辅助",
            lesson_code="02 / 48A-48C",
            name="Open BOM / 开盘区间 / ORBO / Bar 18",
            status=STATUS_IMPLEMENTED,
            implemented=True,
            overlay_group="辅助",
            description="绘制首根K线突破模式、当日开盘区间、Bar 18 和首个 ORBO 位置，方便核对开盘即趋势与日内结构。",
            course_refs=("02A", "02B", "48A", "48B", "48C"),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                str(ADVANCED_INDEX_PATH),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0178.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0163.md"),
            ),
            implementation_notes=(
                "1. 当前按图表所见执行周期统计首根K线突破模式、开盘区间和第 18 根 bar。\n"
                "2. 这部分是图表审计层，不直接决定 CTA 信号。"
            ),
        ),
    ]


def _mark_course_topics_as_partially_implemented(
    course_topics: tuple[KnowledgeTopic, ...],
    implemented_topics: tuple[KnowledgeTopic, ...],
) -> tuple[KnowledgeTopic, ...]:
    """把已被图表功能覆盖到的课程章节标成部分接入。"""
    implemented_refs = {
        ref
        for topic in implemented_topics
        for ref in topic.course_refs
        if ref
    }
    updated_topics: list[KnowledgeTopic] = []
    for topic in course_topics:
        if topic.lesson_code in implemented_refs:
            updated_topics.append(
                KnowledgeTopic(
                    key=topic.key,
                    track=topic.track,
                    module=topic.module,
                    lesson_code=topic.lesson_code,
                    name=topic.name,
                    status=STATUS_IMPLEMENTED_PARTIAL,
                    implemented=topic.implemented,
                    overlay_group=topic.overlay_group,
                    filter_kinds=topic.filter_kinds,
                    description=topic.description,
                    course_refs=topic.course_refs,
                    source_refs=topic.source_refs,
                    implementation_notes=topic.implementation_notes,
                )
            )
        else:
            updated_topics.append(topic)
    return tuple(updated_topics)


def _build_supplement_topics() -> list[KnowledgeTopic]:
    """百科与 Ali 的实战补充主题。"""
    return [
        KnowledgeTopic(
            key="supp_major_trend_reversal",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="主趋势反转（百科/Ali）",
            status=STATUS_CATALOGED,
            description="用百科与 Ali 补 MTR 的案例密度、位置感和失败形态，辅助 22A-22D、38A-39D。",
            course_refs=("22A", "22B", "22C", "22D", "38A", "38B", "38C", "38D", "39A", "39B", "39C", "39D"),
            source_refs=(str(PRACTICAL_INDEX_PATH), str(ALI_INDEX_PATH)),
        ),
        KnowledgeTopic(
            key="supp_breakout",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="突破（百科/Ali）",
            status=STATUS_CATALOGED,
            description="补强 breakout mode、surprise breakout、失败突破、二腿陷阱和 breakout gap 的案例。",
            course_refs=("15A", "15B", "15C", "15D", "15E", "15F", "15G", "15H", "41A", "41B", "41C", "41D", "42A", "42B"),
            source_refs=(str(PRACTICAL_INDEX_PATH), str(ALI_INDEX_PATH), str(BEST10_INDEX_PATH)),
        ),
        KnowledgeTopic(
            key="supp_trading_range",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="交易区间（百科/Ali）",
            status=STATUS_CATALOGED,
            description="补强 TR、TTR、TRD/TTRD、BOM、腿与区间早期迹象的案例。",
            course_refs=("18A", "18B", "18C", "18D", "18E", "18F", "47A", "47B", "47C", "47D"),
            source_refs=(str(PRACTICAL_INDEX_PATH), str(ALI_INDEX_PATH)),
        ),
        KnowledgeTopic(
            key="supp_small_pullback_trend",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="小回调趋势 / 微通道 / 旗形（百科/Ali）",
            status=STATUS_CATALOGED,
            description="补强 small pullback bull/bear trend、micro channel、bull/bear flag 与 trend resumption 的案例。",
            course_refs=("14E", "17A", "17B", "23A", "23B", "43A", "43B", "44A", "44B"),
            source_refs=(
                str(PRACTICAL_INDEX_PATH),
                str(BEST10_INDEX_PATH),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0454.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0402.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0579.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0411.md"),
            ),
        ),
        KnowledgeTopic(
            key="supp_trade_management",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="交易管理（百科/Ali）",
            status=STATUS_CATALOGED,
            description="补强 stop、exit、scale-in、runner、limit order selection、higher timeframe context 的实战处理。",
            course_refs=("37B", "41D", "43C", "44C", "49F", "50A", "50B", "51C", "51D", "52A", "52B"),
            source_refs=(str(PRACTICAL_INDEX_PATH), str(ALI_INDEX_PATH)),
        ),
        KnowledgeTopic(
            key="supp_opening_range",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="开盘区间 / 跳空 / 开盘反转（百科/Ali）",
            status=STATUS_CATALOGED,
            description="补强 gap up/down、ORBO、开盘反转、午间反转、bar 18 与开盘即趋势的案例。",
            course_refs=("02A", "02B", "11A", "11B", "48A", "48B", "48C", "48D", "48E", "48F", "48G", "48H", "48I", "48J", "48K"),
            source_refs=(
                str(PRACTICAL_INDEX_PATH),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0163.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0334.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0312.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0319.md"),
            ),
        ),
        KnowledgeTopic(
            key="supp_signal_entries",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="H1/H2/L1/L2 与首次/二次入场（百科/Ali）",
            status=STATUS_CATALOGED,
            description="补强 High 1/2、Low 1/2、首次失败逆势尝试与二次顺势恢复的案例密度。",
            course_refs=("08D", "09A", "09B", "09C", "17A", "48A", "48B"),
            source_refs=(
                str(PRACTICAL_INDEX_PATH),
                str(BEST10_INDEX_PATH),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0024.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0019.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0023.md"),
                _knowledge_ref("百科幻灯片-9", "pages", "page-0006.md"),
                _knowledge_ref("阿布10种最佳价格行为交易模式", "pages", "page-0005.md"),
            ),
        ),
        KnowledgeTopic(
            key="supp_ema_gap_measured_move",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="EMA 缺口棒 / 测量走势（百科/Ali）",
            status=STATUS_CATALOGED,
            description="补强 EMA gap bar、moving average gap、measured move 与 gap 目标延伸的案例。",
            course_refs=("10A", "11A", "11B", "11C", "11D", "19A", "20A", "20B"),
            source_refs=(
                str(PRACTICAL_INDEX_PATH),
                str(BEST10_INDEX_PATH),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0576.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0487.md"),
                _knowledge_ref("阿布10种最佳价格行为交易模式", "pages", "page-0008.md"),
            ),
        ),
        KnowledgeTopic(
            key="supp_double_top_bottom",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="双顶双底 / 更低高点双顶 / 更低点双底（百科/Ali）",
            status=STATUS_CATALOGED,
            description="补强双顶双底、LHDT、LLDB、cup and handle 这类二次测试与失败突破结构。",
            course_refs=("20A", "21A", "21B", "22A", "22B", "25A", "25B"),
            source_refs=(
                str(PRACTICAL_INDEX_PATH),
                str(BEST10_INDEX_PATH),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0734.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0129.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0299.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0642.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0254.md"),
            ),
        ),
        KnowledgeTopic(
            key="supp_wedge_exhaustion",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="楔形 / 连续楔形 / 高潮衰竭（百科/Ali）",
            status=STATUS_CATALOGED,
            description="补强 wedge、consecutive wedge、parabolic wedge、buy/sell climax 与 exhaustion reversal 的案例。",
            course_refs=("23A", "23B", "24A", "24B", "24C", "24D", "24E", "29A", "29B", "29C", "29D", "42A", "42B"),
            source_refs=(
                str(PRACTICAL_INDEX_PATH),
                str(BEST10_INDEX_PATH),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0040.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0042.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0354.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0397.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0565.md"),
                _knowledge_ref("阿布10种最佳价格行为交易模式", "pages", "page-0006.md"),
            ),
        ),
        KnowledgeTopic(
            key="supp_channel_spike",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="尖峰通道 / 宽窄通道 / 始终在场（百科/Ali）",
            status=STATUS_CATALOGED,
            description="补强 spike and channel、tight/broad bull/bear channel、always in 与通道内趋势恢复的案例。",
            course_refs=("12A", "12B", "14D", "14E", "16A", "16D", "16E", "17A", "43A", "44A", "45A", "46A", "46B"),
            source_refs=(
                str(PRACTICAL_INDEX_PATH),
                str(BEST10_INDEX_PATH),
                _knowledge_ref("百科幻灯片-13", "pages", "page-0254.md"),
                _knowledge_ref("百科幻灯片-13", "pages", "page-0296.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0688.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0698.md"),
                _knowledge_ref("Ali Flash Cards - 完美裁切A3宽(4K屏推荐)", "pages", "page-0699.md"),
                _knowledge_ref("阿布10种最佳价格行为交易模式", "pages", "page-0002.md"),
            ),
        ),
        KnowledgeTopic(
            key="supp_best10",
            track="公用知识体系",
            module="百科/Ali 实战补充",
            lesson_code="补充",
            name="阿布 10 种最佳价格行为模式",
            status=STATUS_CATALOGED,
            description="把突破、H1/H2、楔形、微通道、Gap 与 measured move 的高频实战模式汇总在一卷里。",
            course_refs=("15A", "17A", "17B", "20A", "22A", "24A", "41A", "43A", "44A"),
            source_refs=(str(BEST10_INDEX_PATH),),
        ),
    ]


def _topic_names_by_key(topics: tuple[KnowledgeTopic, ...]) -> dict[str, str]:
    return {topic.key: topic.name for topic in topics}


def _step(
    key: str,
    status: str,
    summary: str,
    *topic_keys: str,
    notes: str = "",
) -> StrategyTemplateStep:
    """创建一个策略流程环节。"""
    return StrategyTemplateStep(
        key=key,
        name=FLOW_STEP_NAME_MAP[key],
        status=status,
        summary=summary,
        topic_keys=tuple(topic_keys),
        notes=notes,
    )


def _build_strategy_blueprints(topic_names: dict[str, str]) -> tuple[StrategyBlueprint, ...]:
    """策略蓝图目录。"""
    strategies = (
        StrategyBlueprint(
            key="strategy_h1_l1",
            family="顺势回调模板",
            name="H1/L1 首次回调顺势",
            status=STRATEGY_STATUS_CODED,
            summary="当前已有首版代码，但还没有把首次回调序列早晚、末端旗形、磁体优先级和更细的出场管理编码完整。",
            steps=(
                _step("background", STEP_STATUS_CODED, "优先要求紧密通道，允许早期宽通道，但不应在明确趋势交易区间尾端继续做 H1/L1。", "bg_narrow_channel", "bg_broad_channel", "course_14E", "course_17A"),
                _step("key_levels", STEP_STATUS_CODED, "至少同时参考 EMA20、前高前低、趋势线/通道线和主要磁体，避免只凭一次回踩。", "key_ema20", "key_magnets", "key_trendline", "key_prior_swing"),
                _step("setup_context", STEP_STATUS_CODED, "把首次回调理解成序列里的第一次逆势尝试，而不是任何第一根反向 K。", "course_09A", "course_09B", "course_17A", "supp_signal_entries"),
                _step("signal_bar", STEP_STATUS_CODED, "当前沿用 H1/L1 signal bar 强中弱规则，但还没叠加序列早晚和末端旗形过滤。", "course_08A", "course_08B", "supp_signal_entries"),
                _step("entry_trigger", STEP_STATUS_CODED, "仍用 signal bar 外一跳 stop 触发，不做主观提前进场。", "course_08A"),
                _step("trigger_invalidation", STEP_STATUS_CODED, "默认 3 根执行周期内未触发失效；若背景快速恶化也会撤单。", "course_17A"),
                _step("initial_stop", STEP_STATUS_CODED, "当前统一 signal bar 外止损，后续要加入 swing stop 与 price action stop 区分。", "course_17A"),
                _step("actual_risk", STEP_STATUS_CODED, "实际风险仍按 entry 到 stop 计算，不看 signal bar 表面大小。", "course_37B"),
                _step("position_leverage", STEP_STATUS_PLANNED, "当前仍是固定手数回测，后续才把费率门槛和风险仓位接进来。"),
                _step("first_target", STEP_STATUS_CODED, "优先看原趋势极值，不足时退回 RR 目标。", "course_19D", "course_20A"),
                _step("management", STEP_STATUS_DESIGNED, "下一步要把它从短持仓剥头皮改成真正的‘先减仓后留 runner’。", "supp_trade_management", "course_49F"),
                _step("breakeven", STEP_STATUS_CODED, "当前 1R 保本偏早，后续要推迟到更合理的位置。", "course_37B", notes="这一步是当前回测过密和大量保本单的主要原因之一。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "应补强反向 surprise bar、回区间中轴和 higher time frame 否决时的提前离场。", "supp_trade_management"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "应区分首次失败后的再入场与同趋势加仓，暂未落代码。"),
            ),
            tuning_notes=(
                "1. 当前最需要补的是“首次回调序列位置”“末端旗形”和“成本门槛”。\n"
                "2. 当前回测已经证明这套策略不是完全无 edge，而是交易过密、费用吃掉了薄 edge。"
            ),
            code_refs=(str((REPO_DIR / "strategies" / "h1_l1_first_pullback_strategy.py").resolve()),),
            source_refs=(
                str(FOUNDATION_INDEX_PATH),
                str((REPO_DIR / "策略资料" / "太妃价格行为" / "L17A - 首次回調序列与均線交易.md").resolve()),
                str((REPO_DIR / "策略资料" / "太妃价格行为" / "L11B - 数k线的原理与应用.md").resolve()),
                str(BEST10_INDEX_PATH),
            ),
        ),
        StrategyBlueprint(
            key="strategy_h2_l2",
            family="顺势回调模板",
            name="H2/L2 二次入场顺势",
            status=STRATEGY_STATUS_CODED,
            summary="当前已有首版代码，是顺势模板里最容易程序化的一层，但还缺更细的结构过滤和分批管理。",
            steps=(
                _step("background", STEP_STATUS_CODED, "优先使用紧密通道和较健康的趋势恢复背景，不应把震荡中部的二次尝试误当 H2/L2。", "bg_narrow_channel", "course_14E", "course_17A"),
                _step("key_levels", STEP_STATUS_CODED, "公共磁体与 EMA20 已接入，但还需要更细的 higher time frame 约束。", "key_ema20", "key_magnets", "key_higher_timeframe"),
                _step("setup_context", STEP_STATUS_CODED, "二次尝试已接代码，当前是 H2/L2 最稳定的一层。", "course_09A", "course_09B", "course_17A", "supp_signal_entries"),
                _step("signal_bar", STEP_STATUS_CODED, "沿用强中弱质量，不接受弱 signal bar。", "course_08A", "course_08B", "supp_signal_entries"),
                _step("entry_trigger", STEP_STATUS_CODED, "沿用 stop 触发。", "course_08A"),
                _step("trigger_invalidation", STEP_STATUS_CODED, "超时或先打止损位就撤。", "course_17A"),
                _step("initial_stop", STEP_STATUS_CODED, "当前 signal bar 外一跳。", "course_17A"),
                _step("actual_risk", STEP_STATUS_CODED, "仍按真实风险计算。", "course_37B"),
                _step("position_leverage", STEP_STATUS_PLANNED, "后续接风险仓位和费率门槛。"),
                _step("first_target", STEP_STATUS_CODED, "原趋势极值优先。", "course_19D", "course_20A"),
                _step("management", STEP_STATUS_DESIGNED, "适合先做成‘第一目标减仓 + 剩余跟踪’的基线管理。", "supp_trade_management"),
                _step("breakeven", STEP_STATUS_CODED, "当前逻辑已经有，但仍偏机械。", "course_37B"),
                _step("early_exit", STEP_STATUS_DESIGNED, "可补强反向 test 失败与区间化退出。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "二次入场天然适合扩展到 add-on，但当前未做。"),
            ),
            tuning_notes=(
                "1. 适合先作为低复杂度基线策略。\n"
                "2. 下一步应把早期宽通道、趋势交易区间和手续费门槛纳入。"
            ),
            code_refs=(str((REPO_DIR / "strategies" / "ema20_h2_l2_trend_strategy.py").resolve()),),
            source_refs=(str(FOUNDATION_INDEX_PATH), str((REPO_DIR / "策略资料" / "策略规格" / "EMA20_H2_L2顺势策略规格.md").resolve())),
        ),
        StrategyBlueprint(
            key="strategy_mag_20_gap",
            family="均线与缺口模板",
            name="20 均线缺口",
            status=STRATEGY_STATUS_CODED,
            summary="当前已有首版代码，按 20-45 根 EMA 缺口后的首次回测实现。",
            steps=(
                _step("background", STEP_STATUS_CODED, "优先要求仍处顺势环境，且不是明显趋势尾端。", "bg_narrow_channel", "bg_broad_channel", "course_17A"),
                _step("key_levels", STEP_STATUS_CODED, "核心是 EMA20，但也要配合前高前低和重要磁体。", "key_ema20", "key_magnets"),
                _step("setup_context", STEP_STATUS_CODED, "当前用连续 20-45 根 gap bars 定义过度延伸均线缺口。", "course_11B", "course_17B", "supp_ema_gap_measured_move"),
                _step("signal_bar", STEP_STATUS_CODED, "仍沿用强中弱质量。", "course_08A", "course_08B"),
                _step("entry_trigger", STEP_STATUS_CODED, "用 stop 触发首次回测。"),
                _step("trigger_invalidation", STEP_STATUS_CODED, "若回测后重新跌回不利侧或超时则失效。"),
                _step("initial_stop", STEP_STATUS_CODED, "当前默认 signal bar 外止损。"),
                _step("actual_risk", STEP_STATUS_CODED, "仍按 entry-stop 真实距离。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "后续加入费率过滤和风险仓位。"),
                _step("first_target", STEP_STATUS_CODED, "优先原趋势极值。", "course_19D", "course_20A"),
                _step("management", STEP_STATUS_DESIGNED, "应加 partial 处理，避免过早保本把 edge 吃掉。", "supp_trade_management"),
                _step("breakeven", STEP_STATUS_CODED, "当前已有，但应和 gap 类型区分。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "应加入连续穿透 EMA 的动能否决。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "暂未做。"),
            ),
            tuning_notes=(
                "1. 当前实现更像 20 gap bar，不等于完整的 first moving average gap 体系。\n"
                "2. 下一步要把两者拆开。"
            ),
            code_refs=(str((REPO_DIR / "strategies" / "mag_20_gap_strategy.py").resolve()),),
            source_refs=(str(FOUNDATION_INDEX_PATH), str((REPO_DIR / "策略资料" / "太妃价格行为" / "L17B - ✨20均线缺口-✨第一均线缺口.md").resolve())),
        ),
        StrategyBlueprint(
            key="strategy_mag_first_gap",
            family="均线与缺口模板",
            name="第一均线缺口",
            status=STRATEGY_STATUS_DESIGNED,
            summary="比 20 均线缺口更靠近趋势尾端，需要把首次回调序列和动能衰竭接进来。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "背景应允许动能衰退，但不能已转成纯震荡。", "bg_broad_channel", "bg_trending_tr", "course_17A"),
                _step("key_levels", STEP_STATUS_CODED, "核心仍是 EMA20 和重要磁体。", "key_ema20", "key_magnets"),
                _step("setup_context", STEP_STATUS_DESIGNED, "价格首次穿透均线对侧后又回到原趋势侧，且应有衰退迹象。", "course_11B", "course_17B", "supp_ema_gap_measured_move"),
                _step("signal_bar", STEP_STATUS_CODED, "可复用现有 signal bar 评分，但需额外过滤强趋势连续穿透。", "course_08A", "course_08B"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "仍建议 stop 触发。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "若再度连续击穿均线且无恢复，应取消。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "偏向 signal bar 外，必要时放宽到 swing 点外。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "应严格计算，避免双重止损。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "后续接成本门槛。"),
                _step("first_target", STEP_STATUS_DESIGNED, "原趋势极值优先。"),
                _step("management", STEP_STATUS_DESIGNED, "应比 20 gap 更保守。"),
                _step("breakeven", STEP_STATUS_PLANNED, "暂未细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "均线再度失守或序列尾端确认后提前离场。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "暂不建议。"),
            ),
            tuning_notes="下一步应和 20 gap bar 拆开管理，不要继续共用一套条件。",
            source_refs=(str(FOUNDATION_INDEX_PATH), str((REPO_DIR / "策略资料" / "太妃价格行为" / "L17B - ✨20均线缺口-✨第一均线缺口.md").resolve())),
        ),
        StrategyBlueprint(
            key="strategy_breakout_pullback",
            family="突破模板",
            name="Breakout Pullback",
            status=STRATEGY_STATUS_DESIGNED,
            summary="当前背景与事件层已具备基础条件，但还没有独立 breakout pullback 策略文件和管理逻辑。",
            steps=(
                _step("background", STEP_STATUS_CODED, "先看 BO / FT / Test 三段式，再看 higher time frame 背景。", "bg_breakout", "key_higher_timeframe", "course_15A", "course_15B", "course_41A"),
                _step("key_levels", STEP_STATUS_CODED, "突破位、测试位、EMA、会话关键位和 measured move 都重要。", "key_all", "key_magnets"),
                _step("setup_context", STEP_STATUS_DESIGNED, "先有真实突破和跟进，再有第一次优质回测。", "course_15D", "course_15E", "course_41B", "supp_breakout"),
                _step("signal_bar", STEP_STATUS_PLANNED, "应按 test bar 与突破位关系细化。"),
                _step("entry_trigger", STEP_STATUS_PLANNED, "可分 aggressive 和 conservative stop entry。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "深回原区间或强反向 trend bar 视为失效。"),
                _step("initial_stop", STEP_STATUS_PLANNED, "应区分突破位外与 signal bar 外。"),
                _step("actual_risk", STEP_STATUS_PLANNED, "暂未独立设计。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "暂未独立设计。"),
                _step("first_target", STEP_STATUS_DESIGNED, "Measured move、原趋势极值与最近磁体并列。", "course_20A", "course_20B"),
                _step("management", STEP_STATUS_DESIGNED, "适合做分批与失败后快速退出。", "supp_trade_management"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "失败突破、无跟进、二腿陷阱要提前离场。", "course_15F", "course_15G"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "突破后第二次测试仍可做再入场。"),
            ),
            tuning_notes=(
                "1. 应优先做 surprise breakout、follow-through、first test 的三段式。\n"
                "2. 不应和 H1/H2/L1/L2 混为同一模板。"
            ),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(ADVANCED_INDEX_PATH), str(PRACTICAL_INDEX_PATH), str((REPO_DIR / "策略资料" / "太妃价格行为" / "L15B - ✨急赴磁体-✨区间突破回调.md").resolve())),
        ),
        StrategyBlueprint(
            key="strategy_buy_close",
            family="极速与动能模板",
            name="收线试驾 / BUYNOW",
            status=STRATEGY_STATUS_DESIGNED,
            summary="对应太妃的收线试驾，翻成 Brooks 语义就是突破后动能阶段的 buy/sell the close。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "应在 spike 或 tight channel 初段，不应在宽通道或 TR 中硬追。", "bg_breakout", "bg_narrow_channel", "course_14B", "course_14E"),
                _step("key_levels", STEP_STATUS_DESIGNED, "要检查路径上是否有前高前低、整数位或 measured move 阻力。", "key_magnets", "key_session_levels"),
                _step("setup_context", STEP_STATUS_DESIGNED, "突破有明显跟进，且价格持续远离突破点。", "course_15A", "course_15B", "supp_breakout"),
                _step("signal_bar", STEP_STATUS_DESIGNED, "趋势 bar 收在线外侧且实体强。", "course_08A"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "当前可按收线追进逻辑设计，不等回调。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "若出现首根明确回调 bar，则退出动能模板。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "推动起点或重要波段点之外。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "不应用情绪窄损。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_DESIGNED, "可用实体投影或 AB=CD。", "course_20A"),
                _step("management", STEP_STATUS_DESIGNED, "偏动能交易，不适合机械保本。"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "首根明确回调 bar 或遇到强磁体时退出。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "可与逆1顺1连续使用。"),
            ),
            tuning_notes="太妃的“收线试驾”可以直接并到 Brooks 的动能阶段 close entry 模板。",
            source_refs=(str((REPO_DIR / "策略资料" / "太妃价格行为" / "L13A - 急速交易 - ✨收线.md").resolve()), str(FOUNDATION_INDEX_PATH)),
        ),
        StrategyBlueprint(
            key="strategy_failed_countertrend_first",
            family="极速与动能模板",
            name="逆 1 失败、顺 1 成功",
            status=STRATEGY_STATUS_DESIGNED,
            summary="对应太妃的逆 1 顺 1，本质是趋势恢复阶段的第一次失败逆势尝试后，顺势恢复再入场。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "应在动能仍强、路径较通畅的趋势恢复环境。", "bg_breakout", "bg_narrow_channel", "course_15B", "course_17A"),
                _step("key_levels", STEP_STATUS_DESIGNED, "要检查路径上是否有强磁体截断。", "key_magnets", "key_session_levels"),
                _step("setup_context", STEP_STATUS_DESIGNED, "逆势第一次尝试失败，顺势第一次恢复更容易成功。", "course_09A", "course_15B", "course_17A"),
                _step("signal_bar", STEP_STATUS_DESIGNED, "顺 1 对应的恢复 bar 需要比逆 1 更强。"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "高/低 1 形式的 stop entry。", "course_09A", "course_09B"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "回调若加深且损害突破点，则失效。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "急速起点或结构点之外。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "应配合动能环境。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_DESIGNED, "AB=CD 或原趋势极值。", "course_20A"),
                _step("management", STEP_STATUS_DESIGNED, "可和收线试驾连续使用，但逻辑必须分开。"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "磁体截断或测试不及应提前放弃。"),
                _step("reentry_addon", STEP_STATUS_DESIGNED, "与动能模板联动是它的特色。"),
            ),
            tuning_notes="这套策略适合挂在‘极速与动能模板’里，而不是单独当成公共知识点。",
            source_refs=(str((REPO_DIR / "策略资料" / "太妃价格行为" / "L13B - 急速交易 - ✨逆1顺1.md").resolve()), str(FOUNDATION_INDEX_PATH)),
        ),
        StrategyBlueprint(
            key="strategy_flag_pullback",
            family="顺势回调模板",
            name="旗形回调（双重顶底 / 楔形作持续）",
            status=STRATEGY_STATUS_DESIGNED,
            summary="对应太妃旗形回调，使用双重顶底或楔形作为更大趋势中的持续形态。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "必须先有主趋势，再有逆势小通道。", "course_05", "course_14A", "bg_broad_channel"),
                _step("key_levels", STEP_STATUS_DESIGNED, "原趋势极值、AB=CD、趋势线/通道线和 EMA 是核心。", "key_magnets", "key_trendline", "key_ema20"),
                _step("setup_context", STEP_STATUS_DESIGNED, "双重顶底或楔形在这里不是做反转，而是找回调结束。", "course_24A", "course_25A", "course_26A", "supp_small_pullback_trend", "supp_double_top_bottom", "supp_wedge_exhaustion"),
                _step("signal_bar", STEP_STATUS_DESIGNED, "更看重突破失败 + 反向 K 线，而不是形态名字。"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "倾向 stop 触发，避免直接限价接刀。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "第二推不及、动能不够或背景已转弱则失效。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "a1 宽损 / a2 窄损两套都应保留。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "不同止损口径必须对应不同目标。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_DESIGNED, "b1 原趋势极值 / b2 形态高度 / b3 AB=CD。", "course_20A"),
                _step("management", STEP_STATUS_DESIGNED, "这套模板非常适合按目标远近拆管理。"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "若小型反转不成立、反而发展成更强逆势通道，应提前认错。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "可扩展，但未细化。"),
            ),
            tuning_notes="这套模板是顺大逆小，不是主趋势反转。",
            source_refs=(str((REPO_DIR / "策略资料" / "太妃价格行为" / "L14A - 旗形回调.md").resolve()), str(FOUNDATION_INDEX_PATH)),
        ),
        StrategyBlueprint(
            key="strategy_double_top_bottom",
            family="反转模板",
            name="双重顶 / 双重底",
            status=STRATEGY_STATUS_DESIGNED,
            summary="双重顶底可以做反转，也可以做持续，具体要服从背景。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "必须先区分它是在主趋势尾端、还是嵌在更大趋势的回调里。", "course_21A", "course_22A", "course_25A"),
                _step("key_levels", STEP_STATUS_DESIGNED, "第一推极值、AB=CD、前高前低与磁体重叠很关键。", "key_prior_swing", "key_magnets", "course_20A"),
                _step("setup_context", STEP_STATUS_DESIGNED, "两次测试同一磁体失败。", "course_25A", "course_25B", "supp_double_top_bottom"),
                _step("signal_bar", STEP_STATUS_DESIGNED, "更看重第二推的失败表现和反向 signal。"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "等第二推到位后用 stop 触发。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "第二推不及或直接加速突破则失效。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "前波段点外或回调极值外。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "需和目标口径联动。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_DESIGNED, "原趋势极值或形态高度。"),
                _step("management", STEP_STATUS_DESIGNED, "反转模板要接受低胜率高盈亏比。"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "一旦形态失败变成更强 BO，应快速退出。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "不优先。"),
            ),
            tuning_notes="双重顶底应该从旗形回调模板和反转模板两边都能调用。",
            source_refs=(str((REPO_DIR / "策略资料" / "太妃价格行为" / "L14A - 旗形回调.md").resolve()), str((REPO_DIR / "策略资料" / "太妃价格行为" / "L14B - ✨双重顶底-✨楔形.md").resolve()), str(FOUNDATION_INDEX_PATH)),
        ),
        StrategyBlueprint(
            key="strategy_wedge",
            family="反转模板",
            name="楔形顶 / 楔形底",
            status=STRATEGY_STATUS_DESIGNED,
            summary="楔形外观不必完美，核心是突破屡屡失败和一推不如一推。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "先判它是主趋势反转，还是更大趋势里的回调持续。", "course_24A", "course_24B", "course_24D", "course_22A"),
                _step("key_levels", STEP_STATUS_DESIGNED, "趋势线、通道线、AB=CD 和重要磁体重叠最关键。", "key_trendline", "key_magnets", "course_20A"),
                _step("setup_context", STEP_STATUS_DESIGNED, "三推、突破失败、逆势力量减弱。", "course_24A", "course_24B", "course_24C", "course_24E", "supp_wedge_exhaustion"),
                _step("signal_bar", STEP_STATUS_DESIGNED, "末端最好有反向 surprise bar 或失败突破。"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "到位后用 stop 触发。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "若第三推继续加速而不是衰竭，则失效。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "第三推极值外或结构外。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "依目标远近而定。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_DESIGNED, "回区间均衡或原趋势极值。"),
                _step("management", STEP_STATUS_DESIGNED, "反转模板。"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "形态失败要快。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "暂不优先。"),
            ),
            tuning_notes="楔形是双重顶底逻辑的三推扩展版本，应共用反转底层模块。",
            source_refs=(str((REPO_DIR / "策略资料" / "太妃价格行为" / "L14B - ✨双重顶底-✨楔形.md").resolve()), str(FOUNDATION_INDEX_PATH), str(BEST10_INDEX_PATH)),
        ),
        StrategyBlueprint(
            key="strategy_fade_breakout",
            family="区间模板",
            name="看衰突破（Fade Breakout in TR）",
            status=STRATEGY_STATUS_DESIGNED,
            summary="区间里押注突破失败并回到均衡，不适合继续放在顺势模板里。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "必须先确认是显著 TR，而不是趋势里的浅回调。", "bg_trading_range", "course_18A", "course_47A"),
                _step("key_levels", STEP_STATUS_DESIGNED, "区间上下缘、中轴、边界外止损位。", "key_prior_swing", "key_magnets"),
                _step("setup_context", STEP_STATUS_DESIGNED, "押注突破失败，而不是押注趋势延续。", "course_18B", "course_47B", "course_47C"),
                _step("signal_bar", STEP_STATUS_DESIGNED, "边界附近的失败突破证据比普通 signal 更重要。"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "折返迹象后再入场。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "若区间不够大、空间不够或真突破跟进强，就不做。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "边界外。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "要先算到中轴是不是够赚。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_DESIGNED, "中轴优先，而不是贪另一侧边线。"),
                _step("management", STEP_STATUS_DESIGNED, "偏限价/回均衡思维。"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "一旦真实跟进出现要撤。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "可做二次失败，但先不细化。"),
            ),
            tuning_notes="太妃的看衰突破可以直接放进 Brooks 的 TR 失败突破交易模板。",
            source_refs=(str((REPO_DIR / "策略资料" / "太妃价格行为" / "L15A - 区间交易-✨看衰突破.md").resolve()), str(ADVANCED_INDEX_PATH), str(PRACTICAL_INDEX_PATH)),
        ),
        StrategyBlueprint(
            key="strategy_magnet_rush",
            family="区间模板",
            name="急赴磁体（Magnet Rush）",
            status=STRATEGY_STATUS_DESIGNED,
            summary="区间里距离边线和磁体很近时，押注剩余射程内的快速触磁体。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "必须在区间背景下讨论，不是任何趋势 bar 都能做。", "bg_trading_range", "course_18A", "course_47A"),
                _step("key_levels", STEP_STATUS_DESIGNED, "磁体本身是核心：区间边线、主要波段点、昨日关键价、MM 目标。", "key_magnets", "key_session_levels", "course_19A", "course_20A"),
                _step("setup_context", STEP_STATUS_DESIGNED, "距离足够近 + 动能足够流畅 + 路径无明显阻力。", "course_19A", "course_19E"),
                _step("signal_bar", STEP_STATUS_DESIGNED, "更看动能顺滑，不必苛求反转 bar。"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "可分 stop 和收线市价。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "一旦路径上多了阻力或动能转差，就放弃。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "前波段点外或区间边线外。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "这套模板很吃距离参数。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_DESIGNED, "要急赴的那一个磁体。"),
                _step("management", STEP_STATUS_DESIGNED, "偏短路径触磁体，不应贪太远。"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "路径受阻就退出。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "不优先。"),
            ),
            tuning_notes="这套模板是太妃区间三方案之一，可直接用 Brooks 的磁体语言表达。",
            source_refs=(str((REPO_DIR / "策略资料" / "太妃价格行为" / "L15B - ✨急赴磁体-✨区间突破回调.md").resolve()), str(FOUNDATION_INDEX_PATH)),
        ),
        StrategyBlueprint(
            key="strategy_tr_breakout_pullback",
            family="区间模板",
            name="区间突破回调",
            status=STRATEGY_STATUS_DESIGNED,
            summary="太妃区间三方案中的第三套，属于突破类，但背景先是区间。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "先是区间，再有真实 breakout。", "bg_trading_range", "bg_breakout", "course_18B", "course_15A"),
                _step("key_levels", STEP_STATUS_DESIGNED, "突破位、回测位、区间边线和 MM 目标都要看。", "key_all"),
                _step("setup_context", STEP_STATUS_DESIGNED, "先有跟进，再有优质回测。", "course_15E", "course_41A", "course_41B"),
                _step("signal_bar", STEP_STATUS_DESIGNED, "重点看回测时逆势方是否衰竭。"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "常用 HL1/LH1。", "course_09A", "course_09B"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "无跟进或深回区间则失效。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "区间对侧边线外。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "应与区间高度同步评估。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_DESIGNED, "区间高度扩张或 AB=CD。", "course_20A", "course_20B"),
                _step("management", STEP_STATUS_DESIGNED, "兼具突破与回测管理。"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "测试失败就快退。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "可做二次回测，暂未细化。"),
            ),
            tuning_notes="这套模板可视为 Breakout Pullback 的区间特化版。",
            source_refs=(str((REPO_DIR / "策略资料" / "太妃价格行为" / "L15B - ✨急赴磁体-✨区间突破回调.md").resolve()), str(FOUNDATION_INDEX_PATH), str(ADVANCED_INDEX_PATH)),
        ),
        StrategyBlueprint(
            key="strategy_spike_channel_reversal",
            family="反转模板",
            name="极速与通道反转（Spike & Channel）",
            status=STRATEGY_STATUS_DESIGNED,
            summary="太妃‘极速与通道’可直接翻成 Brooks 的 spike and channel reversal。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "先有 spike，再有 channel，且动能逐步衰退。", "course_12A", "course_16A", "course_16E", "supp_channel_spike"),
                _step("key_levels", STEP_STATUS_DESIGNED, "AB=CD、昨日关键位、趋势线/通道线重叠很关键。", "key_trendline", "key_magnets", "course_20A"),
                _step("setup_context", STEP_STATUS_DESIGNED, "核心是失衡后的均衡回摆，而不是一根反向 bar。", "supp_channel_spike"),
                _step("signal_bar", STEP_STATUS_DESIGNED, "反向 bar 有存在感更好。"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "左侧可收线试驾，右侧可等趋势线突破回测。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "通道若继续健康发展则失效。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "通道极值外。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "它吃位置，不吃高频。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_DESIGNED, "通道起点或原趋势极值。"),
                _step("management", STEP_STATUS_DESIGNED, "反转模板。"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "反转跟进不足则退。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "不优先。"),
            ),
            tuning_notes="它和末端旗形可共用一部分反转底层模块，但仍应分蓝图。",
            source_refs=(str((REPO_DIR / "策略资料" / "太妃价格行为" / "L16B - ✨极速与通道-✨末端旗形.md").resolve()), str(FOUNDATION_INDEX_PATH)),
        ),
        StrategyBlueprint(
            key="strategy_final_flag",
            family="反转模板",
            name="末端旗形（Final Flag）",
            status=STRATEGY_STATUS_DESIGNED,
            summary="趋势末端的最后一次失败回调，不再恢复趋势，转而促成衰竭段与反转。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "必须先判断趋势已经接近尾端。", "course_17A", "course_23A", "course_40E", "supp_channel_spike", "supp_wedge_exhaustion"),
                _step("key_levels", STEP_STATUS_DESIGNED, "磁体、对角线、通道边线叠加最重要。", "key_magnets", "key_trendline"),
                _step("setup_context", STEP_STATUS_DESIGNED, "多数回调会恢复趋势，但最后有一次不会。", "course_23A", "course_23B", "supp_wedge_exhaustion"),
                _step("signal_bar", STEP_STATUS_DESIGNED, "末端最好有衰竭、失败突破、异色 bar。"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "左侧与右侧都可设计。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "若回调再恢复原趋势则失效。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "结构点外。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "胜率低，必须给空间。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_DESIGNED, "先看回归均衡，再看更大反转空间。"),
                _step("management", STEP_STATUS_DESIGNED, "低胜率高盈亏比模板。"),
                _step("breakeven", STEP_STATUS_PLANNED, "不宜太早。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "若失败后再次恢复原趋势，应快速认错。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "不优先。"),
            ),
            tuning_notes="这套模板属于首次回调序列的末端，不应和早期 pullback 混做。",
            source_refs=(str((REPO_DIR / "策略资料" / "太妃价格行为" / "L16B - ✨极速与通道-✨末端旗形.md").resolve()), str(FOUNDATION_INDEX_PATH), str(ADVANCED_INDEX_PATH)),
        ),
        StrategyBlueprint(
            key="strategy_wedge_mtr",
            family="反转模板",
            name="楔形 / 双顶底 / MTR",
            status=STRATEGY_STATUS_DESIGNED,
            summary="当前图表已有趋势线、通道线和磁体基础，但还没有专门的反转模板策略。",
            steps=(
                _step("background", STEP_STATUS_DESIGNED, "先判定是否进入主要趋势反转语境。", "course_21A", "course_22A", "supp_major_trend_reversal"),
                _step("key_levels", STEP_STATUS_DESIGNED, "趋势线、通道线、前高前低、磁体重叠。", "key_trendline", "key_magnets", "key_prior_swing"),
                _step("setup_context", STEP_STATUS_DESIGNED, "逆向压力积累、趋势线突破、极值不再递进、测试否决。", "course_22A", "course_22B", "course_22C", "course_22D", "supp_double_top_bottom", "supp_wedge_exhaustion"),
                _step("signal_bar", STEP_STATUS_DESIGNED, "大反转不靠单根 signal bar，但 signal bar 仍要有存在感。"),
                _step("entry_trigger", STEP_STATUS_DESIGNED, "左侧/右侧两套入口。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "若原趋势继续强势延伸则失效。"),
                _step("initial_stop", STEP_STATUS_DESIGNED, "结构外。"),
                _step("actual_risk", STEP_STATUS_DESIGNED, "要接受宽损。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_DESIGNED, "至少先回均衡或原趋势极值。"),
                _step("management", STEP_STATUS_DESIGNED, "反转模板。"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "若反转逻辑被否决则退出。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "不优先。"),
            ),
            tuning_notes=(
                "1. 这类策略要单独处理逆向压力积累、趋势线突破、极值不再递进和测试否决。\n"
                "2. 不适合继续挂在顺势模板下面。"
            ),
            source_refs=(str(FOUNDATION_INDEX_PATH), str(PRACTICAL_INDEX_PATH), str(BEST10_INDEX_PATH), str((REPO_DIR / "策略资料" / "太妃价格行为" / "L16A - 反转交易.md").resolve())),
        ),
        StrategyBlueprint(
            key="strategy_channel_tr_range",
            family="区间与通道模板",
            name="宽通道 / 交易区间边界交易",
            status=STRATEGY_STATUS_PLANNED,
            summary="当前公共背景已经能区分 Tight CH / Broad CH / Trend TR / TR，但还没有独立的区间交易模板。",
            steps=(
                _step("background", STEP_STATUS_CODED, "公共背景已能区分宽通道、趋势交易区间和震荡。", "bg_broad_channel", "bg_trending_tr", "bg_trading_range"),
                _step("key_levels", STEP_STATUS_CODED, "磁体与通道边线已接入。", "key_magnets", "key_trendline"),
                _step("setup_context", STEP_STATUS_DESIGNED, "要优先做高抛低吸、二腿陷阱和失败突破。", "course_45A", "course_46A", "course_47B", "course_47C", "supp_trading_range"),
                _step("signal_bar", STEP_STATUS_PLANNED, "待细化。"),
                _step("entry_trigger", STEP_STATUS_PLANNED, "偏限价和失败突破。"),
                _step("trigger_invalidation", STEP_STATUS_DESIGNED, "若演化成真实突破应撤。"),
                _step("initial_stop", STEP_STATUS_PLANNED, "待细化。"),
                _step("actual_risk", STEP_STATUS_PLANNED, "待细化。"),
                _step("position_leverage", STEP_STATUS_PLANNED, "待接入。"),
                _step("first_target", STEP_STATUS_PLANNED, "待细化。"),
                _step("management", STEP_STATUS_DESIGNED, "与顺势模板完全不同。"),
                _step("breakeven", STEP_STATUS_PLANNED, "待细化。"),
                _step("early_exit", STEP_STATUS_DESIGNED, "真突破出现要退。"),
                _step("reentry_addon", STEP_STATUS_PLANNED, "可做区间内二次失败，暂未细化。"),
            ),
            tuning_notes=(
                "1. 这类策略应优先做高抛低吸、限价单、二腿陷阱和失败突破。\n"
                "2. 它和顺势模板的管理方式完全不同，应单独开发。"
            ),
            source_refs=(str(ADVANCED_INDEX_PATH), str(PRACTICAL_INDEX_PATH), str(ALI_INDEX_PATH), str((REPO_DIR / "策略资料" / "太妃价格行为" / "L06A - 区间.md").resolve())),
        ),
    )

    for strategy in strategies:
        missing_keys = [
            key
            for step in strategy.steps
            for key in step.topic_keys
            if key not in topic_names
        ]
        if missing_keys:
            raise RuntimeError(f"策略蓝图 {strategy.key} 引用了不存在的知识点：{missing_keys}")

    return strategies


CHART_MAPPING_TOPICS: tuple[KnowledgeTopic, ...] = tuple(_build_chart_mapping_topics())
COMMON_COURSE_TOPICS: tuple[KnowledgeTopic, ...] = _mark_course_topics_as_partially_implemented(
    tuple(_parse_course_index(FOUNDATION_INDEX_PATH, "基础篇")),
    CHART_MAPPING_TOPICS,
)
COMMON_ADVANCED_TOPICS: tuple[KnowledgeTopic, ...] = _mark_course_topics_as_partially_implemented(
    tuple(_parse_course_index(ADVANCED_INDEX_PATH, "进阶篇")),
    CHART_MAPPING_TOPICS,
)
SUPPLEMENT_TOPICS: tuple[KnowledgeTopic, ...] = tuple(_build_supplement_topics())
KNOWLEDGE_TOPICS: tuple[KnowledgeTopic, ...] = (
    CHART_MAPPING_TOPICS
    + COMMON_COURSE_TOPICS
    + COMMON_ADVANCED_TOPICS
    + SUPPLEMENT_TOPICS
)
KNOWLEDGE_TOPIC_MAP: dict[str, KnowledgeTopic] = {topic.key: topic for topic in KNOWLEDGE_TOPICS}
STRATEGY_BLUEPRINTS: tuple[StrategyBlueprint, ...] = _build_strategy_blueprints(_topic_names_by_key(KNOWLEDGE_TOPICS))
STRATEGY_BLUEPRINT_MAP: dict[str, StrategyBlueprint] = {item.key: item for item in STRATEGY_BLUEPRINTS}
