# 大连商品交易所交易参数

接口：`fut_trade_param_dce`，可以通过数据工具调试和查看数据

描述：获取大连商品交易所交易参数数据
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
| rise_limit_rate | float | Y | 涨跌停板比例(%) |
| rise_limit | float | Y | 涨停板价格(元) |
| fall_limit | float | Y | 跌停板价格(元) |
| self_tot_buy_posi_quota | float | Y | 非期货公司会员-期货 |
| client_buy_posi_quota | float | Y | 客户-持仓限额(手)-期货 |
| self_tot_buy_posi_quota_ser_limit | float | Y | 非期货公司会员-期权 |
| client_buy_posi_quota_ser_limit | float | Y | 客户-持仓限额(手)-期权 |
| fut_code_limit | str | Y | 合约限额 |
| variety_limit | str | Y | 品种限额 |

## 数据样例

```text
 trade_date    ts_code exchange trade_type  type
0     20260914  JM2703.DCE      DCE         期货  分开限仓
1     20260914  PG2703.DCE      DCE         期货  分开限仓
2     20260914  EG2701.DCE      DCE         期货  分开限仓
3     20260914  EG2702.DCE      DCE         期货  分开限仓
4     20260914   A2707.DCE      DCE         期货  分开限仓
245   20260914   Y2703.DCE      DCE         期货  分开限仓
246   20260914   Y2705.DCE      DCE         期货  分开限仓
247   20260914  PG2701.DCE      DCE         期货  分开限仓
248   20260914  PG2702.DCE      DCE         期货  分开限仓
249   20260914   A2611.DCE      DCE         期货  分开限仓
```
