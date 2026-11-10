# 人民币汇率中间价

接口：`fx_midrate`，可以通过数据工具调试和查看数据

描述：获取每天人民币汇率中间价（SAFE / 中国外汇交易中心），数据开始于1994年1月1日

限量：单次最大3000条，可根据代码或日期循环提取

积分：需要2000积分可以调取，5000积分频次更高，积分权限可在权限中心获取

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| trade_date | str | N | 日期（格式：YYYYMMDD，下同） |
| ts_code | str | N | 货币对（例如：CNYUSD，具体列表参考下面详细说明） |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| trade_date | str | Y | 日期，YYYYMMDD，对应官网「日期」 |
| ts_code | str | Y | 币对：直接标价为外币+CNY（如USDCNY，单位：人民币/100外币）；间接标价为CNY+外币（如CNYMYR，单位：外币/100人民币） |
| mid_rate | float | Y | 汇率中间价，官网原值；单位随TS_CODE标价规则 |

人民币交易对字典

| 外币中文名 | 外币英文 | 人民币交易对(ts_code) | 外币国家 |
| --- | --- | --- | --- |
| 美元 | US Dollar | CNYUSD | 美国 |
| 欧元 | Euro | CNYEUR | 欧元区 |
| 日元 | Japanese Yen | CNYJPY | 日本 |
| 港元 | Hong Kong Dollar | CNYHKD | 中国香港 |
| 英镑 | British Pound | CNYGBP | 英国 |
| 澳元 | Australian Dollar | CNYAUD | 澳大利亚 |
| 新西兰元 | New Zealand Dollar | CNYNZD | 新西兰 |
| 新加坡元 | Singapore Dollar | CNYSGD | 新加坡 |
| 瑞士法郎 | Swiss Franc | CNYCHF | 瑞士 |
| 加元 | Canadian Dollar | CNYCAD | 加拿大 |
| 澳门元 | Macanese Pataca | CNYMOP | 中国澳门 |
| 林吉特 | Malaysian Ringgit | CNYMYR | 马来西亚 |
| 卢布 | Russian Ruble | CNYRUB | 俄罗斯 |
| 兰特 | South African Rand | CNYZAR | 南非 |
| 韩元 | South Korean Won | CNYKRW | 韩国 |
| 迪拉姆 | UAE Dirham | CNYAED | 阿联酋 |
| 里亚尔 | Saudi Riyal | CNYSAR | 沙特阿拉伯 |
| 福林 | Hungarian Forint | CNYHUF | 匈牙利 |
| 兹罗提 | Polish Zloty | CNYPLN | 波兰 |
| 丹麦克朗 | Danish Krone | CNYDKK | 丹麦 |
| 瑞典克朗 | Swedish Krona | CNYSEK | 瑞典 |
| 挪威克朗 | Norwegian Krone | CNYNOK | 挪威 |
| 里拉 | Turkish Lira | CNYTRY | 土耳其 |
| 比索 | Mexican Peso | CNYMXN | 墨西哥 |
| 泰铢 | Thai Baht | CNYTHB | 泰国 |

说明：

数据来源于中国外汇交易中心。

交易对统一为 CNY + 外币 ISO 代码（如 CNYUSD）。

人民币对澳门元、马来西亚林吉特、俄罗斯卢布、南非兰特、韩元、阿联酋迪拉姆、沙特里亚尔、匈牙利福林、波兰兹罗提、丹麦克朗、瑞典克朗、挪威克朗、土耳其里拉、墨西哥比索、泰铢汇率中间价采取间接标价法，即100人民币折合多少外币。人民币对其它10种货币汇率中间价仍采取直接标价法，即100外币折合多少人民币。

## 接口示例

```python
# 导入sdk包
import tushare as ts

# 获取接口实例
pro = ts.pro_api()

#获取指定日期的所有币对的汇率中间价
df = pro.fx_midrate(trade_date='20261110')

#获取人民币对美元指定日期段的汇率中间价
df = pro.fx_midrate(ts_code='CNYUSD', start_date='20260101', end_date='20261110')
```

## 数据样例

```text
    trade_date ts_code  mid_rate
0     20261110  CNYUSD    671.67
1     20261109  CNYUSD    671.88
2     20261106  CNYUSD    671.68
3     20261105  CNYUSD    671.56
4     20261104  CNYUSD    671.80
..         ...     ...       ...
200   20260109  CNYUSD    701.28
201   20260108  CNYUSD    701.97
202   20260107  CNYUSD    701.87
203   20260106  CNYUSD    701.73
204   20260105  CNYUSD    702.30
```
