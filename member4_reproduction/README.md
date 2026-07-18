# 成员四（谭燕琪）模型复现交付包

本交付包用于落实成员四负责的三个模型复现任务：SEDS、A Simple Baseline、Sign-IDD。所有文件均按 UTF-8 编码保存，避免中文显示错误；本交付包不会修改原计划文件。

## 推荐复现顺序

1. SEDS：先复现手语检索模型，建立文本与手语视频或动作之间的自动评估能力。
2. A Simple Baseline：再复现文本或语音到 3D 手语动作生成链路，作为近期主成果。
3. Sign-IDD：最后复现扩散式手语生成模型，作为高质量生成对比和后续增强路线。

## 独立环境配置

三个模型的独立环境配置统一放在 `environments/`：

- `environments/seds_environment.yml`：SEDS conda 环境，Python 3.10 + Torch 2.3.1/cu121。
- `environments/spoken2sign.Dockerfile`：A Simple Baseline / Spoken2Sign Docker 环境，基于官方推荐 `rzuo/pose:sing_ISLR_smplx`。
- `environments/sign_idd_environment.yml`：Sign-IDD conda 环境，克隆官方仓库后安装其 `requirements.txt` 或实际存在的 `requirement.txt`。
- `environments/README.md`：三套环境的完整创建、依赖安装、compileall 和最小验证命令。

## 文件说明

- 00_pdf_completion_standards.md：对应 PDF 进度计划中的完成标准。
- 01_seds_reproduction.md：SEDS 复现步骤、数据权重、评估指标和验收标准。
- 02_simple_baseline_reproduction.md：A Simple Baseline 复现步骤和数字人接入重点。
- 03_sign_idd_reproduction.md：Sign-IDD 复现步骤和风险处置。
- 04_evaluation_template.md：统一实验记录、指标、日志和公平对比模板。
- 05_integration_proposal.md：与当前 elise 数字人系统的接入建议。
- 06_progress_report.md：中文汇报稿模板。

## 当前仓库状态说明

当前工作区已包含 `Uni-Sign-main` 和 `elise`，但未包含三个待复现模型的官方源码目录。完成环境配置后，需要按 `environments/README.md` 把 `SEDS`、`SLRT/Spoken2Sign`、`Sign-IDD` 克隆到工作区，再分别执行依赖安装与最小验证。

## 最终建议

短期主推 SEDS + A Simple Baseline。SEDS 先提供检索评估能力；A Simple Baseline 负责补齐文本或音频到手语动作生成能力；Sign-IDD 用于展示扩散模型的高质量生成潜力。
