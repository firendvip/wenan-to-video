#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""音轨装配（在 CosyVoice venv 下运行，需 numpy/soundfile）。

固化流程（顺序不可调换，否则停顿会超标或字幕会失步）：
  1) 逐句去换气：句中保守衰减（不误伤齿音）+ 句首尾直接裁掉（换气都在这里）
  2) 句内超长静音压到 INNER_CAP
  3) 帧 RMS 裁掉首尾（含低电平衰减尾巴）
  4) 仅对语音变速（稿件「放慢」标记不做处理：实测放慢不自然，以自然听感为先）
  5) 按 plan 的 lead 精确插入停顿（构造保证 ≤ CAP，无需事后压缩 → 不会失步）
  5.5) 逐句自适应去沙哑：对 3–6kHz/500–2kHz 能量比偏高的句子，按超出量额外衰减该频段
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
HOARSE_BASE = 0.50   # 沙哑基准；超出者按比例额外削 3–6kHz（上限 -4dB）
# 换气检出参数：上限从 -22dB 放宽到 -16dB（否则较响的换气漏检）；
# 最短时长从 80ms 提到 120ms，用「长而噪」区分换气与清辅音(s/sh/f，通常<100ms)
# 句中换气：保守阈值，避免把 s/sh/x 等齿音当换气压掉（实测句中"噪声段"绝大多数是辅音）
BR_PK_LO, BR_PK_HI, BR_FLAT, BR_HF, BR_MIN = -48.0, -22.0, 0.05, 0.35, 0.12
# 句首尾换气：真正的换气都在这里，直接裁掉。守卫：时长≥EDGE_MIN 且能量远低于本句语音
EDGE_HEAD, EDGE_TAIL, EDGE_MIN, EDGE_REL = 0.60, 0.80, 0.10, 0.30
DIP_MIN = 0.04       # 换气与词之间的静音缝（区分换气 vs 句首清辅音）
HEAD_LONG = 0.15     # 句首噪声段长于此判为吸气（句首清辅音很少 ≥150ms）
EQ = ("highpass=f=70,equalizer=f=250:t=q:w=1.0:g=2.0,equalizer=f=900:t=q:w=1.2:g=1.5,"
      "equalizer=f=3800:t=q:w=1.4:g=-4,equalizer=f=5200:t=q:w=1.2:g=-4.5,"
      "equalizer=f=7000:t=q:w=1.0:g=-3,loudnorm=I=-19:TP=-2.5")


def debreath(y, att, sr=SR):
    """检出换气段并衰减：BR_PK_LO<峰值<BR_PK_HI、平坦度>BR_FLAT、2kHz以上占比>BR_HF、
    时长≥BR_MIN（长而噪 → 换气；短而噪 → 清辅音，不动）。"""
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
        if BR_PK_LO < pk < BR_PK_HI and flat > BR_FLAT and hf > BR_HF:
            cand.append(i)
    mg, last = [], -9
    for i in cand:
        if i - last > 5:
            mg.append([i, i])
        else:
            mg[-1][1] = i
        last = i
    mg = [m for m in mg if (m[1] - m[0] + 1) * 0.02 >= BR_MIN]
    g = np.ones(len(y), np.float32); r = int(0.012 * sr)
    for a, b in mg:
        s = a * H; e = min(len(y), (b + 1) * H)
        w = np.full(e - s, att, np.float32)
        if e - s > 2 * r:
            w[:r] = np.linspace(1, att, r); w[-r:] = np.linspace(att, 1, r)
        g[s:e] = w
    return y * g, len(mg)


def hoarse_ratio(y, sr=SR):
    """沙哑度：3–6kHz 能量 / 500–2kHz 能量，越大越沙哑。"""
    if len(y) < 2048:
        return 0.0
    S = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    f = np.fft.rfftfreq(len(y), 1 / sr)
    return float(S[(f >= 3000) & (f <= 6000)].sum() / (S[(f >= 500) & (f <= 2000)].sum() + 1e-12))


