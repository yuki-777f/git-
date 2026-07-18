# Sign-IDD 复现执行清单

## 模型定位
Sign-IDD 是成员四第三阶段复现对象，定位为高质量扩散式手语生成对比方案。它的创新点是 Iconicity Disentangled Diffusion，即对手语中的象形性和约定性进行解纠缠建模。

## 官方信息
- 仓库：https://github.com/NaVi-start/Sign-IDD
- 论文：Sign-IDD: Iconicity Disentangled Diffusion for Sign Language Production，AAAI 2025
- 主要数据：PHOENIX14T；官方说明 USTC-CSL 数据将后续发布。

## 独立环境配置
本模型使用独立 conda 环境 `sign-idd-reproduction`，配置文件位于 `member4_reproduction/environments/sign_idd_environment.yml`。官方仓库以 `requirements.txt` 为准；若实际克隆版本只有 `requirement.txt`，按实际文件名安装。

```powershell
conda env create -f member4_reproduction/environments/sign_idd_environment.yml
conda activate sign-idd-reproduction
git clone https://github.com/NaVi-start/Sign-IDD.git
Set-Location Sign-IDD
if (Test-Path requirements.txt) { pip install -r requirements.txt } elseif (Test-Path requirement.txt) { pip install -r requirement.txt } else { Write-Error "No requirement file found" }
python -m compileall .
```

## 执行顺序
1. 优先使用 PHOENIX14T 兼容数据跑官方配置。
2. 训练命令：python __main__.py train ./Configs/Sign-IDD.yaml。
3. 推理命令：python __main__.py test ./Configs/Sign-IDD.yaml。
4. 若完整训练成本过高，先完成官方 checkpoint 推理或小样本实验。

## 记录指标
记录训练 loss、验证 loss、DTW、姿态距离、可视化质量、BLEU/BLEURT 或可用的 SLT 回译指标，并补充 SEDS 检索相似度。

## 验收标准
- 官方配置能完成最小训练或推理。
- 输出一段可视化动作或姿态序列。
- 与 A Simple Baseline 对比生成质量、速度、数据需求和数字人接入难度。
- 满足 PDF 中训练日志、指标、微调或替代方案、统一评估和最终对比要求。
