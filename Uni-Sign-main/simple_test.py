"""
完全独立的 Uni-Sign 推理测试脚本
不依赖原有的 datasets.py 和 utils.py，绕过 deepspeed
"""

import torch
import torch.nn.utils.rnn as rnn_utils
from torch.utils.data import Dataset, DataLoader
import argparse
import os
import cv2
import numpy as np
import pickle
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import random

# 导入模型（必须的）
from models import Uni_Sign
from rtmlib import Wholebody

# ============ 简化版工具函数 ============
def set_seed(seed):
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)


# ============ 在线数据集类（简化版） ============
class SimpleOnlineDataset(Dataset):
    """简化的在线数据集，不依赖原始 datasets.py"""

    def __init__(self, args, pose_data, rgb_path=None):
        self.args = args
        self.rgb_support = args.rgb_support
        self.max_length = args.max_length
        self.pose_data = pose_data
        self.rgb_data = rgb_path

        # 简单的图像变换
        from torchvision import transforms
        self.data_transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

    def __len__(self):
        return 1

    def __getitem__(self, index):
        text = ''
        gloss = ''
        name_sample = 'online_data'

        pose_sample, support_rgb_dict = self.load_pose()

        return name_sample, pose_sample, text, gloss, support_rgb_dict

    def load_pose(self):
        """加载姿态数据"""
        pose = self.pose_data

        duration = len(pose['scores'])
        start = 0

        # 采样
        if duration > self.max_length:
            tmp = sorted(random.sample(range(duration), k=self.max_length))
        else:
            tmp = list(range(duration))

        tmp = np.array(tmp) + start

        # 提取关键帧
        skeletons = pose['keypoints']
        confs = pose['scores']
        skeletons_tmp = []
        confs_tmp = []
        for index in tmp:
            skeletons_tmp.append(skeletons[index])
            confs_tmp.append(confs[index])

        skeletons = skeletons_tmp
        confs = confs_tmp

        # 处理姿态数据
        kps_with_scores = self.load_part_kp(skeletons, confs, force_ok=True)

        support_rgb_dict = {}
        if self.rgb_support and self.rgb_data:
            support_rgb_dict = self.load_support_rgb_dict(tmp, skeletons, confs, self.rgb_data)

        return kps_with_scores, support_rgb_dict

    def load_part_kp(self, skeletons, confs, force_ok=False):
        """提取各部位关键点"""
        thr = 0.3
        kps_with_scores = {}
        scale = None

        for part in ['body', 'left', 'right', 'face_all']:
            kps = []
            confidences = []

            for skeleton, conf in zip(skeletons, confs):
                skeleton = skeleton[0]
                conf = conf[0]

                if part == 'body':
                    hand_kp2d = skeleton[[0] + [i for i in range(3, 11)], :]
                    confidence = conf[[0] + [i for i in range(3, 11)]]
                elif part == 'left':
                    hand_kp2d = skeleton[91:112, :]
                    hand_kp2d = hand_kp2d - hand_kp2d[0, :]
                    confidence = conf[91:112]
                elif part == 'right':
                    hand_kp2d = skeleton[112:133, :]
                    hand_kp2d = hand_kp2d - hand_kp2d[0, :]
                    confidence = conf[112:133]
                elif part == 'face_all':
                    indices = [i for i in list(range(23,23+17))[::2]] + [i for i in range(83, 83 + 8)] + [53]
                    hand_kp2d = skeleton[indices, :]
                    hand_kp2d = hand_kp2d - hand_kp2d[-1, :]
                    confidence = conf[indices]
                else:
                    raise NotImplementedError

                kps.append(hand_kp2d)
                confidences.append(confidence)

            kps = np.stack(kps, axis=0)
            confidences = np.stack(confidences, axis=0)

            if part == 'body':
                result, scale, _ = self.crop_scale(
                    np.concatenate([kps, confidences[..., None]], axis=-1), thr
                )
            else:
                result = np.concatenate([kps, confidences[..., None]], axis=-1)
                if scale == 0:
                    result = np.zeros(result.shape)
                else:
                    result[..., :2] = (result[..., :2]) / scale
                    result = np.clip(result, -1, 1)
                    result[result[..., 2] <= thr] = 0

            kps_with_scores[part] = torch.tensor(result)

        return kps_with_scores

    def crop_scale(self, motion, thr):
        """归一化姿态"""
        result = motion.copy()
        valid_coords = motion[motion[..., 2] > thr][:, :2]
        if len(valid_coords) < 4:
            return np.zeros(motion.shape), 0, None
        xmin = min(valid_coords[:, 0])
        xmax = max(valid_coords[:, 0])
        ymin = min(valid_coords[:, 1])
        ymax = max(valid_coords[:, 1])
        ratio = 1
        scale = max(xmax - xmin, ymax - ymin) * ratio
        if scale == 0:
            return np.zeros(motion.shape), 0, None
        xs = (xmin + xmax - scale) / 2
        ys = (ymin + ymax - scale) / 2
        result[..., :2] = (motion[..., :2] - [xs, ys]) / scale
        result[..., :2] = (result[..., :2] - 0.5) * 2
        result = np.clip(result, -1, 1)
        result[result[..., 2] <= thr] = 0
        return result, scale, [xs, ys]

    def load_support_rgb_dict(self, tmp, skeletons, confs, full_path):
        """简化版 RGB 支持（返回空字典）"""
        return {}

    def collate_fn(self, batch):
        """批处理函数"""
        tgt_batch, src_length_batch, name_batch, pose_tmp, gloss_batch = [], [], [], [], []

        for name_sample, pose_sample, text, gloss, _ in batch:
            name_batch.append(name_sample)
            pose_tmp.append(pose_sample)
            tgt_batch.append(text)
            gloss_batch.append(gloss)

        src_input = {}
        keys = pose_tmp[0].keys()

        for key in keys:
            max_len = max([len(vid[key]) for vid in pose_tmp])
            video_length = torch.LongTensor([len(vid[key]) for vid in pose_tmp])

            padded_video = []
            for vid in pose_tmp:
                vid_tensor = vid[key]
                if len(vid_tensor) < max_len:
                    pad = vid_tensor[-1].expand(max_len - len(vid_tensor), -1, -1)
                    padded = torch.cat([vid_tensor, pad], dim=0)
                else:
                    padded = vid_tensor
                padded_video.append(padded)

            img_batch = torch.stack(padded_video, 0)
            src_input[key] = img_batch

            if 'attention_mask' not in src_input:
                src_length_batch = video_length
                mask_gen = [torch.ones([i]) + 7 for i in src_length_batch]
                mask_gen = rnn_utils.pad_sequence(mask_gen, padding_value=0, batch_first=True)
                src_input['attention_mask'] = (mask_gen != 0).long()
                src_input['name_batch'] = name_batch
                src_input['src_length_batch'] = src_length_batch

        tgt_input = {
            'gt_sentence': tgt_batch,
            'gt_gloss': gloss_batch
        }

        return src_input, tgt_input


