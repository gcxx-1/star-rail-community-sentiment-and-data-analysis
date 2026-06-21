# 情感分析

基于DeepSeek API对评论进行三分类情感分析（正向/中性/负向），包含标注抽样、模型评估、全量预测三个环节。

## 文件说明

| 文件 | 说明 |
|---|---|
| [sample_for_annotation.py](./sample_for_annotation.py) | 按版本分层抽样生成标注模板，附带伪标签辅助标注 |
| [标注模板_待标注.csv](./标注模板_待标注.csv) | 抽样生成的待标注CSV，包含评论ID、版本、内容、时间、点赞数及伪标签列 |
| [标注模板_已完成.csv](./标注模板_已完成.csv) | 已完成人工标注的样本，用于评估DeepSeek分类效果（含情感标注和AI关键词列） |
| [train_and_predict.py](./train_and_predict.py) | 读取已完成标注数据，调用DeepSeek API预测，输出Accuracy/Precision/Recall/F1 |
| [predict_all.py](./predict_all.py) | 对数据库中全部评论调用DeepSeek API进行情感预测，结果写入sentiment_result表 |
| [sentiment_predictions.csv](./sentiment_predictions.csv) | 全量预测结果CSV导出 |

## 情感分类体系

| 标签 | 含义 | 典型内容 |
|---|---|---|
| 正向 | 正面情感 | 喜爱、期待、夸赞、厨力表达 |
| 中性 | 无情绪 | 客观询问、兑换码、纯标点 |
| 负向 | 负面情感 | 抱怨、批评、失望、弃坑倾向 |

## 分析流程

1. **抽样标注** — 从各版本中分层抽样200条评论，自动生成伪标签辅助标注
2. **效果评估** — 用已标注数据调用DeepSeek API，计算F1/准确率等指标
3. **全量预测** — 确认效果满意后，对所有评论进行批量预测并入库

## 使用方式

```bash
# 1. 生成标注模板
python sample_for_annotation.py

# 2. 手动标注：将 标注模板_待标注.csv 复制为 标注模板_AI优化.csv，填写情感标注列（-1/0/1 或 负向/中性/正向）

# 3. 评估DeepSeek效果
python train_and_predict.py

# 4. 全量预测
python predict_all.py
```

## 技术细节

- **模型**：DeepSeek Chat API，temperature=0.1 保证输出稳定性
- **批处理**：每次发送15条评论，减少API调用次数
- **自适应**：数据量≥100,000行时使用SQL流式读取，避免内存溢出
- **可选后处理**：内置领域规则（游戏关键词+反讽检测），默认关闭，可设置`USE_DOMAIN_RULES=True`开启

## 输出数据表

- `sentiment_result` — 全量评论的情感预测结果（含预测标签、置信度、关键词）
- `version_summary` — 各版本情感分布汇总
- `v_monthly_sentiment` — 月度情感趋势视图

## 依赖关系

上游依赖：[数据预处理](../数据预处理/) 中的 `b站崩铁社区分析.db`
下游被：[高频词提取](../高频词提取/) 读取
