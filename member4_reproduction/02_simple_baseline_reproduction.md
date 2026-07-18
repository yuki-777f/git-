# A Simple Baseline 复现执行清单

## 模型定位
A Simple Baseline 是成员四近期最重要的主成果。它用于 Spoken/Text to Sign Language Production with 3D Avatars，目标是把当前系统中固定词表动画，升级为文本或语音驱动的 3D 手语动作生成。

## 官方信息
- 仓库：https://github.com/FangyunWei/SLRT/tree/main/Spoken2Sign
- 论文：A Simple Baseline for Spoken Language to Sign Language Translation with 3D Avatars，ECCV 2024
- 输出：SMPL-X 3D 人体姿态参数序列和可渲染 Avatar 动画。

## 独立环境配置
本模型优先使用官方推荐 Docker 独立环境，因为 Spoken2Sign 依赖 Blender、SMPL-X 插件和渲染工具链。Dockerfile 位于 `member4_reproduction/environments/spoken2sign.Dockerfile`。

```powershell
git clone https://github.com/FangyunWei/SLRT.git
docker pull rzuo/pose:sing_ISLR_smplx
docker build -f member4_reproduction/environments/spoken2sign.Dockerfile -t spoken2sign-reproduction:latest .
docker run --gpus all `
  -v C:/path/to/data:/data `
  -v ${PWD}/SLRT:/workspace/SLRT `
  -v C:/path/to/pretrained_models:/pretrained_models `
  --name spoken2sign_smplx --ipc=host -it spoken2sign-reproduction:latest /bin/bash
```

容器内先执行：

```bash
cd /workspace/SLRT/Spoken2Sign
python -m compileall .
```

若不用 Docker，则进入 `SLRT/Spoken2Sign` 后执行 `pip install -r requirements.txt`，但不推荐作为主验收路线。

## 数据和资源
- 数据集：PHOENIX-2014T、CSL-Daily、WLASL、MSASL。
- 关键点：HRNet COCO-WholeBody。
- 分段模型：TwoStream-SLR checkpoint。
- 3D 资源：SMPL-X、SMPL、SMPLH、MANO、Blender、SMPL-X add-on、3D dictionary、video IDs。

## 执行顺序
1. 先完成仓库克隆、依赖安装和 python -m compileall 语法检查。
2. 准备官方 3D dictionary 与 video IDs，优先跑 motion_gen.py 的最小生成样例。
3. 生成 SMPL-X 参数序列后，再运行 render_avatar.py 输出可视化 Avatar 视频。
4. 若要训练 Text2Gloss，按官方 text2gloss/configs/T2G.yaml 执行训练和 prediction。
5. 使用 SEDS 对生成视频或渲染结果做检索相似度评估。

## 记录指标
记录 BLEU、BLEURT、回译分数、生成耗时、动作连续性、渲染是否成功、SEDS 检索分数，以及使用的数据集和 checkpoint 来源。

## 验收标准
- 官方最小样例可以生成 SMPL-X 或 Avatar 视频。
- 代码无语法错误，命令日志完整。
- 输出至少一段可展示的文本到手语动作结果。
- 给出现有 elise 系统从 语音 -> 文本 -> 动作生成 的替换路径。
- 满足 PDF 中 Stage3 微调或替代实验、模型评估、超参数调优和实时演示路径要求。
