"""
video_dimension_analysis.py
============================
版本视频维度分析（方案A: MinMax归一化 + 均值法）:
  传播度=(播放+转发)/2  讨论度=(弹幕+评论)/2  喜爱度=(点赞+投币+收藏)/3
  综合指数=传播×25%+讨论×25%+喜爱×50%

阈值自适应: 小表用 pandas，大表用 SQL 聚合。
"""

import os
import sqlite3
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

import pandas as pd

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "数据预处理", "b站崩铁社区分析.db")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "version_dimension_scores.csv")
LARGE_TABLE_THRESHOLD = 100_000

W_SPREAD, W_DISCUSS, W_LIKE = 0.25, 0.25, 0.50


def _load_pandas(conn):
    df = pd.read_sql("SELECT * FROM videos_clean", conn)
    return df


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


def compute_scores(df):
    raw = {c: df[c].astype(float) for c in ["播放量", "转发量", "弹幕量", "评论量", "点赞量", "投币量", "收藏量"]}
    df["播放量_norm"] = minmax_norm(raw["播放量"])
    df["转发量_norm"] = minmax_norm(raw["转发量"])
    df["弹幕量_norm"] = minmax_norm(raw["弹幕量"])
    df["评论量_norm"] = minmax_norm(raw["评论量"])
    df["点赞量_norm"] = minmax_norm(raw["点赞量"])
    df["投币量_norm"] = minmax_norm(raw["投币量"])
    df["收藏量_norm"] = minmax_norm(raw["收藏量"])

    df["传播度"] = (df["播放量_norm"] + df["转发量_norm"]) / 2
    df["讨论度"] = (df["弹幕量_norm"] + df["评论量_norm"]) / 2
    df["喜爱度"] = (df["点赞量_norm"] + df["投币量_norm"] + df["收藏量_norm"]) / 3
    df["综合指数"] = df["传播度"] * W_SPREAD + df["讨论度"] * W_DISCUSS + df["喜爱度"] * W_LIKE

    ver_scores = df.groupby("version").agg(
        传播度=("传播度", "mean"),
        讨论度=("讨论度", "mean"),
        喜爱度=("喜爱度", "mean"),
        综合指数=("综合指数", "mean"),
        视频数=("version", "count"),
    ).sort_values("综合指数", ascending=False).reset_index()

    for c in ["传播度", "讨论度", "喜爱度", "综合指数"]:
        ver_scores[c] = ver_scores[c].round(2)

    ver_scores.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    conn_out = sqlite3.connect(DB_PATH)
    ver_scores.to_sql("version_dimension_scores", conn_out, if_exists="replace", index=False)
    conn_out.commit()
    conn_out.close()

    return ver_scores, df


def plot_trend(ver_scores):
    fig, ax = plt.subplots(figsize=(18, 6))
    x = range(len(ver_scores))
    labels = ver_scores["version"].tolist()
    ax.plot(x, ver_scores["传播度"], "o-", label="传播度", linewidth=2, markersize=5)
    ax.plot(x, ver_scores["讨论度"], "s-", label="讨论度", linewidth=2, markersize=5)
    ax.plot(x, ver_scores["喜爱度"], "D-", label="喜爱度", linewidth=2, markersize=5)
    ax.plot(x, ver_scores["综合指数"], "^-", label="综合指数", linewidth=2.5, markersize=6, color="black")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("得分 (0~100)")
    ax.set_title("各版本维度得分趋势 (Min-Max归一化)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(SCRIPT_DIR, "version_dimension_trend.png"), dpi=150)
    plt.close(fig)
    print("  ✓ version_dimension_trend.png")


def plot_heatmap(ver_scores):
    heat_data = ver_scores.set_index("version")[["传播度", "讨论度", "喜爱度", "综合指数"]]
    fig, ax = plt.subplots(figsize=(20, 8))
    im = ax.imshow(heat_data.T.values, aspect="auto", cmap="RdYlGn_r", vmin=1, vmax=20)
    ax.set_xticks(range(len(heat_data)))
    ax.set_xticklabels(heat_data.index, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(heat_data.columns)))
    ax.set_yticklabels(heat_data.columns, fontsize=10)
    for i in range(len(heat_data.columns)):
        for j in range(len(heat_data)):
            val = heat_data.iloc[j, i]
            color = "white" if val > 12 else "black"
            ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=7, color=color)
    fig.colorbar(im, ax=ax, shrink=0.8, label="得分")
    ax.set_title("版本维度热力图 (1~20)")
    fig.tight_layout()
    fig.savefig(os.path.join(SCRIPT_DIR, "version_dimension_heatmap.png"), dpi=150)
    plt.close(fig)
    print("  ✓ version_dimension_heatmap.png")


def plot_radar(ver_scores, df):
    top5 = ver_scores.head(5)["version"].tolist()
    radar_labels = ["传播度", "讨论度", "喜爱度"]
    angles = np.linspace(0, 2 * np.pi, len(radar_labels), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw=dict(polar=True))
    colors = plt.cm.tab10(np.linspace(0, 1, len(top5)))
    max_val = max(df[(df["version"].isin(top5))][["传播度", "讨论度", "喜爱度"]].values.max(), 1)

    for idx, ver in enumerate(top5):
        v = ver_scores[ver_scores["version"] == ver].iloc[0]
        values = [v["传播度"], v["讨论度"], v["喜爱度"]]
        values += values[:1]
        ax.fill(angles, values, alpha=0.1, color=colors[idx])
        ax.plot(angles, values, "o-", label=ver, color=colors[idx], linewidth=2)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(radar_labels, fontsize=11)
    ax.set_ylim(0, max_val * 1.15)
    ax.set_title("Top5 版本维度雷达图")
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1))
    fig.tight_layout()
    fig.savefig(os.path.join(SCRIPT_DIR, "version_dimension_radar.png"), dpi=150)
    plt.close(fig)
    print("  ✓ version_dimension_radar.png")


def main():
    print("=" * 60)
    print("  视频版本维度分析 (MinMax归一化)")
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

    ver_scores, df_full = compute_scores(df)

    print(f"\n{'='*60}")
    print("  Top 10 版本综合指数")
    print(f"{'='*60}")
    top10 = ver_scores.head(10)
    print(f"  {'排名':<4} {'版本':<6} {'传播度':>8} {'讨论度':>8} {'喜爱度':>8} {'综合':>8} {'视频数':>6}")
    for i, (_, row) in enumerate(top10.iterrows(), 1):
        print(f"  {i:<4} {row['version']:<6} {row['传播度']:>8.1f} {row['讨论度']:>8.1f} {row['喜爱度']:>8.1f} {row['综合指数']:>8.1f} {int(row['视频数']):>6}")

    print(f"\n  综合指数最高: {ver_scores.iloc[0]['version']} ({ver_scores.iloc[0]['综合指数']:.1f})")
    print(f"  综合指数最低: {ver_scores.iloc[-1]['version']} ({ver_scores.iloc[-1]['综合指数']:.1f})")

    print(f"\n{'='*60}")
    print("  生成图表")
    print(f"{'='*60}")
    plot_trend(ver_scores)
    plot_heatmap(ver_scores)
    plot_radar(ver_scores, df_full)

    print(f"\n  输出: {OUTPUT_CSV}")
    print("=" * 60)


if __name__ == "__main__":
    main()
