#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""理解并提炼口播文案 → plan（cues 原文逐字 + chapters 提炼的 headline/sub）。

用 prompts/distill_plan.md 提示词，经本机 claude CLI（走已登录，无需 API key）产出。
解析/校验失败时回退到 engine.segment 的机械分段，保证流水线不中断。
"""
from __future__ import annotations
import json
import os
import re
import subprocess

from engine import config


def _extract_json(s: str) -> dict | None:
    """从 claude 输出里抽出第一个平衡的 JSON 对象。"""
    if not s:
        return None
    # 去掉 ```json ... ``` 围栏
    s = re.sub(r"```[a-zA-Z]*", "", s)
    start = s.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start:i + 1])
                    except Exception:
                        return None
    return None


def _valid_and_normalize(plan: dict) -> dict | None:
    """校验并规整：cues 连续编号；chapters 覆盖全部 cue、无缝无重叠、字段齐全。"""
    if not isinstance(plan, dict):
        return None
    cues_in = plan.get("cues")
    chs_in = plan.get("chapters")
    if not isinstance(cues_in, list) or not cues_in:
        return None
    if not isinstance(chs_in, list) or not chs_in:
        return None

    cues = []
    for idx, c in enumerate(cues_in, 1):
        txt = (c.get("text") if isinstance(c, dict) else str(c)) or ""
        txt = txt.replace("\n", " ").strip()
        if txt:
            cues.append({"i": idx, "text": txt})
    if not cues:
        return None
    n = len(cues)

    chapters = []
    for ci, ch in enumerate(chs_in, 1):
        if not isinstance(ch, dict):
            return None
        headline = (ch.get("headline") or "").strip()
        if not headline:
            return None
        try:
            cs = int(ch.get("cueStart"))
            ce = int(ch.get("cueEnd"))
        except (TypeError, ValueError):
            return None
        chapters.append({
            "c": ci,
            "title": (ch.get("title") or "").strip(),
            "headline": headline,
            "sub": (ch.get("sub") or "").strip(),
            "cueStart": cs,
            "cueEnd": ce,
        })

    # 覆盖性校验：首章从 1 起、末章到 n、逐章连续
    chapters.sort(key=lambda x: x["cueStart"])
    if chapters[0]["cueStart"] != 1 or chapters[-1]["cueEnd"] != n:
        return None
    for a, b in zip(chapters, chapters[1:]):
        if a["cueEnd"] < a["cueStart"] or b["cueStart"] != a["cueEnd"] + 1:
            return None
    for ci, ch in enumerate(chapters, 1):
        ch["c"] = ci

    return {
        "project": "文案→视频",
        "format": {"orientation": "portrait", "width": config.WIDTH,
                   "height": config.HEIGHT, "fps": config.FPS},
        "cues": cues,
        "chapters": chapters,
    }


DISTILL_MODEL = os.environ.get("DISTILL_MODEL", "claude-sonnet-5")


def _via_deepseek(full: str) -> str | None:
    """首选：DeepSeek（OpenAI 兼容 /chat/completions）。"""
    key = config.DEEPSEEK_API_KEY
    if not key:
        return None
    import urllib.request
    body = json.dumps({
        "model": config.DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": full}],
        "stream": False, "temperature": 0.3, "max_tokens": 8000,
    }).encode("utf-8")
    req = urllib.request.Request(
        config.DEEPSEEK_BASE + "/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=220) as r:
        resp = json.loads(r.read().decode("utf-8"))
    return resp["choices"][0]["message"]["content"]


def _via_api(full: str) -> str | None:
    """优先：有 ANTHROPIC_API_KEY 时直接调 Messages API（最稳，不依赖 CLI 登录）。"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    import urllib.request
    body = json.dumps({
        "model": DISTILL_MODEL, "max_tokens": 4096,
        "messages": [{"role": "user", "content": full}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=200) as r:
        resp = json.loads(r.read().decode("utf-8"))
    return "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")


def _via_cli(full: str) -> str | None:
    """次选：本机 claude CLI（需其已登录）。鉴权失败时返回 None。"""
    try:
        r = subprocess.run([config.CLAUDE_BIN, "-p", full],
                           capture_output=True, text=True, timeout=240)
    except Exception:
        return None
    blob = (r.stdout or "") + (r.stderr or "")
    if "Failed to authenticate" in blob or "OAuth" in blob or "API Error" in blob:
        return None
    return r.stdout or None


def make_plan(text: str, log=None) -> dict:
    """返回 plan（cues 原文 + 提炼后的 chapters）。LLM 不可用/校验不过 → 机械回退。"""
    def _log(m):
        if log:
            log(m)

    try:
        prompt = open(config.PROMPT_PATH, encoding="utf-8").read()
        full = prompt.replace("<<在此粘贴文案>>", text.strip())
        _log("理解并提炼文案…")
        raw = None
        for fn in (_via_deepseek, _via_api, _via_cli):
            try:
                raw = fn(full)
            except Exception:
                raw = None
            if raw:
                break
        if raw:
            plan = _valid_and_normalize(_extract_json(raw) or {})
            if plan:
                _log(f"提炼完成：{len(plan['chapters'])} 章 / {len(plan['cues'])} 句")
                return plan
            _log("提炼输出未通过校验，回退机械分段")
        else:
            _log("LLM 不可用（未设 API Key 且 CLI 未登录），回退机械分段")
    except Exception as e:
        _log(f"提炼异常（{type(e).__name__}），回退机械分段")

    from engine.segment import segment_text
    return segment_text(text)
