# 文案 → 视频（本机网页应用）

把中文口播文案自动做成横屏短视频：**分句配音（IndexTTS 2.0 声音克隆）→ 分章节横屏画面 → 烧录单行抖音字幕 → 合成 1920×1080 成片**，并自动保存到你指定的文件夹。

画面风格接入 `guizang-ppt-skill` 的 9 套设计（WebGL 签名背景 + 逐字取自 skill 的主题色/字体）：A 电子杂志 5 套（🖋 墨水经典 / 🌊 靛蓝瓷 / 🌿 森林墨 / 🍂 牛皮纸 / 🌙 沙丘，流体背景）+ B 瑞士国际主义 4 套（🔵 克莱因蓝 / 🟡 柠檬黄 / 🟢 柠檬绿 / 🟠 安全橙，网格点阵背景）。

## 启动

```bash
cd webapp
./run.sh
```

打开浏览器访问 <http://127.0.0.1:8000>。首次生成会加载 IndexTTS 2.0 模型（约几十秒），请耐心等待。

自定义端口：`PORT=8010 ./run.sh`

## 使用

1. **设置页**（右上角「设置」）配置四项（其余参数已锁定，不可改）：
   - **音色文件**：上传一段清晰 `.wav` 人声（约 8 秒）。默认 `刘佑文音色_8s.wav`。
   - **语速**：0.8–1.3，默认 1.0（保持音高变速）。
   - **视频生成路径**：成片保存到的本机文件夹，默认 `~/Desktop/文案视频`（不存在会自动创建）。
   - **HTML 风格**：9 选 1（A 电子杂志：🖋 墨水经典 / 🌊 靛蓝瓷 / 🌿 森林墨 / 🍂 牛皮纸 / 🌙 沙丘；B 瑞士：🔵 克莱因蓝 / 🟡 柠檬黄 / 🟢 柠檬绿 / 🟠 安全橙）。
2. **主页**粘贴文案，点「生成视频」。进度条实时显示阶段。
3. 完成后显示**已保存的绝对路径** + 内嵌预览，点「在访达中显示」可在 Finder 定位文件。

## 目录结构

```
webapp/
├── engine/
│   ├── config.py       # 锁定的路径与参数（单一真源）
│   ├── segment.py      # 任意中文文案 → plan.json（cues + chapters）
│   ├── styles.py       # 6 种自包含 HTML 风格生成器
│   ├── render.py       # 生成 deck.html + 全局 playwright 截各章静帧
│   ├── shot.js         # playwright 截图脚本（env 传参）
│   ├── audio.py        # atempo 保持音高变速 + 重建 durations
│   ├── subtitles.py    # 强制单行 ASS 字幕（抖音风）
│   ├── assemble.py     # 静帧→silent.mp4 + finalize（烧字幕/挂音轨/loudnorm）
│   └── run_job.py      # 全流程编排 + 状态回调
├── server.py           # FastAPI 后端
├── web/                # 前端（主页 + 设置页 + css/js）
├── run.sh              # 一键启动
├── settings.json       # 用户设置（运行时生成）
├── uploads/            # 上传的音色（运行时生成）
└── jobs/<id>/          # 每个任务的中间产物与 final.mp4（运行时生成）
```

TTS 脚本在 `~/index-tts/gen_job.py`（必须在该目录用 uv 跑，含 torch/MPS + IndexTTS 2.0）。

## 锁定参数（不可改）

- **模型**：IndexTTS 2.0；情感 = 与音色参考相同（不传情感参考）。
- **采样**：`temperature=0.1, top_p=0.8, top_k=30, num_beams=1, repetition_penalty=10, length_penalty=0, max_mel_tokens=1200, max_text_tokens_per_segment=120`。
- **视频**：1080×1920 / 30fps / yuv420p / libx264 crf18；段间静音 0.12s（末段不加）。
- **字幕**：PingFang SC 96 加粗、白字+黑描边(Outline6)+阴影2、**强制单行**、MarginV140、逐条按语音时长比例。
- **音频**：`loudnorm I=-14:TP=-1.5:LRA=11`、立体声、aac 192k、faststart。

## 依赖 / 环境（本机已验证）

- IndexTTS 2.0：`~/index-tts`（uv 管理的 venv，含 torch/MPS）。
- ffmpeg（含 libass）：`/Users/Admin/.hermes/bin/ffmpeg`；ffprobe：`/opt/homebrew/bin/ffprobe`。
- 截图：全局 playwright（`npm root -g` 下的 playwright），Node 运行。
- Web：`uv run --with fastapi --with "uvicorn[standard]" --with python-multipart uvicorn`。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/` | 主页 |
| GET  | `/settings` | 设置页 |
| GET  | `/api/settings` | 读设置 |
| POST | `/api/settings` | 写设置（voice_path/speed/style/output_dir） |
| POST | `/api/voice` | 上传音色 wav（multipart） |
| POST | `/api/generate` | `{text}` → `{job_id}`，后台跑全流程 |
| GET  | `/api/jobs/{id}/status` | `{stage,percent,message,done,error,saved_path,video_url}` |
| GET  | `/api/jobs/{id}/preview` | 内嵌预览（inline mp4） |
| POST | `/api/reveal` | `{path}` → `open -R` 在访达中显示 |

## 注意

- 文案可用**空行分段**，每段作为一个视觉章节；无空行则自动按句数归章（目标 6–10 章）。
- 每条字幕/配音最小单位按句末标点切句，过长句再按逗号切，保证单行可读。
- 成片同时留存于 `jobs/<id>/final.mp4`（供预览）与「视频生成路径」（供使用）。
