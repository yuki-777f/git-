import os
import json
import base64
import logging
from contextlib import asynccontextmanager
import hashlib
import hmac
import urllib.parse
import time
import shutil
import sys
import importlib.util
from types import SimpleNamespace
from threading import Lock
from uuid import uuid4
from datetime import datetime
from time import mktime
from wsgiref.handlers import format_date_time
import websocket

from pythonosc import udp_client
from openai import OpenAI
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_ELISE_DEBUG_LOG = os.path.join(_PROJECT_DIR, "elise_debug.log")

if os.name == "nt":
    # Windows PowerShell 默认可能是 GBK，避免 emoji/中文日志触发编码异常。
    # line_buffering=True 让 print 尽快出现在控制台（否则 uvicorn 下可能长时间看不到输出）。
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

# ==========================================
# 🔑 1. 密钥配置区
# ==========================================
APPID = "43576959"
API_KEY = "7a9194240238dcccb92a72105d521a99"
API_SECRET = "NTVkOGQ1Y2UxM2M3NTQ5YjhiNjIyN2Y3"
ZHIPU_API_KEY = "b6c07d3246a54cb79502f785de43c90d.K9rMow9XdfA8bdSC"

# ==========================================
# ⚙️ 2. 初始化客户端 & FastAPI 实例
# ==========================================
# OSC 发射器：注意这里换成了 9000 端口，避开 UE5 的 8888！
client = udp_client.SimpleUDPClient("127.0.0.1", 9000)
llm_client = OpenAI(api_key=ZHIPU_API_KEY, base_url="https://open.bigmodel.cn/api/paas/v4/")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _elise_console().info(
        "Elise 就绪。若控制台仍无延迟输出: 查看日志文件 %s ；热重载默认关闭，需 watch 文件请设置 ELISE_RELOAD=1",
        _ELISE_DEBUG_LOG,
    )
    yield


app = FastAPI(title="Elise 数字人云端大脑", lifespan=_lifespan)

# 允许跨域请求（极其重要！否则你后期的网页端无法调用这个接口）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有域名访问
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_elise_console_logger = None


class _FlushStreamHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()


class _FlushFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()


def _elise_console():
    """延迟与诊断日志：stderr + 项目目录 elise_debug.log（reload 时控制台可能看不到子进程 stderr）。"""
    global _elise_console_logger
    if _elise_console_logger is not None:
        return _elise_console_logger
    lg = logging.getLogger("elise.console")
    lg.handlers.clear()
    lg.setLevel(logging.INFO)
    lg.propagate = False
    fmt = logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S")
    sh = _FlushStreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    lg.addHandler(sh)
    try:
        fh = _FlushFileHandler(_ELISE_DEBUG_LOG, mode="a", encoding="utf-8")
        fh.setFormatter(fmt)
        lg.addHandler(fh)
    except OSError:
        pass
    _elise_console_logger = lg
    return lg


# 勿用 BaseHTTPMiddleware 记录上传接口：会破坏 multipart 流，导致路由收不到文件且无日志。
@app.middleware("http")
async def _elise_request_logger(request: Request, call_next):
    if request.method == "POST" and request.url.path in ("/voice_to_sign", "/sign_to_text"):
        _elise_console().info(">>> 收到请求 %s %s", request.method, request.url.path)
    return await call_next(request)


# ==========================================
# 🤟 2.1 Uni-Sign 推理配置（视频 -> 文本）
# ==========================================
UNISIGN_ROOT = os.getenv("UNISIGN_ROOT", os.path.join(os.path.dirname(__file__), "..", "Uni-Sign-main"))
UNISIGN_FINETUNE = os.getenv("UNISIGN_FINETUNE", "")
UNISIGN_DEVICE = os.getenv("UNISIGN_DEVICE", "cpu")
UNISIGN_MAX_LENGTH = int(os.getenv("UNISIGN_MAX_LENGTH", "256"))

_unisign_lock = Lock()
_unisign_module = None
_unisign_model = None
_unisign_wholebody = None
_unisign_args = None


