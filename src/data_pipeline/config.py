import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
