"""
jieba高频词提取.py
===================
从 b站崩铁社区分析.db sentiment_result 表读取预测结果，
用 jieba 分词提取：
  1. 版本×情感高频词 → 版本情感高频词.csv + freq_words_version 表
  2. 全版本情感高频词 → 全版本情感高频词.csv + freq_words_overall 表

阈值自适应: 大表用 SQL cursor 读取，小表用 pandas。
"""

import os
import re
import sqlite3
from collections import Counter

import jieba

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "数据预处理", "b站崩铁社区分析.db")
DICT_PATH = os.path.join(SCRIPT_DIR, "jieba游戏词库.txt")
STOPWORDS_PATH = os.path.join(SCRIPT_DIR, "停用词表.txt")
OUTPUT_VERSION_CSV = os.path.join(SCRIPT_DIR, "版本情感高频词.csv")
OUTPUT_OVERALL_CSV = os.path.join(SCRIPT_DIR, "全版本情感高频词.csv")

TOP_K = 15
MIN_COMMENTS = 30
LARGE_TABLE_THRESHOLD = 100_000


def load_dict_and_stopwords():
    if os.path.exists(DICT_PATH):
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if word:
                    jieba.add_word(word)

    stopwords = set()
    if os.path.exists(STOPWORDS_PATH):
        with open(STOPWORDS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip()
                if w:
                    stopwords.add(w)
    return stopwords


def tokenize(text, stopwords):
    words = jieba.cut(str(text))
    result = []
    for w in words:
        w = w.strip()
        if not w or len(w) < 2:
            continue
        if re.match(r"^[\d\.\-\+\%\s]+$", w):
            continue
        if re.match(r"^[a-zA-Z0-9\+\-\*/=_\s]+$", w) and len(w) <= 3:
            continue
        if w in stopwords:
            continue
        result.append(w)
    return result


def _load_sql_cursor(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT version, content, sentiment_label FROM sentiment_result")
    data = {}
    for version, content, label in cursor.fetchall():
        key = (version, label)
        if key not in data:
            data[key] = []
        data[key].append(str(content) if content else "")
    return data


def _load_pandas(conn):
    df = pd.read_sql("SELECT version, content, sentiment_label FROM sentiment_result", conn)
    grp = df.groupby(["version", "sentiment_label"])
    data = {}
    for (ver, label), group in grp:
        data[(ver, label)] = group["content"].astype(str).tolist()
    return data


def main():
    print("=" * 60)
    print("  jieba 高频词提取 (版本 + 全版本)")
    print(f"  游戏词库: {DICT_PATH}")
    print(f"  停用词:   {STOPWORDS_PATH}")
    print("=" * 60)

    stopwords = load_dict_and_stopwords()
    print(f"  停用词:   {len(stopwords)}")

    conn = sqlite3.connect(DB_PATH)
    total_rows = conn.execute("SELECT COUNT(*) FROM sentiment_result").fetchone()[0]
    print(f"\n  sentiment_result: {total_rows:,} 行")

    if total_rows >= LARGE_TABLE_THRESHOLD:
        print(f"  数据量 >= {LARGE_TABLE_THRESHOLD:,} → SQL cursor 流式读取")
        data = _load_sql_cursor(conn)
    else:
        print(f"  数据量 < {LARGE_TABLE_THRESHOLD:,} → pandas")
        data = _load_pandas(conn)
    conn.close()

    # ============================================================
    # 1. 版本×情感高频词
    # ============================================================
    print(f"\n正在分词 (版本×情感 分组: {len(data)} 组)...")

    version_rows = []
    for (ver, label), texts in sorted(data.items(), key=lambda x: (x[0][0], {"正向": 1, "中性": 2, "负向": 3}.get(x[0][1], 9))):
        if label not in ("正向", "负向"):
            continue
        if len(texts) < MIN_COMMENTS:
            continue

        word_counter = Counter()
        for text in texts:
            tokens = tokenize(text, stopwords)
            word_counter.update(tokens)

        for rank, (word, freq) in enumerate(word_counter.most_common(TOP_K), 1):
            version_rows.append({
                "版本": ver,
                "情感": label,
                "排名": rank,
                "高频词": word,
                "频次": freq,
                "评论数": len(texts),
            })

    df_version = pd.DataFrame(version_rows)
    df_version.to_csv(OUTPUT_VERSION_CSV, index=False, encoding="utf-8-sig")

    conn_out = sqlite3.connect(DB_PATH)
    df_version.to_sql("freq_words_version", conn_out, if_exists="replace", index=False)
    conn_out.commit()
    conn_out.close()

    print(f"\n  输出: {OUTPUT_VERSION_CSV} ({len(df_version)} 行)")
    for label in ["正向", "负向"]:
        subset = df_version[df_version["情感"] == label]
        print(f"    {label}: {len(subset)} 条, {subset['版本'].nunique()} 个版本")

    # ============================================================
    # 2. 全版本情感高频词 (合并所有版本的文本)
    # ============================================================
    print(f"\n  合并全版本...")
    overall_texts = {}
    for (ver, label), texts in data.items():
        if label not in ("正向", "负向"):
            continue
        if label not in overall_texts:
            overall_texts[label] = []
        overall_texts[label].extend(texts)

    overall_rows = []
    for label in ["正向", "负向"]:
        texts = overall_texts.get(label, [])
        if not texts:
            continue
        word_counter = Counter()
        for text in texts:
            tokens = tokenize(text, stopwords)
            word_counter.update(tokens)

        for rank, (word, freq) in enumerate(word_counter.most_common(TOP_K), 1):
            overall_rows.append({
                "情感": label,
                "排名": rank,
                "高频词": word,
                "频次": freq,
                "评论数": len(texts),
            })

    df_overall = pd.DataFrame(overall_rows)
    df_overall.to_csv(OUTPUT_OVERALL_CSV, index=False, encoding="utf-8-sig")

    conn_out = sqlite3.connect(DB_PATH)
    df_overall.to_sql("freq_words_overall", conn_out, if_exists="replace", index=False)
    conn_out.commit()
    conn_out.close()

    print(f"  输出: {OUTPUT_OVERALL_CSV} ({len(df_overall)} 行)")
    for label in ["正向", "负向"]:
        subset = df_overall[df_overall["情感"] == label]
        print(f"    {label}: Top{len(subset)} 词 — {', '.join(r['高频词'] for _, r in subset.head(5).iterrows())}")
    print("=" * 60)


if __name__ == "__main__":
    main()
