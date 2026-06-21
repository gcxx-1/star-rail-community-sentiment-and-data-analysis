import sqlite3
import csv
import os
import re
import io

DB_PATH = os.path.join(os.path.dirname(__file__), "bilibili_comments.db")
CSV_DIR = os.path.dirname(__file__)

CSV_FILES = [
    ("1.0", "bilibili_comments_1.0PV.csv"),
    ("1.1", "bilibili_comments_1.1PV.csv"),
    ("1.2", "bilibili_comments_1.2PV.csv"),
    ("1.3", "bilibili_comments_1.3PV.csv"),
    ("1.4", "bilibili_comments_1.4PV.csv"),
    ("1.5", "bilibili_comments_1.5PV.csv"),
    ("1.6", "bilibili_comments_1.6PV.csv"),
    ("2.0", "bilibili_comments_2.0PV.csv"),
    ("2.1", "bilibili_comments_2.1PV.csv"),
    ("2.2", "bilibili_comments_2.2PV.csv"),
    ("2.3", "bilibili_comments_2.3PV.csv"),
    ("2.4", "bilibili_comments_2.4PV.csv"),
    ("2.5", "bilibili_comments_2.5PV.csv"),
    ("2.6", "bilibili_comments_2.6PV.csv"),
    ("2.7", "bilibili_comments_2.7PV.csv"),
    ("3.0", "bilibili_comments_3.0PV.csv"),
    ("3.1", "bilibili_comments_3.1PV.csv"),
    ("3.2", "bilibili_comments_3.2PV.csv"),
    ("3.3", "bilibili_comments_3.3PV.csv"),
    ("3.4", "bilibili_comments_3.4PV.csv"),
    ("3.5", "bilibili_comments_3.5PV.csv"),
    ("3.6", "bilibili_comments_3.6PV.csv"),
    ("3.7", "bilibili_comments_3.7PV.csv"),
    ("3.8", "bilibili_comments_3.8PV.csv"),
    ("4.0", "bilibili_comments_4.0PV.csv"),
    ("4.1", "bilibili_comments_4.1PV.csv"),
    ("4.2", "bilibili_comments_4.2PV.csv"),
    ("4.3", "bilibili_comments_4.3PV.csv"),
]


def read_csv_with_bom(filepath):
    rows = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def extract_major_minor(ver_str):
    parts = ver_str.split(".")
    major = int(parts[0])
    minor = int(parts[1])
    return major, minor


def import_all():
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            version_major INTEGER NOT NULL,
            version_minor INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            user_level INTEGER,
            content TEXT,
            comment_time TEXT NOT NULL,
            comment_datetime TEXT,
            likes INTEGER DEFAULT 0
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_version ON comments(version)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_version_major_minor ON comments(version_major, version_minor)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON comments(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comment_time ON comments(comment_time)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_version_time ON comments(version_major, version_minor, comment_time)")

    cursor.execute("DELETE FROM comments")

    total_count = 0
    version_stats = []

    for version, filename in CSV_FILES:
        filepath = os.path.join(CSV_DIR, filename)
        if not os.path.exists(filepath):
            print(f"  [跳过] {filename} 文件不存在")
            continue

        rows = read_csv_with_bom(filepath)
        major, minor = extract_major_minor(version)

        batch = []
        for row in rows:
            user_id = int(row.get("用户ID", 0))
            user_name = row.get("用户名", "")
            user_level = int(row.get("用户等级", 0) or 0)
            content = row.get("评论内容", "")
            comment_time = row.get("评论时间", "")
            comment_datetime = comment_time
            likes = int(row.get("点赞数", 0) or 0)

            batch.append((
                version, major, minor,
                user_id, user_name, user_level,
                content, comment_time, comment_datetime, likes
            ))

        cursor.executemany("""
            INSERT INTO comments
                (version, version_major, version_minor,
                 user_id, user_name, user_level,
                 content, comment_time, comment_datetime, likes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)

        count = len(batch)
        total_count += count
        version_stats.append((major, minor, version, count))
        print(f"  ✓ {version}版本 ({filename}): {count}条")

    version_stats.sort(key=lambda x: (x[0], x[1]))

    cursor.execute("""
        CREATE VIEW IF NOT EXISTS v_version_summary AS
        SELECT
            version,
            version_major,
            version_minor,
            COUNT(*) AS comment_count,
            COUNT(DISTINCT user_id) AS unique_users,
            SUM(likes) AS total_likes,
            ROUND(AVG(likes), 2) AS avg_likes,
            MIN(comment_time) AS earliest_comment,
            MAX(comment_time) AS latest_comment
        FROM comments
        GROUP BY version, version_major, version_minor
        ORDER BY version_major, version_minor
    """)

    cursor.execute("""
        CREATE VIEW IF NOT EXISTS v_user_activity AS
        SELECT
            user_id,
            user_name,
            MAX(user_level) AS max_level,
            COUNT(*) AS comment_count,
            SUM(likes) AS total_likes,
            COUNT(DISTINCT version) AS versions_participated
        FROM comments
        GROUP BY user_id, user_name
        ORDER BY comment_count DESC
    """)

    conn.commit()
    conn.close()

    print(f"\n总计: {len(CSV_FILES)}个版本, {total_count}条评论")
    print(f"数据库: {DB_PATH}")
    print(f"\n各版本统计:")
    print(f"{'版本':>6} | {'评论数':>8} | 备注")
    print("-" * 40)
    for major, minor, ver, cnt in version_stats:
        print(f"  {ver:>5} | {cnt:>8} |")
    print("-" * 40)
    print(f"{'合计':>6} | {total_count:>8} |")


if __name__ == "__main__":
    import_all()
