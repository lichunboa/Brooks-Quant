# Brooks Quant

基于 `vn.py` 框架做裁剪和二次开发的 `Al Brooks` 价格行为量化研究工程。

这个仓库当前只保留 Brooks 主线需要的内容：

- `brooks_chart_app/`
  - 图表审计、知识点叠加、背景层与事件层显示
- `strategies/`
  - 已落地 CTA 策略
- `backtests/`
  - 回测脚本、参数矩阵、结果导出
- `scripts/`
  - 数据导入与质量检查
- `docs/`
  - 项目自己的流程、知识点、检验清单

## 当前主线

`策略资料 -> 公用知识体系 -> Brooks图表 -> 策略蓝图 -> CTA策略 -> 回测复盘`

## 已落地 CTA 策略

- `EMA20_H2_L2`
- `H1_L1_FIRST_PULLBACK`
- `MAG20_GAP`

## 已接入图表的核心知识点

- 背景层：突破、开盘反转、午间反转、窄幅通道、宽幅通道、趋势交易区间、震荡
- 关键位置：EMA20、前高前低、趋势线 / 通道线、更高周期关键位、会话关键价
- 测量走势：Leg1=Leg2、TR MM、BO MM、Measuring Gap MM、Negative Measuring Gap、Measuring Gap middle line
- 辅助：ii / ioi / oo、微缺口、Open BOM / ORBO / Bar 18

## 运行方式

本项目默认使用 `uv`。

常用入口：

```bash
~/.local/bin/uv run python run_quant_vnpy.py
```

环境检查：

```bash
~/.local/bin/uv run python run_quant_vnpy.py --check
```

## 重要说明

- `策略资料/` 不纳入 Git 跟踪，只作为本地理论资料库。
- 本仓库使用了 `vn.py` 框架代码并做了项目内裁剪，当前目标是保持 Brooks 主线清晰，而不是保留上游完整展示内容。
- 开发中的知识点状态管理、图表叠加和检验清单都在 `Brooks图表 -> 知识点` 里统一维护。

## 相关文档

- [项目执行流程表](./docs/项目执行流程表.md)
- [Brooks 流程架构说明](./docs/brooks_流程架构说明.md)
- [Al Brooks 知识点路线清单](./docs/al_brooks_知识点路线清单.md)
- [vn.py 模块速览](./docs/vnpy_模块速览.md)
- [已开发知识点检验清单](./docs/已开发知识点检验清单.md)
