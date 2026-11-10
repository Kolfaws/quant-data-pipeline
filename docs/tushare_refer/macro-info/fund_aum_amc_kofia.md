# 韩国资产管理公司的AUM

接口：`fund_aum_amc_kofia`，可以通过数据工具调试和查看数据

描述：韩国资产管理公司管理资产规模单位：1亿韩元(100 million Won)

限量：单次最大9000条，可根据代码或日期循环提取

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
| trade_date | str | Y | 交易日期(YYYYMMDD; 区间报表=行日期, 快照报表=快照日) |
| value_type | str | Y | 指标类型(AUM/NAV/FUND_COUNT/SALES/ACCOUNTS) |
| investment_region | str | Y | 投资区域(Investment Region)ALL：全部,Domestic：本土,Overseas：海外 Overseas (30% or more)：境外资产占比 ≥ 30% Overseas (60% or more)：境外资产占比 ≥ 60% |
| cis_type | str | Y | CIS类型(CIS Type)ALL：全部 Investment Company：投资公司 Investment Limited Company：投资有限责任公司 Investment Trust：投资信托 |
| public_private | str | Y | 公募/私募(Public/Private) |
| company_name | str | Y | 公司名称 |
| securities_equity | float | Y | 证券-股票型 |
| securities_hybrid_equity | float | Y | 证券-混合股票型 |
| securities_hybrid_bond | float | Y | 证券-混合债券型 |
| securities_bond | float | Y | 证券-债券型 |
| securities_fund_of_funds | float | Y | 证券-母基金 |
| short_term_finance | float | Y | 短期金融 |
| derivatives | float | Y | 衍生品 |
| real_estate | float | Y | 房地产 |
| special_asset | float | Y | 特殊资产 |
| hybrid_asset | float | Y | 混合资产 |
| pef | float | Y | 私募股权基金 |
| other_discretionary | float | Y | 其他全权委托投资资产 |
| total | float | Y | 合计 |
| under_fiduciary_mgmt | float | Y | 受托管理 |
| change_prev_day | float | Y | 较前一日变动 |
| change_prev_year | float | Y | 较上年变动 |

## 接口示例

```python
# 导入sdk包
import tushare as ts

# 配置凭据，如果已全局配置了，可以忽略。
ts.set_token('<--your-token-->')

# 获取接口实例
pro = ts.pro_api()

# 拉取接口(fund_aum_amc_kofia)数据
# 获取20261104数据
df = pro.fund_aum_amc_kofia(trade_date="20261104")
print(df)
```

## 数据样例

```text
  trade_date  value_type investment_region cis_type under_fiduciary_mgmt
0   20261104         AUM               ALL      ALL            6953.0000
1   20261104  FUND_COUNT               ALL      ALL               0.0000
2   20261104         NAV               ALL      ALL           19070.0000
3   20261104         AUM               ALL      ALL               0.0000
4   20261104  FUND_COUNT               ALL      ALL               0.0000
5   20261104         NAV               ALL      ALL               0.0000
6   20261104         AUM               ALL      ALL            6953.0000
7   20261104  FUND_COUNT               ALL      ALL               0.0000
8   20261104         NAV               ALL      ALL           19070.0000
9   20261104         AUM               ALL      ALL            6953.0000
```
