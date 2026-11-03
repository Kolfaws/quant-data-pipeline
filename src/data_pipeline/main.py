from logger import logger


def run_pipeline():
    logger.info("🚀 启动数据管道...")

    # 1. 获取数据
    # conn = TushareConnector()
    # raw_data = conn.fetch_daily_bars("20231001", "20231031")

    # 2. 处理数据
    # clean_data = clean_data(raw_data)

    # 3. 落地数据
    # save_to_parquet(clean_data, "data/processed/daily_bars.parquet")

    logger.info("✅ 数据管道运行完成！")


if __name__ == "__main__":
    run_pipeline()
