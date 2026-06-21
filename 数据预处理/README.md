# 数据预处理

对爬取的原始数据进行清洗、整理，构建SQLite数据库供下游分析使用。

## 文件说明

| 文件 | 说明 |
|---|---|
| [preprocess.py](./preprocess.py) | 自适应数据预处理脚本：列精简、索引重建、视图创建、摘要报告、导出CSV备份 |
| [b站崩铁社区分析.db](./b站崩铁社区分析.db) | SQLite数据库，包含清洗后的评论表和视频表，以及多个分析视图 |
| [comments_clean.csv](./comments_clean.csv) | 清洗后的评论数据CSV导出（9列：id/版本/用户/内容/时间/点赞等） |
| [videos_clean.csv](./videos_clean.csv) | 清洗后的视频数据CSV导出（含版本归属） |

## preprocess.py 处理流程

1. **列差异分析**：检测现有表结构与目标结构的差异
2. **列精简**：删除不必要的列（如视频时长/BV号/AV号），保留分析必需的字段
3. **索引重建**：为高频查询字段建立索引，提升下游分析效率
4. **视图重建**：
   - `v_version_meta` — 版本综合统计（评论+视频）
   - `v_monthly_trend` — 月度评论趋势
   - `v_user_activity` — 用户活跃度统计
5. **摘要报告**：输出版本评论数、用户数、播放量等统计信息
6. **CSV导出**：清洗后的数据导出为CSV备用

## 数据库表结构

### comments_clean（评论表）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER | 评论ID |
| version | TEXT | 版本号（如"1.0"） |
| version_major | INTEGER | 主版本号 |
| version_minor | INTEGER | 次版本号 |
| user_id | INTEGER | B站用户ID |
| user_level | INTEGER | 用户等级 |
| content | TEXT | 评论内容 |
| comment_time | TEXT | 评论时间 |
| likes | INTEGER | 点赞数 |

### videos_clean（视频表）

包含视频标题、发布时间、播放量、点赞量、弹幕量、评论量、收藏量、转发量、投币量，以及版本归属字段。

## 自适应策略

- 数据量 < 100,000 行时使用pandas灵活处理
- 数据量 ≥ 100,000 行时使用纯SQL避免内存溢出

## 使用方式

```bash
python preprocess.py
```

## 依赖关系

上游依赖：[数据爬取](../数据爬取/) 中导入的数据库
下游被：[情感分析](../情感分析/)、[视频分析](../视频分析/)、[高频词提取](../高频词提取/) 读取
