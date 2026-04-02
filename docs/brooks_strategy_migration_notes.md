# Brooks 策略迁移说明

## 已确认的旧策略主线

来源目录：

- `/Users/mitchellcb/Desktop/AB_回测通过策略整理_20260331`

核心结论：

1. `H1/L1`
2. `H2/L2`
3. `MAG 20/20 Setup`

## 旧代码主要位置

- `H1/L1`
  - `services/signal-service/src/engines/pa/h1_l1_template.py`
  - `services/signal-service/src/engines/pa/trend_recovery.py`
  - `services/signal-service/src/engines/pa/signal_bar.py`
- `H2/L2`
  - `services/signal-service/src/engines/pa/h2_l2_template.py`
  - `services/signal-service/src/engines/pa/breakout_pullback_template.py`
  - `services/signal-service/src/engines/pa/structure_stops.py`
- `MAG`
  - `services/signal-service/src/engines/pa/ema_gap_template.py`
  - `services/signal-service/src/engines/pa/strategy_advanced.py`

## 新 vn.py 仓库中的对应文件

- `H1/L1` 首版：
  - `/Users/mitchellcb/Desktop/量化交易vnpy/strategies/h1_l1_first_pullback_strategy.py`
- `H2/L2` 首版：
  - `/Users/mitchellcb/Desktop/量化交易vnpy/strategies/ema20_h2_l2_trend_strategy.py`
- `MAG 20/20` 首版：
  - `/Users/mitchellcb/Desktop/量化交易vnpy/strategies/mag_20_gap_strategy.py`

## 当前状态

- `H2/L2`
  - 已接入回测、优化、图表审计。
- `H1/L1`
  - 已建立首版策略文件，并已接入 CTA 回测；后续重点是补“首次回调序列位置”和更细的管理逻辑。
- `MAG 20/20`
  - 已建立首版策略文件，并已接入 CTA 回测与图表审计。

## 原则

- 不沿用旧系统的软件层、服务层和桥接层设计。
- 只保留其中符合 Al Brooks 理论的策略语义。
- 在新 `vn.py` 仓库里按“策略源码 + 回测 + 图表审计”重构。
