# 每日涨跌停价格

接口名称：`stk_limit`

接口说明：获取全市场（包含A股、B股和基金）每日的涨停价格和跌停价格。数据始于2007-01-04，每个交易日9点左右更新当日股票的涨跌停价格。

限量：单次最多提取5800条记录，可循环调取，总量不限制。

积分：用户积2000积分可调取。单位分钟有流控，积分越高流量越大，请自行提高积分，具体请参阅积分获取办法。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | TS股票代码 |
| trade_date | str | N | 交易日期（格式：YYYYMMDD） |
| start_date | str | N | 开始日期（格式：YYYYMMDD） |
| end_date | str | N | 结束日期（格式：YYYYMMDD） |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| trade_date | str | Y | 交易日期 |
| ts_code | str | Y | TS股票代码 |
| pre_close | float | N | 昨日收盘价 |
| up_limit | float | Y | 涨停价 |
| down_limit | float | Y | 跌停价 |
| asset_type | str | N | 资产类型，通常为 STK |
| exchange | str | N | 交易所代码：SSE (上交所), SZSE (深交所), BSE (北交所) |

## 接口用例

### 获取指定日期的全市场涨跌停价格

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2019年6月25日 全部股票的涨跌停价格
df = pro.stk_limit(trade_date='20190625')
```

### 获取某只股票历史区间的涨跌停价格

```python
import tushare as ts

pro = ts.pro_api()

# 获取 002149.SZ 从 2019年1月15日到 2019年6月15日的涨跌停价格
df = pro.stk_limit(ts_code='002149.SZ', start_date='20190115', end_date='20190615')
```

### 获取近期数据用于监控

```python
import tushare as ts

pro = ts.pro_api()

# 获取最近一个交易日的涨跌停数据，用于判断市场情绪或个股状态
# 注意：实际使用时需替换为最新的交易日期
df = pro.stk_limit(trade_date='20231027')
```

## 数据样例

```text
     trade_date    ts_code  up_limit  down_limit
0      20190625  000001.SZ     15.06       12.32
1      20190625  000002.SZ     30.94       25.32
2      20190625  000004.SZ     25.15       20.57
3      20190625  000005.SZ      3.49        2.85
4      20190625  000006.SZ      6.14        5.02
5      20190625  000007.SZ      7.74        6.34
```