def _load_unisign_runtime():
    """懒加载 Uni-Sign 模块、模型和姿态提取器。"""
    global _unisign_module, _unisign_model, _unisign_wholebody, _unisign_args

    with _unisign_lock:
        if _unisign_module and _unisign_model and _unisign_wholebody and _unisign_args:
            return _unisign_module, _unisign_model, _unisign_wholebody, _unisign_args

        if not os.path.isdir(UNISIGN_ROOT):
            raise RuntimeError(f"未找到 Uni-Sign 目录: {UNISIGN_ROOT}")
        if not UNISIGN_FINETUNE:
            raise RuntimeError("未配置 UNISIGN_FINETUNE（请设置模型权重路径）")
        if not os.path.isfile(UNISIGN_FINETUNE):
            raise RuntimeError(f"未找到 Uni-Sign 权重文件: {UNISIGN_FINETUNE}")

        if UNISIGN_ROOT not in sys.path:
            sys.path.insert(0, UNISIGN_ROOT)

        module_path = os.path.join(UNISIGN_ROOT, "camera_realtime.py")
        if not os.path.isfile(module_path):
            raise RuntimeError(f"未找到 camera_realtime.py: {module_path}")

        spec = importlib.util.spec_from_file_location("unisign_camera_realtime", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("加载 Uni-Sign 模块失败")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        args = SimpleNamespace(
            finetune=UNISIGN_FINETUNE,
            camera_id=0,
            device=UNISIGN_DEVICE,
            hidden_dim=256,
            max_length=UNISIGN_MAX_LENGTH,
            dataset="CSL_Daily",
            task="SLT",
            label_smoothing=0.2,
            seed=42,
            rgb_support=False,
            output_dir="",
            num_workers=0,
            pin_mem=False,
        )

        module.set_seed(args.seed)
        model = module.Uni_Sign(args=args).to(args.device)
        if args.device == "cuda":
            model.to(module.torch.bfloat16)

        checkpoint = module.torch.load(args.finetune, map_location=args.device)
        if "model" in checkpoint:
            state_dict = checkpoint["model"]
        elif "state_dict" in checkpoint:
            state_dict = checkpoint["state_dict"]
        else:
            state_dict = checkpoint
        model.load_state_dict(state_dict, strict=False)
        model.eval()

        wholebody = module.Wholebody(
            to_openpose=False,
            mode="lightweight",
            backend="onnxruntime",
            device=args.device,
        )

        _unisign_module = module
        _unisign_model = model
        _unisign_wholebody = wholebody
        _unisign_args = args
        print("✅ Uni-Sign 运行时加载完成")
        return _unisign_module, _unisign_model, _unisign_wholebody, _unisign_args


def _read_video_frames(video_path: str):
    """读取上传视频的所有帧。"""
    import cv2  # 延迟导入，避免无依赖时启动失败

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频文件: {video_path}")

    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames


def recognize_sign_video_unisign(video_path: str):
    """调用 Uni-Sign 对上传视频做一次推理。返回 (识别文本, 各阶段耗时毫秒字典)。"""
    timings_ms = {}
    t0 = time.perf_counter()
    module, model, wholebody, args = _load_unisign_runtime()
    timings_ms["load_runtime"] = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    frames = _read_video_frames(video_path)
    timings_ms["read_video"] = (time.perf_counter() - t1) * 1000.0

    if len(frames) < 30:
        raise RuntimeError("录制时间太短，请录制2-3秒")
    if len(frames) > 300:
        raise RuntimeError("录制时间太长，请控制在5秒内")

    t2 = time.perf_counter()
    pose_data = module.pose_extraction_from_frames(frames, wholebody)
    timings_ms["pose_extraction"] = (time.perf_counter() - t2) * 1000.0
    if pose_data is None:
        raise RuntimeError("姿态提取失败")

    t3 = time.perf_counter()
    result = module.run_inference_once(model, args, pose_data)
    timings_ms["inference"] = (time.perf_counter() - t3) * 1000.0
    result = (result or "").strip()
    if not result:
        raise RuntimeError("未识别到有效手势")
    timings_ms["total_pipeline"] = sum(
        timings_ms[k] for k in ("load_runtime", "read_video", "pose_extraction", "inference")
    )
    return result, timings_ms

# ==========================================
# 📚 3. 动态加载 JSON 词库
# ==========================================
json_path = os.path.join(os.path.dirname(__file__), 'lexicon.json')
try:
    with open(json_path, 'r', encoding='utf-8') as f:
        sentence_dictionary = json.load(f)
    dict_sentences = list(sentence_dictionary.keys())
    print(f"📚 成功加载外部词库！当前收录了 {len(dict_sentences)} 种标准动作。")
except Exception as e:
    print(f"❌ 词库加载失败，请检查 lexicon.json 文件: {e}")
    exit()

# ==========================================
# 🧠 4. 大模型语义归一化函数 (保持原样，非常完美)
# ==========================================
def get_matched_anim_key_llm(user_text: str, valid_intents: list) -> str:
    if len(user_text) <= 1:
        return "NONE"

    system_prompt = f"""
    【角色设定】：
    你是一个极其保守、严苛的意图匹配过滤网。你的任务是审查用户的口语，看它是否能与【标准库】中的某一条指令【完美且唯一地】对应。
    
    【标准动作库】：
    {json.dumps(valid_intents, ensure_ascii=False)}
    
    【核心铁律】：
    1. 你只能输出【标准库】中存在的完整词条，绝不能有多余字符或标点。
    2. 【拒绝推测】：如果意图模糊，你【必须】输出 NONE！
    3. 除非达到了【充分且高度相似】，否则一律驳回，输出 NONE。
    """
    try:
        response = llm_client.chat.completions.create(
            model="glm-4-flash", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            temperature=0.0,
            max_tokens=20
        )
        result = response.choices[0].message.content.strip()
        return result if result in valid_intents else "NONE"
    except Exception as e:
        print(f"❌ LLM 路由报错: {e}")
        return "NONE"

# ==========================================
# 🚀 5. 讯飞音频识别底层
# ==========================================
def create_url():
    url = 'ws://ws-api.xfyun.cn/v2/iat'
    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))
    signature_origin = "host: ws-api.xfyun.cn\ndate: " + date + "\nGET /v2/iat HTTP/1.1"
    signature_sha = hmac.new(API_SECRET.encode('utf-8'), signature_origin.encode('utf-8'), digestmod=hashlib.sha256).digest()
    signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')
    authorization_origin = "api_key=\"%s\", algorithm=\"hmac-sha256\", headers=\"host date request-line\", signature=\"%s\"" % (API_KEY, signature_sha)
    authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')
    v = {"authorization": authorization, "date": date, "host": "ws-api.xfyun.cn"}
    return url + '?' + urllib.parse.urlencode(v)