def strip_edge_breath(y, sr=SR):
    """裁掉句首吸气 / 句尾换气。

    判据（实测得出）：换气与词之间存在一个**静音缝**（≥DIP_MIN），而声母 s/sh/x 与词连在一起、
    中间没有缝。因此只要"边缘噪声段 + 缝"成对出现就判为换气，直接裁掉——这样既能清掉较响的
    换气（−11dB 级也能切），又不会误伤句首/句尾的清辅音。
    """
    H = int(0.02 * sr); n = len(y) // H
    if n < 5:
        return y
    win = np.hanning(H); f = np.fft.rfftfreq(H, 1 / sr)
    rms = np.zeros(n); noisy = np.zeros(n, bool)
    for i in range(n):
        x = y[i * H:(i + 1) * H]
        if len(x) < H:
            break
        rms[i] = np.sqrt(np.mean(x ** 2) + 1e-12)
        S = np.abs(np.fft.rfft(x * win)) + 1e-12
        flat = np.exp(np.mean(np.log(S))) / np.mean(S)
        hf = (S[f > 2000] ** 2).sum() / ((S ** 2).sum() + 1e-12)
        noisy[i] = flat > BR_FLAT and hf > BR_HF
    quiet = rms <= TRIM_THR
    minf = max(1, int(EDGE_MIN / 0.02))
    dipf = max(1, int(DIP_MIN / 0.02))

    # 句首：吸气 → 缝 → 说话
    j = 0
    head_lim = int(EDGE_HEAD / 0.02)
    while j < min(n, head_lim) and (noisy[j] or quiet[j]):
        j += 1
    start = 0
    if j >= minf:
        run = quiet[:j]
        has_dip = any(run[k:k + dipf].all() for k in range(max(1, j - dipf + 1)))
        # 有缝 → 换气；或够长（≥HEAD_LONG）→ 吸气（句首清辅音很少这么长）；或明显更轻
        voiced0 = rms[rms > TRIM_THR]
        ref0 = float(np.median(voiced0)) * EDGE_REL if len(voiced0) else 1.0
        if has_dip or j >= int(HEAD_LONG / 0.02) or rms[:j].max() < ref0:
            start = j

    # 句尾：说话 → 缝 → 换气
    i = n - 1
    tail_lim = n - int(EDGE_TAIL / 0.02)
    while i >= max(0, tail_lim) and (noisy[i] or quiet[i]):
        i -= 1
    end = n
    if (n - 1 - i) >= minf:
        run = quiet[i + 1:]
        has_dip = any(run[k:k + dipf].all() for k in range(max(1, len(run) - dipf + 1)))
        voiced = rms[rms > TRIM_THR]
        ref = float(np.median(voiced)) * EDGE_REL if len(voiced) else 1.0
        if has_dip or rms[i + 1:].max() < ref:
            end = i + 1

    return y[start * H:end * H] if end > start else y


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

    speech, nbr, nadapt, nedge = [], 0, 0, 0
    for c in cues:
        y, sr = sf.read(os.path.join(src_job, 'audio_src', f"seg_{c['i']:02d}.wav"))
        if y.ndim > 1:
            y = y.mean(axis=1)
        y = y.astype(np.float32)
        y, k = debreath(y, att); nbr += k          # 1a 句中换气（保守）
        y0 = len(y); y = strip_edge_breath(y)       # 1b 句首尾换气：直接裁掉
        nedge += 1 if len(y) < y0 else 0
        y = cap_silence(y)                          # 2
        y = trim(y)                                 # 3
        # 5.5) 逐句自适应去沙哑：超出基准越多，3–6kHz 削得越多（上限 -4dB）
        hr = hoarse_ratio(y)
        extra = 0.0
        if hr > HOARSE_BASE:
            extra = -min(4.0, 4.0 * (hr / HOARSE_BASE - 1.0))
            nadapt += 1
        af = []
        sp = speed                                  # 4（不做逐句放慢）
        if abs(sp - 1.0) > 1e-6:
            af.append(f'atempo={sp}')
        if extra < -0.2:
            af.append(f'equalizer=f=4500:t=q:w=1.2:g={extra:.2f}')
        if af and len(y):
            sf.write(t1, y, SR)
            subprocess.run([ffmpeg, '-y', '-v', 'error', '-i', t1, '-filter:a', ','.join(af),
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
    # 7) 静音封顶：全局 EQ/响度会把语音尾巴压到阈值以下，使实听停顿变长。
    #    必须在**写时间轴之前**削掉超出部分，并同步平移各句起点——否则字幕失步。
    yy, sr2 = sf.read(full)
    if yy.ndim > 1:
        yy = yy.mean(axis=1)
    yy = yy.astype(np.float32)
    Hc = int(0.01 * sr2); nc = len(yy) // Hc
    q = np.array([np.sqrt(np.mean(yy[i * Hc:(i + 1) * Hc] ** 2) + 1e-12) <= TRIM_THR for i in range(nc)])
    capf = int(CAP / 0.01); keep, cuts, i = [], [], 0
    while i < nc:
        if q[i]:
            j = i
            while j < nc and q[j]:
                j += 1
            if j - i > capf:
                keep.append((i, i + capf)); cuts.append((i * 0.01, (j - i - capf) * 0.01))
            else:
                keep.append((i, j))
            i = j
        else:
            j = i
            while j < nc and not q[j]:
                j += 1
            keep.append((i, j)); i = j
    if cuts:
        yy = np.concatenate([yy[a * Hc:b * Hc] for a, b in keep])
        sf.write(full, yy, sr2)
        for c in durs:                       # 同步平移起点
            c['start'] = round(c['start'] - sum(d for t, d in cuts if t < c['start']), 3)
        log(f'   静音封顶 {len(cuts)} 处，共削 {sum(d for _, d in cuts):.1f}s')
    post = sf.info(full).duration
    json.dump({'gap': 0.4, 'total': round(post, 3), 'cues': durs},
              open(os.path.join(dst_job, 'audio', 'durations.json'), 'w'),
              ensure_ascii=False, indent=2)
    for f in (t1, t2, raw):
        if os.path.exists(f):
            os.remove(f)
    log(f'>> {len(cues)}句 速度{speed} 句中换气{nbr}处 句首尾换气{nedge}句 去沙哑{nadapt}句 '
        f'时长{post/60:.1f}分 漂移{abs(post-pre)*1000:.0f}ms')
    return full


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2],
          speed=float(sys.argv[3]) if len(sys.argv) > 3 else 1.1,
          att=float(os.environ.get('BREATH_ATT', '0.10')))
