#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微软 Edge TTS（免费在线）配音后端。

为每个 cue 生成 `job/audio_src/seg_XX.wav`（1.0x，44100/mono），与 IndexTTS 路径产物一致，
下游 `audio.respeed` 负责变速。纯标点/省略号（不可朗读）自动替换为一小段静音，避免 TTS 报错。
需联网；音色默认 zh-CN-XiaoxiaoNeural（晓晓·亲和女声）。
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import time

from engine import config

_MD = re.compile(r"[*`_#~]+")


def strip_md(text: str) -> str:
    """去除 Markdown 标记符（* ` _ # ~），保留文字；不朗读符号。"""
    return re.sub(r"\s{2,}", " ", _MD.sub("", text or "")).strip()


def _speakable(text: str) -> bool:
    """含中文或字母数字才算可朗读；纯标点/省略号返回 False。"""
    for ch in text:
        if ch.isalnum() or ("一" <= ch <= "鿿"):
            return True
    return False


def _silence(path: str, seconds: float = 0.45) -> None:
    subprocess.run([config.FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=mono", "-t", f"{seconds}",
                    "-c:a", "pcm_s16le", path], check=True, capture_output=True)


def synth(job_dir: str, voice: str | None = None, rate: str = "+0%", log=None) -> str:
    """按 plan.json 的 cues 逐句生成 audio_src/seg_XX.wav，返回 audio_src 目录。"""
    voice = voice or config.EDGE_VOICE_DEFAULT
    plan = json.load(open(os.path.join(job_dir, "plan.json"), encoding="utf-8"))
    cues = plan["cues"]
    srcd = os.path.join(job_dir, "audio_src")
    os.makedirs(srcd, exist_ok=True)
    n = len(cues)
    for k, c in enumerate(cues, 1):
        i = c["i"]
        text = strip_md((c.get("text") or "").replace("\n", " "))
        wav = os.path.join(srcd, f"seg_{i:02d}.wav")
        if os.path.isfile(wav) and os.path.getsize(wav) > 0:
            continue   # 断点续跑：已生成的分段跳过
        if not _speakable(text):
            _silence(wav)
        else:
            mp3 = os.path.join(srcd, f"seg_{i:02d}.mp3")
            cmd = [config.EDGE_TTS, "--voice", voice, "--rate", rate,
                   "--text", text, "--write-media", mp3]
            last = ""
            for attempt in range(5):   # 长跑防偶发网络失败/限流：退避重试
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if r.returncode == 0 and os.path.isfile(mp3) and os.path.getsize(mp3) > 0:
                    break
                last = (r.stderr or r.stdout or "")[-160:]
                time.sleep(1.5 * (attempt + 1))
            else:
                raise RuntimeError(f"edge-tts 失败 seg {i}（重试 5 次）: {last}")
            subprocess.run([config.FFMPEG, "-y", "-loglevel", "error", "-i", mp3,
                            "-ar", "44100", "-ac", "1", wav],
                           check=True, capture_output=True)
            os.remove(mp3)
        if log and (k % 5 == 0 or k == n):
            log(f"配音中 {k}/{n}")
    return srcd
