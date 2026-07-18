"""
基于 simple_test.py 的摄像头开关式实时识别脚本
按键说明：
- s: 开始/停止录制（停止后自动识别）
- q: 退出程序
"""

import argparse
import os
import random
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import torch
import torch.nn.utils.rnn as rnn_utils
from torch.utils.data import DataLoader, Dataset

from models import Uni_Sign
from rtmlib import Wholebody


def set_seed(seed):
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)


class SimpleOnlineDataset(Dataset):
    """简化的在线数据集，不依赖原始 datasets.py"""

    def __init__(self, args, pose_data):
        self.args = args
        self.max_length = args.max_length
        self.pose_data = pose_data

    def __len__(self):
        return 1

    def __getitem__(self, index):
        text = ""
        gloss = ""
        name_sample = "camera_data"
        pose_sample = self.load_pose()
        return name_sample, pose_sample, text, gloss, {}

    def load_pose(self):
        pose = self.pose_data
        duration = len(pose["scores"])

        if duration > self.max_length:
            tmp = sorted(random.sample(range(duration), k=self.max_length))
        else:
            tmp = list(range(duration))

        tmp = np.array(tmp)
        skeletons = pose["keypoints"]
        confs = pose["scores"]
        skeletons = [skeletons[index] for index in tmp]
        confs = [confs[index] for index in tmp]
        return self.load_part_kp(skeletons, confs, force_ok=True)

    def load_part_kp(self, skeletons, confs, force_ok=False):
        thr = 0.3
        kps_with_scores = {}
        scale = None

        for part in ["body", "left", "right", "face_all"]:
            kps = []
            confidences = []

            for skeleton, conf in zip(skeletons, confs):
                skeleton = skeleton[0]
                conf = conf[0]

                if part == "body":
                    hand_kp2d = skeleton[[0] + [i for i in range(3, 11)], :]
                    confidence = conf[[0] + [i for i in range(3, 11)]]
                elif part == "left":
                    hand_kp2d = skeleton[91:112, :]
                    hand_kp2d = hand_kp2d - hand_kp2d[0, :]
                    confidence = conf[91:112]
                elif part == "right":
                    hand_kp2d = skeleton[112:133, :]
                    hand_kp2d = hand_kp2d - hand_kp2d[0, :]
                    confidence = conf[112:133]
                elif part == "face_all":
                    indices = [i for i in list(range(23, 23 + 17))[::2]] + [i for i in range(83, 83 + 8)] + [53]
                    hand_kp2d = skeleton[indices, :]
                    hand_kp2d = hand_kp2d - hand_kp2d[-1, :]
                    confidence = conf[indices]
                else:
                    raise NotImplementedError

                kps.append(hand_kp2d)
                confidences.append(confidence)

            kps = np.stack(kps, axis=0)
            confidences = np.stack(confidences, axis=0)

            if part == "body":
                result, scale, _ = self.crop_scale(np.concatenate([kps, confidences[..., None]], axis=-1), thr)
            else:
                result = np.concatenate([kps, confidences[..., None]], axis=-1)
                if scale == 0:
                    result = np.zeros(result.shape)
                else:
                    result[..., :2] = result[..., :2] / scale
                    result = np.clip(result, -1, 1)
                    result[result[..., 2] <= thr] = 0

            kps_with_scores[part] = torch.tensor(result, dtype=torch.float32)

        return kps_with_scores

    def crop_scale(self, motion, thr):
        result = motion.copy()
        valid_coords = motion[motion[..., 2] > thr][:, :2]
        if len(valid_coords) < 4:
            return np.zeros(motion.shape), 0, None
        xmin = min(valid_coords[:, 0])
        xmax = max(valid_coords[:, 0])
        ymin = min(valid_coords[:, 1])
        ymax = max(valid_coords[:, 1])
        scale = max(xmax - xmin, ymax - ymin)
        if scale == 0:
            return np.zeros(motion.shape), 0, None
        xs = (xmin + xmax - scale) / 2
        ys = (ymin + ymax - scale) / 2
        result[..., :2] = (motion[..., :2] - [xs, ys]) / scale
        result[..., :2] = (result[..., :2] - 0.5) * 2
        result = np.clip(result, -1, 1)
        result[result[..., 2] <= thr] = 0
        return result, scale, [xs, ys]

    def collate_fn(self, batch):
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

            if "attention_mask" not in src_input:
                src_length_batch = video_length
                mask_gen = [torch.ones([i]) + 7 for i in src_length_batch]
                mask_gen = rnn_utils.pad_sequence(mask_gen, padding_value=0, batch_first=True)
                src_input["attention_mask"] = (mask_gen != 0).long()
                src_input["name_batch"] = name_batch
                src_input["src_length_batch"] = src_length_batch

        tgt_input = {"gt_sentence": tgt_batch, "gt_gloss": gloss_batch}
        return src_input, tgt_input


def process_frame(frame, wholebody):
    frame = np.uint8(frame)
    keypoints, scores = wholebody(frame)
    h, w, _ = frame.shape
    return keypoints, scores, [w, h]


def pose_extraction_from_frames(frames, wholebody, max_workers=8):
    data = {"keypoints": [], "scores": []}
    if not frames:
        return None

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_frame, frame, wholebody) for frame in frames]
        for f in futures:
            results.append(f.result())

    for keypoints, scores, w_h in results:
        data["keypoints"].append(keypoints / np.array(w_h)[None, None])
        data["scores"].append(scores)
    return data


