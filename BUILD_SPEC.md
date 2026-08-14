# 文案→视频 网页应用 · 构建规格（BUILD_SPEC）

把当前已跑通的「文案 → 语音 + 分章节HTML视频 → 合成带单行字幕视频」流水线，做成**本机 localhost 网页应用**。用户输入文案、在设置里配置「音色文件 / 语速 / HTML风格(6选1)」，其余参数**锁死**为下述默认值且不可改；系统产出完整视频并可下载。

## 0. 运行环境（本机，已验证）
- IndexTTS 2.0 在 `~/index-tts`，用 `cd ~/index-tts && uv run python <脚本>` 调用（venv 由 uv 管理，含 torch/MPS）。uv=`/Users/Admin/.hermes/bin/uv`。
- ffmpeg（含 libass）=`/Users/Admin/.hermes/bin/ffmpeg`；ffprobe=`/opt/homebrew/bin/ffprobe`。
- 截图：Google Chrome 无头 或 **Node + 全局 playwright**（更快，复用单浏览器）。全局 playwright：`NODE_PATH="$(npm root -g)" node shot.js`（已验证，`~/.nvm/.../node_modules` 下有 playwright 1.60）。Chrome 路径 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`，`--headless=new --window-size=1080,1920 --force-device-scale-factor=1 --screenshot` 可出精确 1080×1920。
- Python Web 后端用 uv 起：`uv run --with fastapi --with "uvicorn[standard]" --with python-multipart uvicorn server:app`（或建 webapp 自己的 pyproject）。

## 1. 必须复用的已验证脚本（直接读它们拿到确切参数/代码，勿臆测）
- `/Users/Admin/Documents/CC All Project/guizang/pipeline/plan.json` —— 契约格式：`cues[]`(i,text) + `chapters[]`(c,title,headline,sub,cueStart,cueEnd)。
- `/Users/Admin/index-tts/gen20.py` —— **2.0 逐段配音**（确切 infer 调用+参数、重采样、拼 full.wav、写 durations.json）。**照抄它的 infer 参数**。
- `/Users/Admin/Documents/CC All Project/guizang/pipeline/respeed.py` —— **atempo 变速**（保持音高）+ 重建 durations。
- `/Users/Admin/Documents/CC All Project/guizang/pipeline/make_subs.py` —— **单行字幕拆分** ASS 生成（当前版本：强制单行、放不下就拆多条依次显示、按语音时长比例切分、避头、均衡）。
- `/Users/Admin/Documents/CC All Project/guizang/pipeline/build_video.py` —— 章节静帧→片段→拼 silent.mp4（时长由 durations 推导）。
- `/Users/Admin/Documents/CC All Project/guizang/pipeline/finalize.sh` —— 合成：`tpad` 克隆末帧补齐 + 烧 `ass` 字幕 + `loudnorm I=-14` + 立体声 + `faststart` + `-shortest`。
- `/Users/Admin/Documents/CC All Project/guizang/pipeline/html/deck.html` —— **风格①的参考实现与质量基准**：固定 1080×1920 stage、`?chapter=C` 直出该章静止态、`window.showChapter(C)`、底部约 22%(≈424px) 字幕安全区留白、画面内不写口播字幕。

## 2. 锁定默认值（不可被用户修改）
- 模型：**IndexTTS 2.0**（用户实测音色更像本人）。情感=「与音色参考音频相同」→ `emo_audio_prompt=None, emo_vector=None, use_emo_text=False`。
- 采样：`do_sample=True, temperature=0.1, top_p=0.8, top_k=30, num_beams=1, repetition_penalty=10, length_penalty=0, max_mel_tokens=1200, max_text_tokens_per_segment=120`。
- 视频：竖屏 **1080×1920 / 30fps / yuv420p / libx264 crf18**。段间静音 gap=0.12s（末段不加）。
- 字幕：PingFang SC **96px 加粗**、白字+黑描边(Outline6)+阴影2、**强制单行**、MarginV140、MarginL/R30、逐条无缝、按语音时长比例（跟音画同步）。
- 音频：`loudnorm I=-14:TP=-1.5:LRA=11`、立体声、aac 192k、faststart。

## 3. 用户可配置（仅这三项）
1. **音色文件**：上传 wav（存到 job/或 uploads/）；默认 `/Users/Admin/Desktop/剪辑好可上传的视频/刘佑文音色_8s.wav`。语言固定 ZH。
2. **语速**：atempo 系数，范围 0.8–1.3，默认 1.0（对已生成配音做保持音高变速）。
3. **HTML 风格**：6 选 1（见 §5）。
4. **视频生成路径**：本机输出文件夹。生成完成的 mp4 **自动保存**到此文件夹，**不提供下载按钮**。默认 `~/Desktop/文案视频`（不存在则自动创建）。

## 4. 分段/分章（任意文案自动化）
新增 `engine/segment.py`：输入任意中文文案 → 输出 plan.json 同格式。
- **cues（字幕/配音最小单位）**：按句末标点（。！？…；）切句；过长句再按逗号/顿号切；每条建议 ≤ ~24 全角字（保证可读、可单行拆）。保留原文所有字。
- **chapters（视觉章节）**：优先按空行分段成章；无空行则按每 ~4–6 个 cue 归一章，目标 6–10 章。每章：`headline`=该章首个 cue 截断到 ~10 字（或首句关键短语），`sub`=次要短句或空，`cueStart/cueEnd`=覆盖的 cue 序号，`title`=可用"第N章"或空。
- chapter 时长 = 其覆盖 cues 的 slot 之和（与 durations 对齐）。

## 5. 六种 HTML 风格（`engine/styles.py`，每个是「给定 chapters+cues → 自包含 deck.html」的生成器；共用契约：1080×1920、`?chapter=C` 出静止态、`showChapter(C)`、底部≥22% 字幕安全区留白、画面不写口播字幕、纯内联零外网、系统字体）
质量必须达到/超过 deck.html，**不得是通用模板脸**。六种：
1. **暖色电子杂志**（Warm Editorial）——移植现有 deck.html：衬线大标题+暖色渐变+幽灵章节号+kicker。
2. **瑞士国际主义**（Swiss）——无衬线、网格/点阵背景、IKB蓝/柠檬黄/安全橙高亮、左对齐大号数字、强层级。
3. **深色奢华**（Dark Luxury）——近黑底、金/香槟色点缀、优雅衬线、微光晕、高对比。
4. **玻璃拟态**（Glassmorphism）——彩色渐变底 + 毛玻璃卡片 + 模糊 + 圆角、鲜明。
5. **极简黑白**（Minimal Mono）——白底黑粗字、大量留白、单一强调色（红）、克制。
6. **彩色 Bento**（Playful Bento）——明亮色块、bento 分格、圆角、几何装饰、活力。

## 6. 后端（`server.py`，FastAPI）
- `GET /` 主页；`GET /settings` 设置页；静态资源 `/static/*`。
- `GET /api/settings` / `POST /api/settings`：读写设置（存 `webapp/settings.json`：voice_path, speed, style）。
- `POST /api/voice`（multipart）：上传音色 wav → 存 `webapp/uploads/`，返回路径；更新设置。
- `POST /api/generate` `{text}`（用当前设置）→ 建 job（`webapp/jobs/<id>/`），后台线程跑全流程，返回 `{job_id}`。
- `GET /api/jobs/<id>/status`：`{stage, percent, message, done, error, video_url}`（轮询或 SSE 均可）。
- 生成完成后**自动把 final.mp4 保存到设置里的「视频生成路径」文件夹**（文件名=文案前几字的安全 slug + 时间戳，如 `你可能刷到过-20260814-153000.mp4`），**不提供下载**。status 返回已保存的绝对路径 `saved_path`。
- `POST /api/reveal` `{path}`：执行 `open -R <path>` 在访达中定位该文件（供前端"在访达中显示"按钮）。可选 `GET /api/jobs/<id>/preview` 用于页面内预览播放（inline，非附件）。
- 全流程编排 `engine/run_job.py`：segment → (subprocess) TTS 2.0 → atempo 变速 → 生成所选风格 deck.html → 截 9(N)章图 → build silent.mp4 → 单行字幕 ass → finalize → final.mp4。每步回调更新 status。TTS 用 `cd ~/index-tts && uv run python gen_job.py <job_dir> <voice_path>`（把 gen20 泛化成读 job 的 plan.json、参数照旧、输出到 job/audio）。

## 7. 前端（`web/`，简洁有设计感，非模板脸；vanilla JS + fetch）
- 主页：大 textarea 输入文案、当前设置摘要、"生成视频"按钮、进度条/阶段文案、完成后**显示已保存到的绝对路径** + 视频内嵌预览 + "在访达中显示"按钮（**无下载按钮**）。
- 设置页：音色文件上传（显示默认/当前）、语速滑块（0.8–1.3，默认1.0）、6 风格卡片单选（每个有缩略/说明）、**视频生成路径**输入框（默认 `~/Desktop/文案视频`）。保存到后端。
- 交互友好、错误可读。

## 8. 交付与自测
- `webapp/run.sh` 一键启动（uv 起 uvicorn，打印本地地址如 http://127.0.0.1:8000）。
- `webapp/README.md`：如何启动、依赖、注意事项。
- **端到端冒烟自测**：用一段**短文案（2–3 句）** 跑通 `/api/generate`（可直接命令行调 run_job），确认产出可播放的 mp4（ffprobe 验证含视频+音频流、时长>0）、字幕为单行。报告结果。
