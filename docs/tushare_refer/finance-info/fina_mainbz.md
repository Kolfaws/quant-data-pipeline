# 主营业务构成

接口名称：`fina_mainbz`

接口说明：获取上市公司主营业务构成数据，支持按产品、地区、行业或销售模式进行分类统计。该数据有助于分析公司的收入来源结构、地域分布及行业集中度。

**注意**：当前 `fina_mainbz` 接口只能按**单只股票**获取其历史数据，且单次最大提取 **100行**。如果需要获取**某一季度全部上市公司**的主营业务构成数据，请使用 `fina_mainbz_vip` 接口（参数一致），该接口需要 5000 积分。

权限：用户需要至少 2000 积分才可以调取。总量不限制，可循环获取。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS股票代码 |
| period | str | N | 报告期（每个季度最后一天的日期，如 20171231 表示年报，20170630 表示半年报） |
| type | str | N | 分类类型：<br>**P** - 按产品<br>**D** - 按地区<br>**I** - 按行业<br>**S** - 按销售模式<br>（请输入大写字母） |
| start_date | str | N | 报告期开始日期（YYYYMMDD） |
| end_date | str | N | 报告期结束日期（YYYYMMDD） |

## 输出参数

| 名称 | 类型 | 描述 |
| --- | --- | --- |
| ts_code | str | TS代码 |
| end_date | str | 报告期 |
| bz_item | str | 主营业务来源名称（如“聚丙烯”、“华东地区”等） |
| bz_code | str | 主营业务来源类型代码（P-按产品, D-按地区, I-按行业） |
| bz_sales | float | 主营业务收入 (元) |
| bz_profit | float | 主营业务利润 (元) |
| bz_cost | float | 主营业务成本 (元) |
| curr_type | str | 货币代码（通常为 CNY） |
| update_flag | str | 是否更新标识 |

## 接口用例

### 获取某只股票按产品划分的主营业务构成

```python
import tushare as ts

pro = ts.pro_api()

# 获取 000627.SZ 按产品 (type='P') 划分的主营业务构成
df = pro.fina_mainbz(ts_code='000627.SZ', type='P')
```

### 获取某只股票按地区划分的主营业务构成

```python
import tushare as ts

pro = ts.pro_api()

# 获取 000627.SZ 在 2018年年报中按地区 (type='D') 划分的构成
df = pro.fina_mainbz(
    ts_code='000627.SZ',
    period='20181231',
    type='D'
)
```

### 获取某只股票按行业划分的主营业务构成

```python
import tushare as ts

pro = ts.pro_api()

# 获取 000627.SZ 按行业 (type='I') 划分的构成
df = pro.fina_mainbz(ts_code='000627.SZ', type='I')
```

### 获取某一季度全市场主营业务构成 (需 VIP 权限)

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2018年年报 (报告期 20181231) 所有上市公司按产品划分的部分数据
# 注意：此接口需要 5000 积分
df = pro.fina_mainbz_vip(
    period='20181231',
    type='P',
    fields='ts_code,end_date,bz_item,bz_sales'
)
```

## 数据样例

```text
     ts_code  end_date    bz_item       bz_sales       bz_profit bz_cost curr_type
0  000627.SZ  20171231    其他产品      1.847507e+08      None    None       CNY
1  000627.SZ  20171231    其他主营业务  1.847507e+08      None    None       CNY
2  000627.SZ  20171231    聚丙烯        6.629111e+07      None    None       CNY
3  000627.SZ  20171231    原料药产品    2.685909e+08      None    None       CNY
4  000627.SZ  20171231    保险业务      5.288595e+10      None    None       CNY
```
