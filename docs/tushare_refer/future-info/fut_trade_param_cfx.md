# 中金期货交易参数

接口：`fut_trade_param_cfx`，可以通过数据工具调试和查看数据

描述：获取中金期货交易参数数据
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
| trade_month | str | Y | 交易月份 |
| listing_date | str | Y | 上市日期 |
| product_id | str | Y | 产品id |
| upper_limit | str | Y | 涨停板幅度(%) |
| lower_limit | str | Y | 跌停板幅度(%) |
| end_trade_date | str | Y | 最后交易日 |
| basis_price | str | Y | 挂盘基准价 |
| long_limit | str | Y | 持仓限额 |
| upper_limit_price | str | Y | 涨停板价位 |
| lower_limit_price | str | Y | 跌停板价位 |

## 数据样例

```text
   trade_date           ts_code upper_limit_price lower_limit_price
0     20260914  IO2703-C-4100.CFX             823.2               0.2
1     20260914  MO2610-P-8300.CFX            1718.6             233.4
2     20260914         IM2612.CFX            7890.2            6455.8
3     20260914         IM2703.CFX            7654.0            6262.4
4     20260914  HO2609-C-2700.CFX             454.8               0.2
711   20260914         TL2703.CFX             119.8             111.7
712   20260914         TL2706.CFX            123.85            107.65
713   20260914  MO2610-P-8100.CFX            1531.2              46.0
714   20260914  MO2610-P-8200.CFX            1623.6             138.4
715   20260914  HO2609-C-2500.CFX             653.6              80.0
```
