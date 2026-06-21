"""
predict_all.py
==============
使用 DeepSeek API 对数据库中所有评论进行情感预测并存入 SQLite 数据库。

用法：
    python predict_all.py
"""

import os
import sqlite3
import time
import json
import numpy as np
from collections import Counter

import pandas as pd

from openai import OpenAI

# ============================================================
# DeepSeek API 配置
# ============================================================
API_KEY = "填写你的DeepSeek API Key"
API_BASE = "https://api.deepseek.com"
MODEL = "deepseek-chat"

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "数据预处理", "b站崩铁社区分析.db")
OUTPUT_DB = DB_PATH
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "sentiment_predictions.csv")
SUMMARY_CSV = os.path.join(OUTPUT_DIR, "sentiment_summary.csv")

BATCH_SIZE = 15
SLEEP_SEC = 0.3
MAX_RETRIES = 3

LARGE_TABLE_THRESHOLD = 100_000

ID2LABEL = {0: "负向", 1: "中性", 2: "正向"}
ID2NUM = {0: -1, 1: 0, 2: 1}
LABEL_MAP = {-1: "负向", 0: "中性", 1: "正向"}

# ============================================================
# 领域规则配置 (可选后处理，默认关闭)
# ============================================================
USE_DOMAIN_RULES = False

POSITIVE_KEYWORDS = [
    ("神", 0.15), ("好看", 0.15), ("燃", 0.10), ("厨力拉满", 0.20),
    ("抽爆", 0.20), ("老婆", 0.15), ("帅爆", 0.20), ("赢麻了", 0.25),
    ("起飞", 0.15), ("绝了", 0.10), ("太强了", 0.15), ("封神", 0.20),
    ("无敌", 0.10), ("良心", 0.10), ("吹爆", 0.20), ("爱了", 0.10),
    ("期待", 0.05), ("不错", 0.05), ("好耶", 0.10), ("抽", 0.05),
    ("双金", 0.20), ("欧皇", 0.15), ("没歪", 0.15), ("不歪", 0.15),
    ("出金", 0.15), ("一发入魂", 0.25), ("十连双金", 0.25),
    ("必抽", 0.10), ("人权卡", 0.10), ("版本答案", 0.15),
    ("满命", 0.10), ("万敌", 0.10), ("白厄", 0.10),
]

NEGATIVE_KEYWORDS = [
    ("退坑", 0.25), ("寄了", 0.20), ("烂活", 0.20), ("坐牢", 0.20),
    ("破防", 0.20), ("不如原神", 0.20), ("答辩", 0.20), ("一坨", 0.20),
    ("膨胀", 0.15), ("逼氪", 0.25), ("劝退", 0.25), ("无聊", 0.10),
    ("失望", 0.15), ("摆烂", 0.20), ("敷衍", 0.15), ("恶心", 0.20),
    ("策划", 0.05), ("产能不足", 0.15), ("骗氪", 0.25), ("没意思", 0.10),
    ("拉胯", 0.15), ("歪了", 0.15), ("沉船", 0.25), ("保底歪", 0.25),
    ("吃保底", 0.20), ("吃井", 0.25), ("退环境", 0.15),
    ("绷不住", 0.20), ("发刀", 0.20), ("被刀", 0.20), ("刀子", 0.15),
    ("亏麻了", 0.20), ("坐牢局", 0.25), ("牢玩家", 0.15),
    ("数值膨胀", 0.20), ("腰斩", 0.15), ("砍了", 0.10),
    ("凉了", 0.15), ("药丸", 0.20), ("要完", 0.15),
    ("太贵", 0.10), ("氪穿", 0.15), ("弃坑", 0.25), ("不玩了", 0.20),
    ("胃疼", 0.15), ("裂开", 0.10), ("绝了", -0.05),
]

IRONY_PATTERNS = [
    "真有你的", "策划真棒啊", "太对了哥", "谢谢你", "不愧是你",
    "可真是", "太感动了", "我谢谢你", "好得很", "真厉害啊策划",
    "这波操作", "米忽悠你是会玩的",
]
IRONY_WEIGHT = 0.35

# ============================================================
# DeepSeek API 调用
# ============================================================
SYSTEM_PROMPT = """你是一个崩坏星穹铁道玩家社区的评论情感分析专家。

分析玩家评论，判定情感倾向，按以下标准：
- 正面（输出:1）：表达对角色/剧情/画面/音乐/活动的喜爱、期待、夸赞、厨力表达
- 中性（输出:0）：客观询问、正常讨论、兑换码/表情/纯标点、无情绪倾向内容
- 负面（输出:-1）：抱怨、批评、失望、攻略吐槽、建议改进、不看好、表示弃坑/摆烂

对每条评论输出一行紧凑JSON（不要换行），格式：
{"n":序号,"s":1/0/-1,"kw":["关键词1","关键词2"]}

输出示例：
{"n":1,"s":1,"kw":["期待","燃"]}
{"n":2,"s":0,"kw":[]}
{"n":3,"s":-1,"kw":["失望","逼氪"]}"""


