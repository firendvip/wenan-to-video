#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全流程编排：segment → TTS(2.0) → atempo 变速 → 生成风格 deck → 截图 → silent.mp4
→ 单行字幕 → finalize → final.mp4。每步更新 job/status.json。"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import config, audio, assemble, render, subtitles, distill


def _status_path(job_dir: str) -> str:
    return os.path.join(job_dir, "status.json")


def set_status(job_dir: str, **kw) -> None:
    p = _status_path(job_dir)
    cur = {}
    if os.path.isfile(p):
        try:
            cur = json.load(open(p, encoding="utf-8"))
        except Exception:
            cur = {}
    cur.update(kw)
    tmp = p + ".tmp"
    json.dump(cur, open(tmp, "w"), ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def get_status(job_dir: str) -> dict:
    p = _status_path(job_dir)
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {"stage": "unknown", "percent": 0, "message": "", "done": False, "error": None}


def _run_tts(job_dir: str, voice_path: str, n_cues: int) -> None:
    """cd ~/index-tts && uv run python gen_job.py <job_dir> <voice> ；流式统计进度。"""
    if not voice_path or not os.path.isfile(voice_path):
        raise RuntimeError(f"音色文件不存在：{voice_path}。请到「设置」重新上传或选择音色文件。")
    cmd = [config.UV, "run", "python", config.GEN_JOB, job_dir, voice_path]
    proc = subprocess.Popen(cmd, cwd=config.INDEXTTS_DIR, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    done = 0
    seen_all = False
    tail: deque[str] = deque(maxlen=20)
    for line in proc.stdout:
        line = line.rstrip()
        tail.append(line)
        if ">> seg_" in line and "done" in line:
            done += 1
            pct = 10 + int(40 * done / max(1, n_cues))
            set_status(job_dir, stage="tts", percent=min(50, pct),
                       message=f"配音中 {done}/{n_cues}")
        elif "ALL_SEGMENTS_DONE" in line:
            seen_all = True
        elif line.startswith(">> model loaded"):
            set_status(job_dir, stage="tts", percent=10, message="模型已加载，开始配音")
    proc.wait()
    if proc.returncode != 0 or not seen_all:
        detail = " | ".join(t for t in list(tail)[-6:] if t)
        raise RuntimeError(f"TTS 失败 rc={proc.returncode}：{detail}")


def run(job_id: str, text: str, voice_path: str, speed: float, style: str,
        output_dir: str | None = None) -> str:
    """执行整条流水线，返回保存到「视频生成路径」的绝对路径。"""
    job_dir = os.path.join(config.JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    output_dir = os.path.expanduser(output_dir or config.DEFAULT_OUTPUT_DIR)
    try:
        set_status(job_dir, stage="segment", percent=2, message="理解并提炼文案…",
                   done=False, error=None, video_url=None)
        plan = distill.make_plan(
            text,
            log=lambda m: set_status(job_dir, stage="segment", percent=4, message=m))
        json.dump(plan, open(os.path.join(job_dir, "plan.json"), "w"),
                  ensure_ascii=False, indent=2)
        n_cues = len(plan["cues"])
        n_ch = len(plan["chapters"])

        set_status(job_dir, stage="tts", percent=6,
                   message=f"加载 TTS 模型…（{n_cues} 句）")
        _run_tts(job_dir, voice_path, n_cues)

        set_status(job_dir, stage="respeed", percent=56, message=f"变速 {speed}×…")
        audio.respeed(job_dir, speed)

        set_status(job_dir, stage="render", percent=64, message="生成画面并截图…")
        deck = render.write_deck(job_dir, style)
        render.shoot(job_dir, deck, n_ch)

        set_status(job_dir, stage="video", percent=80, message="合成画面视频…")
        assemble.build_silent(job_dir)

        set_status(job_dir, stage="subtitles", percent=86, message="生成单行字幕…")
        subtitles.write_ass(job_dir)

        set_status(job_dir, stage="finalize", percent=90, message="烧字幕+挂音轨…")
        out = assemble.finalize(job_dir)

        # 保存到「视频生成路径」：slug + 时间戳
        os.makedirs(output_dir, exist_ok=True)
        fname = f"{config.slugify(text)}-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
        saved_path = os.path.join(output_dir, fname)
        shutil.copy2(out, saved_path)

        set_status(job_dir, stage="done", percent=100, message="完成", done=True,
                   error=None, saved_path=saved_path,
                   video_url=f"/api/jobs/{job_id}/preview")
        return saved_path
    except Exception as e:
        set_status(job_dir, stage="error", done=True,
                   error=f"{type(e).__name__}: {e}", message="出错")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else \
        "你好，这是一次简短的冒烟测试。听说读写，反复练习就会熟。少，即是多。"
    job_id = sys.argv[2] if len(sys.argv) > 2 else f"smoke_{int(time.time())}"
    voice = sys.argv[3] if len(sys.argv) > 3 else config.DEFAULT_VOICE
    speed = float(sys.argv[4]) if len(sys.argv) > 4 else config.SPEED_DEFAULT
    style = sys.argv[5] if len(sys.argv) > 5 else config.STYLE_DEFAULT
    output_dir = sys.argv[6] if len(sys.argv) > 6 else None
    print(f">> run job={job_id} style={style} speed={speed}")
    out = run(job_id, text, voice, speed, style, output_dir)
    print(">> FINAL:", out)
