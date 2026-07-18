# Elise 设计说明

蔡亲正，湖南大学，学号 202208010226，指导教师许莹。日期 2026.05.05，版本 v1.0

---

## 1 仓库里有什么

本系统是我做的语音转手语数字人、手语视频转文字的一体化网页：用 `index.html` 做左右分栏主界面，后端是 `elise/main.py`（FastAPI），数字人用 UE5 打包在本机跑，画面进浏览器靠 Pixel Streaming，信令用自带的 `SignallingWebServer`（Node）。

**本仓库没有完整 UE 工程。** 工程加资产体积太大，本机开编辑器也很吃内存，我只把打好的 `Windows/myproject.exe`（以本机实际文件名为准）放进仓库；改蓝图、蒙太奇等要在我本地 UE 工程里改完再打新包。
**注意：保持 elise 与 Uni-Sign-main 同级**

---

## 2 我做了什么

浏览器里用 RecordRTC 录 16k 语音，手语用 `MediaRecorder` 录成 webm。语音上传后走讯飞听写拿文字，再用智谱 `glm-4-flash` 对照 `lexicon.json`；命中了就用 `python-osc` 往本机 `127.0.0.1:9000` 发 `/sign` 加动画名。手语走 Uni-Sign，结果只显示文字，**不会**再给数字人发 OSC。

---

## 3 端口和数据怎么走

后端默认 **8000**；信令网页 **8080**；UE 推流连信令 **8888**；流送组件还有 **8889**。UE 里 OSC 监听 **9000**，和流端口分开是我刻意避开的。

浏览器用 `fetch` 打 `8000`；数字人画面 iframe 指 `8080` 下的 `player.html`，具体路径要和 `config.json` 里的 `http_root` 对上。我默认用的是：

```
http://127.0.0.1:8080/SignallingWebServer/www/player.html
```

`config.json` 里相关片段是：

```json
"streamer_port": "8888",
"player_port": "8080",
"sfu_port": "8889",
"serve": true,
"http_root": "..",
"homepage": "index.html",
"https": false
```

改端口时要一起改 `index.html` 里 iframe、`start_elise.ps1` 里 UE 参数，别只改一处。

---

## 4 关于前端

左栏是摄像头、手语按钮和结果；右栏嵌流送页面，下面有语音按钮；最底下是一段日志区。语音点一次开始、再点一次结束，太短的我直接丢掉不上传。摄像头就绪后会调一次 `/warmup_unisign`，免得第一次手语卡很久。

---

## 5 关于后端 main.py 里我做了什么

启动时读 `lexicon.json`，读失败就退出。讯飞、智谱密钥现在写死在文件里，交作业前要脱敏，**不要**把真密钥 push 上去。

`/voice_to_sign` 收 wav：先 ASR，再让大模型在词表里选一句；选到了就发 OSC，JSON 里带延迟毫秒；没选到也返回 200，只是 `status` 不同；真正崩了才会 500。`/sign_to_text` 收视频，走 Uni-Sign，成功失败多数时候都是 200，看 `status` 和 `message`。详细字段写在代码里，起服务后需要可打开：

```
http://127.0.0.1:8000/docs
```

---

## 6 关于数字人

UE 工程里我配好了收 OSC。后端只负责发，地址固定 **`/sign`**，参数一个字符串，内容是 `lexicon.json` 里的 value（例如 `Anim_02`），**不是**中文 key。联调验收：项目跑起来，说命中词表的话，人能动，浏览器里画面跟得上。
详细的数字人部署说明见**elise/Elise系统部署说明.docx**

---

## 7 关于手语 Uni-Sign 的集成

我把 Uni-Sign 放在仓库外一层目录，用环境变量指过去；第一次识别时才 `importlib` 加载，不然启动太慢。权重路径、用 cpu 还是 cuda，在 `start_elise.ps1` 开手语时会注入。

**手语识别还要单独搞一套环境。** Uni-Sign 官方推荐 Anaconda，按仓库说明建 conda 环境、装依赖；这和 `elise` 里跑 FastAPI 的 Python 可以不是同一个解释器，版本与包以官方为准：`https://github.com/ZechengLi19/Uni-Sign`。我本地是装好 conda 后，把 `Uni-Sign-main` 整份 clone 到与 `elise` 同级目录，再配 `UNISIGN_*`。

**mT5 基座（`mt5-base`）也要配。** 手语管线会用到 `google/mt5-base`，在 `Uni-Sign-main/config.py` 里改 **`mt5_path`**。第一次建议写 `mt5_path = "google/mt5-base"`，跑通一次后会从 Hugging Face 下到本机缓存；下完后把 **`mt5_path` 改成你机器上实际目录**（一般在用户目录 `.cache/huggingface/hub/` 下带 `models--google--mt5-base` 的 snapshots 路径），以后不必每次都联网拉。`config.py` 前几行注释也有示例。

另外：帧太少或太多时 `main.py` 会直接报错，要录大约两三秒到几秒；姿态相关 onnx 第一次会下到用户目录缓存。

---

## 8 关于大致运行流程

先装好 **Python 3.10** 和 **Node LTS**。手语环境也要单独配好，可在 Uni-Sign 目录下先跑通 `camera_realtime.py` 看效果。进 `elise/SignallingWebServer` 执行一次 `npm install`。

在 `elise` 目录开 PowerShell：

```
powershell -ExecutionPolicy Bypass -File .\start_elise.ps1 -InstallDeps -StartUE -OpenUI
```

要带手语后端就加 `-EnableSignLanguageBackend`，具体开关看 `start_elise.ps1` 文件头。关服务用 `stop_elise.bat`。若开过 `ELISE_RELOAD=1` 热重载，占 8000 的进程有时对不上 netstat，脚本里按命令行多杀了一道兜底。

---

## 9 我实测的感受（不是实验室标准）

语音从说完到数字人动起来，体感要**两秒多**，和论文表 4.2 接近；数字人窗口我这边能稳在**60 帧左右**；动作主观上还行，论文请人打分综合大约 **4.42**。手语识别跟显卡关系很大：笔记本核显时等得有点烦，换独显会好不少。录太短会提示再录一段，这是我写死帧数阈值时的取舍。

---

## 10 我还想改进的地方

词表只有几句口语，日常聊天很容易返回 `unmatched`（听写对上了，但话不在 `lexicon.json` 里，大模型就不会匹配到固定话术，数字人也不播动作）。手语在逆光或乱背景下会飘，数字人手指细节也不够细。以后想多加话术，并把前处理做稳一点。

---

## 附录：目录大概长这样

```
elise/
  main.py
  lexicon.json
  index.html
  start_elise.ps1
  stop_elise.bat / stop_ports.ps1
  SignallingWebServer/   （Node 信令 + www 静态页）
  Windows/myproject.exe  （UE 打包，仅此，无整工程）
Uni-Sign-main/           （与 UNISIGN_ROOT 对应）
```

