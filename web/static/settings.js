// 设置页：读写 voice_path / speed / style / output_dir。
const $ = (id) => document.getElementById(id);
const STYLE_DESC = {
  ink:        ["🖋 墨水经典",   "电子杂志 · 流体背景 · 纯墨黑 + 暖米白"],
  indigo:     ["🌊 靛蓝瓷",     "电子杂志 · 流体背景 · 深靛蓝 + 瓷白"],
  forest:     ["🌿 森林墨",     "电子杂志 · 流体背景 · 森林绿 + 象牙"],
  kraft:      ["🍂 牛皮纸",     "电子杂志 · 流体背景 · 深棕 + 暖米"],
  dune:       ["🌙 沙丘",       "电子杂志 · 流体背景 · 炭灰 + 沙色"],
  ikb:        ["🔵 克莱因蓝",   "瑞士 · 网格点阵 · IKB 克莱因蓝"],
  lemon:      ["🟡 柠檬黄",     "瑞士 · 网格点阵 · 柠檬黄高亮"],
  lemongreen: ["🟢 柠檬绿",     "瑞士 · 网格点阵 · 荧光柠檬绿"],
  orange:     ["🟠 安全橙",     "瑞士 · 网格点阵 · 安全橙"],
};

let cur = null;

function showMsg(t, kind){ const m=$("msg"); m.textContent=t; m.className="msg show "+(kind||""); }

function baseName(p){ return (p||"").split("/").pop() || "—"; }

function renderStyles(sel){
  const grid = $("styles");
  grid.innerHTML = "";
  Object.keys(STYLE_DESC).forEach(key=>{
    const [name, desc] = STYLE_DESC[key];
    const card = document.createElement("div");
    card.className = "style-card" + (key===sel ? " sel" : "");
    card.dataset.key = key;
    card.innerHTML =
      `<div class="tick">✓</div>
       <div class="thumb th-${key}">${name.split(' ')[0]}</div>
       <div class="meta"><div class="name">${name}</div><div class="desc">${desc}</div></div>`;
    card.addEventListener("click", ()=>{
      document.querySelectorAll(".style-card").forEach(c=>c.classList.remove("sel"));
      card.classList.add("sel");
      cur.style = key;
    });
    grid.appendChild(card);
  });
}

async function load(){
  cur = await (await fetch("/api/settings")).json();
  $("voiceCur").textContent = "当前：" + (cur.voice_path || "—");
  $("speed").value = cur.speed;
  $("speedVal").textContent = Number(cur.speed).toFixed(2) + "×";
  $("output").value = cur.output_dir || "";
  renderStyles(cur.style);
}

$("speed").addEventListener("input", ()=>{
  $("speedVal").textContent = Number($("speed").value).toFixed(2) + "×";
});

$("uploadVoice").addEventListener("click", async ()=>{
  const f = $("voice").files[0];
  if(!f){ showMsg("请先选择 .wav 文件", "err"); return; }
  const fd = new FormData(); fd.append("file", f);
  showMsg("上传中…", "");
  try{
    const r = await fetch("/api/voice", {method:"POST", body: fd});
    if(!r.ok){ const e=await r.json().catch(()=>({})); throw new Error(e.detail||("HTTP "+r.status)); }
    const {voice_path} = await r.json();
    cur.voice_path = voice_path;
    $("voiceCur").textContent = "当前：" + voice_path;
    showMsg("音色已上传 ✓", "ok");
  }catch(e){ showMsg("上传失败：" + e.message, "err"); }
});

$("save").addEventListener("click", async ()=>{
  const body = {
    speed: Number($("speed").value),
    style: cur.style,
    output_dir: $("output").value.trim(),
    voice_path: cur.voice_path,
  };
  try{
    const r = await fetch("/api/settings", {method:"POST",
      headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
    if(!r.ok){ const e=await r.json().catch(()=>({})); throw new Error(e.detail||("HTTP "+r.status)); }
    showMsg("设置已保存 ✓", "ok");
  }catch(e){ showMsg("保存失败：" + e.message, "err"); }
});

load();
