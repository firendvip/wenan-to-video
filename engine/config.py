#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""集中所有锁定的路径与参数（BUILD_SPEC §2 锁定默认值）。"""
import os

# ---- 绝对路径（本机已验证）----
HERE = os.path.dirname(os.path.abspath(__file__))          # .../webapp/engine
WEBAPP_DIR = os.path.dirname(HERE)                          # .../webapp
JOBS_DIR = os.path.join(WEBAPP_DIR, "jobs")
UPLOADS_DIR = os.path.join(WEBAPP_DIR, "uploads")
SETTINGS_PATH = os.path.join(WEBAPP_DIR, "settings.json")

UV = "/Users/Admin/.hermes/bin/uv"
FFMPEG = "/Users/Admin/.hermes/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"
SHOT_JS = os.path.join(HERE, "shot.js")

INDEXTTS_DIR = "/Users/Admin/index-tts"
GEN_JOB = "gen_job.py"                                      # 相对 INDEXTTS_DIR 执行

CLAUDE_BIN = "/Users/Admin/.local/bin/claude"              # 提炼备选（本机 claude CLI）
PROMPT_PATH = os.path.join(WEBAPP_DIR, "prompts", "distill_plan.md")


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
