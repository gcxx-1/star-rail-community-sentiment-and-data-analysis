import time, random, sys, os
from datetime import datetime
from bilibili_comment_scraper import fetch_comments
#要爬取的视频的版本、视频号、AV号、开始时间、结束时间、输出文件名，按顺序对应
TASKS = [
    ("3.5", "BV1gHhAz9EpC", "114941176579205", "2025-08-02", "2025-09-11", "bilibili_comments_3.5PV.csv"),
]

TOTAL = len(TASKS)
print("=" * 70)
print(f"  B站版本PV评论批量爬取 - 共 {TOTAL} 个版本")
print("=" * 70)
sys.stdout.flush()

for idx, (label, bv_id, av_id, start_str, end_str, output_file) in enumerate(TASKS):
    print(f"\n{'#' * 70}")
    print(f"# [{idx+1}/{TOTAL}] {label} 版本PV")
    print(f"{'#' * 70}")
    sys.stdout.flush()

    start_dt = datetime.strptime(start_str, "%Y-%m-%d")
    end_dt = datetime.strptime(end_str, "%Y-%m-%d")
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_file)

    try:
        fetch_comments(bv_id, av_id, start_dt, end_dt, output_path)
    except Exception as e:
        print(f"[ERROR] {label} 版本爬取失败: {e}")
        sys.stdout.flush()

    if idx < TOTAL - 1:
        delay = random.uniform(3.0, 6.0)
        print(f"\n[INFO] 休息 {delay:.1f}s 后继续...")
        sys.stdout.flush()
        time.sleep(delay)

print(f"\n{'=' * 70}")
print(f"  全部 {TOTAL} 个版本PV评论爬取完成！")
print(f"{'=' * 70}")
