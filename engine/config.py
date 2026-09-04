#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""集中所有锁定的路径与参数（BUILD_SPEC §2 锁定默认值）。"""
import os
import shutil


def _tool(env: str, name: str, *candidates: str) -> str:
    """解析外部可执行文件路径，保证跨机可移植：
    环境变量 > 已存在的候选路径 > PATH(which) > 裸名(留给 PATH 运行时解析)。"""
    v = os.environ.get(env)
    if v:
        return v
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    w = shutil.which(name)
    if w:
        return w
    return name


# ---- 路径（相对定位，不再硬编码某台机器）----
HERE = os.path.dirname(os.path.abspath(__file__))          # .../webapp/engine
WEBAPP_DIR = os.path.dirname(HERE)                          # .../webapp
JOBS_DIR = os.path.join(WEBAPP_DIR, "jobs")
UPLOADS_DIR = os.path.join(WEBAPP_DIR, "uploads")
SETTINGS_PATH = os.path.join(WEBAPP_DIR, "settings.json")

# 外部可执行文件：可用同名大写环境变量覆盖（UV_BIN / FFMPEG_BIN / FFPROBE_BIN / CLAUDE_BIN）
UV = _tool("UV_BIN", "uv",
           os.path.expanduser("~/.hermes/bin/uv"),
           os.path.expanduser("~/.local/bin/uv"))
FFMPEG = _tool("FFMPEG_BIN", "ffmpeg",
               os.path.expanduser("~/.hermes/bin/ffmpeg"),
               "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg")
FFPROBE = _tool("FFPROBE_BIN", "ffprobe",
                "/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe")
SHOT_JS = os.path.join(HERE, "shot.js")

# IndexTTS 安装目录：环境变量 INDEXTTS_DIR 覆盖，否则默认 ~/index-tts
INDEXTTS_DIR = os.environ.get("INDEXTTS_DIR") or os.path.expanduser("~/index-tts")
GEN_JOB = "gen_job.py"                                      # 相对 INDEXTTS_DIR 执行

CLAUDE_BIN = _tool("CLAUDE_BIN", "claude",
                   os.path.expanduser("~/.local/bin/claude"))   # 提炼备选（本机 claude CLI）
PROMPT_PATH = os.path.join(WEBAPP_DIR, "prompts", "distill_plan.md")

# ---- 配音引擎 ----
# indextts：本机 IndexTTS 2.0 声音克隆；edge：微软 Edge TTS（免费在线，需联网）
EDGE_TTS = _tool("EDGE_TTS_BIN", "edge-tts", os.path.expanduser("~/.local/bin/edge-tts"))
VOICE_ENGINE_DEFAULT = os.environ.get("VOICE_ENGINE", "edge")
EDGE_VOICE_DEFAULT = "zh-CN-XiaoxiaoNeural"   # 晓晓 · 亲和女声

# ---- CosyVoice3 声音克隆（我的声音）----
COSY_VENV = os.environ.get("COSY_VENV", os.path.expanduser("~/CosyVoice/.venv/bin/python"))
COSY_DIR = os.environ.get("COSY_DIR", os.path.expanduser("~/CosyVoice"))
COSY_REF = os.environ.get("COSY_REF", os.path.expanduser("~/voice-rec/REF_FINAL3.wav"))
COSY_RT = os.environ.get("COSY_RT", "春天的清晨，山谷里飘着薄雾，风从林间穿过，两只喜鹊落在枝头，叫声清脆，老人推开木窗，深深吸了一口气。")
BREATH_ATT = float(os.environ.get("BREATH_ATT", "0.10"))   # 去换气衰减(0.10=-20dB)
SLOW_FACTOR = float(os.environ.get("SLOW_FACTOR", "0.75")) # 稿件「放慢」句的额外倍率



def _load_llm() -> dict:
    """本地 LLM 配置（密钥不写进源码）：webapp/llm.json 或环境变量。"""
    import json as _json
    cfg = {}
    p = os.path.join(WEBAPP_DIR, "llm.json")
    if os.path.isfile(p):
        try:
            cfg = _json.load(open(p, encoding="utf-8"))
        except Exception:
            cfg = {}
    return cfg


_LLM = _load_llm()
# 提炼首选：DeepSeek（OpenAI 兼容）
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY") or _LLM.get("deepseek_api_key", "")
DEEPSEEK_BASE = (_LLM.get("deepseek_base") or "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = _LLM.get("deepseek_model") or "deepseek-chat"

DEFAULT_VOICE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "default_voice.wav")
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/Desktop/文案视频")   # 视频生成路径（不存在自动创建）

# ---- 锁定默认值 ----
GAP = 0.12                     # 段间静音（末段不加）

# 屏幕方向：当前仅开放竖屏；横屏在前端可见但禁用、暂不开发
ORIENTATIONS = {"portrait": "竖屏", "landscape": "横屏"}
ORIENTATION_ENABLED = {"portrait": True, "landscape": False}
ORIENTATION_DEFAULT = "portrait"

WIDTH = 1080                   # 竖屏（当前唯一开放方向）
HEIGHT = 1920
FPS = 30

SPEED_MIN = 0.8
SPEED_MAX = 1.3
SPEED_DEFAULT = 1.05

# 单一固定 HTML 风格（参照 lIxflkxP6BA7cfH5pnBI8g.mp4：暖色电子杂志 · 竖屏）
STYLES = {"magazine": "电子杂志 · 竖屏"}
STYLE_DEFAULT = "magazine"

# ---- 主题（影响画面模板与字幕配色）----
THEME = os.environ.get("THEME", "night")   # night 暗色/睡前（默认） | day 暖色亮版
# ASS 颜色 &HAABBGGRR。night：暖白字(#E7DAC6) + 柔和暗描边，夜里不刺眼
SUB_THEME = {
    "night": {"primary": "&H00C6DAE7", "outline_col": "&H00100A05",
              "back": "&H50000000", "outline": 4, "shadow": 3},
    "day":   {"primary": "&H00FFFFFF", "outline_col": "&H00000000",
              "back": "&H64000000", "outline": 6, "shadow": 2},
}


def ffprobe_duration(path: str) -> float:
    import subprocess
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def slugify(text: str, maxlen: int = 12) -> str:
    """取文案前几字生成安全文件名前缀：保留中文/字母/数字，其余转 -。"""
    import re
    s = (text or "").strip().replace("\n", " ")
    kept = []
    for ch in s:
        if ch.isalnum() or ('一' <= ch <= '鿿'):
            kept.append(ch)
        elif ch in " ，,。.、":
            kept.append("-")
        if len(kept) >= maxlen:
            break
    slug = re.sub(r"-{2,}", "-", "".join(kept)).strip("-")
    return slug or "video"


def clamp_speed(v) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return SPEED_DEFAULT
    return max(SPEED_MIN, min(SPEED_MAX, v))
