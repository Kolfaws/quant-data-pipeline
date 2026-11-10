# 业绩快报

接口名称：`express`

接口说明：获取上市公司业绩快报数据。业绩快介于定期报告正式披露前发布，包含主要财务数据和指标，具有较高的时效性。

**注意**：当前 `express` 接口只能按**单只股票**获取其历史数据。如果需要获取**某一季度全部上市公司**的业绩快报数据，请使用 `express_vip` 接口（参数一致），该接口需要 5000 积分。

权限：用户需要至少 2000 积分才可以调取，具体请参阅积分获取办法。

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS股票代码 |
| ann_date | str | N | 公告日期（YYYYMMDD格式） |
| start_date | str | N | 公告开始日期（YYYYMMDD格式） |
| end_date | str | N | 公告结束日期（YYYYMMDD格式） |
| period | str | N | 报告期（每个季度最后一天的日期，如 20171231 表示年报，20170630 表示半年报，20170930 表示三季报） |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS股票代码 |
| ann_date | str | Y | 公告日期 |
| end_date | str | Y | 报告期 |
| revenue | float | Y | 营业收入 (元) |
| operate_profit | float | Y | 营业利润 (元) |
| total_profit | float | Y | 利润总额 (元) |
| n_income | float | Y | 净利润 (元) |
| total_assets | float | Y | 总资产 (元) |
| total_hldr_eqy_exc_min_int | float | Y | 股东权益合计 (不含少数股东权益) (元) |
| diluted_eps | float | Y | 每股收益 (摊薄) (元) |
| diluted_roe | float | Y | 净资产收益率 (摊薄) (%) |
| yoy_net_profit | float | Y | 去年同期修正后净利润 (元) |
| bps | float | Y | 每股净资产 (元) |
| yoy_sales | float | N | 同比增长率: 营业收入 (%) |
| yoy_op | float | N | 同比增长率: 营业利润 (%) |
| yoy_tp | float | N | 同比增长率: 利润总额 (%) |
| yoy_dedu_np | float | N | 同比增长率: 归属母公司股东的净利润 (%) |
| yoy_eps | float | N | 同比增长率: 基本每股收益 (%) |
| yoy_roe | float | N | 同比增减: 加权平均净资产收益率 (%) |
| growth_assets | float | N | 比年初增长率: 总资产 (%) |
| yoy_equity | float | N | 比年初增长率: 归属母公司的股东权益 (%) |
| growth_bps | float | N | 比年初增长率: 归属于母公司股东的每股净资产 (%) |
| or_last_year | float | N | 去年同期营业收入 (元) |
| op_last_year | float | N | 去年同期营业利润 (元) |
| tp_last_year | float | N | 去年同期利润总额 (元) |
| np_last_year | float | N | 去年同期净利润 (元) |
| eps_last_year | float | N | 去年同期每股收益 (元) |
| open_net_assets | float | N | 期初净资产 (元) |
| open_bps | float | N | 期初每股净资产 (元) |
| perf_summary | str | N | 业绩简要说明 |
| is_audit | int | N | 是否审计：1-是，0-否 |
| remark | str | N | 备注 |

## 接口用例

### 获取单只股票的历史业绩快报

```python
import tushare as ts

pro = ts.pro_api()

# 获取 600000.SH (浦发银行) 在 2018年上半年的业绩快报数据
df = pro.express(
    ts_code='600000.SH',
    start_date='20180101',
    end_date='20180701',
    fields='ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,total_assets'
)
```

### 获取某一季度全市场业绩快报数据 (需 VIP 权限)

```python
import tushare as ts

pro = ts.pro_api()

# 获取 2018年年报 (报告期 20181231) 所有上市公司的部分业绩快报数据
# 注意：此接口需要 5000 积分
df = pro.express_vip(
    period='20181231',
    fields='ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,total_assets'
)
```

## 数据样例

```text
     ts_code  ann_date  end_date       revenue  operate_profit  total_profit      n_income  total_assets  \
0  603535.SH  20180411  20180331  2.064659e+08    3.345047e+07  3.340047e+07  2.672643e+07  1.682111e+09  
1  603535.SH  20180208  20171231  1.034262e+09    1.323373e+08  1.440493e+08  1.188325e+08  1.710466e+09  
2  603535.SH  20171016  20170930  7.064117e+08    9.509520e+07  9.931530e+07  8.202480e+07  1.672986e+09  
```
