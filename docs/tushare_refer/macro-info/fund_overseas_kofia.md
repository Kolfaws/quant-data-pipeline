# 韩国海外投资基金规模

接口：`fund_overseas_kofia`，可以通过数据工具调试和查看数据

描述：韩国海外投资基金规模单位：1亿韩元(100 million Won)

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
| trade_date | str | Y | 交易日期 |
| cis_type | str | Y | CIS类型(CIS Type) |
| public_private | str | Y | 公募/私募(Public/Private) |
| fund_type | str | Y | 基金类型 |
| overseas_fund_count | float | Y | 基金数量-境外投资基金 |
| overseas_aum | float | Y | 资产规模-境外投资基金 |
| overseas_nav | float | Y | 净值-境外投资基金 |
| mixed_fund_count | float | Y | 基金数量-混合(境内外)资产基金 |
| mixed_aum | float | Y | 资产规模-混合(境内外)资产基金 |
| mixed_nav | float | Y | 净值-混合(境内外)资产基金 |

## 接口示例

```python
# 导入sdk包
import tushare as ts

# 配置凭据，如果已全局配置了，可以忽略。
ts.set_token('<--your-token-->')

# 获取接口实例
pro = ts.pro_api()

# 拉取接口(fund_overseas_kofia)数据
# 示例：获取2026年11月06数据
df = pro.fund_overseas_kofia(trade_date="20261104")
print(df)
```

## 数据样例

```text
  trade_date public_private overseas_fund_count  overseas_aum  overseas_nav
0   20261104            ALL           2650.0000  2321322.0000  2591330.0000
1   20261104        Private           1058.0000   738061.0000   795022.0000
2   20261104         Public           1592.0000  1583261.0000  1796308.0000
3   20261104            ALL              1.0000      140.0000      125.0000
4   20261104            ALL              4.0000     3818.0000     1609.0000
5   20261104            ALL           2649.0000  2321182.0000  2591205.0000
6   20261104            ALL            836.0000  1339772.0000  1425985.0000
7   20261104        Private             66.0000   108117.0000   110691.0000
8   20261104         Public            770.0000  1231655.0000  1315294.0000
9   20261104            ALL              0.0000        0.0000        0.0000
```
