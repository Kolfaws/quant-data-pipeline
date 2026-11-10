# 美股ETF列表

接口：`us_etf_basic`，可以通过数据工具调试和查看数据

描述：获取美股ETF基金基本信息，包含纽交所，纳斯达克交易所，及部分OTC市场的ETF基金数据。

限量：单次最大6000条，可根据代码或日期循环提取

积分：需要5000积分可以调取，具体请参阅积分获取办法

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | 基金代码 |
| list_date | str | Y | 上市日期 |
| list_status | str | Y | 上市状态 L上市 D退市 P待上市 |
| exchange | str | Y | 交易所 NASDAQ:纳斯达克交易所;NYSE:纽交所;NYSEARCA:纽交所(群岛);BZX:芝加哥期权;OTC。 |
| mgr_name | str | Y | 基金管理人名称 |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | 代码 |
| name | str | Y | 中文名称 |
| enname | str | Y | 英文名称 |
| exchange | str | Y | 交易所 NASDAQ:纳斯达克交易所;NYSE:纽交所;NYSEARCA:纽交所(群岛);BZX:芝加哥期权;OTC。 |
| list_date | str | Y | 上市日期 |
| delist_date | str | Y | 退市日期 |
| list_status | str | Y | 上市状态 L上市 D退市 P待上市 |
| type | str | Y | 基金类型 ETF |
| setup_country | str | Y | 注册国家 |
| mgr_name | str | Y | 基金管理人名称 |
| custod_name | str | Y | 基金托管人名称 |
| invest_goal | str | Y | 投资目标 |
| fund_class_oper | str | Y | 基金运作模 一般开放式 |
| fund_type | str | Y | 基金投资类型 |
| invest_field | str | Y | 基金投资范围 |
| invest_strat | str | Y | 投资策略 |
| divi_type | str | Y | 基金分红方式 现金分红；红利再投资 |
| divi_freq | str | Y | 基金分红频率 |
| index_code | str | Y | ETF基准指数代码 |
| index_name | str | Y | ETF基准指数中文全称 |
| curr_type | str | Y | 交易货币 |
| is_lever | str | Y | 是否日内杠杆 |
| lever_mult | str | Y | 杠杆倍数 |
| lever_adjust_freq | str | Y | 杠杆调整频率 |
| min_pur_redem_unit | str | Y | 最小申赎单位 份 |
| min_pur_redem_cost | str | Y | 最小申赎单位费用 元 |
| fund_desc | str | Y | 基金简介 |

## 接口示例

```python
pro = ts.pro_api()

#获取默认美股ETF基础信息，单次6000行
df = pro.us_etf_basic()


#查询当前所有正常上市交易的美股ETF列表

data = pro.us_etf_basic(exchange='', list_status='L', fields='ts_code,symbol,name,type,list_date,mgr_name')
```

## 数据样例

```text
   ts_code                                      name type fund_type  exchange
0        VOX       Vanguard Communication Services ETF  ETF       股票型  NYSEARCA
1       ODDS  Pacer BlueStar Digital Entertainment ETF  ETF       股票型    NASDAQ
2       UITB  VictoryShares Core Intermediate Bond ETF  ETF       债券型    NASDAQ
3       TRFK     Pacer Data and Digital Revolution ETF  ETF       股票型  NYSEARCA
4       UCRD          VictoryShares Corporate Bond ETF  ETF       债券型    NASDAQ
...      ...                                       ...  ...       ...       ...
4697    KAIT        KraneShares Asia AI Technology ETF  ETF      None  NYSEARCA
4698    AHBM            Amplify Top 10 Asia Memory ETF  ETF      None  NYSEARCA
4699    BBLS                      Munificent Seven ETF  ETF       股票型  NYSEARCA
4700    GEEQ     Guggenheim Enhanced Equity Income ETF  ETF     另类资产型  NYSEARCA
4701    GCLO       Guggenheim Investment Grade CLO ETF  ETF       债券型  NYSEARCA
```
