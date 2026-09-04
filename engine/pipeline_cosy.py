#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键流水线：口播稿 Markdown → 用「我的声音」朗读的竖屏成片。

    python engine/pipeline_cosy.py <口播稿.md> [job_id] [--speed 1.1] [--reuse <已有job>]

步骤：解析稿件(停顿/放慢/分章) → CosyVoice3 逐句克隆 → 音轨装配(去换气+精确停顿+去沙哑)
      → 暗色V2画面 → 暖白单行字幕 → 合成并保存到「视频生成路径」。
`--reuse` 可复用已生成的逐句配音（同一稿件重出片时免去重跑 TTS）。
"""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import config, script_parse, render, assemble, subtitles   # noqa: E402


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def _venv_run(script: str, *args: str) -> None:
    """在 CosyVoice venv 下运行（该环境才有 torch/librosa/soundfile）。"""
    env = dict(os.environ)
    env['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
    env.setdefault('BREATH_ATT', str(config.BREATH_ATT))
    env.setdefault('COSY_REF', config.COSY_REF)
    env.setdefault('COSY_RT', config.COSY_RT)
    r = subprocess.run([config.COSY_VENV, os.path.join(config.HERE, script), *args],
                       cwd=config.COSY_DIR, env=env)
    if r.returncode != 0:
        raise RuntimeError(f'{script} 失败 rc={r.returncode}')


def run(md_path: str, job_id: str | None = None, speed: float = 1.1,
        reuse: str | None = None, output_dir: str | None = None) -> str:
    job_id = job_id or f"cosy_{time.strftime('%Y%m%d-%H%M%S')}"
    job = os.path.join(config.JOBS_DIR, job_id)
    os.makedirs(job, exist_ok=True)

    log('解析稿件…')
    plan = script_parse.write_plan(job, md_path, log=log)
    n_ch = len(plan['chapters'])
    log(f"{len(plan['cues'])} 句 / {n_ch} 章")

    src = job
    if reuse:                                   # 复用已有逐句配音
        src_dir = reuse if os.path.isabs(reuse) else os.path.join(config.JOBS_DIR, reuse)
        os.makedirs(os.path.join(job, 'audio_src'), exist_ok=True)
        for f in os.listdir(os.path.join(src_dir, 'audio_src')):
            if f.endswith('.wav'):
                dst = os.path.join(job, 'audio_src', f)
                if not os.path.exists(dst):
                    shutil.copy2(os.path.join(src_dir, 'audio_src', f), dst)
        log(f'复用配音 {len(os.listdir(os.path.join(job, "audio_src")))} 段')
    log('CosyVoice 逐句克隆（断点续跑）…')
    _venv_run('cosy_worker.py', job)

    log('装配音轨（去换气 + 精确停顿 + 去沙哑）…')
    _venv_run('audio_build.py', src, job, str(speed))

    log('生成暗色画面并截图…')
    deck = render.write_deck(job, config.STYLE_DEFAULT)
    render.shoot(job, deck, n_ch)
    log('合成画面视频…'); assemble.build_silent(job)
    log('生成暖白单行字幕…'); subtitles.write_ass(job)
    log('烧字幕 + 挂音轨…'); out = assemble.finalize(job)

    out_dir = os.path.expanduser(output_dir or config.DEFAULT_OUTPUT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(md_path))[0]
    saved = os.path.join(out_dir, f"{base}-{time.strftime('%Y%m%d-%H%M%S')}.mp4")
    shutil.copy2(out, saved)
    log(f'完成 {config.ffprobe_duration(out)/60:.1f} 分钟 -> {saved}')
    return saved


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('md')
    ap.add_argument('job_id', nargs='?')
    ap.add_argument('--speed', type=float, default=1.1)
    ap.add_argument('--reuse')
    ap.add_argument('--out')
    a = ap.parse_args()
    run(a.md, a.job_id, a.speed, a.reuse, a.out)
