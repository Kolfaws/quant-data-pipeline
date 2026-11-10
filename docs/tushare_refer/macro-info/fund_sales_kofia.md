# 韩国分销渠道划分的销售余额

接口：`fund_sales_kofia`，可以通过数据工具调试和查看数据

描述：韩国按销售渠道的销售余额/账户数单位：1亿韩元/千账户

限量：单次最大300条，可根据代码或日期循环提取

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
| investment_region | str | Y | 投资区域 |
| cis_type | str | Y | CIS类型(CIS Type) |
| public_private | str | Y | 公募/私募(Public/Private) |
| fund_type | str | Y | 基金类型(Fund Type) |
| securities_data | float | Y | 数据-证券 |
| securities_ratio | float | Y | 占比-证券 |
| bank_data | float | Y | 数据-银行 |
| bank_ratio | float | Y | 占比-银行 |
| insurance_data | float | Y | 数据-保险 |
| insurance_ratio | float | Y | 占比-保险 |
| others_data | float | Y | 数据-其他 |
| others_ratio | float | Y | 占比-其他 |
| total | float | Y | 合计(Total) |

## 接口示例

```python
# 导入sdk包
import tushare as ts

# 配置凭据，如果已全局配置了，可以忽略。
ts.set_token('<--your-token-->')

# 获取接口实例
pro = ts.pro_api()

# 拉取接口(fund_sales_kofia)数据
#示例：获取2026年9月数据
df = pro.fund_sales_kofia(trade_date="20260930")
print(df)
```

## 数据样例

```text
  trade_date public_private    fund_type securities_data securities_ratio
0   20260930            ALL   Securities       5908.0000          19.6200
1   20260930        Private   Securities         18.0000          90.0000
2   20260930         Public   Securities       5890.0000          19.5800
3   20260930            ALL   Securities         21.0000          47.7300
4   20260930            ALL  Real Estate          0.0000           0.0000
5   20260930            ALL   Securities       5887.0000          19.5800
6   20260930            ALL   Securities       1847.0000          13.4800
7   20260930            ALL   Securities       4061.0000          24.7600
8   20260930            ALL   Securities       1094.0000          28.8000
9   20260930            ALL   Securities       2967.0000          23.5400
```