def build_batch_prompt(batch_items):
    lines = []
    for idx, text in batch_items:
        text_clean = str(text).replace("\n", " ").replace("\r", " ").strip()
        if not text_clean:
            text_clean = "(空)"
        lines.append(f"{idx}. {text_clean}")
    return "\n".join(lines)


def call_api(batch_items, retries=MAX_RETRIES):
    client = OpenAI(api_key=API_KEY, base_url=API_BASE)
    user_msg = build_batch_prompt(batch_items)

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=200 * len(batch_items),
                timeout=60,
            )
            content = response.choices[0].message.content
            return parse_batch_response(content, len(batch_items))
        except Exception as e:
            print(f"    API 错误 (第{attempt+1}次): {type(e).__name__}: {str(e)[:80]}")
            if attempt < retries - 1:
                wait = (attempt + 1) * 3
                print(f"    等待 {wait}s 后重试...")
                time.sleep(wait)
            else:
                raise


def parse_batch_response(content, expected_count):
    results = []
    lines = content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            sentiment = obj.get("s", 0)
            if isinstance(sentiment, str):
                if sentiment in ("正向", "正面", "1"):
                    sentiment = 1
                elif sentiment in ("负向", "负面", "-1"):
                    sentiment = -1
                else:
                    sentiment = 0
            sentiment = int(sentiment)
            if sentiment not in (-1, 0, 1):
                sentiment = 0
            results.append({
                "sentiment": sentiment,
                "keywords": ",".join(obj.get("kw", [])),
            })
        except (json.JSONDecodeError, KeyError, ValueError):
            results.append({"sentiment": 0, "keywords": "解析失败"})

    while len(results) < expected_count:
        results.append({"sentiment": 0, "keywords": "解析遗漏"})

    return results[:expected_count]


def detect_keywords(text, keyword_list):
    text = str(text)
    total_weight = 0.0
    for kw, weight in keyword_list:
        if kw in text:
            total_weight += weight
    return min(total_weight, 0.6)


def detect_irony(text):
    text = str(text)
    has_irony = any(p in text for p in IRONY_PATTERNS)
    if not has_irony:
        return False, 0.0
    has_positive = any(kw in text for kw, _ in POSITIVE_KEYWORDS)
    if has_positive:
        return True, IRONY_WEIGHT
    return False, 0.0


def apply_domain_rules(text, sentiment_raw):
    neg_weight = detect_keywords(text, NEGATIVE_KEYWORDS)
    pos_weight = detect_keywords(text, POSITIVE_KEYWORDS)
    is_irony, irony_w = detect_irony(text)
    adjusted_score = float(sentiment_raw)
    if neg_weight > 0:
        adjusted_score -= neg_weight * 0.6
    if pos_weight > 0:
        adjusted_score += pos_weight * 0.4
    if is_irony:
        adjusted_score -= irony_w * 0.9
    adjusted_score = max(-1.0, min(1.0, adjusted_score))
    if adjusted_score > 0.3:
        return 1, "正向"
    elif adjusted_score < -0.3:
        return -1, "负向"
    else:
        return 0, "中性"


# ============================================================
# 数据加载 — 自适应
# ============================================================
def _load_sql(conn):
    cursor = conn.cursor()
    total = cursor.execute("SELECT COUNT(*) FROM comments_clean").fetchone()[0]
    cursor.execute("SELECT content FROM comments_clean")
    texts = [row[0] for row in cursor.fetchall()]
    return texts, total


