# 统一评估与实验记录模板

## 基本信息

- 模型名称：
- 仓库地址：
- commit 或下载日期：
- 环境名称：
- Python / PyTorch / CUDA 版本：
- 操作系统：
- GPU / CPU：
- 运行日期：
- 负责人：谭燕琪

## 数据集记录

- 数据集名称：CSL_Daily / PHOENIX14T / How2Sign / 其他
- 数据路径：
- 样本数量：
- 训练 / 验证 / 测试划分：
- 是否与团队统一划分一致：
- 若使用替代数据，替代原因：

## 运行命令

记录完整命令、配置文件、checkpoint 路径、日志保存位置和随机种子。

## 指标记录

### SEDS
- Recall@1：
- Recall@5：
- Recall@10：
- Median Rank：
- Mean Rank：

### A Simple Baseline
- BLEU：
- BLEURT：
- 回译分数：
- SEDS 相似度或检索排名：
- 生成耗时：
- 渲染是否成功：

### Sign-IDD
- loss：
- DTW 或姿态距离：
- BLEU/BLEURT 或回译指标：
- SEDS 相似度或检索排名：
- 可视化质量说明：

## 超参数记录

- learning rate：
- batch size：
- epoch / steps：
- seed：
- 输入长度：
- checkpoint 来源：
- 调优前指标：
- 调优后指标：

## 公平对比说明

必须标明结果属于官方预训练推理、小样本微调还是完整训练。不同条件的结果可以并列展示，但不能直接作为同等训练成本下的优劣结论。
