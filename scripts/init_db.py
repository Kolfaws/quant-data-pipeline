import sys
from pathlib import Path
import duckdb
from loguru import logger

# 将项目根目录加入 sys.path，以便能导入 src 下的模块
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.data_pipeline.config import DUCKDB_PATH


def init_database():
    # 1. 将字符串转换为 Path 对象
    db_path = Path(DUCKDB_PATH)

    # 2. 确保数据库所在的父文件夹存在 (例如 F:/QuantData/)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"数据库准备创建或连接于: {db_path}")

    # 3. 连接数据库 (如果文件不存在，会自动创建)
    # 注意：Windows 下路径最好转为字符串
    conn = duckdb.connect(database=str(db_path), read_only=False)
    logger.info("✅ 成功连接 DuckDB")

    try:
        # 4. 执行建表 SQL (使用 IF NOT EXISTS 保证幂等，多次运行不会报错)
        # 这里以量化常用的日线行情表为例
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS daily_bars (
            ts_code VARCHAR,       -- 股票代码 (如 000001.SZ)
            trade_date DATE,       -- 交易日期
            open DOUBLE,           -- 开盘价
            high DOUBLE,           -- 最高价
            low DOUBLE,            -- 最低价
            close DOUBLE,          -- 收盘价
            pre_close DOUBLE,      -- 昨收价
            vol DOUBLE,            -- 成交量
            amount DOUBLE,         -- 成交额
            PRIMARY KEY (ts_code, trade_date) -- 设置主键防止数据重复
        );
        """
        conn.execute(create_table_sql)
        logger.info("!!Success!! 表 'daily_bars' 初始化成功")

        # 5. 你可以在这里继续建其他的表 (如：复权因子表、财务数据表等)
        # conn.execute("CREATE TABLE IF NOT EXISTS adj_factors (...)")

    except Exception as e:
        logger.error(f"!!Failure!! 初始化数据库表失败: {e}")
    finally:
        # 6. 关闭连接
        conn.close()
        logger.info("!!Success!! 数据库连接已关闭")


if __name__ == "__main__":
    init_database()
