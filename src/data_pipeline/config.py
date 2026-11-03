import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
DUCKDB_PATH = os.getenv("DUCKDB_PATH")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # Default log level = INFO
