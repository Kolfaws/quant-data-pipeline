# 每日指标

接口名称：`daily_basic`

接口说明：获取全部股票每日重要的基本面指标，可用于选股分析、报表展示等。数据在交易日每日15点～17点之间更新。单次请求最大返回6000条数据，可按日线循环提取全部历史。

积分：至少2000积分才可以调取，5000积分无总量限制，具体请参阅积分获取办法。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS股票代码（与 trade_date 二选一，通常配合使用） |
| trade_date | str | N | 交易日期（格式：YYYYMMDD） |
| start_date | str | N | 开始日期（格式：YYYYMMDD） |
| end_date | str | N | 结束日期（格式：YYYYMMDD） |

注：日期都填 YYYYMMDD 格式，比如 20181010。

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS股票代码 |
| trade_date | str | Y | 交易日期 |
| close | float | Y | 当日收盘价 |
| turnover_rate | float | Y | 换手率（%）(成交量/无限售流通股数) |
| turnover_rate_f | float | Y | 换手率（%）（自由流通股）(成交量/自由流通股数) |
| volume_ratio | float | Y | 量比 (VOL/MA) |
| pe | float | Y | 市盈率（总市值/净利润，亏损的PE为空） |
| pe_ttm | float | Y | 市盈率TTM（总市值/净利润TTM，亏损的PE为空） |
| pb | float | Y | 市净率（总市值/(净资产-其他权益工具)） |
| ps | float | Y | 市销率（总市值/营业收入(最新年报)） |
| ps_ttm | float | Y | 市销率TTM（总市值/营业收入TTM） |
| dv_ratio | float | Y | 股息率（%），除息日发生在去年期间的派现 |
| dv_ttm | float | Y | 股息率TTM（%），除息日在近12个月且分红报告期在12个月以内的派现 |
| total_share | float | Y | 总股本（万股） |
| float_share | float | Y | 流通股本（万股） |
| free_share | float | Y | 自由流通股本（万股） |
| total_mv | float | Y | 总市值（万元） |
| circ_mv | float | Y | 流通市值（万元） |
| limit_status | int | N | 收盘涨跌状态：0-平盘，1-上涨(不含涨停)，2-涨停(不含一字涨停)，3-一字涨停，4-下跌(不含跌停)，5-跌停(不含一字跌停)，6-一字跌停 |

## 接口用例

### 获取指定日期的全市场指标

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2018年7月26日 全市场的部分指标
df = pro.daily_basic(trade_date='20180726', fields='ts_code,trade_date,turnover_rate,volume_ratio,pe,pb')

# 或者使用 query 方式
df = pro.query('daily_basic', trade_date='20180726', fields='ts_code,trade_date,turnover_rate,volume_ratio,pe,pb')
```

### 获取某只股票的历史每日指标

```python
import tushare as ts

pro = ts.pro_api()

# 获取 000001.SZ 在指定时间段内的每日指标
df = pro.daily_basic(
    ts_code='000001.SZ',
    start_date='20230101',
    end_date='20231231',
    fields='ts_code,trade_date,close,pe,pb,total_mv,circ_mv'
)
```

### 获取全市场近期指标用于选股

```python
import tushare as ts

pro = ts.pro_api()

# 获取最近一个交易日的低市盈率、低市净率股票
# 注意：实际使用时需先获取最新交易日期
df = pro.daily_basic(trade_date='20231027', fields='ts_code,trade_date,pe_ttm,pb,dv_ttm')
low_pe_stocks = df[df['pe_ttm'] < 10]
```

## 数据样例

```text
    ts_code     trade_date  turnover_rate  volume_ratio        pe       pb
0     600230.SH   20180726         2.4584          0.72    8.6928   3.7203
1     600237.SH   20180726         1.4737          0.88  166.4001   1.8868
2     002465.SZ   20180726         0.7489          0.72   71.8943   2.6391
3     300732.SZ   20180726         6.7083          0.77   21.8101   3.2513
4     600007.SH   20180726         0.0381          0.61   23.7696   2.3774
5     300068.SZ   20180726         1.4583          0.52   27.8166   1.7549
```
