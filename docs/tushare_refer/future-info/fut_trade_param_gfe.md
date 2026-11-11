# 广州期货交易参数

接口：`fut_trade_param_gfe`，可以通过数据工具调试和查看数据

描述：获取广州期货交易参数数据
限量：单次最大3000条，可根据代码或日期循环提取
积分：需要5000积分可以调取，具体请参阅积分获取办法

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | 期货代码 |
| trade_date | str | N | 交易日期（YYYYMMDD） |
| start_date | str | N | 开始日期（YYYYMMDD） |
| end_date | str | N | 结束日期（YYYYMMDD） |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | 合约代码或类型 |
| trade_date | str | Y | 交易日期（YYYYMMDD） |
| exchange | str | Y | 期货公司会员简称 |
| trade_type | str | Y | 交易类型 |
| type | str | Y | 限仓模式 |
| spec_buy_rate | float | Y | 投机买保证金率(%) |
| spec_buy | float | Y | 投机买保证金金额(元/手) |
| hedge_buy_rate | float | Y | 套保买保证金率(%) |
| hedge_buy | float | Y | 套保买保证金金额(元/手) |
| rise_limit_rate | float | Y | 涨停板比例(%) |
| rise_limit | float | Y | 涨停板价格(元) |
| fall_limit | float | Y | 跌停板价格(元) |
| agent_tot_buy_posi_quota | float | Y | 经纪会员总买持仓限额(手) |
| self_tot_buy_posi_quota | float | Y | 自营总买持仓限额(手) |
| client_buy_posi_quota | float | Y | 客户买持仓限额(手) |
| self_tot_buy_ser_limit | float | Y | 自营总买限仓(手) |
| client_buy_ser_limit | float | Y | 客户买限仓(手) |

## 数据样例

```text
  trade_date             ts_code trade_type  spec_buy
0      20260924     PD2708-C-260.GFE         期权  119328.0
1      20260924     PT2702-P-288.GFE         期权   36122.0
2      20260924  LC2705-C-154000.GFE         期权   15367.5
3      20260924  LC2705-C-156000.GFE         期权   14997.5
4      20260924  LC2611-C-106000.GFE         期权   40110.0
2995   20260924     PT2702-C-680.GFE         期权   36122.0
2996   20260924     PT2702-C-688.GFE         期权   35972.0
2997   20260924     PT2702-C-696.GFE         期权   35822.0
2998   20260924     PT2702-C-704.GFE         期权   35672.0
2999   20260924     PT2702-C-712.GFE         期权   35572.0
```