def run_inference_once(model, args, pose_data):
    """CPU 版本的推理函数"""
    online_data = SimpleOnlineDataset(args, pose_data)
    online_dataloader = DataLoader(
        online_data,
        batch_size=1,
        collate_fn=online_data.collate_fn,
        shuffle=False,
    )

    model.eval()
    tgt_pres = []

    with torch.no_grad():
        for src_input, tgt_input in online_dataloader:
            # 将数据移动到 CPU（或 GPU）
            for key in src_input.keys():
                if isinstance(src_input[key], torch.Tensor):
                    src_input[key] = src_input[key].to(dtype=torch.float32, device=args.device)

            # 前向传播
            stack_out = model(src_input, tgt_input)

            # 生成结果
            output = model.generate(stack_out, max_new_tokens=100, num_beams=4)
            for i in range(len(output)):
                tgt_pres.append(output[i])

    if len(tgt_pres) == 0:
        return "未生成结果"

    tokenizer = model.mt5_tokenizer
    texts = [tokenizer.decode(p, skip_special_tokens=True) for p in tgt_pres]
    result = texts[0] if texts else "未生成结果"

    # 过滤无效结果
    if result == "?" or result.count("?") > 20 or result == "？？？":
        return "未检测到有效手势，请重新录制"

    return result


def draw_overlay(frame, is_recording, result_text):
    """只在屏幕上显示状态，结果显示在控制台"""
    status_text = "REC: ON" if is_recording else "REC: OFF"
    status_color = (0, 0, 255) if is_recording else (0, 255, 0)

    cv2.putText(frame, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, status_color, 2, cv2.LINE_AA)
    cv2.putText(
        frame,
        "Press 's' to start/stop, 'q' to quit",
        (10, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    # 结果不在屏幕上显示，避免中文乱码


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--finetune", required=True, type=str, help="模型权重路径")
    parser.add_argument("--camera_id", default=0, type=int, help="摄像头编号")
    parser.add_argument("--device", default="cpu", type=str, choices=["cuda", "cpu"], help="设备")
    parser.add_argument("--hidden_dim", default=256, type=int)
    parser.add_argument("--max_length", default=256, type=int)
    parser.add_argument("--dataset", default="CSL_Daily", type=str)
    parser.add_argument("--task", default="SLT", type=str)
    parser.add_argument("--label_smoothing", default=0.2, type=float)
    parser.add_argument("--seed", default=42, type=int)

    # 添加模型需要的参数
    parser.add_argument("--rgb_support", action='store_true')
    parser.add_argument("--output_dir", default="", type=str)
    parser.add_argument("--num_workers", default=0, type=int)
    parser.add_argument("--pin_mem", action='store_true')

    args = parser.parse_args()

    set_seed(args.seed)

    if not os.path.exists(args.finetune):
        print(f"错误: 模型文件不存在 - {args.finetune}")
        return

    # 设备设置
    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        print("CUDA 不可用，切换到 CPU")
        device = "cpu"
    print(f"使用设备: {device}")
    args.device = device

    print("=" * 50)
    print("Uni-Sign 摄像头开关式实时识别")
    print("=" * 50)
    print(f"模型路径: {args.finetune}")
    print(f"设备: {device}")
    print("按键: s 开始/停止录制；q 退出")

    # 初始化姿态估计器（使用 CPU）
    wholebody = Wholebody(
        to_openpose=False,
        mode="lightweight",
        backend="onnxruntime",
        device=device,
    )

    # 初始化模型
    print("加载模型中...")
    model = Uni_Sign(args=args)

    # 移动到指定设备
    model = model.to(device)
    # CPU 不支持 bfloat16，保持 float32
    if device == "cuda":
        model.to(torch.bfloat16)
    else:
        print("CPU 模式，使用 float32")

    print(f"加载权重: {args.finetune}")
    checkpoint = torch.load(args.finetune, map_location=device)
    if "model" in checkpoint:
        state_dict = checkpoint["model"]
    elif "state_dict" in checkpoint:
        state_dict = checkpoint["state_dict"]
    else:
        state_dict = checkpoint

    ret = model.load_state_dict(state_dict, strict=False)
    if ret.missing_keys:
        print(f"警告: 缺失的键数量: {len(ret.missing_keys)}")
    if ret.unexpected_keys:
        print(f"警告: 多余的键数量: {len(ret.unexpected_keys)}")

    model.eval()
    print("模型加载完成，准备就绪！")

    # 打开摄像头
    cap = cv2.VideoCapture(args.camera_id)
    if not cap.isOpened():
        print(f"错误: 无法打开摄像头 {args.camera_id}")
        return

    is_recording = False
    recorded_frames = []
    latest_result = "暂无"

    while True:
        ret_frame, frame = cap.read()
        if not ret_frame:
            print("读取摄像头帧失败")
            break

        if is_recording:
            recorded_frames.append(frame.copy())

        display = frame.copy()
        draw_overlay(display, is_recording, latest_result)
        cv2.imshow("Uni-Sign Camera Recognition", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("s"):
            if not is_recording:
                is_recording = True
                recorded_frames = []
                latest_result = "录制中..."
                print("\n[状态] 开始录制")
            else:
                is_recording = False
                print(f"\n[状态] 停止录制，帧数: {len(recorded_frames)}，开始识别...")

                if len(recorded_frames) < 30:
                    latest_result = "录制时间太短，请录制2-3秒"
                    print(f"[结果] {latest_result}")
                    continue

                if len(recorded_frames) > 300:
                    latest_result = "录制时间太长，请控制在5秒内"
                    print(f"[结果] {latest_result}")
                    continue

                pose_data = pose_extraction_from_frames(recorded_frames, wholebody)
                if pose_data is None:
                    latest_result = "姿态提取失败"
                    print("[结果] 姿态提取失败")
                    continue

                result = run_inference_once(model, args, pose_data)
                print(f"[识别结果] {result}")
                latest_result = result

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    main()