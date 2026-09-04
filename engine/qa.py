#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成片音轨自动质检（在 CosyVoice venv 下运行，需 numpy/soundfile）。

检查项与判定：
  停顿    最长静音 ≤ PAUSE_CAP(1.05s)，否则列出超标处
  换气    句间/句尾仍可听见的换气残留应为 0
          （句中噪声段是清辅音、紧贴句首的是声母，均不计入）
  沙哑    逐句 3–6kHz/500–2kHz 能量比：中位数 ≤ HOARSE_MED，超标句 ≤ HOARSE_RATE
  同步    durations.json 记录的总时长与实际音轨长度偏差 ≤ SYNC_TOL

用法: qa.py <job_dir>   （退出码 0=全部通过，1=有不合格项）
"""
import json
import os
import sys

import numpy as np
import soundfile as sf

PAUSE_CAP = 1.05      # 秒
RESID_PK = -34.0      # dB，高于此的换气残留算「听得见」
HOARSE_TH = 0.60      # 单句沙哑阈值
HOARSE_MED = 0.40     # 全片中位数上限
HOARSE_RATE = 0.10    # 超标句占比上限
SYNC_TOL = 0.10       # 秒


def _frames(y, sr, h=0.02):
    H = int(h * sr)
    n = len(y) // H
    return H, n


def check_pause(y, sr, thr=0.006):
    H = int(0.01 * sr); n = len(y) // H
    rms = np.array([np.sqrt(np.mean(y[i * H:(i + 1) * H] ** 2) + 1e-12) for i in range(n)])
    sil = rms <= thr
    runs, i = [], 0
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]:
                j += 1
            if (j - i) * 0.01 >= 0.25:
                runs.append((round(i * 0.01, 2), round((j - i) * 0.01, 3)))
            i = j
        else:
            i += 1
    over = [r for r in runs if r[1] > PAUSE_CAP]
    return {'count': len(runs), 'max': max([r[1] for r in runs], default=0.0), 'over': over}


def check_breath(y, sr, durs=None):
    """成片中仍然「听得见」的换气残留。

    只统计**句首尾/句间空档**的噪声段：句中的噪声段绝大多数是 s/sh/x 等清辅音，
    实测 128 处里 121 处在句中，若一并计入会严重误判。"""
    H, n = _frames(y, sr)
    f = np.fft.rfftfreq(H, 1 / sr); win = np.hanning(H); cand = []
    for i in range(n):
        x = y[i * H:(i + 1) * H]
        if len(x) < H:
            break
        pk = 20 * np.log10(np.abs(x).max() + 1e-12)
        if pk <= RESID_PK:
            continue
        S = np.abs(np.fft.rfft(x * win)) + 1e-12
        flat = np.exp(np.mean(np.log(S))) / np.mean(S)
        hf = (S[f > 2000] ** 2).sum() / ((S ** 2).sum() + 1e-12)
        if flat > 0.05 and hf > 0.35:
            cand.append(i)
    mg, last = [], -9
    for i in cand:
        if i - last > 3:
            mg.append([i, i])
        else:
            mg[-1][1] = i
        last = i
    mg = [m for m in mg if (m[1] - m[0] + 1) * 0.02 >= 0.12]
    if durs:                      # 排除句中（清辅音）
        keep = []
        for a, b in mg:
            t = a * 0.02
            skip = False
            for c in durs['cues']:
                s0, e0 = c['start'], c['start'] + c['dur']
                if s0 <= t <= e0:
                    # 句中噪声段 = 清辅音；紧贴句首(<60ms)的噪声 = 声母，均不计
                    skip = ((t - s0 > 0.25) and (e0 - t > 0.25)) or (t - s0 <= 0.06)
                    break
            if not skip:
                keep.append((a, b))
        mg = keep
    return {'count': len(mg), 'at': [round(a * 0.02, 1) for a, _ in mg[:12]]}


def check_hoarse(y, sr, durs):
    def ratio(seg):
        if len(seg) < 2048:
            return None
        S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
        f = np.fft.rfftfreq(len(seg), 1 / sr)
        return float(S[(f >= 3000) & (f <= 6000)].sum() / (S[(f >= 500) & (f <= 2000)].sum() + 1e-12))
    vals = []
    for c in durs['cues']:
        a = int(c['start'] * sr); b = a + int(c['dur'] * sr)
        r = ratio(y[a:min(b, len(y))])
        if r:
            vals.append((c['i'], r))
    v = np.array([x for _, x in vals]) if vals else np.array([0.0])
    bad = [(i, round(r, 2)) for i, r in vals if r > HOARSE_TH]
    return {'median': round(float(np.median(v)), 3), 'bad': len(bad),
            'rate': round(len(bad) / max(1, len(vals)), 3),
            'worst': sorted(bad, key=lambda x: -x[1])[:8]}


def run(job_dir):
    full = os.path.join(job_dir, 'audio', 'full.wav')
    durs = json.load(open(os.path.join(job_dir, 'audio', 'durations.json'), encoding='utf-8'))
    y, sr = sf.read(full)
    if y.ndim > 1:
        y = y.mean(axis=1)
    y = y.astype(np.float32)

    p = check_pause(y, sr)
    b = check_breath(y, sr, durs)
    h = check_hoarse(y, sr, durs)
    drift = abs(len(y) / sr - durs['total'])

    ok_p = not p['over']
    ok_b = b['count'] == 0
    ok_h = h['median'] <= HOARSE_MED and h['rate'] <= HOARSE_RATE
    ok_s = drift <= SYNC_TOL
    allok = ok_p and ok_b and ok_h and ok_s

    print('===== 音轨质检 =====')
    print(f"[{'通过' if ok_p else '不合格'}] 停顿  共{p['count']}处 最长{p['max']:.2f}s "
          f"超{PAUSE_CAP}s {len(p['over'])}处" + (f" @{p['over'][:5]}" if p['over'] else ''))
    print(f"[{'通过' if ok_b else '不合格'}] 换气  可听见残留 {b['count']}处"
          + (f" @{b['at']}秒" if b['count'] else ''))
    print(f"[{'通过' if ok_h else '不合格'}] 沙哑  中位{h['median']} 超标{h['bad']}句"
          f"({h['rate']*100:.0f}%)" + (f" 最差{h['worst'][:5]}" if h['worst'] else ''))
    print(f"[{'通过' if ok_s else '不合格'}] 同步  时长偏差 {drift*1000:.0f}ms")
    print(f"===== {'全部通过' if allok else '存在不合格项'} =====")
    return allok


if __name__ == '__main__':
    sys.exit(0 if run(sys.argv[1]) else 1)
