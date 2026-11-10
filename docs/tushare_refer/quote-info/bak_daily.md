# 备用行情

接口名称：`bak_daily`

接口说明：获取A股备用行情数据，包含丰富的特定行情指标（如量比、换手率、振幅、内外盘、行业地域、强弱度等）。数据始于2017年中左右，早期可能存在少量缺失，近期数据正常。

限量：单次最大返回7000行数据，可根据日期参数循环获取。

积分：正式权限需要5000积分。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | TS股票代码 |
| trade_date | str | N | 交易日期（格式：YYYYMMDD） |
| start_date | str | N | 开始日期（格式：YYYYMMDD） |
| end_date | str | N | 结束日期（格式：YYYYMMDD） |
| offset | str | N | 开始行数（用于分页） |
| limit | str | N | 最大行数（用于分页，最大7000） |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | 股票代码 |
| trade_date | str | Y | 交易日期 |
| name | str | Y | 股票名称 |
| pct_change | float | Y | 涨跌幅（%） |
| close | float | Y | 收盘价 |
| change | float | Y | 涨跌额 |
| open | float | Y | 开盘价 |
| high | float | Y | 最高价 |
| low | float | Y | 最低价 |
| pre_close | float | Y | 昨收价 |
| vol_ratio | float | Y | 量比 |
| turn_over | float | Y | 换手率（%） |
| swing | float | Y | 振幅（%） |
| vol | float | Y | 成交量（手） |
| amount | float | Y | 成交额（元） |
| selling | float | Y | 内盘（主动卖，手） |
| buying | float | Y | 外盘（主动买，手） |
| total_share | float | Y | 总股本（亿股） |
| float_share | float | Y | 流通股本（亿股） |
| pe | float | Y | 市盈率（动态） |
| industry | str | Y | 所属行业 |
| area | str | Y | 所属地域 |
| float_mv | float | Y | 流通市值（亿元） |
| total_mv | float | Y | 总市值（亿元） |
| avg_price | float | Y | 平均价 |
| strength | float | Y | 强弱度（%） |
| activity | float | Y | 活跃度（%） |
| avg_turnover | float | Y | 笔换手 |
| attack | float | Y | 攻击波（%） |
| interval_3 | float | Y | 近3月涨幅（%） |
| interval_6 | float | Y | 近6月涨幅（%） |

## 接口用例

### 获取指定日期的全市场备用行情

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2021年10月12日 的部分字段数据
df = pro.bak_daily(trade_date='20211012', fields='trade_date,ts_code,name,close,open')
```

### 获取某只股票的历史备用行情

```python
import tushare as ts

pro = ts.pro_api()

# 获取 000001.SZ 在 2023年1月的备用行情数据
df = pro.bak_daily(
    ts_code='000001.SZ',
    start_date='20230101',
    end_date='20230131'
)
```

### 获取包含行业和强弱度的选股数据

```python
import tushare as ts

pro = ts.pro_api()

# 获取某日全市场数据，用于筛选强势股
df = pro.bak_daily(
    trade_date='20231027',
    fields='ts_code,name,industry,strength,pct_change,total_mv'
)
# 筛选强弱度大于80且涨幅大于3%的股票
strong_stocks = df[(df['strength'] > 80) & (df['pct_change'] > 3)]
```

## 数据样例

```text
    ts_code     trade_date      name  close   open
0     300605.SZ   20211012  恒锋信息  14.86  12.65
1     301017.SZ   20211012  漱玉平民  25.21  20.82
2     300755.SZ   20211012  华致酒行  40.45  37.01
3     300255.SZ   20211012  常山药业   8.39   7.26
4     688378.SH   20211012   奥来德  68.62  67.00
...         ...        ...   ...    ...    ...
4533  605566.SH   20211012  福莱蒽特   0.00   0.00
```
