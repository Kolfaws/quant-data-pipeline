# 韩国货币市场基金MMF

接口：`fund_mmf_kofia`，可以通过数据工具调试和查看数据

描述：韩国按期限/周期划分的货币市场基金（MMF）资产管理规模。单位：1亿韩元(100 million Won)

限量：单次最大3000条，可根据代码或日期循环提取

积分：需要5000积分可以调取，具体请参阅积分获取办法

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| trade_date | str | N | 交易日期（YYYYMMDD） |
| start_date | str | N | 开始日期（YYYYMMDD） |
| end_date | str | N | 结束日期（YYYYMMDD） |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| trade_date | str | Y | 交易日期(YYYYMMDD) |
| value_type | str | Y | 指标类型(AUM/NAV/FUND_COUNT/SALES/ACCOUNTS) |
| asset_management_firm | str | Y | 资产管理公司(Asset Management Firm) |
| mmf_total | float | Y | MMF-合计 |
| mmf_individual | float | Y | MMF-个人 |
| mmf_corporate | float | Y | MMF-企业 |
| mmf_under_former_law | float | Y | 旧法下MMF |
| change_prev_day | float | Y | 较前一日变动 |
| change_prev_month | float | Y | 较上月变动 |

## 接口示例

```python
# 导入sdk包
import tushare as ts

# 配置凭据，如果已全局配置了，可以忽略。
ts.set_token('<--your-token-->')

# 获取接口实例
pro = ts.pro_api()

# 拉取接口(fund_mmf_kofia)数据
# 获取2026年11月03日货币市场基金MMF数据
df = pro.fund_mmf_kofia(trade_date="20261103")
print(df)
```

## 数据样例

```text
  trade_date value_type   mmf_total mmf_individual mmf_corporate
0   20261103        AUM  68167.0000      4726.0000    63441.0000
1   20261103        NAV  68631.0000      4840.0000    63791.0000
2   20261103        AUM  74837.0000      3209.0000    71628.0000
3   20261103        NAV  76385.0000      3263.0000    73123.0000
4   20261103        AUM  22179.0000         0.0000    22179.0000
5   20261103        NAV  22268.0000         0.0000    22268.0000
6   20261103        AUM  62845.0000         0.0000    62845.0000
7   20261103        NAV  64397.0000         0.0000    64397.0000
8   20261103        AUM  17766.0000         0.0000    17766.0000
9   20261103        NAV  18057.0000         0.0000    18057.0000
```
