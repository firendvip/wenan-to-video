#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""音轨装配（在 CosyVoice venv 下运行，需 numpy/soundfile）。

固化流程（顺序不可调换，否则停顿会超标或字幕会失步）：
  1) 逐句去换气（衰减 BREATH_ATT；先做，避免气声在拼接后与停顿合并成超长静音）
  2) 句内超长静音压到 INNER_CAP
  3) 帧 RMS 裁掉首尾（含低电平衰减尾巴）
  4) 仅对语音变速（稿件「放慢」标记不做处理：实测放慢不自然，以自然听感为先）
  5) 按 plan 的 lead 精确插入停顿（构造保证 ≤ CAP，无需事后压缩 → 不会失步）
  6) 全局去沙哑 EQ + 响度
产物：<job>/audio/full.wav 与 <job>/audio/durations.json（供字幕与画面对齐）

用法: audio_build.py <src_job> <dst_job> [speed]
环境: BREATH_ATT(默认0.10=-20dB)
"""
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

SR = 24000
CAP = 1.0            # 停顿上限（秒）
INNER_CAP = 0.60     # 句内静音上限
TRIM_THR = 0.006     # 帧 RMS 裁切阈值
EQ = ("highpass=f=70,equalizer=f=250:t=q:w=1.0:g=2.0,equalizer=f=900:t=q:w=1.2:g=1.5,"
      "equalizer=f=3800:t=q:w=1.4:g=-4,equalizer=f=5200:t=q:w=1.2:g=-4.5,"
      "equalizer=f=7000:t=q:w=1.0:g=-3,loudnorm=I=-19:TP=-2.5")


def debreath(y, att, sr=SR):
    """检出换气段并衰减：−48<峰值<−22dB、频谱平坦度>0.05、2kHz以上占比>0.35、时长≥80ms。"""
    H = int(0.02 * sr); n = len(y) // H
    if n == 0:
        return y, 0
    f = np.fft.rfftfreq(H, 1 / sr); win = np.hanning(H); cand = []
    for i in range(n):
        x = y[i * H:(i + 1) * H]
        if len(x) < H:
            break
        pk = 20 * np.log10(np.abs(x).max() + 1e-12)
        S = np.abs(np.fft.rfft(x * win)) + 1e-12
        flat = np.exp(np.mean(np.log(S))) / np.mean(S)
        hf = (S[f > 2000] ** 2).sum() / ((S ** 2).sum() + 1e-12)
        if -48 < pk < -22 and flat > 0.05 and hf > 0.35:
            cand.append(i)
    mg, last = [], -9
    for i in cand:
        if i - last > 5:
            mg.append([i, i])
        else:
            mg[-1][1] = i
        last = i
    mg = [m for m in mg if (m[1] - m[0] + 1) * 0.02 >= 0.08]
    g = np.ones(len(y), np.float32); r = int(0.012 * sr)
    for a, b in mg:
        s = a * H; e = min(len(y), (b + 1) * H)
        w = np.full(e - s, att, np.float32)
        if e - s > 2 * r:
            w[:r] = np.linspace(1, att, r); w[-r:] = np.linspace(att, 1, r)
        g[s:e] = w
    return y * g, len(mg)


def cap_silence(y, cap_s=INNER_CAP, thr=TRIM_THR, sr=SR):
    """句内超长静音压到上限（在裁切/拼接前做，长度变化不影响时间轴）。"""
    H = int(0.01 * sr); n = len(y) // H
    if n == 0:
        return y
    loud = np.array([np.abs(y[i * H:(i + 1) * H]).max() > thr for i in range(n)])
    keep, i, cf = [], 0, int(cap_s / 0.01)
    while i < n:
        j = i
        while j < n and loud[j] == loud[i]:
            j += 1
        keep.append((i, i + cf) if (not loud[i] and j - i > cf) else (i, j))
        i = j
    return np.concatenate([y[a * H:b * H] for a, b in keep]) if keep else y


def trim(y, thr=TRIM_THR, margin=0.015, sr=SR):
    """按 10ms 帧 RMS 裁掉首尾，避免低电平尾巴与设计停顿叠加。"""
    H = int(0.01 * sr); n = len(y) // H
    if n == 0:
        return y
    rms = np.array([np.sqrt(np.mean(y[i * H:(i + 1) * H] ** 2) + 1e-12) for i in range(n)])
    idx = np.where(rms > thr)[0]
    if len(idx) == 0:
        return y[:0]
    m = int(margin / 0.01)
    return y[max(0, idx[0] - m) * H: min(n, idx[-1] + 1 + m) * H]


def build(src_job, dst_job, speed=1.1, att=0.10, ffmpeg=None, log=print):
    ffmpeg = ffmpeg or os.environ.get('FFMPEG_BIN', '/Users/Admin/.hermes/bin/ffmpeg')
    plan = json.load(open(os.path.join(src_job, 'plan.json'), encoding='utf-8'))
    cues = plan['cues']
    os.makedirs(os.path.join(dst_job, 'audio'), exist_ok=True)
    t1, t2 = os.path.join(dst_job, '_t.wav'), os.path.join(dst_job, '_t2.wav')

    speech, nbr = [], 0
    for c in cues:
        y, sr = sf.read(os.path.join(src_job, 'audio_src', f"seg_{c['i']:02d}.wav"))
        if y.ndim > 1:
            y = y.mean(axis=1)
        y = y.astype(np.float32)
        y, k = debreath(y, att); nbr += k          # 1
        y = cap_silence(y)                          # 2
        y = trim(y)                                 # 3
        sp = speed                                  # 4（不做逐句放慢）
        if abs(sp - 1.0) > 1e-6 and len(y):
            sf.write(t1, y, SR)
            subprocess.run([ffmpeg, '-y', '-v', 'error', '-i', t1, '-filter:a', f'atempo={sp}',
                            '-ar', str(SR), '-ac', '1', t2], check=True)
            y = sf.read(t2)[0].astype(np.float32)
        speech.append(y)

    out, durs, cursor = [], [], 0.0                 # 5
    lead0 = min(float(cues[0].get('lead', 1.0)), CAP)
    out.append(np.zeros(int(lead0 * SR), np.float32)); cursor += lead0
    for k, c in enumerate(cues):
        y = speech[k]; d = len(y) / SR
        gap = min(float(cues[k + 1].get('lead', 0.4)), CAP) if k < len(cues) - 1 else 0.30
        out += [y, np.zeros(int(gap * SR), np.float32)]
        durs.append({'i': c['i'], 'text': c['text'], 'file': f"seg_{c['i']:02d}.wav",
                     'dur': round(d, 3), 'slot': round(d + gap, 3), 'start': round(cursor, 3)})
        cursor += d + gap

    raw = os.path.join(dst_job, 'audio', '_raw.wav')
    sf.write(raw, np.concatenate(out), SR)
    pre = sf.info(raw).duration
    full = os.path.join(dst_job, 'audio', 'full.wav')
    subprocess.run([ffmpeg, '-y', '-v', 'error', '-i', raw, '-af', EQ,   # 6
                    '-ar', str(SR), '-ac', '1', full], check=True)
    post = sf.info(full).duration
    json.dump({'gap': 0.4, 'total': round(post, 3), 'cues': durs},
              open(os.path.join(dst_job, 'audio', 'durations.json'), 'w'),
              ensure_ascii=False, indent=2)
    for f in (t1, t2, raw):
        if os.path.exists(f):
            os.remove(f)
    log(f'>> {len(cues)}句 速度{speed} 去换气{nbr}处 '
        f'时长{post/60:.1f}分 漂移{abs(post-pre)*1000:.0f}ms')
    return full


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2],
          speed=float(sys.argv[3]) if len(sys.argv) > 3 else 1.1,
          att=float(os.environ.get('BREATH_ATT', '0.10')))
