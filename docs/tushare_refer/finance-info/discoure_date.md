# 财报披露计划

接口名称：`disclosure_date`

接口说明：获取上市公司财报（年报、半年报、季报）的预计披露日期和实际披露日期。可用于跟踪财报发布节奏，规避或参与财报行情。

限量：单次最大返回 6000 条记录，总量不限制，可循环调取。

积分：用户需要至少 2000 积分才可以调取，积分越多权限越大，具体请参阅积分获取办法。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | TS股票代码 |
| end_date | str | N | 财报周期/报告期（每个季度最后一天的日期，如 20181231 表示 2018 年年报，20180630 表示中报） |
| pre_date | str | N | 计划披露日期（YYYYMMDD） |
| ann_date | str | N | 最新披露公告日（YYYYMMDD） |
| actual_date | str | N | 实际披露日期（YYYYMMDD） |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS代码 |
| ann_date | str | Y | 最新披露公告日 |
| end_date | str | Y | 报告期 |
| pre_date | str | Y | 预计披露日期 |
| actual_date | str | Y | 实际披露日期 |
| modify_date | str | N | 披露日期修正记录 |

## 接口用例

### 获取指定报告期的全市场披露计划

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2018 年年报 (报告期 20181231) 所有股票的披露日期计划
df = pro.disclosure_date(end_date='20181231')
```

### 获取某只股票的历史披露日期

```python
import tushare as ts

pro = ts.pro_api()

# 获取 000001.SZ 的所有历史财报披露日期
df = pro.disclosure_date(ts_code='000001.SZ')
```

### 筛选特定时间段内披露的股票

```python
import tushare as ts

pro = ts.pro_api()

# 获取计划在 2019年1月31日 披露 2018 年年报的股票
df = pro.disclosure_date(end_date='20181231', pre_date='20190131')
```

## 数据样例

```text
        ts_code  ann_date  end_date  pre_date actual_date modify_date
0     300619.SZ  20181228  20181231  20190122    20190122        None
1     300125.SZ  20181228  20181231  20190129    20190129        None
2     601619.SH  20181227  20181231  20190129    20190129        None
3     000055.SZ  20181228  20181231  20190130    20190130        None
4     002910.SZ  20181228  20181231  20190131        None        None
```
