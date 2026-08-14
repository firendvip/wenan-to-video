#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把任意中文文案切成 plan.json 契约：cues[]（配音/字幕最小单位）+ chapters[]（视觉章节）。

规则（BUILD_SPEC §4）：
- cues：按句末标点（。！？…；）切句；过长句再按逗号/顿号切；每条 ≤ ~24 全角字。保留原文所有字符。
- chapters：优先按空行分段成章；无空行则按 ~5 个 cue 归一章，目标 6–10 章。
"""
from __future__ import annotations

# 句末标点（切句后标点跟随前句）
SENT_END = set("。！？!?…；;")
# 句中可切分点（长句二次切分）
CLAUSE_SEP = set("，,、：:")

MAX_CUE_W = 24.0      # 单条 cue 目标最大全角宽度
HEADLINE_W = 10.0     # 章节大标题目标宽度
SUB_W = 16.0          # 章节副标题目标宽度


def _w(ch: str) -> float:
    """全角字符 1.0，ASCII 0.5。"""
    return 0.5 if ord(ch) < 128 else 1.0


def _width(s: str) -> float:
    return sum(_w(c) for c in s)


def _split_sentences(text: str) -> list[str]:
    """按句末标点切句，标点随前句；连续句末标点（如“？！”）合并。"""
    out, buf = [], []
    for ch in text:
        buf.append(ch)
        if ch in SENT_END:
            # 处理连续句末标点：向后由循环自然吞并（下一个仍是句末标点→再切）
            out.append("".join(buf))
            buf = []
    if buf:
        out.append("".join(buf))
    # 合并「仅标点」的碎片到前一句（例如引号收尾）
    merged: list[str] = []
    for seg in out:
        if merged and seg.strip() and all(c in SENT_END or c in "”’」』）)】》" or c.isspace() for c in seg):
            merged[-1] += seg
        else:
            merged.append(seg)
    return [s for s in (x.strip() for x in merged) if s]


def _hard_wrap(s: str, budget: float) -> list[str]:
    """按宽度硬切（保证每片 ≤ budget），尽量在 ASCII 词边界之外的位置切。"""
    pieces, cur, curw = [], [], 0.0
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        w = _w(ch)
        if curw + w > budget and cur:
            pieces.append("".join(cur))
            cur, curw = [ch], w
        else:
            cur.append(ch)
            curw += w
        i += 1
    if cur:
        pieces.append("".join(cur))
    return [p.strip() for p in pieces if p.strip()]


def _split_long(sentence: str, budget: float) -> list[str]:
    """长句二次切分：先按 逗号/顿号 处断，仍过长则硬切。"""
    if _width(sentence) <= budget:
        return [sentence]
    # 按 clause 分隔符切（分隔符随前段）
    parts, buf = [], []
    for ch in sentence:
        buf.append(ch)
        if ch in CLAUSE_SEP:
            parts.append("".join(buf))
            buf = []
    if buf:
        parts.append("".join(buf))
    # 贪心合并小片，超预算就落一条
    out, cur, curw = [], [], 0.0
    for p in parts:
        pw = _width(p)
        if cur and curw + pw > budget:
            out.append("".join(cur))
            cur, curw = [p], pw
        else:
            cur.append(p)
            curw += pw
    if cur:
        out.append("".join(cur))
    # 单个 clause 仍过长 → 硬切
    final: list[str] = []
    for seg in out:
        seg = seg.strip()
        if not seg:
            continue
        if _width(seg) > budget * 1.15:
            final.extend(_hard_wrap(seg, budget))
        else:
            final.append(seg)
    return [s for s in final if s]


def _truncate(s: str, budget: float) -> str:
    """截断到 budget 全角宽度，超出补 …。保留完整 ASCII 词。"""
    s = s.strip()
    if _width(s) <= budget:
        return s
    out, w = [], 0.0
    for ch in s:
        cw = _w(ch)
        if w + cw > budget:
            break
        out.append(ch)
        w += cw
    res = "".join(out).rstrip("，,、：:。！？!?…；; ")
    return (res + "…") if res else s[:1]


def _even_groups(n: int, k: int) -> list[tuple[int, int]]:
    """把 [0,n) 尽量均匀分成 k 组，返回 (start,end) 半开区间列表。"""
    k = max(1, min(k, n))
    base, extra = divmod(n, k)
    groups, idx = [], 0
    for g in range(k):
        size = base + (1 if g < extra else 0)
        groups.append((idx, idx + size))
        idx += size
    return groups


def segment_text(text: str) -> dict:
    """任意中文文案 → plan.json（dict）。"""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise ValueError("文案为空")

    # 段落（按空行）
    paragraphs = [p.strip() for p in _split_paragraphs(raw)]
    paragraphs = [p for p in paragraphs if p]

    # 生成 cues，同时记录每段覆盖的 cue 索引
    cues: list[dict] = []
    para_ranges: list[tuple[int, int]] = []      # 1-based 闭区间 [start_i, end_i]
    for para in paragraphs:
        start_i = len(cues) + 1
        for sent in _split_sentences(para):
            for piece in _split_long(sent, MAX_CUE_W):
                cues.append({"i": len(cues) + 1, "text": piece})
        end_i = len(cues)
        if end_i >= start_i:
            para_ranges.append((start_i, end_i))

    if not cues:
        raise ValueError("无法从文案中切出任何句子")

    n = len(cues)

    # 章节划分
    if 2 <= len(para_ranges) <= 12:
        ranges = para_ranges
    else:
        target = max(1, min(10, round(n / 5) or 1))
        ranges = [(a + 1, b) for (a, b) in _even_groups(n, target)]

    chapters = []
    text_by_i = {c["i"]: c["text"] for c in cues}
    for ci, (a, b) in enumerate(ranges, start=1):
        headline = _truncate(text_by_i[a], HEADLINE_W)
        sub = ""
        if b > a:
            sub = _truncate(text_by_i[a + 1], SUB_W)
        chapters.append({
            "c": ci,
            "title": f"第{ci}章",
            "headline": headline,
            "sub": sub,
            "cueStart": a,
            "cueEnd": b,
        })

    return {
        "project": "文案→视频",
        "format": {"orientation": "portrait", "width": 1080, "height": 1920, "fps": 30},
        "notes": "cues=配音+字幕最小单位；chapters=视觉章节；字幕最后统一烧录，画面底部留白做安全区。",
        "cues": cues,
        "chapters": chapters,
    }


def _split_paragraphs(raw: str) -> list[str]:
    """按空行切段。"""
    import re
    return re.split(r"\n\s*\n+", raw)


if __name__ == "__main__":
    import json, sys
    t = sys.argv[1] if len(sys.argv) > 1 else "你好世界。这是第一段测试。\n\n第二段：听说读写，反复练习就会熟。"
    plan = segment_text(t)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    print(f"\n>> {len(plan['cues'])} cues, {len(plan['chapters'])} chapters", file=sys.stderr)
