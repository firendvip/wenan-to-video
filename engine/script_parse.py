#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""口播稿 Markdown → plan.json（cues 逐句原文 + 停顿/放慢标记 + 分章提炼标题）。

规则来自稿件《录音须知》：
- 只念「引子」第一句 → 「收句」最后一句之间的正文；元信息/须知/标题/时间码/表格/
  行首引用/文末切片方案整块跳过；星号等符号只念文字。
- 停顿（上限 CAP=1 秒）：开头 1.0；（停）0.5；（停一拍/停一秒再开口/停两拍）1.0；
  `……` 独立成行 1.0；`---` 分隔线 1.0；跨 `###` 小标题 0.8。
- 句间默认停顿按上一句末标点分级（不再统一）：。！？→0.45；，、；：→0.25；其他→0.40。
- `（放慢…）` 标记：下一句放慢（slow=True），由 audio_build 按 SLOW_FACTOR 单独变速。
"""
from __future__ import annotations
import json
import math
import os
import re

from engine import config, distill

CAP = 1.0
GAP_SENTENCE = 0.45      # 上一句以 。！？…… 结尾
GAP_CLAUSE = 0.25        # 上一句以 ，、；： 结尾
GAP_DEFAULT = 0.40
GAP_SUBSECTION = 0.80    # 跨 ### 小标题
OPEN_PAUSE = 1.0


def _strip_markers(s: str) -> str:
    s = re.sub(r'（(停[^）]*|放慢[^）]*)）', '', s)
    s = s.replace('**', '').replace('「', '').replace('」', '').replace('【', '').replace('】', '')
    s = re.sub(r'\d{2}:\d{2}[–\-]\d{2}:\d{2}', '', s)
    return s.strip()


def _pause_of(s: str):
    """返回该行代表的停顿秒数；不是停顿行则返回 None。"""
    if s in ('……', '---') or set(s) == {'-'}:
        return CAP
    if re.fullmatch(r'（[^）]*）', s):
        if '放慢' in s:
            return 0.0          # 放慢不产生停顿，只标记下一句
        if '停一秒' in s or '停一拍' in s or '停两' in s:
            return CAP
        if '停' in s:
            return 0.5
        return 0.0
    return None


def _body(lines: list[str]) -> list[str]:
    """截取「引子」→「抖音切片方案」之间的正文；找不到标记则用全文。"""
    start = next((i for i, l in enumerate(lines) if l.startswith('##') and '引子' in l), None)
    end = next((i for i, l in enumerate(lines) if l.startswith('## ') and '切片' in l), len(lines))
    return lines[(start + 1) if start is not None else 0:end]


def _gap_after(text: str) -> float:
    if text and text[-1] in '。！？!?…':
        return GAP_SENTENCE
    if text and text[-1] in '，,、；;：:':
        return GAP_CLAUSE
    return GAP_DEFAULT


def parse_cues(md_text: str) -> list[dict]:
    lines = md_text.split('\n')
    cues: list[dict] = []
    pending = 0.0        # 下一句之前的停顿
    slow_next = False

    for raw in _body(lines):
        s = raw.strip()
        if not s:
            continue
        if s.startswith('###'):                     # 跨小标题：给一个结构停顿
            pending = max(pending, GAP_SUBSECTION)
            continue
        if s.startswith('#') or s.startswith('>') or s.startswith('|'):
            continue
        if '放慢' in s and re.fullmatch(r'（[^）]*）', s):
            slow_next = True
            continue
        p = _pause_of(s)
        if p is not None:
            pending = max(pending, min(p, CAP))
            continue
        t = _strip_markers(s)
        if not t:
            continue
        lead = pending if pending > 0 else (_gap_after(cues[-1]['text']) if cues else 0.0)
        cue = {'i': len(cues) + 1, 'text': t, 'lead': round(min(lead, CAP), 3)}
        if slow_next:
            cue['slow'] = True
            slow_next = False
        cues.append(cue)
        pending = 0.0

    if cues:                                        # 引子第一句之前先空一秒
        cues[0]['lead'] = OPEN_PAUSE
    return cues


def build_chapters(cues: list[dict], per_chapter: int = 18, log=None) -> list[dict]:
    """按句数切章，并用 LLM 提炼每章 headline/sub（失败则回退取首句）。"""
    n = len(cues)
    k = max(1, round(n / per_chapter))
    size = math.ceil(n / k)
    chunks = [(cues[s]['i'], cues[min(s + size, n) - 1]['i'],
               ' '.join(c['text'] for c in cues[s:s + size])) for s in range(0, n, size)]
    blocks = [f'[{i+1}] {txt[:360]}' for i, (a, b, txt) in enumerate(chunks)]
    prompt = ('你在为一档竖屏口播视频做分章画面标题。下面按顺序给出 '
              f'{len(chunks)} 个片段。为每个片段提炼：headline(画面大标题,凝练主旨,4–10字,'
              '可对比式但必须贴合,不照抄整句)；sub(副标题,≤16字)。语气沉静。严格输出 JSON：'
              '{"chapters":[{"headline":"...","sub":"..."}]}，'
              f'长度正好 {len(chunks)}，顺序对应，只输出 JSON。\n\n' + '\n\n'.join(blocks))
    items = []
    try:
        items = (distill._extract_json(distill._via_deepseek(prompt) or '') or {}).get('chapters') or []
    except Exception:
        items = []
    if log:
        log(f'提炼分章标题：{len(items)}/{len(chunks)}')
    out = []
    for i, (a, b, txt) in enumerate(chunks):
        it = items[i] if i < len(items) else {}
        out.append({'c': i + 1, 'title': '',
                    'headline': (it.get('headline') or txt[:8]).strip(),
                    'sub': (it.get('sub') or '').strip(), 'cueStart': a, 'cueEnd': b})
    return out


def make_plan(md_text: str, project: str = '口播视频', log=None) -> dict:
    cues = parse_cues(md_text)
    if not cues:
        raise RuntimeError('未解析出任何正文句子，请检查稿件格式')
    if log:
        log(f'解析正文 {len(cues)} 句 / {sum(len(c["text"]) for c in cues)} 字')
    return {'project': project,
            'format': {'orientation': 'portrait', 'width': config.WIDTH,
                       'height': config.HEIGHT, 'fps': config.FPS},
            'cues': cues, 'chapters': build_chapters(cues, log=log)}


def write_plan(job_dir: str, md_path: str, log=None) -> dict:
    md = open(md_path, encoding='utf-8').read()
    plan = make_plan(md, project=os.path.splitext(os.path.basename(md_path))[0], log=log)
    os.makedirs(job_dir, exist_ok=True)
    json.dump(plan, open(os.path.join(job_dir, 'plan.json'), 'w'), ensure_ascii=False, indent=2)
    return plan
