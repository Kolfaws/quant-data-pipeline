# 中信指数日度成分权重

接口：`ci_index_weight_d`，可以通过数据工具调试和查看数据

描述：可按交易日提取中信行业日度成分权重（即历史成分快照），也可按股票代码提取所属分类

限量：单次最大8000条，可根据代码或日期循环提取

积分：需要10000积分可以调取，积分权限可在权限中心获取

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | 指数代码(例如：CI005001.CI) |
| con_code | str | N | 股票成分代码 |
| index_type | str | N | 指数类别：l1:一级行业指数;l2:二级行业指数;l3:三级行业指数 |
| trade_date | str | N | 交易日期（YYYYMMDD格式） |
| start_date | str | N | 开始日期（YYYYMMDD格式） |
| end_date | str | N | 结束日期（YYYYMMDD格式） |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | 指数代码 |
| con_code | str | Y | 成分代码 |
| trade_date | str | Y | 交易日期（YYYYMMDD格式） |
| index_type | str | Y | 指数类别：l1:一级行业指数;l2:二级行业指数;l3:三级行业指数; |
| weight | float | Y | 权重 |

## 接口示例

```python
# 导入sdk包
import tushare as ts

# 获取接口实例
pro = ts.pro_api()

# 拉取接口(ci_index_weight_d)数据
# 获取指定指数指定日期的权重数据
df = pro.ci_index_weight_d(index_code="CI005001.CI", trade_date="20261109")

#获取指定指数某一时间段的权重数据
df = pro.ci_index_weight_d(index_code="CI005001.CI",start_date="20261105", end_date="20261109")
print(df)
```

## 数据样例

```text
    index_code   con_code trade_date index_type    weight
0  CI005001.CI  000059.SZ   20261109         l1  0.006038
1  CI005001.CI  000096.SZ   20261109         l1  0.002926
2  CI005001.CI  000159.SZ   20261109         l1  0.002691
3  CI005001.CI  000301.SZ   20261109         l1  0.032746
4  CI005001.CI  000554.SZ   20261109         l1  0.003513
5  CI005001.CI  000637.SZ   20261109         l1  0.001653
6  CI005001.CI  000698.SZ   20261109         l1  0.002519
7  CI005001.CI  000703.SZ   20261109         l1  0.039191
8  CI005001.CI  000819.SZ   20261109         l1  0.004541
9  CI005001.CI  000968.SZ   20261109         l1  0.004608
```
