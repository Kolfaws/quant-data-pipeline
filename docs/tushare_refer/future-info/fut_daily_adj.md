# 期货复权行情

接口：`fut_daily_adj`，可以通过数据工具调试和查看数据

描述：获取主力合约的后复权日线行情
限量：单次最大3000条，可根据代码或日期循环提取
积分：需要5000积分可以调取，具体请参阅积分获取办法

## 注意

复权数据是参考股票计算，在主力合约切换时以新的合约和旧的合约的收盘价相比得出

主力发生变化的交易日:
每个切换点 k 取切换前一日新旧主力的同日收盘价之比 `r_k = C_new / C_old`（C 取 raw_1day 当日真实收盘），
复权因子从最早段起为 1.0，每越过一个切换点累乘 `1/r_k`：
切换前段（首日 .. 第一个切换前一日）：adj = 1.0；
第 k 段（第 k 次切换日及之后，直到下一个切换）：adj = Π_{j<=k} (1/r_j)。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| trade_date | str | N | 交易日期（格式：YYYYMMDD） |
| ts_code | str | N | 合约代码 |
| exchange | str | N | 交易所代码(CFFEX,CZCE,DCE,GFEX,INE,SHFE) |
| start_date | str | N | 开始日期（格式：YYYYMMDD） |
| end_date | str | N | 结束日期（格式：YYYYMMDD） |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS代码 |
| trade_date | str | Y | 交易代码 |
| pre_close | float | Y | 昨收盘价 |
| pre_settle | float | Y | 昨结算价 |
| open | float | Y | 开盘价 |
| high | float | Y | 最高价 |
| low | float | Y | 最低价 |
| close | float | Y | 收盘价 |
| settle | float | Y | 结算价 |
| change1 | float | Y | 涨跌1,收盘价-昨结算价 |
| change2 | float | Y | 涨跌2,结算价-昨结算价 |
| vol | float | Y | 成交量(手) |
| amount | float | Y | 成交金额(万元) |
| oi | float | Y | 持仓量(手) |
| oi_chg | float | Y | 持仓量变化 |
| delv_settle | float | N | 交割结算价 |
| exchange | str | Y | 交易所 |

## 数据样例

```text
    ts_code trade_date   pre_close  pre_settle
0      IF.CFX   20260907   7188.6210   7186.4029
1     IFL.CFX   20260907   7357.1309   7354.8609
2    IFL1.CFX   20260907   5168.7921   5166.7294
3    IFL2.CFX   20260907   5696.1245   5694.8457
4    IFL3.CFX   20260907   4386.6971   4384.8949
..        ...        ...         ...         ...
195    YL.DCE   20260907   2551.8884   2537.1713
196    ZC.ZCE   20260907   2381.9820   2381.9820
197   ZCL.ZCE   20260907   1057.3599   1057.3599
198    ZN.SHF   20260907  30220.9139  30220.9139
199   ZNL.SHF   20260907  34471.3651  34503.6296
```
