# ES 数据接入选型

## 当前结论

- 目标如果是和 Al Brooks 百科、课程截图、Ali 实战案例做细粒度对照，`US500 CFD` 不是最终基准，`ES.CME` 才是更合适的主线。
- 真正“免费 + 高质量 + 1 分钟级 + 长历史 + 稳定可重复”的 `ES` 历史数据，当前基本拿不到。
- 原因不是代码问题，而是 `ES` 属于 `CME` 授权数据，分钟级和逐笔级历史通常受许可和平台限制。

## 为什么不建议继续把 US500 当最终基准

- `US500.OTC` 是 `CFD`，交易时段、维护时段、成交量语义都和 `ES` 不一样。
- Brooks 课程和百科里最常见的是 `E-mini S&P 500` 的日内语境，尤其是：
  - 开盘区间
  - 午间反转
  - ORBO
  - 日内两波与 Measuring Gap
- 这些知识点一旦进入精细验证，`CFD 24 小时连续图` 会持续造成语境偏差。

## 现阶段推荐顺序

### 方案 1：IBKR + CME 订阅

- 适合你后续长期做 Brooks 图表审计、手工复盘和策略补数。
- 优点：
  - 真实期货交易语境更接近目标
  - 能直接服务后续 `ES` 图表和 CTA 优化
  - 和你现在本地研究流程比较容易衔接
- 不足：
  - 不是免费
  - 历史范围和 API 细节要受券商规则约束
- 适用结论：
  - 如果你要长期做 `ES` 优化，这是最稳的主线

### 方案 2：Databento

- 适合一次性补较长历史，或者要稳定导出统一格式再落库。
- 优点：
  - 历史数据产品化程度高
  - 批量下载、导出、重建本地库更方便
  - 更适合做一段时间范围较长的批量研究
- 不足：
  - 不是免费
  - 仍然受交易所授权和套餐限制
- 适用结论：
  - 如果你更看重“批量历史整理”和“统一数据生产流程”，它比券商接口更顺手

### 方案 3：CME DataMine

- 适合补正式、很久的历史档案。
- 优点：
  - 来源最靠近交易所官方历史产品
- 不足：
  - 成本最高
  - 对我们现在这条“先验证知识点与图表”的主线来说偏重
- 适用结论：
  - 现在不作为第一选择

## 免费方案怎么判断

- 如果你要求：
  - 免费
  - 高质量
  - 1 分钟或更细
  - 长历史
  - 可持续复现
- 我的判断是：当前没有合格主方案。

能找到的一些“免费 ES 数据”通常有这些问题：

- 只有日线或结算口径
- 分钟历史很短
- 连续合约拼接规则不透明
- 交易时段和维护时段说明不完整
- 无法稳定复现

所以它们可以做临时参考，但不适合做你后面要的优化系统基准。

## 仓库内的落地口径

- 仓库内部统一符号：`ES`
- 统一交易所：`CME`
- 先把外部平台导出的分钟线 `CSV` 落到本地 DuckDB
- 统一通过：
  [`/Users/mitchellcb/Desktop/量化交易vnpy/scripts/import_generic_csv_to_duckdb.py`](/Users/mitchellcb/Desktop/量化交易vnpy/scripts/import_generic_csv_to_duckdb.py)
  导入
- 导入后再用：
  [`/Users/mitchellcb/Desktop/量化交易vnpy/scripts/check_bar_data_quality.py`](/Users/mitchellcb/Desktop/量化交易vnpy/scripts/check_bar_data_quality.py)
  做质量检查

推荐命令：

```bash
cd /Users/mitchellcb/Desktop/量化交易vnpy
uv run python scripts/import_generic_csv_to_duckdb.py \
  --csv /绝对路径/es_1m.csv \
  --symbol ES \
  --exchange CME \
  --interval 1m \
  --datetime-column datetime \
  --open-column open \
  --high-column high \
  --low-column low \
  --close-column close \
  --volume-column volume \
  --timezone UTC \
  --database-file database_import_staging.duckdb

uv run python scripts/check_bar_data_quality.py --symbols ES --interval 1m --database-file database_import_staging.duckdb
```

## 当前建议

- `US500.OTC` 已从主库移除，不再作为当前主线研究样本。
- 同时尽快补 `ES.CME 1m` 数据。
- 等 `ES` 数据落库后，再做：
  - `Leg1=Leg2`
  - `Measuring Gap MM`
  - `Opening Reversal`
  - `Midday Reversal`
  的百科逐图核对。

## 外部资料

- CME 历史数据产品：
  [CME DataMine](https://www.cmegroup.com/market-data/datamine-historical-data.html)
- IBKR 历史数据接口：
  [Interactive Brokers Historical Bars](https://interactivebrokers.github.io/tws-api/historical_bars.html)
- Nasdaq Data Link 文档：
  [Nasdaq Data Link Docs](https://docs.data.nasdaq.com/)
- Databento 期货资料：
  [Databento Futures](https://databento.com/futures)
