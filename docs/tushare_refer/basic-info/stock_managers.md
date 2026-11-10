# 上市公司管理层

接口：`stk_managers`

描述：获取上市公司管理层

积分：用户需要2000积分才可以调取，5000积分以上频次相对较高，具体请参阅积分获取办法

## 输入参数

| 名称 | 类型 | 必选 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | N | 股票代码，支持单个或多个股票输入 |
| ann_date | str | N | 公告日期（YYYYMMDD格式，下同） |
| start_date | str | N | 公告开始日期 |
| end_date | str | N | 公告结束日期 |

## 输出参数

| 名称 | 类型 | 默认显示 | 描述 |
| --- | --- | --- | --- |
| ts_code | str | Y | TS股票代码 |
| ann_date | str | Y | 公告日期 |
| name | str | Y | 姓名 |
| gender | str | Y | 性别 |
| lev | str | Y | 岗位类别 |
| title | str | Y | 岗位 |
| edu | str | Y | 学历 |
| national | str | Y | 国籍 |
| birthday | str | Y | 出生年月 |
| begin_date | str | Y | 上任日期 |
| end_date | str | Y | 离任日期 |
| resume | str | N | 个人简历 |

## 接口用例

```python
pro = ts.pro_api()

# 获取单个公司高管全部数据
df = pro.stk_managers(ts_code='000001.SZ')

# 获取多个公司高管全部数据
df = pro.stk_managers(ts_code='000001.SZ,600000.SH')
```

## 数据样例

```text
    ts_code  ann_date     name    gender  ... national  birthday begin_date  end_date
0    000001.SZ  20190604  姚贵平      M  ...       中国     1961   20180815  20190604
1    000001.SZ  20190604  姚贵平      M  ...       中国     1961   20170629  20190604
2    000001.SZ  20190604  姚贵平      M  ...       中国     1961   20180129  20190604
3    000001.SZ  20190309   吴鹏      M  ...       中国     1965   20110817  20190309
4    000001.SZ  20190307  孙永桢      F  ...       中国     1968   20181025      None
5    000001.SZ  20180816  杨志群      M  ...       中国     1970   20180815      None
```
