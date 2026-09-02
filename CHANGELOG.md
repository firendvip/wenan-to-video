# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/) 与 [SemVer](https://semver.org/lang/zh-CN/)。

## [0.2.2] - 2026-09-02

### Fixed
- Edge TTS 长稿稳定性：逐句生成支持**断点续跑**（跳过已存在分段），失败**退避重试 5 次**，避免偶发网络/限流导致整条中断。

## [0.2.1] - 2026-09-01

### Fixed
- 配音与字幕不再朗读/显示 Markdown 标记：`tts_edge.strip_md` 去除 `* \` _ # ~`，正文行内加粗（`**...**`）等只保留文字。

## [0.2.0] - 2026-09-01

### Added
- 微软 Edge TTS 配音后端（`engine/tts_edge.py`）：免费在线，默认音色 `zh-CN-XiaoxiaoNeural`（晓晓·亲和女声）；逐句生成 `audio_src/seg_XX.wav`，复用现有变速/合成链路；纯标点/省略号自动转静音；长跑重试 3 次。
- 配音引擎可选：`config.VOICE_ENGINE_DEFAULT`（`edge` / `indextts`），`run_job.run` 增加 `voice_engine` / `voice_name` 分支。
- 字幕主题化：`config.SUB_THEME`（`night` / `day`），暗色下为暖白柔影单行字幕。

### Changed
- **画面默认主题改为「暗色 / 睡前 v2」**（`engine/styles.py`）：暖调近黑背景 + 边缘暗角 + 低蓝光低对比，适合夜间/助眠观看。
- 默认配音引擎切换为 `edge`（微软晓晓）。

## [0.1.0] - 2026-09-01

### Added
- 文案→竖屏字幕视频本地 Web 应用初始版本：DeepSeek 提炼主旨 → IndexTTS 配音 → HTML 模板截帧 → ffmpeg 合成；任务列表（单并发/可取消）+ 设置弹窗。
- 可移植化：外部工具路径按 `环境变量 > 候选 > PATH` 解析，去除硬编码机器路径。
