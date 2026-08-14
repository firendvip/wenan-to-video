#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对 gen_job 产出的 1.0x 配音做保持音高的变速（atempo），重建 full.wav + durations.json。

移植自 pipeline/respeed.py：读 job/audio_src/seg_XX.wav → 写 job/audio/。tempo=1.0 也走一遍
（identity），保证 durations 与最终音频严格对齐。
"""
from __future__ import annotations
import json
import os
import subprocess

from engine import config

GAP = config.GAP
FF = config.FFMPEG


def respeed(job_dir: str, tempo: float) -> str:
    """把 audio_src 变速到 audio/，重建 full.wav + durations.json，返回 durations.json 路径。"""
    tempo = config.clamp_speed(tempo)
    plan = json.load(open(os.path.join(job_dir, "plan.json"), encoding="utf-8"))
    cues = plan["cues"]
    n = len(cues)
    srcd = os.path.join(job_dir, "audio_src")
    adir = os.path.join(job_dir, "audio")
    os.makedirs(adir, exist_ok=True)

    for c in cues:
        i = c["i"]
        src = os.path.join(srcd, f"seg_{i:02d}.wav")
        dst = os.path.join(adir, f"seg_{i:02d}.wav")
        if not os.path.isfile(src):
            raise RuntimeError(f"缺少配音片段 {src}")
        subprocess.run([FF, "-y", "-i", src, "-filter:a", f"atempo={tempo}",
                        "-ar", "44100", "-ac", "1", dst], check=True, capture_output=True)

    sil = os.path.join(adir, "_sil.wav")
    subprocess.run([FF, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-t", str(GAP), "-c:a", "pcm_s16le", sil], check=True, capture_output=True)
    listf = os.path.join(adir, "_concat.txt")
    lines = []
    for idx, c in enumerate(cues):
        lines.append(f"file '{adir}/seg_{c['i']:02d}.wav'")
        if idx < n - 1:
            lines.append(f"file '{sil}'")
    open(listf, "w").write("\n".join(lines) + "\n")
    full = os.path.join(adir, "full.wav")
    subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", listf,
                    "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", full],
                   check=True, capture_output=True)

    durs = [config.ffprobe_duration(os.path.join(adir, f"seg_{c['i']:02d}.wav")) for c in cues]
    out_cues, start = [], 0.0
    for idx, c in enumerate(cues):
        d = round(durs[idx], 3)
        slot = round(d + (GAP if idx < n - 1 else 0.0), 3)
        out_cues.append({"i": c["i"], "text": c["text"], "file": f"seg_{c['i']:02d}.wav",
                         "dur": d, "slot": slot, "start": round(start, 3)})
        start = round(start + slot, 3)
    total = round(config.ffprobe_duration(full), 3)
    dpath = os.path.join(adir, "durations.json")
    json.dump({"gap": GAP, "total": total, "cues": out_cues},
              open(dpath, "w"), ensure_ascii=False, indent=2)
    os.remove(sil)
    os.remove(listf)
    return dpath