# ============ 姿态提取函数 ============
def process_frame(frame, wholebody):
    frame = np.uint8(frame)
    keypoints, scores = wholebody(frame)
    H, W, C = frame.shape
    return keypoints, scores, [W, H]


def pose_extraction(video_path, device="cuda"):
    """从视频提取姿态关键点"""
    max_workers = 8

    wholebody = Wholebody(
        to_openpose=False,
        mode="lightweight",
        backend="onnxruntime",
        device=device
    )

    data = {"keypoints": [], "scores": []}

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"无法打开视频: {video_path}")
        return None

    vid_data = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        vid_data.append(frame)
    cap.release()

    print(f"视频共 {len(vid_data)} 帧，开始提取姿态...")

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_frame, frame, wholebody) for frame in vid_data]
        for f in tqdm(futures, desc="提取姿态", total=len(vid_data)):
            results.append(f.result())

    for keypoints, scores, w_h in results:
        data['keypoints'].append(keypoints / np.array(w_h)[None, None])
        data['scores'].append(scores)

    print("姿态提取完成")
    return data


# ============ 推理函数 ============
def inference(data_loader, model):
    """运行推理并输出结果"""
    model.eval()

    target_dtype = torch.bfloat16

    with torch.no_grad():
        tgt_pres = []

        for step, (src_input, tgt_input) in enumerate(data_loader):
            # 将数据移动到 GPU
            if target_dtype is not None:
                for key in src_input.keys():
                    if isinstance(src_input[key], torch.Tensor):
                        src_input[key] = src_input[key].to(target_dtype).cuda()

            # 前向传播
            stack_out = model(src_input, tgt_input)

            # 生成翻译结果
            output = model.generate(
                stack_out,
                max_new_tokens=100,
                num_beams=4,
            )

            for i in range(len(output)):
                tgt_pres.append(output[i])

    # 解码结果
    if len(tgt_pres) > 0:
        tokenizer = model.mt5_tokenizer
        tgt_pres = [tokenizer.decode(p, skip_special_tokens=True) for p in tgt_pres]

        print(f"\n{'='*50}")
        print(f"翻译结果: {tgt_pres[0]}")
        print(f"{'='*50}\n")
    else:
        print("未生成任何结果")


