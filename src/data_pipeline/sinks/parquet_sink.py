from pathlib import Path

import polars as pl


def save_to_parquet(df: pl.DataFrame, filepath: str):
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    # df.write_parquet(path)
    print(f"数据已保存至 {path}")
