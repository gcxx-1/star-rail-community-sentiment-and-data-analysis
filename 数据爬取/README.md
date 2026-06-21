# 数据爬取

从B站API爬取《崩坏：星穹铁道》官方账号的视频信息和PV评论数据。

## 文件说明

| 文件 | 说明 |
|---|---|
| [bilibili_scraper.py](./bilibili_scraper.py) | 爬取指定UID（官方账号）的全部视频信息，包括标题、发布时间、播放量、点赞/收藏/弹幕/评论/转发/投币数、BV号/AV号等 |
| [bilibili_comment_scraper.py](./bilibili_comment_scraper.py) | 爬取指定视频的评论数据（含用户ID、用户名、等级、评论内容、时间、点赞数），按用户去重取最早评论 |
| [batch_comment_scraper.py](./batch_comment_scraper.py) | 批量调用评论爬虫，按版本PV配置依次爬取各版本的评论数据 |
| [import_to_sql.py](./import_to_sql.py) | 将各版本的评论CSV文件导入SQLite数据库（`bilibili_comments.db`），建表并创建统计视图 |
| [版本时间段.xlsx](./版本时间段.xlsx) | 各游戏版本的起止时间信息，用于限定评论爬取的时间范围 |
| [bilibili_videos.csv](./bilibili_videos.csv) | 爬取的视频信息输出文件 |

## 爬虫原理

- **WBI签名**：B站新版API需要对请求参数进行WBI签名，脚本自动获取`img_key`和`sub_key`并生成签名
- **分页爬取**：视频列表和评论均支持分页，自动翻页直到数据获取完毕
- **频率控制**：内置随机延时（1~3秒），避免触发B站反爬机制
- **断点保护**：视频爬取每50条保存一次中间结果

## 使用方式

```bash
# 1. 爬取官方账号视频列表
python bilibili_scraper.py

# 2. 爬取单个视频评论（命令行参数）
python bilibili_comment_scraper.py <BV号> <AV号> <起始日期> <结束日期> <输出文件名>

# 3. 批量爬取各版本PV评论（需修改TASKS列表中的配置）
python batch_comment_scraper.py

# 4. 将评论CSV导入SQLite
python import_to_sql.py
```

## 注意事项

- 需要填写有效的B站Cookie和UID，Cookie过期后需重新获取
- `batch_comment_scraper.py`中的TASKS列表需要根据实际版本PV信息进行配置
- 爬取大量数据时建议分批次运行，避免长时间连续请求
