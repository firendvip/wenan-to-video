#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""根据 job/plan.json + job/audio/durations.json 生成抖音风 ASS（强制单行）。

移植自 pipeline/make_subs.py：一句放不下一行就拆成多条单行字幕，在该句语音时段内按
文字宽度比例依次显示（音画同步、逐条无缝、避头、均衡）。锁定样式：PingFang SC 96 加粗、
白字+黑描边(Outline6)+阴影2、MarginV140、MarginL/R30。
"""
from __future__ import annotations
import json
import os

from engine import config

NO_START = set("，。！？、；：）】》」』”’.,!?;:)")  # 避头


def _params() -> dict:
    """按 config 尺寸（方向）给出字幕样式与单行折分预算。"""
    portrait = config.HEIGHT >= config.WIDTH
    if portrait:  # 竖屏 1080×1920
        return {"fontsize": 96, "outline": 6, "shadow": 2,
                "marginlr": 30, "marginv": 140, "single": 10.0, "hard": 10.4}
    # 横屏 1920×1080
    return {"fontsize": 68, "outline": 5, "shadow": 2,
            "marginlr": 160, "marginv": 90, "single": 23.0, "hard": 24.0}


def _ts(sec: float) -> str:
    if sec < 0:
        sec = 0
    cs = int(round(sec * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _tokens(text: str):
    toks, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch == " ":
            toks.append(" "); i += 1
        elif ord(ch) < 128:
            j = i
            while j < n and ord(text[j]) < 128 and text[j] != " ":
                j += 1
            toks.append(text[i:j]); i = j
        else:
            toks.append(ch); i += 1
    return toks


def _uw(tok: str) -> float:
    if tok == " ":
        return 0.6
    if len(tok) == 1 and ord(tok) >= 128:
        return 1.0
    return len(tok) * 0.6


def _wsum(s: str) -> float:
    return sum(_uw(t) for t in _tokens(s))


def _greedy_lines(toks, budget):
    cur, curw, lines = [], 0.0, []
    for t in toks:
        w = _uw(t)
        if cur and t != " " and t not in NO_START and curw + w > budget:
            lines.append("".join(cur).strip()); cur, curw = [t], w
        else:
            cur.append(t); curw += w
    if "".join(cur).strip():
        lines.append("".join(cur).strip())
    return [l for l in lines if l]


def split_lines(text: str, single: float = 10.0, hard: float = 10.4):
    toks = _tokens(text)
    total = sum(_uw(t) for t in toks)
    if total <= single:
        return ["".join(toks).strip()]
    if total <= 2 * hard:
        best = None
        prefix = 0.0
        for i in range(1, len(toks)):
            prefix += _uw(toks[i - 1])
            if toks[i] == " " or toks[i] in NO_START:
                continue
            l1 = "".join(toks[:i]).strip()
            l2 = "".join(toks[i:]).strip()
            if not l1 or not l2:
                continue
            w1, w2 = _wsum(l1), _wsum(l2)
            if w1 > hard or w2 > hard:
                continue
            bonus = -2.0 if (toks[i - 1] in NO_START or toks[i - 1] == " ") else 0.0
            score = abs(w1 - w2) + bonus
            if best is None or score < best[0]:
                best = (score, i)
        if best is not None:
            i = best[1]
            return ["".join(toks[:i]).strip(), "".join(toks[i:]).strip()]
    return _greedy_lines(toks, single)


def _header(p: dict) -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {config.WIDTH}\n"
        f"PlayResY: {config.HEIGHT}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: TV.709\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Douyin,PingFang SC,{p['fontsize']},&H00FFFFFF,&H000000FF,"
        f"&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{p['outline']},"
        f"{p['shadow']},2,{p['marginlr']},{p['marginlr']},{p['marginv']},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )


def write_ass(job_dir: str) -> str:
    """写 job/final/subs.ass，返回路径。"""
    plan = json.load(open(os.path.join(job_dir, "plan.json"), encoding="utf-8"))
    dur = json.load(open(os.path.join(job_dir, "audio", "durations.json"), encoding="utf-8"))
    text_by_i = {c["i"]: c["text"] for c in plan["cues"]}
    cues = sorted(dur["cues"], key=lambda c: c["i"])

    PA = _params()
    out = [_header(PA)]
    for c in cues:
        i = c["i"]
        S = float(c["start"])
        d = float(c.get("dur", 0.8))
        span = float(c.get("slot", d))
        txt = text_by_i.get(i, c.get("text", "")).replace("\n", " ").strip()
        pieces = split_lines(txt, PA["single"], PA["hard"])
        W = sum(_wsum(p) for p in pieces) or 1.0
        cum = 0.0
        for k, p in enumerate(pieces):
            s = S + d * (cum / W)
            cum += _wsum(p)
            e = (S + span) if k == len(pieces) - 1 else (S + d * (cum / W))
            out.append(f"Dialogue: 0,{_ts(s)},{_ts(e)},Douyin,,0,0,0,,{p}")

    dst = os.path.join(job_dir, "final", "subs.ass")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return dst
