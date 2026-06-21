# 视频分析

对崩坏星穹铁道各版本PV视频进行多维度综合分析与可视化。

## 文件说明

| 文件 | 说明 |
|---|---|
| [video_dimension_analysis.py](./video_dimension_analysis.py) | 版本维度分析主脚本：MinMax归一化 + 传播度/讨论度/喜爱度三维评分 + 综合指数计算 + 图表输出 |
| [video_top_detail.py](./video_top_detail.py) | 版本Top3视频明细 + 全版本Top10极值分析 |
| [version_dimension_scores.csv](./version_dimension_scores.csv) | 各版本维度得分结果CSV |

## 维度定义

所有指标先经过MinMax归一化（0~100），再按以下公式合成：

| 维度 | 公式 | 含义 |
|---|---|---|
| 传播度 | (播放量_norm + 转发量_norm) / 2 | 视频传播范围 |
| 讨论度 | (弹幕量_norm + 评论量_norm) / 2 | 用户讨论热度 |
| 喜爱度 | (点赞量_norm + 投币量_norm + 收藏量_norm) / 3 | 用户认可程度 |
| 综合指数 | 传播度×25% + 讨论度×25% + 喜爱度×50% | 加权综合评分 |

## 输出图表

| 图表 | 说明 |
|---|---|
| `version_dimension_trend.png` | 各版本三维度+综合指数趋势折线图 |
| `version_dimension_heatmap.png` | 版本×维度热力图 |
| `version_dimension_radar.png` | Top5版本三维度雷达对比图 |

## 使用方式

```bash
# 版本维度分析 + 趋势图/热力图/雷达图
python video_dimension_analysis.py

# 各版本Top3明细 + 全版本Top10极值
python video_top_detail.py
```

## 技术细节

- **归一化方式**：MinMax归一化（各指标独立归一化到0~100）
- **自适应**：数据量≥100,000行时使用SQL读取，避免pandas全量加载
- **图表引擎**：matplotlib，中文字体自动适配（SimHei → Microsoft YaHei → DejaVu Sans）

## 依赖关系

上游依赖：[数据预处理](../数据预处理/) 中的 `b站崩铁社区分析.db`（videos_clean表）