# ============ 主函数 ============
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--online_video", required=True, type=str)
    parser.add_argument("--finetune", required=True, type=str)
    parser.add_argument("--rgb_support", action='store_true')
    parser.add_argument("--device", default="cuda", type=str)
    parser.add_argument("--hidden_dim", default=256, type=int)
    parser.add_argument("--max_length", default=256, type=int)
    parser.add_argument("--dataset", default="CSL_Daily", type=str)
    parser.add_argument("--task", default="SLT", type=str)
    parser.add_argument("--label_smoothing", default=0.2, type=float)
    parser.add_argument("--seed", default=42, type=int)

    args = parser.parse_args()

    print("="*50)
    print("Uni-Sign 独立推理测试")
    print("="*50)
    print(f"视频路径: {args.online_video}")
    print(f"模型路径: {args.finetune}")
    print(f"RGB支持: {args.rgb_support}")
    print(f"设备: {args.device}")

    # 设置随机种子
    set_seed(args.seed)

    # 检查文件
    if not os.path.exists(args.online_video):
        print(f"错误: 视频文件不存在 - {args.online_video}")
        return
    if not os.path.exists(args.finetune):
        print(f"错误: 模型文件不存在 - {args.finetune}")
        return

    # 设置设备
    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        print("CUDA 不可用，切换到 CPU")
        device = "cpu"

    # 1. 提取姿态
    print("\n[步骤 1/4] 提取视频姿态...")
    pose_data = pose_extraction(args.online_video, device=device)
    if pose_data is None:
        print("姿态提取失败")
        return

    # 2. 创建数据集
    print("\n[步骤 2/4] 创建数据集...")
    online_data = SimpleOnlineDataset(args, pose_data, args.online_video if args.rgb_support else None)
    online_dataloader = DataLoader(
        online_data,
        batch_size=1,
        collate_fn=online_data.collate_fn,
        shuffle=False
    )

    # 3. 创建模型
    print("\n[步骤 3/4] 加载模型...")
    model = Uni_Sign(args=args)
    model.cuda()

    # 加载权重
    print(f"加载权重: {args.finetune}")
    checkpoint = torch.load(args.finetune, map_location='cpu')

    # 处理不同的 checkpoint 格式
    if 'model' in checkpoint:
        state_dict = checkpoint['model']
    elif 'state_dict' in checkpoint:
        state_dict = checkpoint['state_dict']
    else:
        state_dict = checkpoint

    # 加载权重
    ret = model.load_state_dict(state_dict, strict=False)
    if ret.missing_keys:
        print(f"警告: 缺失的键数量: {len(ret.missing_keys)}")
    if ret.unexpected_keys:
        print(f"警告: 多余的键数量: {len(ret.unexpected_keys)}")

    model.eval()
    model.to(torch.bfloat16)

    # 4. 运行推理
    print("\n[步骤 4/4] 运行推理...")
    inference(online_dataloader, model)


if __name__ == '__main__':
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    main()