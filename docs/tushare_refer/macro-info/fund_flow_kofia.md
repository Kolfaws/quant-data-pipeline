# 韩国基金资金流

接口：`fund_flow_kofia`，可以通过数据工具调试和查看数据

描述：韩国基金资金流出流入单位：1亿韩元(100 million Won)

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
| cis_type | str | Y | CIS类型 |
| public_private | str | Y | 公募/私募(Public/Private) |
| fund_category | str | Y | 基金类别 |
| etf_included | str | Y | 是否包含ETF(1-是 0-否) |
| total_establishment | float | Y | 设立(存入)-合计 |
| total_termination | float | Y | 终止(赎回)-合计 |
| total_change | float | Y | 变动-合计 |
| domestic_establishment | float | Y | 设立(存入)-境内投资 |
| domestic_termination | float | Y | 终止(赎回)-境内投资 |
| domestic_change | float | Y | 变动-境内投资 |
| overseas_establishment | float | Y | 设立(存入)-境外投资 |
| overseas_termination | float | Y | 终止(赎回)-境外投资 |
| overseas_change | float | Y | 变动-境外投资 |

## 接口示例

```python
# 导入sdk包
import tushare as ts

# 配置凭据，如果已全局配置了，可以忽略。
ts.set_token('<--your-token-->')

# 获取接口实例
pro = ts.pro_api()

# 拉取接口(fund_flow_kofia)数据
# 获取2026年11月03日韩国基金资金流出流入数据
df = pro.fund_flow_kofia(trade_date="20261103")
print(df)
```

## 数据样例

```text
  trade_date public_private total_establishment total_termination total_change
0   20261103            ALL         363493.0000       307402.0000   56092.0000
1   20261103            ALL         388884.0000       333752.0000   55132.0000
2   20261103            ALL          10596.0000         6038.0000    4558.0000
3   20261103            ALL              0.0000            0.0000       0.0000
4   20261103            ALL          15688.0000        13603.0000    2085.0000
5   20261103            ALL           7426.0000         9613.0000   -2186.0000
6   20261103            ALL           1851.0000          929.0000     922.0000
7   20261103            ALL            694.0000         1086.0000    -392.0000
8   20261103            ALL            434.0000          312.0000     122.0000
9   20261103            ALL             12.0000           26.0000     -14.0000
```
