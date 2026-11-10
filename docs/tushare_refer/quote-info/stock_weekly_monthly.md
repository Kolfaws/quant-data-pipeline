# 股票周/月线行情(每日更新)

接口名称：`stk_weekly_monthly`

接口说明：股票周/月线行情数据，每日更新。返回结果为未复权行情；如需前复权、后复权行情，请使用通用行情接口 `pro_bar`。

限量：单次最大 6000 条，可使用交易日期循环提取，总量不限制。

积分：用户需要至少 2000 积分才可以调取，具体请参阅积分获取办法。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | TS代码 |
| trade_date | str | N | 交易日期，格式：YYYYMMDD。填写每周或每月最后一个交易日的日期 |
| start_date | str | N | 开始交易日期 |
| end_date | str | N | 结束交易日期 |
| freq | str | Y | 频率：week 表示周线，month 表示月线 |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | 股票代码 |
| trade_date | str | Y | 交易日期 |
| end_date | str | Y | 计算截至日期 |
| freq | str | Y | 频率，week 表示周，month 表示月 |
| open | float | Y | 周/月开盘价 |
| high | float | Y | 周/月最高价 |
| low | float | Y | 周/月最低价 |
| close | float | Y | 周/月收盘价 |
| pre_close | float | Y | 上一周/上一月收盘价 |
| vol | float | Y | 周/月成交量 |
| amount | float | Y | 周/月成交额 |
| change | float | Y | 周/月涨跌额 |
| pct_chg | float | Y | 周/月涨跌幅，未复权。如需复权涨跌幅，请使用通用行情接口 |

## 接口用例

### 获取指定周线行情

```python
import tushare as ts

pro = ts.pro_api()

# 获取 20251024 这周的周线数据
df = pro.stk_weekly_monthly(trade_date='20251024', freq='week')
```

### 获取指定月线行情

```python
import tushare as ts

pro = ts.pro_api()

# 获取 202510 月的月线数据
df = pro.stk_weekly_monthly(trade_date='20251031', freq='month')
```

### 获取某只股票的周线行情

```python
import tushare as ts

pro = ts.pro_api()

# 获取 000001.SZ 一段时间内的周线数据
df = pro.stk_weekly_monthly(
    ts_code='000001.SZ',
    start_date='20250101',
    end_date='20251024',
    freq='week'
)
```

### 获取某只股票的月线行情

```python
import tushare as ts

pro = ts.pro_api()

# 获取 000001.SZ 一段时间内的月线数据
df = pro.stk_weekly_monthly(
    ts_code='000001.SZ',
    start_date='20250101',
    end_date='20251031',
    freq='month'
)
```

## 数据样例

```text
            ts_code trade_date  end_date  ...      amount  change  pct_chg
    0     600137.SH   20251024  20251023  ...   429206.49    2.18    11.93
    1     600236.SH   20251024  20251023  ...   510772.77    0.25     3.49
    2     301262.SZ   20251024  20251023  ...  1140060.52    5.69    24.69
    3     600114.SH   20251024  20251023  ...  1786514.91   -0.41    -1.39
    4     301509.SZ   20251024  20251023  ...   225023.73    0.47     1.34
    ...         ...        ...       ...  ...         ...     ...      ...
    5432  301195.SZ   20251024  20251023  ...   186490.18    1.86     5.66
```
