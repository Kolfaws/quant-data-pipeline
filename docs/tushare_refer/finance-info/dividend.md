# 分红送股

接口名称：`dividend`

接口说明：获取上市公司分红送股数据，包括现金分红、送股、转增股本等详细信息。数据始于2000-01-01，每日20:00~21:00更新。

权限：用户需要至少2000积分才可以调取。单次查询最大返回2000行，可循环调取。

**注意**：输入参数中 `ts_code`, `ann_date`, `record_date`, `ex_date`, `imp_ann_date` 至少有一个不能为空。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | TS代码 |
| ann_date | str | N | 公告日（预案或决议公告日） |
| record_date | str | N | 股权登记日期 |
| ex_date | str | N | 除权除息日 |
| imp_ann_date | str | N | 实施公告日 |

*(注：以上5个参数至少需提供一个)*

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS代码 |
| end_date | str | Y | 分红年度 |
| ann_date | str | Y | 公告日 (预案，决案) |
| div_proc | str | Y | 实施进度 (如：预案、股东大会通过、实施) |
| stk_div | float | Y | 每股送转 (送股+转增) |
| stk_bo_rate | float | Y | 每股送股比例 |
| stk_co_rate | float | Y | 每股转增比例 |
| cash_div | float | Y | 每股分红（税后） |
| cash_div_tax | float | Y | 每股分红（税前） |
| record_date | str | Y | 股权登记日 |
| ex_date | str | Y | 除权除息日 |
| pay_date | str | Y | 派息日 |
| div_listdate | str | Y | 红股上市日 |
| imp_ann_date | str | Y | 实施公告日 |
| base_date | str | N | 基准日 |
| base_share | float | N | 基准股本（万股） |

## 接口用例

### 获取某只股票的历史分红送股记录

```python
import tushare as ts

pro = ts.pro_api()

# 获取 600848.SH 的分红送股数据，只选取部分关键字段
df = pro.dividend(ts_code='600848.SH', fields='ts_code,div_proc,stk_div,cash_div_tax,record_date,ex_date')
```

### 获取指定除权除息日的分红数据

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2018年5月23日 除权除息的所有股票
df = pro.dividend(ex_date='20180523')
```

### 获取某年度的分红预案

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2018年公告的分红预案
df = pro.dividend(ann_date='20180101', fields='ts_code,ann_date,div_proc,cash_div_tax')
# 注意：实际使用中可能需要结合 start_date/end_date 或遍历 ann_date 来获取全年数据
```

## 数据样例

```text
             ts_code div_proc  stk_div record_date   ex_date
    0  600848.SH       实施     0.10    19950606  19950607
    1  600848.SH       实施     0.10    19970707  19970708
    2  600848.SH       实施     0.15    19960701  19960702
    3  600848.SH       实施     0.10    19980706  19980707
    4  600848.SH       预案     0.00        None      None
    5  600848.SH       实施     0.00    20180522  20180523
```
