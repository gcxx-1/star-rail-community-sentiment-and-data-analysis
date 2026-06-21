"""
数据预处理 (自适应 SQL/pandas 混合版)
=====================================
连接到 b站崩铁社区分析.db，对 comments_clean 和 videos_clean 表:
  1. 列精简 — 删除用不到的列
  2. 版本聚合统计
  3. 视图重建
  4. 摘要报告

策略:
  - 数据量大 (>= THRESHOLD): 纯 SQL (CREATE TABLE AS SELECT / GROUP BY)
  - 数据量小 (<  THRESHOLD): pandas 按需读取，灵活处理
"""

import os
import sqlite3

import pandas as pd

# ============================================================
# 配置
# ============================================================
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(OUTPUT_DIR, "b站崩铁社区分析.db")

# 超过此行数则使用纯 SQL 避免全量拉取内存
LARGE_TABLE_THRESHOLD = 100_000

# ============================================================
# comments_clean: 所有 9 列均被下游使用，无需删除
# ============================================================
COMMENT_COLS = [
    "id", "version", "version_major", "version_minor",
    "user_id", "user_level", "content", "comment_time", "likes",
]

# ============================================================
# videos_clean: 仅保留分析需要的 12 列
# 删除: 视频时长(s) / BV号 / AV号
# ============================================================
VIDEO_COLS = [
    "version", "version_major", "version_minor",
    "视频标题", "发布时间",
    "播放量", "点赞量", "弹幕量", "评论量",
    "收藏量", "转发量", "投币量",
]


def _table_size(conn, table_name):
    """返回表的行数"""
    return conn.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]


def _use_pandas(conn, table_name):
    """判断该表是否适合用 pandas 处理"""
    return _table_size(conn, table_name) < LARGE_TABLE_THRESHOLD


# ============================================================
# 列差异分析
# ============================================================
def column_stats(conn):
    print("=" * 60)
    print("列差异分析")
    print("=" * 60)

    cc_cols = [r[1] for r in conn.execute("PRAGMA table_info(comments_clean)")]
    vc_cols = [r[1] for r in conn.execute("PRAGMA table_info(videos_clean)")]

    print(f"\ncomments_clean: {len(cc_cols)} 列 → 保留 {len(COMMENT_COLS)} 列")
    removed_cc = set(cc_cols) - set(COMMENT_COLS)
    if removed_cc:
        print(f"  将删除: {', '.join(sorted(removed_cc))}")
    else:
        print(f"  无需删除列")

    print(f"\nvideos_clean: {len(vc_cols)} 列 → 保留 {len(VIDEO_COLS)} 列")
    removed_vc = set(vc_cols) - set(VIDEO_COLS)
    if removed_vc:
        print(f"  将删除: {', '.join(sorted(removed_vc))}")
    else:
        print(f"  无需删除列")

    return bool(removed_cc), bool(removed_vc)


# ============================================================
# 视图管理
# ============================================================
def drop_views(conn):
    views = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'"
    ).fetchall()
    for (vname,) in views:
        conn.execute(f"DROP VIEW IF EXISTS [{vname}]")
        print(f"  DROP VIEW {vname}")


# ============================================================
# 列精简 — 自适应 pandas / SQL
# ============================================================
def _trim_via_pandas(conn, table_name, keep_cols):
    """pandas 路径: 仅读取需要的列 → to_sql 写回"""
    df = pd.read_sql_query(
        f"SELECT {', '.join(keep_cols)} FROM [{table_name}]", conn
    )
    df.to_sql(f"{table_name}_new", conn, if_exists="replace", index=False)
    conn.execute(f"DROP TABLE [{table_name}]")
    conn.execute(f"ALTER TABLE [{table_name}_new] RENAME TO [{table_name}]")
    print(f"  ✓ {table_name} 已精简 (pandas, {len(df)} 行, {len(keep_cols)} 列)")


