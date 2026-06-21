import requests
import time
import csv
import os
import random
import sys
from functools import reduce
from hashlib import md5
import urllib.parse
from datetime import datetime

mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

COOKIE = "填写你的B站Cookie"

wbi_keys_cache = {"img_key": None, "sub_key": None, "ts": 0}


def getMixinKey(orig: str) -> str:
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]


def getWbiKeys(bv_id: str) -> tuple:
    now = time.time()
    if wbi_keys_cache["img_key"] and wbi_keys_cache["sub_key"] and (now - wbi_keys_cache["ts"]) < 3600:
        return wbi_keys_cache["img_key"], wbi_keys_cache["sub_key"]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": f"https://www.bilibili.com/video/{bv_id}",
        "Origin": "https://www.bilibili.com",
        "Cookie": COOKIE,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    url = "https://api.bilibili.com/x/web-interface/nav"
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    wbi_img = data["data"]["wbi_img"]
    img_url = wbi_img["img_url"]
    sub_url = wbi_img["sub_url"]
    img_key = img_url.rsplit("/", 1)[1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]

    wbi_keys_cache["img_key"] = img_key
    wbi_keys_cache["sub_key"] = sub_key
    wbi_keys_cache["ts"] = now
    return img_key, sub_key


def encWbi(params: dict, img_key: str, sub_key: str) -> dict:
    mixin_key = getMixinKey(img_key + sub_key)
    curr_time = round(time.time())
    params["wts"] = curr_time
    params = dict(sorted(params.items()))
    params = {
        k: "".join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = wbi_sign
    return params


def fetch_comments(bv_id: str, av_id: str, start_dt: datetime, end_dt: datetime, output_file: str):
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": f"https://www.bilibili.com/video/{bv_id}",
        "Origin": "https://www.bilibili.com",
        "Cookie": COOKIE,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    COMMENT_API = "https://api.bilibili.com/x/v2/reply/wbi/main"

    user_comments = {}
    cursor_next = 0
    page = 0

    print("=" * 60)
    print(f"评论爬虫 - 视频: {bv_id}")
    print(f"时间范围: {start_dt.strftime('%Y-%m-%d')} ~ {end_dt.strftime('%Y-%m-%d')}")
    print("=" * 60)
    sys.stdout.flush()

    while True:
        page += 1

        params = {
            "oid": av_id,
            "type": "1",
            "mode": "2",
            "next": cursor_next,
            "ps": "20",
        }

        try:
            img_key, sub_key = getWbiKeys(bv_id)
            signed_params = encWbi(params, img_key, sub_key)
            query = urllib.parse.urlencode(signed_params)
            url = f"{COMMENT_API}?{query}"
        except Exception as e:
            print(f"[ERROR] WBI签名失败: {e}")
            sys.stdout.flush()
            time.sleep(3)
            continue

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] 第{page}页网络请求失败: {e}")
            sys.stdout.flush()
            time.sleep(5)
            continue
        except Exception as e:
            print(f"[ERROR] 第{page}页解析失败: {e}")
            sys.stdout.flush()
            time.sleep(3)
            continue

        if data.get("code") != 0:
            print(f"[ERROR] API错误 (page={page}): code={data.get('code')}, message={data.get('message')}")
            sys.stdout.flush()
            if data.get("code") == -799:
                print("[ERROR] 请求被拒绝，可能需要更新Cookie或WBI签名")
            break

        replies = data.get("data", {}).get("replies")
        if not replies:
            print(f"[INFO] 第{page}页无评论，爬取结束")
            break

        page_collected = 0
        reached_lower_bound = False

        for reply in replies:
            if reply is None:
                continue

            ctime = reply.get("ctime", 0)

            if ctime < start_ts:
                reached_lower_bound = True
                continue

            if ctime > end_ts:
                continue

            mid = str(reply.get("mid", ""))
            if not mid:
                continue

            member = reply.get("member", {})
            level_info = member.get("level_info", {})
            content = reply.get("content", {})

            comment_data = {
                "用户ID": mid,
                "用户名": member.get("uname", ""),
                "用户等级": level_info.get("current_level", 0),
                "评论内容": content.get("message", ""),
                "评论时间": datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S"),
                "点赞数": reply.get("like", 0),
            }

            if mid in user_comments:
                existing_ts = user_comments[mid].get("_ts", 0)
                if ctime < existing_ts:
                    comment_data["_ts"] = ctime
                    user_comments[mid] = comment_data
                continue

            comment_data["_ts"] = ctime
            user_comments[mid] = comment_data
            page_collected += 1

        total_collected = len(user_comments)
        print(f"[PAGE {page}] 本页新增 {page_collected} 条, 累计去重用户数 {total_collected}")
        sys.stdout.flush()

        if reached_lower_bound:
            print(f"[INFO] 已到达时间下限 {start_dt.strftime('%Y-%m-%d')}，停止爬取")
            break

        cursor_info = data.get("data", {}).get("cursor", {})
        if cursor_info.get("is_end", False):
            print(f"[INFO] 已到最后一页 (is_end=true)")
            break

        next_val = cursor_info.get("next", 0)
        if next_val == 0 or next_val == cursor_next:
            print(f"[INFO] 分页游标无变化 (next={next_val}), 停止")
            break

        cursor_next = next_val

        delay = random.uniform(1.2, 2.8)
        time.sleep(delay)

    save_comments(user_comments, output_file)
    return user_comments


def save_comments(comments: dict, filepath: str):
    if not comments:
        print("[WARN] 无评论数据可保存")
        return

    sorted_comments = sorted(comments.values(), key=lambda x: x.get("_ts", 0))

    fieldnames = ["用户ID", "用户名", "用户等级", "评论内容", "评论时间", "点赞数"]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(sorted_comments)

    print(f"\n[DONE] 评论数据已保存到: {filepath}")
    print(f"[DONE] 共 {len(sorted_comments)} 条评论（已按用户去重，取最早评论）")

    level_counts = {}
    for c in sorted_comments:
        lv = c.get("用户等级", 0)
        level_counts[lv] = level_counts.get(lv, 0) + 1
    print(f"[INFO] 用户等级分布: {dict(sorted(level_counts.items()))}")


def main():
    if len(sys.argv) < 6:
        print("用法: python bilibili_comment_scraper.py <BV号> <AV号> <起始日期 YYYY-MM-DD> <结束日期 YYYY-MM-DD> <输出文件名>")
        print("示例: python bilibili_comment_scraper.py BV1E1Li6GEwq 116615928614715 2026-05-22 2026-06-11 bilibili_comments_4.3PV.csv")
        sys.exit(1)

    bv_id = sys.argv[1]
    av_id = sys.argv[2]
    start_dt = datetime.strptime(sys.argv[3], "%Y-%m-%d")
    end_dt = datetime.strptime(sys.argv[4], "%Y-%m-%d")
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), sys.argv[5])

    fetch_comments(bv_id, av_id, start_dt, end_dt, output_file)


if __name__ == "__main__":
    main()
