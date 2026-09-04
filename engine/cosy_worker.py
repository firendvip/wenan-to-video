#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CosyVoice3 逐句配音 worker（在 ~/CosyVoice/.venv 下运行）。

读取 <job_dir>/plan.json 的 cues，用零样本克隆（参考音 REF + 逐字转写 RT）逐句生成
<job_dir>/audio_src/seg_XX.wav，供 webapp 现有 respeed/assemble/subtitles 复用。
沿用已验证方案：每块 ≤78 字（避免内部拆分）、裁头 0.20s + despike + 淡入、气泡音重掷。

用法: PYTORCH_ENABLE_MPS_FALLBACK=1 ~/CosyVoice/.venv/bin/python cosy_worker.py <job_dir> [limit]
环境可覆盖: COSY_REF, COSY_RT
"""
import warnings; warnings.filterwarnings('ignore')
import sys, os, re, json, time
sys.path.insert(0, '/Users/Admin/CosyVoice')
sys.path.insert(0, '/Users/Admin/CosyVoice/third_party/Matcha-TTS')
sys.path.insert(0, '/Users/Admin/voice-pipeline')
import numpy as np, torch, torchaudio, librosa
from cosyvoice.cli.cosyvoice import AutoModel
from despike import despike

JOB = sys.argv[1]
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0
REF = os.environ.get('COSY_REF', '/Users/Admin/voice-rec/REF_FINAL3.wav')
RT = os.environ.get('COSY_RT', '春天的清晨，山谷里飘着薄雾，风从林间穿过，两只喜鹊落在枝头，叫声清脆，老人推开木窗，深深吸了一口气。')
SYS = 'You are a helpful assistant.<|endofprompt|>'
CAP = 78
FRY_MAX, FRY_GOOD, TRIES = 2.5, 1.2, 3

srcd = os.path.join(JOB, 'audio_src'); os.makedirs(srcd, exist_ok=True)
cues = json.load(open(os.path.join(JOB, 'plan.json'), encoding='utf-8'))['cues']
if LIMIT:
    cues = cues[:LIMIT]


def speakable(t):
    return any(ch.isalnum() or ('一' <= ch <= '鿿') for ch in t)


def hs(t, cap):
    if len(t) <= cap:
        return [t]
    ps = re.split(r'(?<=[。？！；，])', t); o = []; c = ''
    for p in ps:
        if len(c) + len(p) > cap and c:
            o.append(c); c = p
        else:
            c += p
    if c:
        o.append(c)
    return [x for x in o if x]


m = AutoModel(model_dir='pretrained_models/Fun-CosyVoice3-0.5B'); SR = m.sample_rate
TRIM = int(0.20 * SR); FADE = int(0.02 * SR)
print(f'>> model loaded SR={SR}', flush=True)


def clean(w):
    w = w[:, TRIM:] if w.shape[1] > TRIM * 2 else w
    w = despike(w, SR)
    if w.shape[1] > FADE:
        w = w.clone(); w[:, :FADE] *= torch.linspace(0., 1., FADE)
    return w


def fry(w):
    y = librosa.resample(w[0].numpy(), orig_sr=SR, target_sr=16000)
    f0, _, _ = librosa.pyin(y, fmin=50, fmax=400, sr=16000, frame_length=1024, hop_length=256)
    v = f0[~np.isnan(f0)]
    return 100.0 if len(v) < 20 else (v < 80).sum() / len(v) * 100


t0 = time.time(); rerolls = 0
for k, c in enumerate(cues, 1):
    i = c['i']
    out = os.path.join(srcd, f'seg_{i:02d}.wav')
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        continue                                  # 断点续跑
    text = (c.get('text') or '').strip()
    if not speakable(text):                        # 纯标点/省略号 → 短静音
        torchaudio.save(out, torch.zeros(1, int(0.5 * SR)), SR)
        print(f'   {k}/{len(cues)} seg{i} (静音)', flush=True)
        continue
    parts = []                                     # 停顿统一由 audio_build 精确插入
    for piece in hs(text, CAP):
        best, bestf = None, 999
        for tri in range(TRIES):
            ch = [j['tts_speech'] for j in m.inference_zero_shot(piece, SYS + RT, REF, stream=False)]
            w = clean(torch.cat(ch, dim=1)); r = fry(w)
            if r < bestf:
                bestf, best = r, w
            if r <= FRY_GOOD:
                break
            if tri == 0 and r <= FRY_MAX:
                break
            if tri > 0:
                rerolls += 1
        parts.append(best)
    torchaudio.save(out, torch.cat(parts, dim=1), SR)
    print(f'   {k}/{len(cues)} seg{i} 气泡音{bestf:.1f}% 重掷{rerolls} 用时{(time.time()-t0)/60:.1f}分', flush=True)

print(f'>> ALL_SEGMENTS_DONE {len(cues)}句 重掷{rerolls} 总耗时{(time.time()-t0)/60:.1f}分', flush=True)
