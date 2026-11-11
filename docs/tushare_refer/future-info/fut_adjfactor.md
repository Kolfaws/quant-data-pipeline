# 期货复权因子

接口：`fut_adjfactor`，可以通过数据工具调试和查看数据

描述：获取主力合约的复权因子
限量：单次最大3000条，可根据代码或日期循环提取
积分：需要5000积分可以调取，具体请参阅积分获取办法

## 注

前复权行情：当日收盘价 × 当日复权因子 / 最新复权因子
后复权行情：当日收盘价 × 当日复权因子 也可以直接取期货复权行情

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| trade_date | str | N | 交易日期（YYYYMMDD） |
| ts_code | str | N | 合约代码 |
| exchange | str | N | 交易所代码 |
| start_date | str | N | 开始日期（YYYYMMDD） |
| end_date | str | N | 结束日期（YYYYMMDD） |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | 股票代码 |
| exchange | str | Y | 交易所 |
| trade_date | str | Y | 交易日（YYYYMMDD） |
| adj_factor | float | Y | 累计复权因子 |

## 数据样例

```text
   ts_code exchange trade_date adj_factor
0    A.DCE      DCE   20261012   0.877641
1   AD.SHF     SHFE   20261012   0.976876
2  ADL.SHF     SHFE   20261012   1.014848
3   AG.SHF     SHFE   20261012   0.670013
4  AGL.SHF     SHFE   20261012   0.528900
5   AL.DCE      DCE   20261012   0.401399
6   AL.SHF     SHFE   20261012   0.708825
7  ALL.SHF     SHFE   20261012   1.081992
8   AO.SHF     SHFE   20261012   1.022086
9  AOL.SHF     SHFE   20261012   0.842868
```
