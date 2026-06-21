"""
sample_for_annotation.py
=========================
从 b站崩铁社区分析.db 的 comments_clean 表中按版本分层抽样，
生成待标注 CSV。

数据量小时用 pandas 灵活分析，大时用 SQL 聚合 + 游标抽样。
"""

import os
import re
import sqlite3
import random

import pandas as pd

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "数据预处理", "b站崩铁社区分析.db")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "标注模板_待标注.csv")

SAMPLE_PER_VERSION = 200
SEED = 42
LARGE_TABLE_THRESHOLD = 100_000

MIN_COMMENT_LEN = 8
POSITIVE_KW = ["抽", "出金", "欧皇", "好看", "燃", "期待", "老婆", "封神", "吹爆", "厨力", "不歪",
               "双金", "十连", "起飞", "没歪", "好耶", "神", "爱了", "帅爆", "赢麻了", "必抽", "人权卡"]
NEGATIVE_KW = ["退坑", "答辩", "一坨", "烂活", "寄了", "破防", "歪了", "沉船", "吃保底", "逼氪",
               "骗氪", "无聊", "摆烂", "失望", "敷衍", "恶心", "拉胯", "不如原神", "坐牢", "弃坑"]
NEUTRAL_PATTERNS = [
    r"^\d+$", r"^[A-Za-z0-9+/=]+$",
    r"^[?？…\.。,，!！\s]+$",
    r"^[😂😭😅😊🙏👍👀💪🔥]+$",
]

random.seed(SEED)


def _is_neutral_like(text):
    text = str(text).strip()
    for pat in NEUTRAL_PATTERNS:
        if re.fullmatch(pat, text):
            return True
    return False


def predict_pseudo_label(text):
    text = str(text)
    pos_count = sum(1 for kw in POSITIVE_KW if kw in text)
    neg_count = sum(1 for kw in NEGATIVE_KW if kw in text)
    if pos_count > neg_count:
        return "正向"
    elif neg_count > pos_count:
        return "负向"
    return "中性"


# ============================================================
# 大表: SQL 聚合 + 游标抽样
# ============================================================
def _sample_via_sql(conn):
    print(f"\n[SQL抽样] 按版本分层，每版本 {SAMPLE_PER_VERSION} 条")
    cursor = conn.cursor()

    versions = [r[0] for r in cursor.execute(
        "SELECT version FROM comments_clean GROUP BY version "
        "ORDER BY version_major, version_minor"
    ).fetchall()]

    all_rows = []
    for ver in versions:
        candidates = cursor.execute(
            "SELECT id, version, content, comment_time, likes FROM comments_clean WHERE version = ?",
            (ver,)
        ).fetchall()

        pool = []
        for cid, v, txt, tm, lk in candidates:
            txt_str = str(txt).strip() if txt else ""
            if len(txt_str) < MIN_COMMENT_LEN:
                continue
            pool.append((cid, v, txt_str, tm, lk))

        if len(pool) <= SAMPLE_PER_VERSION:
            sampled = pool
        else:
            sampled = random.sample(pool, SAMPLE_PER_VERSION)

        for cid, v, txt, tm, lk in sampled:
            pseudo = predict_pseudo_label(txt)
            all_rows.append({
                "评论ID": cid,
                "版本": v,
                "评论内容": txt,
                "评论时间": tm,
                "点赞数": lk,
                "伪标签": pseudo,
            })

        print(f"  {ver}: 候选 {len(pool)}, 抽样 {len(sampled)}")

    return pd.DataFrame(all_rows)


# ============================================================
# 小表: pandas
# ============================================================
def _sample_via_pandas(conn):
    print(f"\n[pandas抽样] 按版本分层，每版本 {SAMPLE_PER_VERSION} 条")
    df = pd.read_sql("SELECT id, version, content, comment_time, likes FROM comments_clean", conn)

    df = df[df["content"].astype(str).str.len() >= MIN_COMMENT_LEN].copy()
    df["伪标签"] = df["content"].astype(str).apply(predict_pseudo_label)

    result_rows = []
    for ver, grp in df.groupby("version"):
        if len(grp) <= SAMPLE_PER_VERSION:
            sampled = grp
        else:
            sampled = grp.sample(n=SAMPLE_PER_VERSION, random_state=SEED)
        result_rows.append(sampled.rename(columns={"id": "评论ID", "version": "版本",
                                                     "content": "评论内容", "comment_time": "评论时间",
                                                     "likes": "点赞数"}))
        print(f"  {ver}: 候选 {len(grp)}, 抽样 {len(sampled)}")

    return pd.concat(result_rows, ignore_index=True)[["评论ID", "版本", "评论内容", "评论时间", "点赞数", "伪标签"]]


def main():
    print("=" * 60)
    print("  分层抽样标注 (自适应 SQL/pandas)")
    print(f"  数据库: {DB_PATH}")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    total_rows = conn.execute("SELECT COUNT(*) FROM comments_clean").fetchone()[0]
    print(f"\n  comments_clean: {total_rows:,} 行")

    if total_rows >= LARGE_TABLE_THRESHOLD:
        print(f"  数据量 >= {LARGE_TABLE_THRESHOLD:,} → SQL 抽样")
        result = _sample_via_sql(conn)
    else:
        print(f"  数据量 < {LARGE_TABLE_THRESHOLD:,} → pandas 抽样")
        result = _sample_via_pandas(conn)

    conn.close()

    result.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n  输出: {OUTPUT_CSV} ({len(result)} 条)")
    print(f"  版本数: {result['版本'].nunique()}")
    dist = result["伪标签"].value_counts()
    for label in ["正向", "中性", "负向"]:
        print(f"    {label}: {dist.get(label, 0)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
