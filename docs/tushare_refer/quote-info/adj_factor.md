# 复权因子

接口名称：`adj_factor`

接口说明：获取股票的复权因子数据。该接口由 Tushare 自行生产，支持提取单只股票的全部历史复权因子，也可以提取指定交易日全市场所有股票的复权因子。复权因子是计算前复权和后复权价格的基础数据。

更新时间：盘前 9:15 ~ 9:20 完成当日复权因子入库。

积分要求：2000 积分起调，5000 积分以上可高频调取。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | TS代码 |
| trade_date | str | N | 交易日期（格式：YYYYMMDD） |
| start_date | str | N | 开始日期（格式：YYYYMMDD） |
| end_date | str | N | 结束日期（格式：YYYYMMDD） |

注：日期均填写 YYYYMMDD 格式，例如 20181010。

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | 股票代码 |
| trade_date | str | Y | 交易日期 |
| adj_factor | float | Y | 复权因子 |

## 接口用例

### 获取单只股票全部历史复权因子

```python
import tushare as ts

pro = ts.pro_api()

# 提取 000001.SZ 的全部历史复权因子
df = pro.adj_factor(ts_code='000001.SZ')
```

### 获取指定日期的全市场复权因子

```python
import tushare as ts

pro = ts.pro_api()

# 提取 2018年7月18日 所有股票的复权因子
df = pro.adj_factor(trade_date='20180718')

# 或者使用 query 方式
df = pro.query('adj_factor', trade_date='20180718')
```

### 获取指定时间区间的复权因子

```python
import tushare as ts

pro = ts.pro_api()

# 提取 000001.SZ 在 2018年1月1日至2018年12月31日 期间的复权因子
df = pro.adj_factor(
    ts_code='000001.SZ',
    start_date='20180101',
    end_date='20181231'
)
```

## 数据样例

```text
        ts_code trade_date  adj_factor
0     000001.SZ   20180809     108.031
1     000001.SZ   20180808     108.031
2     000001.SZ   20180807     108.031
3     000001.SZ   20180806     108.031
4     000001.SZ   20180803     108.031
5     000001.SZ   20180802     108.031
```