def recognize_audio_xf(audio_path):
    wsUrl = create_url()
    ws = websocket.create_connection(wsUrl)
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    d = {
        "common": {"app_id": APPID},
        "business": {"domain": "iat", "language": "zh_cn", "accent": "mandarin", "vinfo": 1, "vad_eos": 10000},
        "data": {"status": 2, "format": "audio/L16;rate=16000", "audio": base64.b64encode(audio_data).decode('utf-8'), "encoding": "raw"}
    }
    ws.send(json.dumps(d))
    result_text = ""
    while True:
        res = ws.recv()
        res_dict = json.loads(res)
        if res_dict["code"] != 0:
            print(f"❌ 讯飞请求报错: {res_dict['message']}")
            break
        ws_data = res_dict["data"]["result"]["ws"]
        for w in ws_data:
            for cw in w["cw"]:
                result_text += cw["w"]
        if res_dict["data"]["status"] == 2:
            break
    ws.close()
    return result_text

# ==========================================
# 🌐 6. FastAPI 核心路由接口
# ==========================================
@app.get("/")
def read_root():
    return {"status": "ok", "message": "Elise 神经中枢已上线，等待语音指令..."}


@app.get("/warmup_unisign")
def warmup_unisign():
    """仅懒加载 Uni-Sign（不读视频）。供前端预热，勿再上传伪 webm。"""
    lg = _elise_console()
    lg.info(">>> 收到请求 GET /warmup_unisign")
    t0 = time.perf_counter()
    _load_unisign_runtime()
    ms = (time.perf_counter() - t0) * 1000.0
    lg.info("[延迟] Uni-Sign 预热-仅加载运行时: %.1f ms", ms)
    return {"status": "ok", "message": "Uni-Sign 运行时已加载", "latency_ms": {"load_runtime": round(ms, 2)}}

