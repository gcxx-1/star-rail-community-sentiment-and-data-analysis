import requests
import time
import csv
import os
import math
import random
import sys
from functools import reduce
from hashlib import md5
import urllib.parse

mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

UID = "1340190821"
COOKIE = "填写你的B站Cookie"

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bilibili_videos.csv")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Cookie": COOKIE,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

wbi_keys_cache = {"img_key": None, "sub_key": None, "ts": 0}


def getMixinKey(orig: str) -> str:
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, '')[:32]


def getWbiKeys() -> tuple:
    now = time.time()
    if wbi_keys_cache["img_key"] and wbi_keys_cache["sub_key"] and (now - wbi_keys_cache["ts"]) < 3600:
        return wbi_keys_cache["img_key"], wbi_keys_cache["sub_key"]

    url = "https://api.bilibili.com/x/web-interface/nav"
    resp = requests.get(url, headers=HEADERS, timeout=15)
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
    print(f"[INFO] 获取WBI密钥: img_key={img_key[:8]}..., sub_key={sub_key[:8]}...")
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


def fetch_video_list(page: int, page_size: int = 50) -> dict:
    img_key, sub_key = getWbiKeys()
    params = {
        "mid": UID,
        "ps": page_size,
        "pn": page,
        "tid": 0,
        "keyword": "",
        "order": "pubdate",
        "order_avoided": "true",
    }
    signed_params = encWbi(params, img_key, sub_key)
    query = urllib.parse.urlencode(signed_params)
    url = f"https://api.bilibili.com/x/space/wbi/arc/search?{query}"

    print(f"[INFO] 请求第{page}页视频列表...")
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_video_detail(bvid: str) -> dict:
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_video_stat(aid: int) -> dict:
    url = f"https://api.bilibili.com/x/web-interface/archive/stat?aid={aid}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def safe_get(d, *keys, default=""):
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    return d if d is not None else default


def scrape_all_videos():
    all_videos = []
    page = 1
    total_pages = None

    while True:
        try:
            result = fetch_video_list(page, page_size=50)
        except Exception as e:
            print(f"[ERROR] 请求第{page}页失败: {e}")
            time.sleep(5)
            continue

        if result.get("code") != 0:
            print(f"[ERROR] API返回错误 (page={page}): code={result.get('code')}, message={result.get('message')}")
            if result.get("code") == -799:
                print("[ERROR] 请求被拒绝(reply), 可能需要更新Cookie或WBI签名")
            break

        data = result.get("data", {})
        page_info = data.get("page", {})
        total_pages = page_info.get("count", 0) if total_pages is None else total_pages

        vlist = data.get("list", {}).get("vlist", [])
        if not vlist:
            print(f"[INFO] 第{page}页无视频数据，爬取结束")
            break

        print(f"[INFO] 第{page}页获取到 {len(vlist)} 个视频")
        all_videos.extend(vlist)

        if page >= math.ceil(page_info.get("count", 0) / 50):
            print(f"[INFO] 已获取全部 {page_info.get('count', 0)} 个视频")
            break

        page += 1
        time.sleep(random.uniform(1.0, 2.5))

    print(f"\n[INFO] 共获取 {len(all_videos)} 个视频基本信息，正在获取详细数据...")
    sys.stdout.flush()

    detailed_data = []
    total = len(all_videos)

    interim_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bilibili_videos_partial.csv")
    fieldnames = ["视频标题", "发布时间", "播放量", "点赞量", "收藏量", "弹幕量", "评论量", "转发量", "投币量", "视频时长(s)", "BV号", "AV号"]

    for idx, video in enumerate(all_videos):
        bvid = video.get("bvid", "")
        aid = video.get("aid", 0)
        title = safe_get(video, "title")
        created = safe_get(video, "created")
        pubdate = ""
        if created:
            try:
                pubdate = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(created)))
            except:
                pubdate = str(created)

        play = safe_get(video, "play", default=0)
        comment = safe_get(video, "comment", default=0)
        video_review = safe_get(video, "video_review", default=0)

        likes = 0
        coins = 0
        favorites = 0
        shares = 0
        danmaku = 0
        duration = 0

        try:
            detail = fetch_video_detail(bvid)
            if detail.get("code") == 0:
                d = detail.get("data", {})
                stat = d.get("stat", {})
                likes = safe_get(stat, "like", default=0)
                coins = safe_get(stat, "coin", default=0)
                favorites = safe_get(stat, "favorite", default=0)
                shares = safe_get(stat, "share", default=0)
                danmaku = safe_get(stat, "danmaku", default=0)
                duration = safe_get(d, "duration", default=0)
                comment = safe_get(stat, "reply", default=comment)
                play = safe_get(stat, "view", default=play)

                record = {
                    "视频标题": title,
                    "发布时间": pubdate,
                    "播放量": play,
                    "点赞量": likes,
                    "收藏量": favorites,
                    "弹幕量": danmaku,
                    "评论量": comment,
                    "转发量": shares,
                    "投币量": coins,
                    "视频时长(s)": duration,
                    "BV号": bvid,
                    "AV号": aid,
                }
                detailed_data.append(record)
                print(f"[{idx+1}/{total}] {title[:30]}... - 播放:{play} 点赞:{likes} 时长:{duration}s")
                sys.stdout.flush()
            else:
                print(f"[{idx+1}/{total}] {title[:30]}... - API错误: code={detail.get('code')}")
                sys.stdout.flush()
        except Exception as e:
            print(f"[{idx+1}/{total}] {title[:30]}... - 异常: {e}")
            sys.stdout.flush()
            record = {
                "视频标题": title,
                "发布时间": pubdate,
                "播放量": play,
                "点赞量": 0,
                "收藏量": 0,
                "弹幕量": 0,
                "评论量": comment,
                "转发量": 0,
                "投币量": 0,
                "视频时长(s)": 0,
                "BV号": bvid,
                "AV号": aid,
            }
            detailed_data.append(record)

        if (idx + 1) % 50 == 0:
            with open(interim_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(detailed_data)
            print(f"[SAVE] 已保存 {len(detailed_data)} 条中间结果")
            sys.stdout.flush()

        time.sleep(random.uniform(0.8, 1.8))

    return detailed_data


def save_to_csv(data: list, filepath: str):
    if not data:
        print("[WARN] 无数据可保存")
        return

    fieldnames = ["视频标题", "发布时间", "播放量", "点赞量", "收藏量", "弹幕量", "评论量", "转发量", "投币量", "视频时长(s)", "BV号", "AV号"]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    print(f"\n[DONE] 数据已保存到: {filepath}")
    print(f"[DONE] 共 {len(data)} 条记录")


def main():
    print("=" * 60)
    print("B站视频爬虫 - 崩坏星穹铁道 (UID: 1340190821)")
    print("=" * 60)

    data = scrape_all_videos()
    save_to_csv(data, OUTPUT_FILE)


if __name__ == "__main__":
    main()