def _trim_via_sql(conn, table_name, keep_cols):
    """SQL 路径: CREATE TABLE AS SELECT 在引擎内部完成，不拉取到 Python"""
    cols = ", ".join(keep_cols)
    conn.execute(f"DROP TABLE IF EXISTS [{table_name}_new]")
    conn.execute(f"""
        CREATE TABLE [{table_name}_new] AS
        SELECT {cols} FROM [{table_name}]
    """)
    conn.execute(f"DROP TABLE [{table_name}]")
    conn.execute(f"ALTER TABLE [{table_name}_new] RENAME TO [{table_name}]")
    row_cnt = _table_size(conn, table_name)
    print(f"  ✓ {table_name} 已精简 (SQL, {row_cnt} 行, {len(keep_cols)} 列)")


def rebuild_tables(conn, trim_cc, trim_vc):
    print(f"\n{'='*60}")
    print("重建精简表")
    print(f"{'='*60}")

    if trim_cc:
        tname = "comments_clean"
        size = _table_size(conn, tname)
        if _use_pandas(conn, tname):
            print(f"  {tname}: {size} 行 < {LARGE_TABLE_THRESHOLD} → pandas")
            _trim_via_pandas(conn, tname, COMMENT_COLS)
        else:
            print(f"  {tname}: {size} 行 >= {LARGE_TABLE_THRESHOLD} → SQL")
            _trim_via_sql(conn, tname, COMMENT_COLS)

    if trim_vc:
        tname = "videos_clean"
        size = _table_size(conn, tname)
        if _use_pandas(conn, tname):
            print(f"  {tname}: {size} 行 < {LARGE_TABLE_THRESHOLD} → pandas")
            _trim_via_pandas(conn, tname, VIDEO_COLS)
        else:
            print(f"  {tname}: {size} 行 >= {LARGE_TABLE_THRESHOLD} → SQL")
            _trim_via_sql(conn, tname, VIDEO_COLS)

    cc_cnt = _table_size(conn, "comments_clean")
    vc_cnt = _table_size(conn, "videos_clean")
    print(f"\n  最终: comments_clean {cc_cnt} 行, videos_clean {vc_cnt} 行")


