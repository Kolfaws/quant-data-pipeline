# 股票基础信息

接口：`stock_basic`，可以通过数据工具调试和查看数据

描述：获取基础信息数据，包括股票代码、名称、上市日期、退市日期等

限量：每次最多返回6000行数据（覆盖全市场A股，会随股票总数增长而增加）

权限：2000积分起，每分钟请求50次。此接口是基础信息，调取一次就可以拉取完，建议保存到本地存储后使用

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | TS股票代码（格式说明） |
| name | str | N | 名称 |
| market | str | N | 市场类别（主板/创业板/科创板/CDR/北交所） |
| list_status | str | N | 上市状态：L上市 D退市 P暂停上市 G未交易 UN未上市，默认是L |
| exchange | str | N | 交易所：SSE上交所 SZSE深交所 BSE北交所 |
| is_hs | str | N | 是否沪深港通标的：N否 H沪股通 S深股通 |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS代码 |
| symbol | str | Y | 股票代码 |
| name | str | Y | 股票名称 |
| area | str | Y | 地域 |
| industry | str | Y | 所属行业 |
| fullname | str | N | 股票全称 |
| enname | str | N | 英文全称 |
| cnspell | str | Y | 拼音缩写 |
| market | str | Y | 市场类型（主板/创业板/科创板/CDR） |
| exchange | str | N | 交易所代码 |
| curr_type | str | N | 交易货币 |
| list_status | str | N | 上市状态：L上市 D退市 G过会未交易 P暂停上市 UN未上市 |
| list_date | str | Y | 上市日期 |
| delist_date | str | N | 退市日期 |
| is_hs | str | N | 是否沪深港通标的：N否 H沪股通 S深股通 |
| act_name | str | Y | 实控人名称 |
| act_ent_type | str | Y | 实控人企业性质 |

说明：旧版上的PE/PB/股本等字段，请在行情接口“每日指标”中获取。

## 接口示例

```python
pro = ts.pro_api()
# 查询当前所有正常上市交易的股票列表
data = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
```

或者：

```python
# 查询当前所有正常上市交易的股票列表
data = pro.query('stock_basic', exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')
```

## 数据样例

```text
    ts_code     symbol     name     area industry    list_date
0     000001.SZ  000001  平安银行   深圳       银行  19910403
1     000002.SZ  000002   万科A   深圳     全国地产  19910129
2     000004.SZ  000004  国农科技   深圳     生物制药  19910114
3     000005.SZ  000005  世纪星源   深圳     房产服务  19901210
4     000006.SZ  000006  深振业A   深圳     区域地产  19920427
5     000007.SZ  000007   全新好   深圳     酒店餐饮  19920413
```

股本情况（盘前）

接口：stk_premarket

描述：每日开盘前获取当日股票的股本情况，包括总股本和流通股本，涨跌停价格等。数据开始时间2024-05-01，1天更新2次，早上是9点，晚上是18点10分更新数据。

限量：单次最大8000条数据，可循环提取

权限：本接口数据需单独开通权限，请参考权限列表，前往权限中心申请（需勾选“盘前股本”）。

输入参数

名称    类型    必选    描述
ts_code    str    N    股票代码
trade_date    str    N    交易日期(YYYYMMDD格式，下同)
start_date    str    N    开始日期
end_date    str    N    结束日期

输出参数

名称    类型    默认显示    描述
trade_date    str    Y    交易日期
ts_code    str    Y    TS股票代码
total_share    float    Y    总股本（万股）
float_share    float    Y    流通股本（万股）
pre_close    float    Y    昨日收盘价
up_limit    float    Y    今日涨停价
down_limit    float    Y    今日跌停价

接口示例

pro = ts.pro_api()

# 获取某一日盘前所有股票当日的最新股本

df = pro.stk_premarket(trade_date='20240603')

数据示例

```text
    trade_date    ts_code  total_share  float_share pre_close up_limit down_limit
0      20240603  001387.SZ   17778.8000    4355.7297    17.000   18.700     15.300
1      20240603  600460.SH  166407.1845  166407.1845    18.790   20.670     16.910
2      20240603  603052.SH   13484.8000    4096.4000    30.270   33.300     27.240
3      20240603  603269.SH   22053.6977   22053.6977    10.140   11.150      9.130
4      20240603  001339.SZ   24974.4000    7157.2575    29.210   32.130     26.290
...         ...        ...          ...          ...       ...      ...        ...
5339   20240603  920002.BJ    3175.2120     475.0000      None   77.840     41.920
```
