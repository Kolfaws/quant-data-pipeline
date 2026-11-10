# 业绩预告

接口名称：`forecast`

接口说明：获取上市公司业绩预告数据。包含预告净利润变动幅度、预告净利润区间、变动原因等关键信息。数据通常在每日 20:00 ~ 21:00 更新。

**注意**：当前 `forecast` 接口只能按**单只股票**或**特定公告日期**获取数据。如果需要获取**某一季度全部上市公司**的业绩预告数据，请使用 `forecast_vip` 接口（参数一致），该接口需要 5000 积分。

权限：用户需要至少 2000 积分才可以调取。单次最大返回 3500 行，可循环调取。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | TS股票代码（与 ann_date 二选一） |
| ann_date | str | N | 公告日期（YYYYMMDD格式，与 ts_code 二选一） |
| start_date | str | N | 公告开始日期（YYYYMMDD格式） |
| end_date | str | N | 公告结束日期（YYYYMMDD格式） |
| period | str | N | 报告期（每个季度最后一天的日期，如 20171231 表示年报，20170630 表示半年报） |
| type | str | N | 预告类型筛选：<br>预增、预减、扭亏、首亏、续亏、续盈、略增、略减 |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS股票代码 |
| ann_date | str | Y | 公告日期 |
| end_date | str | Y | 报告期 |
| type | str | Y | 业绩预告类型（预增/预减/扭亏/首亏/续亏/续盈/略增/略减） |
| p_change_min | float | Y | 预告净利润变动幅度下限（%） |
| p_change_max | float | Y | 预告净利润变动幅度上限（%） |
| net_profit_min | float | Y | 预告净利润下限（万元） |
| net_profit_max | float | Y | 预告净利润上限（万元） |
| last_parent_net | float | Y | 上年同期归属母公司净利润（万元） |
| first_ann_date | str | Y | 首次公告日 |
| summary | str | Y | 业绩预告摘要 |
| change_reason | str | Y | 业绩变动原因 |

## 接口用例

### 获取指定公告日期的业绩预告

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2019年1月31日 公告的业绩预告数据
df = pro.forecast(
    ann_date='20190131',
    fields='ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max'
)
```

### 获取某只股票的历史业绩预告

```python
import tushare as ts

pro = ts.pro_api()

# 获取 000001.SZ 在 2018年全年的业绩预告
df = pro.forecast(
    ts_code='000001.SZ',
    start_date='20180101',
    end_date='20181231'
)
```

### 获取某一季度全市场业绩预告 (需 VIP 权限)

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2018年年报 (报告期 20181231) 所有上市公司的业绩预告
# 注意：此接口需要 5000 积分
df = pro.forecast_vip(
    period='20181231',
    fields='ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min'
)
```

### 筛选特定类型的预告（如“扭亏”）

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2019年1月31日 公告且类型为“扭亏”的股票
df = pro.forecast(
    ann_date='20190131',
    type='扭亏'
)
```

## 数据样例

```text
       ts_code  ann_date  end_date type  p_change_min  p_change_max  \
0    000005.SZ  20190131  20181231   预增      618.5600      945.1800  
1    000825.SZ  20190131  20181231   略增        3.8500       12.5100  
2    000566.SZ  20190131  20181231   预增       50.0000      100.0000  
3    000932.SZ  20190131  20181231   预增       60.8864       68.1664  
4    000557.SZ  20190131  20181231   预增       66.6800       66.6800  
5    600127.SH  20190131  20181231   首亏     -601.5517     -510.3604  
6    600159.SH  20190131  20181231   预增      315.0000      315.0000  
7    600963.SH  20190131  20181231   略增        2.3800       11.5800  
8    002336.SZ  20190131  20181231   续亏       33.1367       47.9952  
9    601608.SH  20190131  20181231   预增      228.5900      274.5700  
```
