"""
情感分析：DeepSeek API 评估
==========================
使用 DeepSeek API 对标注数据进行情感预测，评估准确率/召回率/F1。

用法：
    python train_and_predict.py
"""

import os
import sys
import time
import json
import warnings
import numpy as np
import pandas as pd
from collections import Counter
from openai import OpenAI
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix,
)

warnings.filterwarnings("ignore")

# ============================================================
# DeepSeek API 配置
# ============================================================
API_KEY = "填写你的DeepSeek API Key"
API_BASE = "https://api.deepseek.com"
MODEL = "deepseek-chat"

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
ANNOTATION_CSV = os.path.join(OUTPUT_DIR, "标注模板_AI优化.csv")

BATCH_SIZE = 15
SLEEP_SEC = 0.3
MAX_RETRIES = 3
MAX_SAMPLES = 0

LABEL_MAP = {"负向": 0, "中性": 1, "正向": 2}
NUMERIC_LABEL_MAP = {-1: 0, 0: 1, 1: 2}
ID2LABEL = {0: "负向", 1: "中性", 2: "正向"}

# ============================================================
# Prompt
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


def load_annotations(csv_path):
    print(f"\n[1] 加载标注数据: {csv_path}")
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    label_col = None
    for col in ["情感标注", "sentiment_label", "label"]:
        if col in df.columns:
            label_col = col
            break
    if label_col is None:
        print("错误: 未找到标注列，请确保 CSV 包含 '情感标注' 列（值为 -1/0/1 或 正向/负向/中性）")
        sys.exit(1)

    df = df.dropna(subset=[label_col]).copy()

    raw_values = df[label_col].astype(str).str.strip()
    if raw_values.str.match(r"^-?\d+$").all():
        df["_label_id"] = raw_values.astype(int).map(NUMERIC_LABEL_MAP)
    else:
        df["_label_id"] = raw_values.map(LABEL_MAP)

    df = df.dropna(subset=["_label_id"]).copy()
    df["_label_id"] = df["_label_id"].astype(int)

    print(f"  有效标注: {len(df)} 条")
    dist = df["_label_id"].value_counts().sort_index()
    for lid, cnt in dist.items():
        print(f"    {ID2LABEL[lid]}: {cnt} ({cnt/len(df)*100:.1f}%)")

    content_col = None
    for col in ["评论内容", "content"]:
        if col in df.columns:
            content_col = col
            break

    texts = df[content_col].astype(str).tolist()
    labels = df["_label_id"].tolist()
    return texts, labels, dist


def main():
    print("=" * 60)
    print("  情感分析：DeepSeek API 评估")
    print(f"  模型: {MODEL}")
    print("=" * 60)

    if not os.path.exists(ANNOTATION_CSV):
        print(f"\n错误: 标注文件不存在: {ANNOTATION_CSV}")
        sys.exit(1)

    texts, labels, dist = load_annotations(ANNOTATION_CSV)

    if MAX_SAMPLES > 0 and MAX_SAMPLES < len(texts):
        texts = texts[:MAX_SAMPLES]
        labels = labels[:MAX_SAMPLES]
        print(f"\n  限定评估样本数: {MAX_SAMPLES}")

    actual_labels = labels
    pred_numerics = []

    print(f"\n[2] DeepSeek API 批量预测 ({len(texts)} 条, batch_size={BATCH_SIZE})")
    for i in range(0, len(texts), BATCH_SIZE):
        batch_end = min(i + BATCH_SIZE, len(texts))
        batch_texts = texts[i:batch_end]
        batch_items = [(j + 1, text) for j, text in enumerate(batch_texts)]

        try:
            results = call_api(batch_items)
        except Exception as e:
            print(f"  [{batch_end}/{len(texts)}] 失败: {e}")
            results = [{"sentiment": 0, "keywords": "API失败"} for _ in range(len(batch_texts))]

        for result in results:
            sentiment_raw = result["sentiment"]
            internal_label = NUMERIC_LABEL_MAP.get(sentiment_raw, 1)
            pred_numerics.append(internal_label)

        if (batch_end) % 500 == 0 or batch_end >= len(texts):
            print(f"  已预测 {batch_end} / {len(texts)} 条...")

        time.sleep(SLEEP_SEC)

    pred_labels = np.array(pred_numerics)
    true_labels = np.array(actual_labels)

    print("\n" + "=" * 60)
    print("  评估结果")
    print("=" * 60)

    acc = accuracy_score(true_labels, pred_labels)
    p, r, f1, _ = precision_recall_fscore_support(true_labels, pred_labels, average="weighted", zero_division=0)
    print(f"\n  整体指标:")
    print(f"    Accuracy : {acc:.4f}")
    print(f"    Precision: {p:.4f}")
    print(f"    Recall   : {r:.4f}")
    print(f"    F1-score : {f1:.4f}")

    print(f"\n  分类报告:")
    print(classification_report(true_labels, pred_labels, target_names=list(ID2LABEL.values()), zero_division=0))

    cm = confusion_matrix(true_labels, pred_labels)
    print(f"  混淆矩阵 (行=真实, 列=预测):")
    print(f"           预测\\真实")
    print(f"           {'  '.join(f'{ID2LABEL[i]:>4s}' for i in range(3))}")
    for i in range(3):
        print(f"    {ID2LABEL[i]:4s}  {'  '.join(f'{cm[i][j]:>4d}' for j in range(3))}")

    pred_dist = Counter(pred_numerics)
    true_dist = Counter(actual_labels)
    print(f"\n  标签分布对比:")
    print(f"    {'类别':6s}  {'真实':>6s}  {'预测':>6s}  {'差异':>6s}")
    for lid in range(3):
        t = true_dist.get(lid, 0)
        p_d = pred_dist.get(lid, 0)
        diff = p_d - t
        print(f"    {ID2LABEL[lid]:6s}  {t:>6d}  {p_d:>6d}  {diff:>+6d}")

    print("\n" + "=" * 60)
    print("  评估完成!")
    print(f"  DeepSeek API ({MODEL}) 在标注数据上的 F1: {f1:.4f}")
    print(f"  如果满意，运行: python 情感分析/predict_all.py 进行全量预测")
    print("=" * 60)


if __name__ == "__main__":
    main()
