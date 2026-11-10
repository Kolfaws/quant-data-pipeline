# 韩国股票市场趋势

接口：`stk_trend_kofia`，可以通过数据工具调试和查看数据

描述：韩国股票市场趋势数据：日主要股市行情快照：股票价格指数，交易规模，市值，单位：1亿韩元(100 million Won)、万株(10 thousand shares)

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
| trade_date | str | Y | 交易日期(快照日,YYYYMMDD) |
| category | str | Y | 项目大类:Stock Price Index：股票价格指数/Trading Size：交易规模/Market Cap.：市值 |
| metric | str | Y | 指标 |
| kospi | float | Y | 韩国综合股价指数(KOSPI) |
| kosdaq | float | Y | 韩国创业板指数(KOSDAQ) |
| k_otc | float | Y | K-OTC指数 |

## 接口示例

```python
# 导入sdk包
import tushare as ts

# 配置凭据，如果已全局配置了，可以忽略。
ts.set_token('<--your-token-->')

# 获取接口实例
pro = ts.pro_api()

# 拉取接口(stk_trend_kofia)数据
# 获取20261103数据
df = pro.stk_trend_kofia(trade_date="20261103",fields='trade_date,category,metric,kospi')
print(df)
```

## 数据样例

```text
  trade_date           category                          metric        kospi
0    20261103  Stock Price Index                     Daily Index      5648.79
1    20261103  Stock Price Index    Change from the Previous Day      -210.29
2    20261103  Stock Price Index                        Ratio(%)        -3.58
3    20261103  Stock Price Index  Change from the Previous Month       -81.95
4    20261103  Stock Price Index                        Ratio(%)        -1.43
5    20261103  Stock Price Index   Change from the Previous Year      1722.20
6    20261103  Stock Price Index                        Ratio(%)        43.86
7    20261103       Trading Size                  Trading Volume     20737.00
8    20261103       Trading Size    Change from the Previous Day       924.00
9    20261103       Trading Size                        Turnover    147148.00
10   20261103       Trading Size    Change from the Previous Day    -10210.00
11   20261103        Market Cap.                           Total  46624247.00
12   20261103        Market Cap.                      Foreigners  18127324.00
13   20261103        Market Cap.                        Ratio(%)        38.88
```