def _load_pandas(conn):
    df = pd.read_sql("SELECT * FROM comments_clean", conn)
    texts = df["content"].astype(str).tolist()
    return df, texts


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 60)
    print("  全量情感预测 (DeepSeek API) + 入库")
    print(f"  模型: {MODEL}")
    print(f"  领域规则: {'开启' if USE_DOMAIN_RULES else '关闭'}")
    print("=" * 60)

    print(f"\n[1] 加载数据库: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    total_rows = conn.execute("SELECT COUNT(*) FROM comments_clean").fetchone()[0]
    print(f"  评论数: {total_rows:,}")

    if total_rows >= LARGE_TABLE_THRESHOLD:
        print(f"  数据量 >= {LARGE_TABLE_THRESHOLD:,} → SQL 读取")
        texts, _ = _load_sql(conn)
        df = None
    else:
        print(f"  数据量 < {LARGE_TABLE_THRESHOLD:,} → pandas 加载")
        df, texts = _load_pandas(conn)
    conn.close()

    all_preds_num, all_preds_label, all_keywords, all_confidences = [], [], [], []

    print(f"\n[2] 开始预测 (batch_size={BATCH_SIZE}, 总批次≈{(len(texts) + BATCH_SIZE - 1) // BATCH_SIZE})")
    for i in range(0, len(texts), BATCH_SIZE):
        batch_end = min(i + BATCH_SIZE, len(texts))
        batch_texts = texts[i:batch_end]
        batch_items = [(j + 1, text) for j, text in enumerate(batch_texts)]

        try:
            results = call_api(batch_items)
        except Exception as e:
            print(f"  [{batch_end}/{len(texts)}] 失败: {e}")
            results = [{"sentiment": 0, "keywords": "API失败"} for _ in range(len(batch_texts))]

        for j, text in enumerate(batch_texts):
            sentiment_raw = results[j]["sentiment"]
            kw = results[j].get("keywords", "")

            if USE_DOMAIN_RULES:
                sentiment_raw, final_label = apply_domain_rules(text, sentiment_raw)
                confidence = 1.0
            else:
                final_label = LABEL_MAP.get(sentiment_raw, "中性")
                confidence = 1.0

            all_preds_num.append(sentiment_raw)
            all_preds_label.append(final_label)
            all_keywords.append(kw)
            all_confidences.append(confidence)

        if (batch_end) % 5000 == 0 or batch_end >= len(texts):
            print(f"  已预测 {batch_end:,} / {len(texts):,} 条...")

        time.sleep(SLEEP_SEC)

    if df is None:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT * FROM comments_clean", conn)
        conn.close()

    df["sentiment_label"] = all_preds_label
    df["sentiment"] = all_preds_num
    df["api_confidence"] = all_confidences
    df["api_keywords"] = all_keywords

    dist = Counter(all_preds_label)
    total = len(all_preds_label)
    print(f"\n[3] 预测分布 ({total:,} 条):")
    for label in ["正向", "中性", "负向"]:
        print(f"    {label}: {dist.get(label, 0)} ({dist.get(label, 0)/total*100:.1f}%)")

    print(f"\n[4] 存入主数据库 sentiment_result 表: {OUTPUT_DB}")
    db_conn = sqlite3.connect(OUTPUT_DB)

    sentiment_cols = [
        ("id", "INTEGER PRIMARY KEY"),
        ("version", "TEXT"),
        ("version_major", "INTEGER"),
        ("version_minor", "INTEGER"),
        ("user_id", "INTEGER"),
        ("user_level", "INTEGER"),
        ("content", "TEXT"),
        ("comment_time", "TEXT"),
        ("likes", "INTEGER"),
        ("sentiment_label", "TEXT"),
        ("sentiment", "INTEGER"),
        ("api_confidence", "REAL"),
        ("api_keywords", "TEXT"),
    ]
    cols_def = ", ".join(f"{c} {t}" for c, t in sentiment_cols)
    db_conn.execute("DROP TABLE IF EXISTS sentiment_result")
    db_conn.execute(f"CREATE TABLE sentiment_result ({cols_def})")
    db_conn.commit()

    row_cols = [c for c, _ in sentiment_cols]
    db_rows = []
    for _, row in df.iterrows():
        vals = [row.get(c, None) for c in row_cols]
        db_rows.append(tuple(vals))
    placeholders = ", ".join("?" for _ in row_cols)
    db_conn.executemany(f"INSERT INTO sentiment_result VALUES ({placeholders})", db_rows)
    db_conn.commit()

    df[row_cols].to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    summary_rows = []
    for v in sorted(df["version"].unique()):
        v_df = df[df["version"] == v]
        v_total = len(v_df)
        v_dist = Counter(v_df["sentiment_label"])
        summary_rows.append({
            "version": v, "total": v_total,
            "正向": v_dist.get("正向", 0), "中性": v_dist.get("中性", 0), "负向": v_dist.get("负向", 0),
            "正向占比": f"{v_dist.get('正向',0)/v_total:.2%}",
            "负向占比": f"{v_dist.get('负向',0)/v_total:.2%}",
            "中性占比": f"{v_dist.get('中性',0)/v_total:.2%}",
        })

    pd.DataFrame(summary_rows).to_sql("version_summary", db_conn, if_exists="replace", index=False)

    db_conn.execute("""
        CREATE VIEW IF NOT EXISTS v_monthly_sentiment AS
        SELECT SUBSTR(comment_time,1,7) AS month, version, sentiment, COUNT(*) AS cnt
        FROM sentiment_result GROUP BY month, version, sentiment
        ORDER BY month, version, sentiment
    """)
    db_conn.commit()

    cursor = db_conn.cursor()
    db_count = cursor.execute("SELECT COUNT(*) FROM sentiment_result").fetchone()[0]
    db_conn.close()

    pd.DataFrame(summary_rows).to_csv(SUMMARY_CSV, index=False, encoding="utf-8-sig")

    pos_v = sum(1 for r in summary_rows if r["正向"] > r["负向"])
    neg_v = sum(1 for r in summary_rows if r["负向"] > r["正向"])

    print(f"\n[5] 完成!")
    print(f"  数据库: {OUTPUT_DB}")
    print(f"  sentiment_result: {db_count:,} 条")
    print(f"  version_summary: {len(summary_rows)} 个版本")
    print(f"  v_monthly_sentiment: 月度趋势视图")
    print(f"  CSV备份: {OUTPUT_CSV}")
    print(f"  CSV汇总: {SUMMARY_CSV}")
    print(f"  正向为主版本: {pos_v}  负向为主版本: {neg_v}")


if __name__ == "__main__":
    main()
