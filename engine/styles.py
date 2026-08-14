#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单一固定 HTML 风格：暖色电子杂志 · 竖屏 1080×1920。
参照 lIxflkxP6BA7cfH5pnBI8g.mp4（原 pipeline/html/deck.html）：衬线大标题 + 暖色渐变 +
幽灵章节号 + kicker + 副标题；底部约 22% 字幕安全区留白，画面不写口播字幕。
一屏一章，画面上是**提炼的主旨**（headline/sub），原文只进字幕。

契约：`?slide=C` / `?chapter=C` 直出该章静止态；`window.showSlide/showChapter(C)`；
截图前置位 `window.__deckReady=true`（字体就绪后）。build_deck(style, chapters) 忽略 style。
"""
from __future__ import annotations
import json


def build_deck(style: str, chapters: list) -> str:
    ch = sorted(chapters, key=lambda c: c.get("c", 0))
    data = [{
        "tag": (c.get("title") or "").strip(),
        "wm": f"{c.get('c', i + 1):02d}",
        "hl": (c.get("headline") or "").strip(),
        "sub": (c.get("sub") or "").strip(),
    } for i, c in enumerate(ch)]
    n = len(data) or 1
    ch_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>文案→视频 · 竖屏 Deck</title>
<style>
  :root{{
    --stage-w:1080px; --stage-h:1920px;
    --pad-x:108px; --pad-top:138px; --caption-safe:424px;
    --bg-top:#FDF7EF; --bg-bottom:#F6E5D1; --glow:rgba(255,214,168,.55);
    --ink:#2A211B; --ink-2:#6E5F52; --ink-3:#9A8B7C;
    --accent:#D9682A; --accent-soft:rgba(217,104,42,.12); --hair:rgba(42,33,27,.14);
    --serif:"Songti SC","STSong",Georgia,"Times New Roman",serif;
    --sans:"PingFang SC","Hiragino Sans GB",-apple-system,"Helvetica Neue",Arial,sans-serif;
  }}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  html,body{{height:100%;}}
  body{{background:#1a1613;font-family:var(--sans);display:flex;align-items:center;justify-content:center;min-height:100vh;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;}}
  .stage{{position:relative;width:var(--stage-w);height:var(--stage-h);overflow:hidden;color:var(--ink);
    background:radial-gradient(120% 62% at 50% 20%,var(--glow) 0%,rgba(255,214,168,0) 58%),linear-gradient(178deg,var(--bg-top) 0%,#FBEFE0 46%,var(--bg-bottom) 100%);}}
  .stage::after{{content:"";position:absolute;inset:0;opacity:.05;pointer-events:none;mix-blend-mode:multiply;
    background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.5'/%3E%3C/svg%3E");}}
  .safe{{position:absolute;left:0;right:0;top:0;height:calc(var(--stage-h) - var(--caption-safe));padding:var(--pad-top) var(--pad-x) 40px;display:flex;flex-direction:column;z-index:2;}}
  .top{{display:flex;align-items:flex-start;justify-content:space-between;}}
  .brand{{display:inline-flex;align-items:center;gap:0;padding:16px 22px;border:1.5px solid var(--hair);border-radius:999px;background:rgba(255,255,255,.42);}}
  .brand .dot{{width:14px;height:14px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 6px var(--accent-soft);}}
  .counter{{text-align:right;}}
  .counter .num{{font-family:var(--serif);font-size:40px;font-weight:700;color:var(--ink);letter-spacing:.06em;}}
  .counter .num .of{{color:var(--ink-3);font-weight:600;}}
  .dots{{display:flex;gap:12px;justify-content:flex-end;margin-top:18px;flex-wrap:wrap;max-width:420px;}}
  .dots i{{width:12px;height:12px;border-radius:50%;background:rgba(42,33,27,.16);}}
  .dots i.on{{width:34px;border-radius:6px;background:var(--accent);}}
  .hero{{flex:1;position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;}}
  .watermark{{position:absolute;top:50%;left:50%;transform:translate(-50%,-58%);font-family:var(--serif);font-weight:700;font-size:640px;line-height:1;color:rgba(42,33,27,.045);letter-spacing:.02em;pointer-events:none;user-select:none;z-index:0;}}
  .eyebrow{{position:relative;z-index:1;display:inline-flex;align-items:center;gap:20px;font-size:32px;font-weight:600;letter-spacing:.42em;text-indent:.42em;color:var(--accent);margin-bottom:52px;min-height:40px;}}
  .eyebrow.empty::before,.eyebrow.empty::after{{display:none;}}
  .eyebrow::before,.eyebrow::after{{content:"";width:40px;height:2px;background:var(--accent);opacity:.55;}}
  .headline{{position:relative;z-index:1;font-family:var(--serif);font-weight:700;line-height:1.05;letter-spacing:.005em;color:var(--ink);white-space:nowrap;}}
  .rule{{position:relative;z-index:1;width:128px;height:7px;border-radius:99px;margin:56px 0 46px;background:linear-gradient(90deg,var(--accent),#E9925A);}}
  .sub{{position:relative;z-index:1;font-family:var(--sans);font-size:47px;font-weight:400;line-height:1.42;letter-spacing:.04em;color:var(--ink-2);max-width:820px;min-height:1px;}}
</style>
</head>
<body>
  <main class="stage" id="stage">
    <div class="safe">
      <header class="top">
        <span class="brand"><span class="dot"></span></span>
        <div class="counter">
          <div class="num"><span id="cn">01</span> <span class="of">/ {n:02d}</span></div>
          <div class="dots" id="dots"></div>
        </div>
      </header>
      <section class="hero">
        <span class="watermark" id="wm">01</span>
        <span class="eyebrow" id="eyebrow"></span>
        <h1 class="headline" id="headline"></h1>
        <span class="rule"></span>
        <p class="sub" id="sub"></p>
      </section>
    </div>
  </main>
<script>
  var CH = {ch_json};
  var N = CH.length;
  var stage=document.getElementById('stage'), cnEl=document.getElementById('cn'),
      dotsEl=document.getElementById('dots'), wmEl=document.getElementById('wm'),
      eyebrowEl=document.getElementById('eyebrow'), headEl=document.getElementById('headline'),
      subEl=document.getElementById('sub');
  for(var i=0;i<N;i++){{ dotsEl.appendChild(document.createElement('i')); }}
  var dots=dotsEl.children;
  var AVAIL = 1080 - 2*108;   // headline 可用宽度
  function clampC(c){{ c=parseInt(c,10); if(isNaN(c)) c=1; return Math.min(N,Math.max(1,c)); }}
  function fit(el){{
    var px=300; el.style.fontSize=px+'px';
    while(px>42 && el.scrollWidth>AVAIL){{ px-=4; el.style.fontSize=px+'px'; }}
  }}
  function show(c){{
    c=clampC(c); var d=CH[c-1]||{{}};
    cnEl.textContent=("0"+c).slice(-2);
    wmEl.textContent=d.wm||("0"+c).slice(-2);
    eyebrowEl.textContent=d.tag||"";
    eyebrowEl.className = d.tag ? "eyebrow" : "eyebrow empty";
    headEl.textContent=d.hl||"";
    subEl.textContent=d.sub||"";
    fit(headEl);
    for(var i=0;i<dots.length;i++){{ dots[i].className=(i===c-1)?'on':''; }}
    document.title='Deck · '+("0"+c).slice(-2)+' '+(d.tag||"");
  }}
  window.showSlide=show; window.showChapter=show;
  function ready(){{
    window.__deckReady=true;
  }}
  (function init(){{
    var m=/[?&](?:slide|chapter)=(\\d+)/.exec(location.search);
    show(m?m[1]:1);
    if(document.fonts && document.fonts.ready){{
      document.fonts.ready.then(function(){{ show(m?m[1]:1); ready(); }});
    }} else {{ ready(); }}
    setTimeout(ready, 1200);
  }})();
</script>
</body>
</html>
"""
