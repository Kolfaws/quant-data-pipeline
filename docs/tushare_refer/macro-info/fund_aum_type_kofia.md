# 国投资资产类型的基金AUM

接口：`fund_aum_type_kofia`，可以通过数据工具调试和查看数据

描述：韩国按投资资产类型的基金AUM、；单位：1亿韩元(100 million Won)

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
| equity | float | Y | 股票型 |
| hybrid_equity | float | Y | 混合-股票型 |
| hybrid_bond | float | Y | 混合-债券型 |
| bond | float | Y | 债券型 |
| fund_of_funds | float | Y | 母基金 |
| short_term_finance | float | Y | 短期金融 |
| derivatives | float | Y | 衍生品 |
| real_estate | float | Y | 房地产 |
| special_asset | float | Y | 特殊资产 |
| hybrid_asset | float | Y | 混合资产 |
| total | float | Y | 合计 |

## 接口示例

```python
# 导入sdk包
import tushare as ts

# 配置凭据，如果已全局配置了，可以忽略。
ts.set_token('<--your-token-->')

# 获取接口实例
pro = ts.pro_api()

# 拉取接口(fund_aum_type_kofia)数据
# 示例：获取2026年1月到10月之间数据
df = pro.fund_aum_type_kofia(start_date="20260101", end_date="20261101")
print(df)
```

## 数据样例

```text
  trade_date        equity hybrid_equity  hybrid_bond          bond
0   20261030  3167427.0000   120804.0000  354875.0000  2201781.0000
1   20260930  3432203.0000   119208.0000  354029.0000  2139010.0000
2   20260831  3381378.0000   120633.0000  355121.0000  2128536.0000
3   20260731  3226220.0000   120288.0000  349941.0000  2131574.0000
4   20260630  3788548.0000   119333.0000  358529.0000  2124247.0000
5   20260529  3753755.0000   115462.0000  328886.0000  2172029.0000
6   20260430  3166184.0000   118068.0000  297519.0000  2152552.0000
7   20260331  2608904.0000   114972.0000  271745.0000  2116686.0000
8   20260227  2797076.0000   113864.0000  256216.0000  2178005.0000
9   20260130  2455759.0000   110833.0000  243970.0000  2179867.0000
```
