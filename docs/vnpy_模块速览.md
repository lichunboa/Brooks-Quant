# vn.py 模块速览

## 你现在最该怎么用

如果目标是按 `Al Brooks` 体系做单品种策略开发和回测，建议主线就三步：

1. 用 `DataManager` 或脚本把历史数据准备好
2. 用 `CTA回测` 做参数研究、回测和优化
3. 用 `Brooks图表` 做信号和成交审计

策略稳定以后，再决定是否进入 `CTA策略` 做实盘或仿真运行。

## 当前我们已经很好利用的模块

- `CTA回测`
  - 已作为主研究入口
  - 适合你当前按 Brooks 蓝图做策略回测
- `CTA策略`
  - 已用于承接真正落地成 `CtaTemplate` 的策略
- `DataManager`
  - 已作为本地数据集入口
- `RiskManager`
  - 启动链路里已接入
- `DataRecorder`
  - 已在启动链路里保留，后续适合持续录实盘数据
- `Brooks图表`
  - 这是你这个仓库自定义加的审计层，不是 vn.py 原生模块，但已经接进主终端

## 当前没必要急着用、但属于成熟可用模块

- `PaperAccount`
  - 适合以后做纸面仿真，不是当前研究主线
- `ChartWizard`
  - 适合纯看图，不带 Brooks 审计逻辑
- `AlgoTrading`
  - 偏执行算法，不适合当前知识点补全阶段
- `PortfolioStrategy`
  - 做多品种组合时再用
- `PortfolioManager`
  - 做组合看板时再用
- `SpreadTrading`
  - 只在价差策略时有意义

## 当前看到的“别的 CTA 策略”是什么

你在 CTA 里看到的许多策略，不是这个项目自己写的，而是 `vnpy_ctastrategy` 包自带的示例策略。

典型包括：

- `atr_rsi_strategy.py`
- `boll_channel_strategy.py`
- `double_ma_strategy.py`
- `dual_thrust_strategy.py`
- `king_keltner_strategy.py`
- `multi_signal_strategy.py`
- `multi_timeframe_strategy.py`
- `turtle_signal_strategy.py`

它们的主要作用是：

- 参考 `CtaTemplate` 写法
- 参考参数暴露方式
- 参考持仓管理写法

但它们不属于你的 Brooks 策略体系，不需要并入当前主线。

## 一个要点

当前最值得继续“复用成熟模块”的方向，不是再引入更多策略示例，而是继续沿用：

- `CTA回测` 做研究
- `CTA策略` 承接已落地蓝图
- `DataManager`/`DataRecorder` 负责数据
- `RiskManager` 做统一风控外壳

## 左边栏常见模块

### 主开发主线

- `CTA回测`
  - 图形化做单策略回测、参数优化、成交明细分析
  - 你现在做研究，优先用它
- `CTA策略`
  - 把已经写好的 `CtaTemplate` 策略实例化，初始化、启动、停止
  - 更偏向运行策略，不是主要研究入口
- `Brooks图表`
  - 这是这个仓库自定义加的图表审计工具
  - 适合核对 H1/H2/L1/L2、背景、生命周期、成交位置

### 数据相关

- `DataManager`
  - 看本地数据库里已经有什么历史数据
  - 做导入、导出、删除、下载
- `DataRecorder`
  - 连接实盘接口后，把实时 `Tick` 或 `Bar` 录到本地库
  - 适合后续持续积累自己的数据
- `ChartWizard`
  - 通用图表查看工具
  - 不带 Brooks 审计逻辑

### 交易执行相关

- `AlgoTrading`
  - 算法执行模块，偏下单执行，不是你当前主线
- `RiskManager`
  - 做委托频率、撤单次数、总成交量等风控限制
- `PaperAccount`
  - 纸面账户，用来模拟资金和持仓

### 多品种或结构化策略

- `PortfolioStrategy`
  - 多合约组合策略
  - 做跨品种协同、篮子、组合逻辑时才需要
- `PortfolioManager`
  - 组合维度的持仓和盈亏看板
- `SpreadTrading`
  - 价差交易专用，不适合你现在这套 Brooks 单图单品种策略主线

## 你现在的建议工作流

- 数据准备：
  先跑
  [`/Users/mitchellcb/Desktop/量化交易vnpy/scripts/import_dukascopy_to_duckdb.py`](/Users/mitchellcb/Desktop/量化交易vnpy/scripts/import_dukascopy_to_duckdb.py)
  和
  [`/Users/mitchellcb/Desktop/量化交易vnpy/scripts/import_binance_spot_to_duckdb.py`](/Users/mitchellcb/Desktop/量化交易vnpy/scripts/import_binance_spot_to_duckdb.py)
- 质量复查：
  跑
  [`/Users/mitchellcb/Desktop/量化交易vnpy/scripts/check_bar_data_quality.py`](/Users/mitchellcb/Desktop/量化交易vnpy/scripts/check_bar_data_quality.py)
- 策略开发：
  把策略文件放在
  [`/Users/mitchellcb/Desktop/量化交易vnpy/strategies`](/Users/mitchellcb/Desktop/量化交易vnpy/strategies)
- 回测研究：
  用 `CTA回测` 或 `backtests/` 里的脚本
- 审计：
  回测后回到 `Brooks图表` 看信号、成交和生命周期

## 一句话结论

- 研究开发和回测：以 `CTA回测` 为主
- 稳定后运行：再进 `CTA策略`
- 你当前这套 Brooks 工作流里，`Brooks图表` 是审计层，不替代回测层
