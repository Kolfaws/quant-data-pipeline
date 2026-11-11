# 交易日历

接口：`fut_trade_cal`，可以通过数据工具调试和查看数据

描述：获取各大期货交易所交易日历数据
积分：需2000积分才可以提取数据

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| exchange | str | N | 交易所 SHFE 上期所 DCE 大商所 CFFEX中金所 CZCE郑商所 INE上海国际能源交易所 |
| start_date | str | N | 开始日期 |
| end_date | str | N | 结束日期 |
| is_open | int | N | 是否交易 0休市 1交易 |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| exchange | str | Y | 交易所 同参数部分描述 |
| cal_date | str | Y | 日历日期 |
| is_open | int | Y | 是否交易 0休市 1交易 |
| pretrade_date | str | N | 上一个交易日 |

## 接口示例

```python
pro = ts.pro_api('your token')


df = pro.fut_trade_cal(exchange='DCE', start_date='20180101', end_date='20181231')
或者

df = pro.query('fut_trade_cal', exchange='DCE', start_date='20180101', end_date='20181231')
```

## 数据样例

```text
        exchange  cal_date  is_open
0        DCE  20180101        0
1        DCE  20180102        1
2        DCE  20180103        1
3        DCE  20180104        1
4        DCE  20180105        1
5        DCE  20180106        0
6        DCE  20180107        0
7        DCE  20180108        1
8        DCE  20180109        1
9        DCE  20180110        1
..       ...       ...      ...
335      DCE  20181202        0
336      DCE  20181203        1
337      DCE  20181204        1
338      DCE  20181205        1
339      DCE  20181206        1
340      DCE  20181207        1
```
