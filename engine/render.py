#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成所选风格的 deck.html 并用全局 playwright 截各章静帧 PNG。"""
from __future__ import annotations
import json
import os
import subprocess

from engine import config
from engine.styles import build_deck


def write_deck(job_dir: str, style: str) -> str:
    """读 job 的 plan.json，生成 deck.html 到 job/html/deck.html，返回路径。"""
    plan = json.load(open(os.path.join(job_dir, "plan.json"), encoding="utf-8"))
    chapters = sorted(plan["chapters"], key=lambda c: c["c"])
    html = build_deck(style, chapters)
    html_dir = os.path.join(job_dir, "html")
    os.makedirs(html_dir, exist_ok=True)
    deck = os.path.join(html_dir, "deck.html")
    with open(deck, "w", encoding="utf-8") as f:
        f.write(html)
    return deck


def _npm_root_global() -> str:
    r = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True)
    return r.stdout.strip()


def shoot(job_dir: str, deck_path: str, n_chapters: int) -> str:
    """截 n_chapters 张 chapter_C.png 到 job/video/frames/，返回 frames 目录。"""
    frames = os.path.join(job_dir, "video", "frames")
    os.makedirs(frames, exist_ok=True)
    env = dict(os.environ)
    env["NODE_PATH"] = _npm_root_global()
    env["DECK_PATH"] = deck_path
    env["N"] = str(n_chapters)
    env["OUT_DIR"] = frames
    env["W"] = str(config.WIDTH)
    env["H"] = str(config.HEIGHT)
    r = subprocess.run(["node", config.SHOT_JS], env=env, capture_output=True, text=True)
    if r.returncode != 0 or "ALL_DONE" not in r.stdout:
        raise RuntimeError(f"截图失败: rc={r.returncode} {r.stderr[-400:]}")
    missing = [c for c in range(1, n_chapters + 1)
               if not os.path.isfile(os.path.join(frames, f"chapter_{c}.png"))]
    if missing:
        raise RuntimeError(f"缺少章节截图: {missing}")
    return frames
