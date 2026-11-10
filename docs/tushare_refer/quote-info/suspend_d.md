# 每日停复牌信息

接口名称：`suspend_d`

接口说明：获取股票每日的停复牌信息。数据始于2000-01-03，支持按日期查询全市场或指定股票的停牌（S）和复牌（R）状态。对于日内临时停牌的股票，会返回具体的停牌时间段。

更新时间：不定期更新。

限量：单次查询最大返回5000行。

积分：至少2000积分可以调用，5000积分可以获得更高的调取频次。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | TS股票代码（支持多值输入，如 '000001.SZ,000002.SZ'） |
| trade_date | str | N | 交易日期（格式：YYYYMMDD） |
| start_date | str | N | 停复牌查询开始日期（格式：YYYYMMDD） |
| end_date | str | N | 停复牌查询结束日期（格式：YYYYMMDD） |
| suspend_type | str | N | 停复牌类型筛选：<br>S - 停牌<br>R - 复牌<br>不填则返回所有状态 |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS代码 |
| trade_date | str | Y | 停复牌日期（若长期停牌，则覆盖从停牌开始到结束期间的连续日期） |
| suspend_timing | str | Y | 日内停牌时间段。仅当发生日内临时停牌时有值（如 "09:30-10:00"），否则为空值 (None) |
| suspend_type | str | Y | 停复牌类型：<br>S - 停牌<br>R - 复牌 |

## 接口用例

### 获取指定日期的全市场停牌股票

```python
import tushare as ts

pro = ts.pro_api()

# 提取 2020年3月12日 所有停牌的股票
df = pro.suspend_d(suspend_type='S', trade_date='20200312')
```

### 获取某只股票的历史停复牌记录

```python
import tushare as ts

pro = ts.pro_api()

# 获取 000001.SZ 在 2020年全年的停复牌信息
df = pro.suspend_d(
    ts_code='000001.SZ',
    start_date='20200101',
    end_date='20201231'
)
```

### 获取指定时间段内的复牌股票

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2020年3月1日至2020年3月31日期间复牌的股票
df = pro.suspend_d(
    suspend_type='R',
    start_date='20200301',
    end_date='20200331'
)
```

## 数据样例

```text
        ts_code suspend_type trade_date suspend_timing
0   000029.SZ            S     20200312           None
1   000502.SZ            S     20200312           None
2   000939.SZ            S     20200312           None
3   000977.SZ            S     20200312           None
4   000995.SZ            S     20200312           None
5   002260.SZ            S     20200312           None
6   002450.SZ            S     20200312           None
7   002604.SZ            S     20200312           None
8   300028.SZ            S     20200312           None
9   300104.SZ            S     20200312           None
10  300216.SZ            S     20200312           None
11  300592.SZ            S     20200312           None
12  300819.SZ            S     20200312    09:30-10:00
13  300821.SZ            S     20200312    09:30-10:00
... ... ...
```