# ============================================================
# 索引
# ============================================================
def build_indexes(conn):
    print(f"\n{'='*60}")
    print("重建索引")
    print(f"{'='*60}")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_cc_ver ON comments_clean(version_major, version_minor)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cc_time ON comments_clean(comment_time)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cc_uid ON comments_clean(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_vc_ver ON videos_clean(version_major, version_minor)")
    print("  ✓ 4 个索引已建立")


# ============================================================
# 视图
# ============================================================
def build_views(conn):
    print(f"\n{'='*60}")
    print("重建视图")
    print(f"{'='*60}")

    conn.execute("""
        CREATE VIEW v_version_meta AS
        SELECT
            c.version,
            c.version_major,
            c.version_minor,
            COUNT(*) AS comment_count,
            COUNT(DISTINCT c.user_id) AS unique_users,
            ROUND(AVG(c.user_level), 2) AS avg_user_level,
            SUM(c.likes) AS total_likes,
            ROUND(AVG(c.likes), 2) AS avg_likes,
            MIN(c.comment_time) AS first_comment,
            MAX(c.comment_time) AS last_comment,
            v.视频标题,
            v.发布时间,
            v.播放量,
            v.点赞量 AS 视频点赞,
            v.弹幕量,
            v.评论量 AS 视频评论量,
            v.收藏量,
            v.转发量,
            v.投币量
        FROM comments_clean c
        LEFT JOIN videos_clean v
            ON c.version = v.version
        GROUP BY c.version, c.version_major, c.version_minor
        ORDER BY c.version_major, c.version_minor
    """)
    print("  ✓ v_version_meta")

    conn.execute("""
        CREATE VIEW v_monthly_trend AS
        SELECT
            version,
            version_major,
            version_minor,
            substr(comment_time, 1, 7) AS year_month,
            COUNT(*) AS comment_count,
            SUM(likes) AS total_likes,
            COUNT(DISTINCT user_id) AS unique_users
        FROM comments_clean
        GROUP BY version, year_month
        ORDER BY version_major, version_minor, year_month
    """)
    print("  ✓ v_monthly_trend")

    conn.execute("""
        CREATE VIEW v_user_activity AS
        SELECT
            user_id,
            MAX(user_level) AS max_level,
            COUNT(*) AS comment_count,
            SUM(likes) AS total_likes,
            COUNT(DISTINCT version) AS versions_participated,
            MIN(comment_time) AS first_comment,
            MAX(comment_time) AS last_comment
        FROM comments_clean
        GROUP BY user_id
        ORDER BY comment_count DESC
    """)
    print("  ✓ v_user_activity")


# ============================================================
# 摘要 — 数据量小时可用 pandas 做更丰富的分析
# ============================================================
def _summary_sql(conn):
    """SQL 聚合: 仅拉取统计结果，不拉全量"""
    st = conn.execute("""
        SELECT COUNT(*), COUNT(DISTINCT user_id),
               MIN(version), MAX(version),
               ROUND(AVG(user_level), 2), ROUND(AVG(likes), 1)
        FROM comments_clean
    """).fetchone()

    print(f"\n评论数据 (comments_clean):")
    print(f"  总评论数: {st[0]}")
    print(f"  独立用户: {st[1]}")
    print(f"  版本范围: {st[2]} ~ {st[3]}")
    print(f"  用户等级: 平均 {st[4]}")
    print(f"  平均点赞: {st[5]}")

    vs = conn.execute("""
        SELECT COUNT(*),
               ROUND(AVG(播放量), 0), ROUND(AVG(弹幕量), 0),
               ROUND(AVG(评论量), 0),  ROUND(AVG(点赞量), 0),
               ROUND(AVG(收藏量), 0),  ROUND(AVG(转发量), 0),
               ROUND(AVG(投币量), 0)
        FROM videos_clean
    """).fetchone()

    print(f"\n视频数据 (videos_clean):")
    print(f"  视频数: {vs[0]}")
    print(f"  平均播放: {int(vs[1]) if vs[1] else 0}  平均弹幕: {int(vs[2]) if vs[2] else 0}")
    print(f"  平均评论: {int(vs[3]) if vs[3] else 0}  平均点赞: {int(vs[4]) if vs[4] else 0}")
    print(f"  平均收藏: {int(vs[5]) if vs[5] else 0}  平均转发: {int(vs[6]) if vs[6] else 0}")
    print(f"  平均投币: {int(vs[7]) if vs[7] else 0}")

    # 版本分组
    print(f"\n各版本统计:")
    print(f"{'版本':>5} | {'评论数':>7} | {'独立用户':>7} | {'均点赞':>6} | {'视频播放':>10} | {'视频弹幕':>7} | 视频标题")
    print("-" * 110)

    rows = conn.execute("""
        SELECT
            c.version, c.version_major, c.version_minor,
            COUNT(*) AS cnt,
            COUNT(DISTINCT c.user_id) AS ucnt,
            ROUND(AVG(c.likes), 1) AS avg_likes,
            v.播放量, v.弹幕量, v.视频标题
        FROM comments_clean c
        LEFT JOIN videos_clean v
            ON c.version = v.version
        GROUP BY c.version, c.version_major, c.version_minor
        ORDER BY c.version_major, c.version_minor
    """).fetchall()

    total = 0
    for row in rows:
        ver, maj, min_ver, cnt, ucnt, avg_l, plays, dm, title = row
        total += cnt
        plays_str = str(plays) if plays is not None else "-"
        dm_str = str(dm) if dm is not None else "-"
        title_str = (str(title)[:35] if title else "(无匹配视频)")
        print(f"  {ver:>4} | {cnt:>7} | {ucnt:>7} | {avg_l:>5.1f} | {plays_str:>10} | {dm_str:>7} | {title_str}")

    print("-" * 110)
    print(f"{'合计':>5} | {total:>7} |")

    # TopK
    print(f"\n视频播放量 Top5:")
    for i, (ver, title, plays) in enumerate(
        conn.execute("SELECT version, 视频标题, 播放量 FROM videos_clean ORDER BY 播放量 DESC LIMIT 5").fetchall(), 1
    ):
        print(f"  {i}. [{ver}] {str(title)[:40]} — {plays:,} 播放")

    print(f"\n评论点赞 Top5:")
    for i, (ver, txt, lk) in enumerate(
        conn.execute("SELECT version, content, likes FROM comments_clean ORDER BY likes DESC LIMIT 5").fetchall(), 1
    ):
        print(f"  {i}. [{ver}] {str(txt)[:50]}... — {lk} 赞")


def _summary_pandas(conn):
    """pandas 路径: 数据量小时可以灵活做更多统计分析"""
    cc = pd.read_sql("SELECT * FROM comments_clean", conn)
    vc = pd.read_sql("SELECT * FROM videos_clean", conn)

    print(f"\n评论数据 (comments_clean):")
    print(f"  总评论数: {len(cc)}")
    print(f"  独立用户: {cc['user_id'].nunique()}")
    print(f"  版本范围: {cc['version'].min()} ~ {cc['version'].max()}")
    print(f"  用户等级: 平均 {cc['user_level'].mean():.2f}")
    print(f"  平均点赞: {cc['likes'].mean():.1f}")

    print(f"\n视频数据 (videos_clean):")
    print(f"  视频数: {len(vc)}")
    print(f"  平均播放: {vc['播放量'].mean():.0f}  平均弹幕: {vc['弹幕量'].mean():.0f}")
    print(f"  平均评论: {vc['评论量'].mean():.0f}  平均点赞: {vc['点赞量'].mean():.0f}")
    print(f"  平均收藏: {vc['收藏量'].mean():.0f}  平均转发: {vc['转发量'].mean():.0f}")
    print(f"  平均投币: {vc['投币量'].mean():.0f}")

    # 版本分组 (pandas groupby)
    grp = cc.groupby(["version_major", "version_minor", "version"])
    merged = grp.agg(
        评论数=("id", "count"), 独立用户=("user_id", "nunique"), 均点赞=("likes", "mean")
    ).reset_index()
    merged["均点赞"] = merged["均点赞"].round(1)
    merged = merged.merge(
        vc[["version", "播放量", "弹幕量", "视频标题"]], on="version", how="left"
    )
    merged = merged.sort_values(["version_major", "version_minor"])

    print(f"\n各版本统计:")
    print(f"{'版本':>5} | {'评论数':>7} | {'独立用户':>7} | {'均点赞':>6} | {'视频播放':>10} | {'视频弹幕':>7} | 视频标题")
    print("-" * 110)

    total = 0
    for _, r in merged.iterrows():
        total += int(r["评论数"])
        plays = f"{int(r['播放量']):,}" if pd.notna(r["播放量"]) else "-"
        dm = str(int(r["弹幕量"])) if pd.notna(r["弹幕量"]) else "-"
        title = str(r["视频标题"])[:35] if pd.notna(r["视频标题"]) else "(无匹配视频)"
        print(f"  {r['version']:>4} | {int(r['评论数']):>7} | {int(r['独立用户']):>7} | {r['均点赞']:>5.1f} | {plays:>10} | {dm:>7} | {title}")

    print("-" * 110)
    print(f"{'合计':>5} | {total:>7} |")

    # TopK
    print(f"\n视频播放量 Top5:")
    for i, (_, r) in enumerate(vc.nlargest(5, "播放量").iterrows(), 1):
        print(f"  {i}. [{r['version']}] {str(r['视频标题'])[:40]} — {int(r['播放量']):,} 播放")

    print(f"\n评论点赞 Top5:")
    for i, (_, r) in enumerate(cc.nlargest(5, "likes").iterrows(), 1):
        print(f"  {i}. [{r['version']}] {str(r['content'])[:50]}... — {int(r['likes'])} 赞")


def print_summary(conn):
    print(f"\n{'='*60}")
    print("数据摘要")
    print(f"{'='*60}")

    cc_size = _table_size(conn, "comments_clean")
    if cc_size < LARGE_TABLE_THRESHOLD:
        print(f"  comments_clean: {cc_size} 行 < {LARGE_TABLE_THRESHOLD} → pandas 分析")
        _summary_pandas(conn)
    else:
        print(f"  comments_clean: {cc_size} 行 >= {LARGE_TABLE_THRESHOLD} → SQL 聚合")
        _summary_sql(conn)


# ============================================================
# 下游兼容性验证
# ============================================================
def verify_downstream(conn):
    print(f"\n{'='*60}")
    print("下游兼容性检查")
    print(f"{'='*60}")

    cc_cols = set(r[1] for r in conn.execute("PRAGMA table_info(comments_clean)"))
    vc_cols = set(r[1] for r in conn.execute("PRAGMA table_info(videos_clean)"))

    cc_needed = {"id", "version", "version_major", "version_minor",
                 "user_id", "user_level", "content", "comment_time", "likes"}
    vc_needed = {"version", "视频标题", "发布时间", "播放量", "点赞量", "弹幕量",
                 "评论量", "收藏量", "转发量", "投币量"}

    cc_missing = cc_needed - cc_cols
    vc_missing = vc_needed - vc_cols

    if cc_missing:
        print(f"  ✗ comments_clean 缺少: {cc_missing}")
    else:
        print(f"  ✓ comments_clean: {len(cc_cols)} 列，下游所需列全部满足")

    if vc_missing:
        print(f"  ✗ videos_clean 缺少: {vc_missing}")
    else:
        print(f"  ✓ videos_clean: {len(vc_cols)} 列，下游所需列全部满足")


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 60)
    print("数据预处理 (自适应 SQL/pandas)")
    print(f"数据库: {DB_PATH}")
    print(f"大表阈值: {LARGE_TABLE_THRESHOLD:,} 行")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)

    trim_cc, trim_vc = column_stats(conn)

    if not trim_cc and not trim_vc:
        print("\n  无需精简，列已是最优状态。")

    print(f"\n{'='*60}")
    print("清理旧视图")
    print(f"{'='*60}")
    drop_views(conn)

    if trim_cc or trim_vc:
        rebuild_tables(conn, trim_cc, trim_vc)

    build_indexes(conn)
    build_views(conn)

    conn.commit()

    cc = pd.read_sql("SELECT * FROM comments_clean", conn)
    vc = pd.read_sql("SELECT * FROM videos_clean", conn)
    cc.to_csv(os.path.join(OUTPUT_DIR, "comments_clean.csv"), index=False, encoding="utf-8-sig")
    vc.to_csv(os.path.join(OUTPUT_DIR, "videos_clean.csv"), index=False, encoding="utf-8-sig")
    print(f"\n  ✓ CSV备份: comments_clean.csv + videos_clean.csv")

    print_summary(conn)
    verify_downstream(conn)

    conn.close()

    vc_kept = len(VIDEO_COLS)
    vc_orig = vc_kept + 3  # 删 3 列
    print(f"\n{'='*60}")
    print("预处理完成!")
    print(f"数据库: {DB_PATH}")
    print(f"  - comments_clean: {len(COMMENT_COLS)} 列 (全保留)")
    print(f"  - videos_clean:   {vc_kept} 列 (原 {vc_orig} 列，精简 3 列)")
    print(f"  - 3 个视图已重建")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