@app.post("/voice_to_sign")
async def process_voice(file: UploadFile = File(...)):
    lg = _elise_console()
    lg.info("收到语音包: %s", file.filename)
    t_request = time.perf_counter()

    # 1. 保存前端传来的临时录音文件
    temp_filename = f"temp_req_{int(time.time())}.wav"
    with open(temp_filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    t_after_save = time.perf_counter()

    try:
        # 2. 调用讯飞进行 ASR 识别
        lg.info("语音识别: 呼叫讯飞 ASR ...")
        t_asr0 = time.perf_counter()
        user_text = recognize_audio_xf(temp_filename)
        t_asr1 = time.perf_counter()
        ms_asr = (t_asr1 - t_asr0) * 1000.0
        user_text = user_text.replace("。", "").replace("？", "").replace("，", "").strip()
        lg.info("语音识别: 听写结果=%s", user_text)
        lg.info("[延迟] 语音识别-讯飞ASR: %.1f ms", ms_asr)

        if not user_text:
            ms_total = (time.perf_counter() - t_request) * 1000.0
            lg.info(
                "[延迟] 语音识别-请求总耗时(失败): %.1f ms (含保存文件 %.1f ms)",
                ms_total,
                (t_after_save - t_request) * 1000.0,
            )
            return {
                "status": "error",
                "message": "未识别到清晰的人声",
                "latency_ms": {"total": round(ms_total, 2), "xfyun_asr": round(ms_asr, 2), "save_file": round((t_after_save - t_request) * 1000.0, 2)},
            }

        # 3. 大模型语义匹配
        lg.info("语音识别: 请求大模型意图匹配 ...")
        t_llm0 = time.perf_counter()
        matched_sentence = get_matched_anim_key_llm(user_text, dict_sentences)
        t_llm1 = time.perf_counter()
        ms_llm = (t_llm1 - t_llm0) * 1000.0
        lg.info("[延迟] 语音识别-大模型意图匹配: %.1f ms", ms_llm)

        ms_total = (time.perf_counter() - t_request) * 1000.0
        ms_save = (t_after_save - t_request) * 1000.0
        latency = {
            "total": round(ms_total, 2),
            "save_file": round(ms_save, 2),
            "xfyun_asr": round(ms_asr, 2),
            "llm_match": round(ms_llm, 2),
        }
        lg.info(
            "[延迟] 语音识别-请求总耗时: %.1f ms (保存 %.1f + ASR %.1f + LLM %.1f)",
            ms_total,
            ms_save,
            ms_asr,
            ms_llm,
        )

        # 4. 判断并发送 OSC
        if matched_sentence != "NONE":
            anim_code = sentence_dictionary[matched_sentence]
            lg.info("语义匹配成功 intent=%s osc=%s", matched_sentence, anim_code)

            # 向 UE5 蓝图发送 OSC！
            client.send_message("/sign", anim_code)

            return {
                "status": "success",
                "text_recognized": user_text,
                "intent_matched": matched_sentence,
                "osc_sent": anim_code,
                "latency_ms": latency,
            }
        else:
            lg.info("语义匹配失败，保持待机")
            return {
                "status": "unmatched",
                "text_recognized": user_text,
                "message": "大模型判断输入与现有词库毫无关联",
                "latency_ms": latency,
            }

    except Exception as e:
        _elise_console().exception("语音识别处理异常")
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # 5. 无论成功失败，必须清理临时语音文件，防止把硬盘撑爆
        if os.path.exists(temp_filename):
            os.remove(temp_filename)


@app.post("/sign_to_text")
async def process_sign_video(file: UploadFile = File(...)):
    lg = _elise_console()
    lg.info("收到手语视频: %s", file.filename)
    t_request = time.perf_counter()

    suffix = os.path.splitext(file.filename or "")[1] or ".webm"
    temp_filename = f"temp_sign_{int(time.time())}_{uuid4().hex[:8]}{suffix}"
    with open(temp_filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    t_after_save = time.perf_counter()
    ms_save = (t_after_save - t_request) * 1000.0

    try:
        lg.info("手语识别: Uni-Sign 推理 ...")
        t_infer0 = time.perf_counter()
        sign_text, pipe_ms = recognize_sign_video_unisign(temp_filename)
        t_infer1 = time.perf_counter()
        ms_infer_wall = (t_infer1 - t_infer0) * 1000.0
        lg.info("手语识别: 文本结果=%s", sign_text)
        # 分阶段（与 wall 可能略有差异，因 perf 边界）
        lr = pipe_ms.get("load_runtime", 0)
        rv = pipe_ms.get("read_video", 0)
        pe = pipe_ms.get("pose_extraction", 0)
        inf = pipe_ms.get("inference", 0)
        lg.info("[延迟] 手语识别-加载模型/运行时: %.1f ms", lr)
        lg.info("[延迟] 手语识别-读视频帧: %.1f ms", rv)
        lg.info("[延迟] 手语识别-姿态提取: %.1f ms", pe)
        lg.info("[延迟] 手语识别-模型推理: %.1f ms", inf)
        ms_total = (time.perf_counter() - t_request) * 1000.0
        latency = {
            "total": round(ms_total, 2),
            "save_file": round(ms_save, 2),
            "uni_pipeline_wall": round(ms_infer_wall, 2),
            "load_runtime": round(lr, 2),
            "read_video": round(rv, 2),
            "pose_extraction": round(pe, 2),
            "inference": round(inf, 2),
        }
        lg.info(
            "[延迟] 手语识别-请求总耗时: %.1f ms (保存 %.1f + Uni-Sign 管线约 %.1f)",
            ms_total,
            ms_save,
            ms_infer_wall,
        )
        # 手语模块与数字人动作模块解耦：这里只返回翻译文本，不做词库匹配和 OSC 联动。
        return {
            "status": "success",
            "text": sign_text,
            "latency_ms": latency,
        }
    except Exception as e:
        lg = _elise_console()
        lg.exception("手语接口处理失败")
        ms_total = (time.perf_counter() - t_request) * 1000.0
        lg.info("[延迟] 手语识别-请求总耗时(失败): %.1f ms", ms_total)
        return {
            "status": "error",
            "message": str(e),
            "latency_ms": {"total": round(ms_total, 2), "save_file": round(ms_save, 2)},
        }
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

# ==========================================
# 🏁 7. 启动服务器
# ==========================================
if __name__ == "__main__":
    print("========================================")
    print("🚀 Elise FastAPI 服务器启动中...")
    print("服务器地址: http://127.0.0.1:8000")
    print("延迟/诊断日志文件:", _ELISE_DEBUG_LOG)
    print("开启热重载: set ELISE_RELOAD=1  （默认关闭，避免 Windows 下子进程日志难对齐）")
    print("========================================\n")
    _use_reload = os.getenv("ELISE_RELOAD", "0").strip().lower() in ("1", "true", "yes", "on")
    # 默认不传 import 字符串，避免本文件再以「main」被导入一次导致词库等顶层 print 重复。
    if _use_reload:
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    else:
        uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)