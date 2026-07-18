# SEDS 复现执行清单

## 模型定位
SEDS 是成员四最先复现的模型。它属于手语视频与文本双向检索，不直接生成动作，但可以作为后续两个生成模型的自动评估工具。

## 官方信息
- 仓库：https://github.com/longtaojiang/SEDS
- 分支：master
- 论文：SEDS，ACM MM 2024
- 数据和权重：processed I3D features、RTM keypoints、pre-trained model，BaiduDrive 提取码 seds。

## 独立环境配置
本模型使用独立 conda 环境 `seds-reproduction`，配置文件位于 `member4_reproduction/environments/seds_environment.yml`。

```powershell
conda env create -f member4_reproduction/environments/seds_environment.yml
conda activate seds-reproduction
git clone https://github.com/longtaojiang/SEDS.git
Set-Location SEDS
pip install -r requirements.txt
python -m compileall .
```

若 Windows PowerShell 无法直接执行 bash 脚本，后续评估命令使用 Git Bash 或 WSL 运行。

## 数据准备
- 数据目录建议为 datasets/CSL/I3D_features 与 datasets/CSL/RTMpose。
- PHOENIX-2014-T 与 How2Sign 按官方同级结构放置。
- 训练前把 pretrain_signbert.pth 放入 ckpts，把 ViT-B-32.pt 放入 modules。
- 若 CSL_Daily 与官方 CSL 命名不完全一致，需记录映射关系和样本数量。

## 执行顺序
1. 优先跑官方评估：bash scripts/eval_csl.sh。
2. CSL 数据未就绪时，先跑 PHOENIX：bash scripts/eval_ph.sh。
3. 评估跑通后再训练：bash scripts/train_csl.sh。
4. Windows 下 bash 失败时，使用 Git Bash 或 WSL。

## 记录指标
记录 Text-to-Video 与 Video-to-Text 的 Recall@1、Recall@5、Recall@10、Median Rank、Mean Rank，并保存 checkpoint、数据版本、硬件信息和耗时。

## 验收标准
- 至少一个数据集完成 evaluation。
- 生成可汇报检索指标。
- 形成评分接口草案：输入文本和生成视频或动作可视化结果，输出相似度或检索排名。
- 满足 PDF 中代码可运行、记录训练日志和指标、统一评估指标的要求。
