# Brooks 图表标注说明

## 用途

这个本地应用的目标不是替代完整策略回测，而是把 `EMA20 + H2/L2 + signal bar + entry/stop/target` 直接标到 K 线上，方便只看图也能核对规则。

显示内容包括：

- `EMA20`
- `H2` / `L2` 标签
- signal bar 高亮框
- `入场` / `止损` / `目标` 水平线

## 理论来源

本实现的理论支持来自桌面另一个项目中的原始资料：

- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /1.《价格行为学》（基础篇1-36章）/pages/page-0413.md`
- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /1.《价格行为学》（基础篇1-36章）/pages/page-0414.md`
- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /1.《价格行为学》（基础篇1-36章）/pages/page-0436.md`
- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /1.《价格行为学》（基础篇1-36章）/pages/page-0437.md`
- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /1.《价格行为学》（基础篇1-36章）/pages/page-1432.md`
- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /1.《价格行为学》（基础篇1-36章）/pages/page-1522.md`
- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /1.《价格行为学》（基础篇1-36章）/pages/page-1676.md`
- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /1.《价格行为学》（基础篇1-36章）/pages/page-1876.md`
- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /1.《价格行为学》（基础篇1-36章）/pages/page-1926.md`
- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /1.《价格行为学》（基础篇1-36章）/pages/page-2528.md`
- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /1.《价格行为学》（基础篇1-36章）/pages/page-2609.md`
- `../量化交易Evo/策略资料/al brooks参考资料agent专用版 /2.《价格行为学》（进阶篇37-52章）/pages/page-0285.md`

## 重要说明

这个标注器是为了“程序化近似 + 图表核对”，不是宣称已经完整复刻 Brooks 的全部语境判断。

它当前采用的约束是：

- 大周期只作为背景，不机械否决当前周期
- H2 / L2 只取 `EMA20` 附近的顺势 setup
- signal bar 需要达到最低质量要求
- entry 采用 signal bar 外一跳的 stop 触发
- stop 使用 signal bar stop
- target 优先取最近磁点，否则退化为 `2R`

## 后续扩展方向

后续可以继续补：

- 更细的 `H1/H2/L1/L2` 统计
- `MTR` 标注
- `gap setup` 标注
- 更强的目标位优先级排序
- 策略信号与实际成交对照
