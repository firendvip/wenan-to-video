#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""章节静帧 → silent.mp4（时长由 durations 推导），再合成 final.mp4。

- build_silent 移植自 pipeline/build_video.py
- finalize 移植自 pipeline/finalize.sh：tpad 克隆末帧 1.5s + 烧 ass + loudnorm I=-14 +
  立体声 + aac192k + faststart + -shortest。
"""
from __future__ import annotations
import json
import os
import subprocess

from engine import config

FF = config.FFMPEG


def _run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg 失败: " + " ".join(cmd[:6]) + " ...\n"
                           + r.stderr.decode(errors="ignore")[-500:])


def build_silent(job_dir: str) -> str:
    """章节静帧按各章时长转片段并拼成 job/video/silent.mp4。"""
    plan = json.load(open(os.path.join(job_dir, "plan.json"), encoding="utf-8"))
    dur = json.load(open(os.path.join(job_dir, "audio", "durations.json"), encoding="utf-8"))
    by_i = {c["i"]: c for c in dur["cues"]}
    fdir = os.path.join(job_dir, "video", "frames")
    cdir = os.path.join(job_dir, "video", "clips")
    os.makedirs(cdir, exist_ok=True)

    chapters = sorted(plan["chapters"], key=lambda c: c["c"])
    listfile = os.path.join(cdir, "concat.txt")
    lines = []
    for ch in chapters:
        c = ch["c"]
        start = float(by_i[ch["cueStart"]]["start"])
        last = by_i[ch["cueEnd"]]
        end = float(last["start"]) + float(last["slot"])
        d = round(end - start, 3)
        png = os.path.join(fdir, f"chapter_{c}.png")
        clip = os.path.join(cdir, f"clip_{c}.mp4")
        if not os.path.isfile(png):
            raise RuntimeError(f"缺少 {png}")
        _run([FF, "-y", "-loglevel", "error", "-loop", "1", "-t", f"{d}", "-i", png,
              "-vf", f"scale={config.WIDTH}:{config.HEIGHT},fps={config.FPS},format=yuv420p",
              "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", clip])
        lines.append(f"file '{clip}'")

    with open(listfile, "w") as f:
        f.write("\n".join(lines) + "\n")
    out = os.path.join(job_dir, "video", "silent.mp4")
    _run([FF, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
          "-i", listfile, "-c", "copy", out])
    return out


def finalize(job_dir: str) -> str:
    """silent.mp4 + full.wav + subs.ass → job/final.mp4。"""
    silent = os.path.join(job_dir, "video", "silent.mp4")
    full = os.path.join(job_dir, "audio", "full.wav")
    ass = os.path.join(job_dir, "final", "subs.ass")
    for p in (silent, full, ass):
        if not os.path.isfile(p):
            raise RuntimeError(f"缺少 {p}")
    out = os.path.join(job_dir, "final.mp4")
    # ass 路径含空格/中文，交给 ffmpeg 时用相对目录避免转义问题：切到 final 目录引用相对名
    _run([FF, "-y", "-loglevel", "error", "-i", silent, "-i", full,
          "-vf", f"tpad=stop_mode=clone:stop_duration=1.5,ass={_ass_arg(ass)}",
          "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
          "-map", "0:v:0", "-map", "1:a:0",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", "-r", "30",
          "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "44100",
          "-movflags", "+faststart", "-shortest", out])
    return out


def _ass_arg(path: str) -> str:
    """转义 ass 滤镜路径中的特殊字符（: 与 \\ 与 ')。"""
    p = path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return p
