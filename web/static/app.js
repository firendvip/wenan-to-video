// 主界面：任务列表（新增/轮询/取消）+ 设置弹窗。单并发由后端保证。
const $ = (id) => document.getElementById(id);
const baseName = (p) => (p || "").split("/").pop() || "—";
const fmtSpeed = (v) => (Number(v).toFixed(2).replace(/\.?0+$/, "")) + "×";

// ---------- 设置 ----------
let SET = null;

async function loadSettings() {
  SET = await (await fetch("/api/settings")).json();
  $("voiceName").textContent = baseName(SET.voice_path);
  $("speed").value = SET.speed;
  $("speedVal").textContent = fmtSpeed(SET.speed);
  $("output").value = SET.output_dir;
  const orient = $("orient");
  orient.innerHTML = "";
  Object.entries(SET.orientations).forEach(([k, label]) => {
    const enabled = !!SET.orientation_enabled[k];
    const w = document.createElement("label");
    if (!enabled) w.className = "disabled";
    w.innerHTML = `<input type="radio" name="orient" value="${k}" ${k === SET.orientation ? "checked" : ""} ${enabled ? "" : "disabled"}>`
      + `<span>${label}${enabled ? "" : "（暂未开放）"}</span>`;
    orient.appendChild(w);
  });
}

function openSettings() { loadSettings(); $("settingsMsg").className = "smsg"; $("settingsMsg").textContent = ""; $("settingsModal").hidden = false; }
function closeSettings() { $("settingsModal").hidden = true; }

async function saveSettings() {
  const orient = document.querySelector('input[name="orient"]:checked');
  const body = {
    speed: parseFloat($("speed").value),
    output_dir: $("output").value.trim(),
    orientation: orient ? orient.value : "portrait",
  };
  const m = $("settingsMsg");
  try {
    const r = await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error("HTTP " + r.status);
    m.className = "smsg ok"; m.textContent = "已保存 ✓";
    await loadSettings();
  } catch (e) { m.className = "smsg err"; m.textContent = "保存失败：" + e.message; }
}

async function uploadVoice(file) {
  const m = $("settingsMsg");
  const fd = new FormData(); fd.append("file", file);
  m.className = "smsg"; m.textContent = "上传中…";
  try {
    const r = await fetch("/api/voice", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status));
    $("voiceName").textContent = baseName(j.voice_path);
    m.className = "smsg ok"; m.textContent = "音色已更新 ✓";
  } catch (e) { m.className = "smsg err"; m.textContent = "上传失败：" + e.message; }
}

async function pickFolder() {
  const m = $("settingsMsg");
  try {
    const j = await (await fetch("/api/pick-folder", { method: "POST" })).json();
    if (j.path) { $("output").value = j.path; m.className = "smsg ok"; m.textContent = "已选择文件夹"; }
  } catch (e) { m.className = "smsg err"; m.textContent = "选择失败：" + e.message; }
}

// ---------- 任务列表 ----------
function taskItem(t) {
  const el = document.createElement("div");
  el.className = "task " + t.status;
  const badgeText = { queued: "排队中", running: "进行中", done: "已完成", error: "出错", canceled: "已取消" }[t.status] || t.status;
  let body = `<div class="t-text">${escapeHtml(t.short || "（空）")}</div>`;
  body += `<div class="t-row"><span class="badge ${t.status}">${badgeText}</span>`;
  if (t.status === "running" || t.status === "queued") body += `<span>${escapeHtml(t.message || "")}${t.percent ? " · " + Math.round(t.percent) + "%" : ""}</span>`;
  body += `</div>`;
  if (t.status === "running" || t.status === "queued")
    body += `<div class="bar-wrap"><i style="width:${Math.max(2, t.percent || 0)}%"></i></div>`;
  if (t.status === "done" && t.saved_path)
    body += `<div class="saved">已保存 <b>✓</b> ${escapeHtml(t.saved_path)}</div>`;
  if (t.status === "error")
    body += `<div class="errline">${escapeHtml(t.error || "未知错误")}</div>`;

  const actions = document.createElement("div"); actions.className = "t-actions";
  if (t.status === "running" || t.status === "queued") {
    const b = document.createElement("button"); b.className = "btn ghost sm"; b.textContent = "取消";
    b.onclick = () => cancelTask(t.id); actions.appendChild(b);
  }
  if (t.status === "done" && t.saved_path) {
    const b = document.createElement("button"); b.className = "btn ghost sm"; b.textContent = "在访达中显示";
    b.onclick = () => reveal(t.saved_path); actions.appendChild(b);
  }
  const main = document.createElement("div"); main.className = "t-main"; main.innerHTML = body;
  el.appendChild(main); el.appendChild(actions);
  return el;
}

function escapeHtml(s) { return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

async function refreshTasks() {
  try {
    const { tasks } = await (await fetch("/api/tasks")).json();
    const box = $("tasks");
    if (!tasks.length) { box.innerHTML = '<div class="empty">还没有任务。粘贴文案，点「添加任务」。</div>'; return; }
    box.innerHTML = "";
    tasks.forEach((t) => box.appendChild(taskItem(t)));
  } catch (e) { /* keep */ }
}

async function addTask() {
  const text = $("text").value.trim();
  if (!text) { $("text").focus(); return; }
  $("addTask").disabled = true;
  try {
    const r = await fetch("/api/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || ("HTTP " + r.status)); }
    $("text").value = ""; $("charcount").textContent = "0 字";
    await refreshTasks();
  } catch (e) { alert("添加失败：" + e.message); }
  $("addTask").disabled = false;
}

async function cancelTask(id) {
  try { await fetch(`/api/tasks/${id}/cancel`, { method: "POST" }); await refreshTasks(); } catch (e) { /* */ }
}
async function reveal(path) {
  try { await fetch("/api/reveal", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) }); } catch (e) { /* */ }
}

// ---------- 事件 ----------
$("openSettings").onclick = openSettings;
$("closeSettings").onclick = closeSettings;
$("settingsModal").addEventListener("click", (e) => { if (e.target === $("settingsModal")) closeSettings(); });
$("saveSettings").onclick = saveSettings;
$("voiceBtn").onclick = () => $("voiceInput").click();
$("voiceInput").onchange = (e) => { if (e.target.files[0]) uploadVoice(e.target.files[0]); };
$("pickFolder").onclick = pickFolder;
$("speed").oninput = () => { $("speedVal").textContent = fmtSpeed($("speed").value); };
$("addTask").onclick = addTask;
$("text").addEventListener("input", () => { $("charcount").textContent = $("text").value.length + " 字"; });
$("text").addEventListener("keydown", (e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") addTask(); });

loadSettings();
refreshTasks();
setInterval(refreshTasks, 1300);
