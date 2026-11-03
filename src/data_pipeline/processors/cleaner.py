import polars as pl


def clean_data(df: pl.DataFrame) -> pl.DataFrame:
    # 示例：去重、处理缺失值
    if df is None:
        return None
    return df.drop_nulls()
