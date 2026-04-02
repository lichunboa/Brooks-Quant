# Brooks 图表到策略的流程架构说明

## 目标

把当前项目里“资料 -> 知识点 -> 图表 -> 策略 -> 回测”的主干流程讲清楚，避免后续继续开发时，被看不见的旧分支、旧口径污染。

## 当前六层

### 1. 资料层

- 原课程大纲：
  `/Users/mitchellcb/Desktop/量化交易vnpy/策略资料/al brooks参考资料agent专用版 /AL brooks原课程大纲.md`
- 基础篇、进阶篇章节索引
- 百科主题总索引 / 实战主题总索引
- Ali Flash Cards / 10 Best Patterns
- 太妃课程笔记

这一层只负责理论来源，不负责代码逻辑。

### 2. 公用知识体系层

- 由 `brooks_chart_app/catalog.py` 组织。
- 先按课程大纲解析基础篇 `01-36`、进阶篇 `37-52`。
- 再补 `图表映射` 和 `百科/Ali 实战补充`。

这一层是公共底座，不绑定某一个策略。

### 3. 图表映射与审计层

- 入口在 `brooks_chart_app/logic.py` 和 `brooks_chart_app/ui.py`。
- 主链路：
  - `analyze_brooks_context()`
  - `brooks_chart_app/setup_engine.py`
  - `build_brooks_annotations()`
  - 图表展示 / 知识点叠加 / 审核记录

这一层负责把公共概念映射到图表上，让人能核对背景、事件、关键位置和信号。

### 4. 策略开发蓝图层

- 入口在 `brooks_chart_app/catalog.py` 的 `StrategyBlueprint`。
- 每个策略都按固定 14 步流程模板组织：
  - 背景
  - 关键位置
  - setup 前提
  - signal bar 类型
  - entry trigger
  - 触发失效
  - 初始止损类型
  - 实际风险
  - 仓位与杠杆
  - 第一目标
  - partial / scalp / swing
  - BE 条件
  - 提前离场
  - re-entry / add-on

这一层只做策略蓝图和微调方向，不直接下单。

### 5. CTA 策略执行层

- 入口在 `strategies/`。
- 当前真正接入 CTA 的只有：
  - `ema20_h2_l2_trend_strategy.py`
  - `h1_l1_first_pullback_strategy.py`
  - `mag_20_gap_strategy.py`

这一层负责把某个蓝图真正落成 `CtaTemplate` 策略。
当前 CTA 层的 setup 候选也已经复用 `brooks_chart_app/setup_engine.py`，不再各自手写一套状态机。

### 6. 回测 / 导出 / 复盘层

- 入口在：
  - `backtests/`
  - `cta_backtester_sync.py`
  - `backtest_result_utils.py`
- 负责回测、结果导出、生命周期整理、图表复盘读取。
- 所有回测必须调用 `vnpy_ctastrategy.BacktestingEngine` 或图形界面的 `CTA回测`。
- 禁止自写独立撮合引擎、自写回测收益计算引擎来替代 CTA 回测层。

## 当前主干是否单一

结论：主干是单一且顺畅的。

当前公共主干是：

`资料层 -> 公用知识体系 -> 图表映射 -> 策略蓝图 -> CTA策略 -> 回测/复盘`

目录层、图表层、策略层、回测层现在已经各自分工明确，不再像之前那样把“公用知识点”和“单个策略执行流程”混在一起。

## 当前仍然存在的一处分叉

当前唯一需要明确写出来的分叉是：

- `图表信号生成`
  - 在 `brooks_chart_app/logic.py`
  - 通过 `build_brooks_annotations()` 调用共享候选生成
- `CTA 策略信号生成`
  - 在 `strategies/*.py`
  - 在 `on_signal_bar()` 里挑选共享候选生成待触发单

这两条分支已经共享同一个背景分析入口：

- `analyze_brooks_context()`
- `is_signal_context_supported()`
- `brooks_chart_app/setup_engine.py`

所以它们不是“隐形旧分支”，而是“已暴露、已收敛到同一背景层，并且 setup 候选已经抽成共享模块”。

后续如果还要继续收口，最值得做的是把候选生成之后的触发与管理逻辑也进一步模块化。

## 知识点协作原则

图表知识点不能各算各的。

当前应该优先复用这些公共底座：

- `analyze_brooks_context()`
  - 提供结构层、事件层、更高周期方向。
- `EMA20`
  - 作为均值、回调深浅和优势侧参考。
- `前高前低 / 波段摆点`
  - 作为 Leg、Double Top/Bottom、楔形和 MM 的骨架。
- `趋势线 / 通道线`
  - 作为结构边界和目标位过滤。
- `会话关键价 / 开盘区间`
  - 作为日内语境过滤。

以 `Leg1=Leg2` 为例，当前不再只靠“三个摆点”单独计算，而是同时参考：

- 摆点序列
- 当前结构背景
- EMA20 附近回调
- 回调深度
- 突破事件层 / Measuring Gap 语境

以 `Opening Reversal / Midday Reversal` 为例，当前也不再单独算一套状态，而是接进共同事件层：

- 开盘区间 / Open BOM
- EMA20
- 最近几根 bar 的单边推进
- 当前会话内的局部极值与反向夺回

这样做的目的是：

- 避免同一图上大量无语境的 MM 乱画
- 避免每个知识点都维护自己的背景判断
- 避免 UI 层和逻辑层重复维护相同的会话分组、结构分组规则

后续新知识点默认都要先问 2 个问题：

1. 它能不能复用已有背景层、关键位置层和会话层？
2. 它是不是在 UI 层重复做了逻辑层已经做过的事情？

如果答案分别是“能”和“是”，就优先复用与去重，而不是再写一套独立算法。

## 关于 UI 里的“信号类型”

当前下拉框筛选的是：

- `H1`
- `H2`
- `L1`
- `L2`
- `MAG`

它们不是抽象的“类型”，更接近：

- 建仓信号
- setup 家族
- 策略信号家族

因此 UI 已改名为 `建仓信号`，避免和公共知识点里的“信号 bar 类型”混淆。

## 下一步建议

下一窗口继续做知识点补全时，建议遵守这条顺序：

1. 只补 `公用知识体系`
2. 需要策略化时，只去改 `策略开发蓝图`
3. 决定落地某个策略后，再写 `strategies/*.py`
4. 最后再接入回测与图表审计

这样就不会再把公共知识点和策略模板搅在一起。
