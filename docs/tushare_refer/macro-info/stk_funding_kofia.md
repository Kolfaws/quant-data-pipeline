# 韩国股票市场资金详情

接口：`stk_funding_kofia`，可以通过数据工具调试和查看数据

描述：韩国股票市场融资详情（证券市场资金走势）；单位：百万韩元(1 million Won)

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
| trade_date | str | Y | 日期（交易日）（YYYYMMDD） |
| investor_deposits | float | Y | 投资者保证金存款（不含衍生品交易保证金） |
| investor_deposits_deriv | float | Y | 交易所交易衍生品客户保证金 |
| rp_sales_balance | float | Y | 回购协议（RP）卖出余额 |
| brokerage_receivables | float | Y | 券商经纪应收款项 |
| liquidated_amount | float | Y | 经纪应收款项回收（Covering）金额 |
| liq_to_recv_ratio | float | Y | 回收金额/应收款项比率（%） |

## 接口示例

```python
# 导入sdk包
import tushare as ts

# 配置凭据，如果已全局配置了，可以忽略。
ts.set_token('<--your-token-->')

# 获取接口实例
pro = ts.pro_api()

# 拉取接口(stk_funding_kofia)数据
# 示例：获取20261025-20261103之间数据
df = pro.stk_funding_kofia(start_date="20261025", end_date="20261103",fields='trade_date,investor_deposits,rp_sales_balance')
print(df)
```

## 数据样例

```text
  trade_date  investor_deposits  rp_sales_balance
0   20261103         88241278.0       107049218.0
1   20261102         90462878.0       108466684.0
2   20261030         90235106.0       107901750.0
3   20261029         88713283.0       107761849.0
4   20261028         88297500.0       107431369.0
5   20261027         90102980.0       107945678.0
6   20261026         88682580.0       107774189.0
```
