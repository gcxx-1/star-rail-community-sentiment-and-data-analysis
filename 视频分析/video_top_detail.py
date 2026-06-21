"""
video_top_detail.py
====================
各版本 Top3 视频明细 + 全版本 Top10 极值。

阈值自适应: 小表用 pandas，大表用 SQL。
"""

import os
import sqlite3
import numpy as np

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "数据预处理", "b站崩铁社区分析.db")
LARGE_TABLE_THRESHOLD = 100_000


def _load_pandas(conn):
    return pd.read_sql("SELECT * FROM videos_clean", conn)


def _load_sql_cols(conn):
    rows = conn.execute("""
        SELECT version, 视频标题,
               播放量, 转发量, 弹幕量, 评论量, 点赞量, 投币量, 收藏量
        FROM videos_clean
    """).fetchall()
    cols = ["version", "视频标题", "播放量", "转发量", "弹幕量", "评论量", "点赞量", "投币量", "收藏量"]
    return pd.DataFrame(rows, columns=cols)


def minmax_norm(series):
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([50.0] * len(series), index=series.index)
    return (series - mn) / (mx - mn) * 100


def print_per_version_top3(df):
    print(f"\n{'='*90}")
    print(f"各版本 Top3 综合得分")
    print(f"{'='*90}")

    raw_cols = ["播放量", "转发量", "弹幕量", "评论量", "点赞量", "投币量", "收藏量"]
    for c in raw_cols:
        df[f"{c}_norm"] = minmax_norm(df[c].astype(float))

    df["传播度"] = (df["播放量_norm"] + df["转发量_norm"]) / 2
    df["讨论度"] = (df["弹幕量_norm"] + df["评论量_norm"]) / 2
    df["喜爱度"] = (df["点赞量_norm"] + df["投币量_norm"] + df["收藏量_norm"]) / 3
    df["综合指数"] = df["传播度"] * 0.25 + df["讨论度"] * 0.25 + df["喜爱度"] * 0.50

    for ver, grp in df.groupby("version", sort=False):
        top3 = grp.nlargest(3, "综合指数")
        print(f"\n  [{ver}]")
        for i, (_, row) in enumerate(top3.iterrows(), 1):
            title = str(row["视频标题"])[:40]
            print(f"    {i}. {title}")
            print(f"       综合:{row['综合指数']:.1f}  传播:{row['传播度']:.1f}  讨论:{row['讨论度']:.1f}  喜爱:{row['喜爱度']:.1f}")
            print(f"       播放:{int(row['播放量']):,}  弹幕:{int(row['弹幕量']):,}  评论:{int(row['评论量']):,}  点赞:{int(row['点赞量']):,}")


def print_alltime_top10(df):
    print(f"\n{'='*90}")
    print(f"全版本 Top10 极值")
    print(f"{'='*90}")

    metrics = [
        ("播放量", "播放量"),
        ("弹幕量", "弹幕量"),
        ("评论量", "评论量"),
        ("点赞量", "点赞量"),
        ("投币量", "投币量"),
        ("收藏量", "收藏量"),
        ("转发量", "转发量"),
    ]

    for label, col in metrics:
        top10 = df.nlargest(10, col)
        print(f"\n  {label} Top10:")
        for i, (_, row) in enumerate(top10.iterrows(), 1):
            title = str(row["视频标题"])[:40]
            print(f"    {i:>2}. [{row['version']}] {title} — {int(row[col]):,}")


def main():
    print("=" * 60)
    print("  视频 Top3 明细 (自适应 SQL/pandas)")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    total_rows = conn.execute("SELECT COUNT(*) FROM videos_clean").fetchone()[0]
    print(f"\n  videos_clean: {total_rows:,} 行")

    if total_rows >= LARGE_TABLE_THRESHOLD:
        print(f"  数据量 >= {LARGE_TABLE_THRESHOLD:,} → SQL 读取")
        df = _load_sql_cols(conn)
    else:
        print(f"  数据量 < {LARGE_TABLE_THRESHOLD:,} → pandas")
        df = _load_pandas(conn)
    conn.close()

    print_per_version_top3(df)
    print_alltime_top10(df)

    print(f"\n{'='*60}")
    print("  Top3 明细完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
