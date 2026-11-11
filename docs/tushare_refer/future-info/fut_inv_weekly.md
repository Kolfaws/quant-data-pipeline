# 期货交易所库存周报

接口：`fut_inv_weekly`，可以通过数据工具调试和查看数据

描述：获取上海期货交易所库存周报（其他交易所未披露）
限量：单次最大3000条，可根据代码或日期循环提取
积分：需要5000积分可以调取，具体请参阅积分获取办法

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| trade_date | str | N | 交易日期（YYYYMMDD） |
| ts_code | str | N | 期货代码 |
| start_date | str | N | 开始日期（YYYYMMDD） |
| end_date | str | N | 结束日期（YYYYMMDD） |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | 期货代码 |
| trade_date | str | Y | 交易日期（YYYYMMDD） |
| fut_name | str | Y | 品种名称 |
| exchange | str | Y | 交易所 |
| area | str | Y | 地区 |
| warehouse | str | Y | 仓库名称 |
| grade | str | Y | 品级/油种 |
| pre_total | float | Y | 上周库存小计 |
| pre_futures | float | Y | 上周库存期货 |
| cur_total | float | Y | 本周库存小计 |
| cur_futures | float | Y | 本周库存期货 |
| chg_total | float | Y | 库存增减小计 |
| chg_futures | float | Y | 库存增减期货 |
| pre_capacity | float | Y | 可用库容量上周 |
| cur_capacity | float | Y | 可用库容量本周 |
| chg_capacity | float | Y | 可用库容量增减 |
| unit | str | Y | 单位 |

## 数据样例

```text
 ts_code trade_date fut_name exchange warehouse
0         AD   20260911    铸造铝合金     SHFE        总计
1         AD   20260911    铸造铝合金     SHFE    世天威外高桥
2         AD   20260911    铸造铝合金     SHFE      中储大场
3         AD   20260911    铸造铝合金     SHFE      中储浦东
4         AD   20260911    铸造铝合金     SHFE        合计
..       ...        ...      ...      ...       ...
597       ZN   20260911        锌     SHFE     百金汇物流
598       ZN   20260911        锌     SHFE        合计
599       ZN   20260911        锌     SHFE    国储837处
600       ZN   20260911        锌     SHFE     宁波九龙仓
601       ZN   20260911        锌     SHFE      浙江田川
```
