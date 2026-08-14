#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文案→视频 本机网页应用后端（FastAPI）。
主界面=任务列表：可新增多任务；单并发（一次只跑 1 个）；进行中的任务可取消。"""
from __future__ import annotations
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine import config, run_job

app = FastAPI(title="文案→视频")

WEB_DIR = os.path.join(config.WEBAPP_DIR, "web")
RUN_JOB_PY = os.path.join(config.HERE, "run_job.py")
os.makedirs(config.JOBS_DIR, exist_ok=True)
os.makedirs(config.UPLOADS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(WEB_DIR, "static")), name="static")


# ---------------- settings ----------------
def default_settings() -> dict:
    return {
        "voice_path": config.DEFAULT_VOICE,
        "speed": config.SPEED_DEFAULT,
        "orientation": config.ORIENTATION_DEFAULT,
        "output_dir": config.DEFAULT_OUTPUT_DIR,
    }


def _coerce_orientation(v: str | None) -> str:
    v = (v or "").strip()
    if v in config.ORIENTATIONS and config.ORIENTATION_ENABLED.get(v):
        return v
    return config.ORIENTATION_DEFAULT      # 横屏暂未开发 → 落回竖屏


def load_settings() -> dict:
    s = default_settings()
    if os.path.isfile(config.SETTINGS_PATH):
        try:
            s.update(json.load(open(config.SETTINGS_PATH, encoding="utf-8")))
        except Exception:
            pass
    s["speed"] = config.clamp_speed(s.get("speed"))
    s["orientation"] = _coerce_orientation(s.get("orientation"))
    if not s.get("voice_path"):
        s["voice_path"] = config.DEFAULT_VOICE
    if not s.get("output_dir"):
        s["output_dir"] = config.DEFAULT_OUTPUT_DIR
    s.pop("style", None)                    # 单一固定风格，不作为用户设置
    return s


def save_settings(s: dict) -> None:
    tmp = config.SETTINGS_PATH + ".tmp"
    json.dump(s, open(tmp, "w"), ensure_ascii=False, indent=2)
    os.replace(tmp, config.SETTINGS_PATH)


# ---------------- pages ----------------
@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


# ---------------- settings API ----------------
class SettingsIn(BaseModel):
    voice_path: str | None = None
    speed: float | None = None
    orientation: str | None = None
    output_dir: str | None = None


@app.get("/api/settings")
def api_get_settings():
    return {
        **load_settings(),
        "orientations": config.ORIENTATIONS,
        "orientation_enabled": config.ORIENTATION_ENABLED,
        "speed_min": config.SPEED_MIN, "speed_max": config.SPEED_MAX,
    }


@app.post("/api/settings")
def api_set_settings(body: SettingsIn):
    s = load_settings()
    if body.voice_path is not None:
        s["voice_path"] = body.voice_path.strip() or config.DEFAULT_VOICE
    if body.speed is not None:
        s["speed"] = config.clamp_speed(body.speed)
    if body.orientation is not None:
        s["orientation"] = _coerce_orientation(body.orientation)
    if body.output_dir is not None:
        s["output_dir"] = os.path.expanduser(body.output_dir.strip() or config.DEFAULT_OUTPUT_DIR)
    save_settings(s)
    return {"ok": True, "settings": s}


@app.post("/api/voice")
async def api_voice(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(400, "请上传 .wav 音色文件")
    dst = os.path.join(config.UPLOADS_DIR, f"voice_{int(time.time())}.wav")
    with open(dst, "wb") as f:
        f.write(await file.read())
    s = load_settings()
    s["voice_path"] = dst
    save_settings(s)
    return {"ok": True, "voice_path": dst}


@app.post("/api/pick-folder")
def api_pick_folder():
    """调用 macOS 原生「选择文件夹」，返回 POSIX 路径。"""
    script = 'POSIX path of (choose folder with prompt "选择视频生成文件夹")'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    path = r.stdout.strip().rstrip("/")
    if r.returncode == 0 and path:
        return {"path": path}
    return JSONResponse({"canceled": True})


# ---------------- 任务队列（单并发，可取消）----------------
TASKS: dict[str, dict] = {}
TASK_ORDER: list[str] = []
LOCK = threading.Lock()
Q: "queue.Queue[str]" = queue.Queue()
CURRENT: dict = {"id": None, "proc": None}


def _job_dir(tid: str) -> str:
    return os.path.join(config.JOBS_DIR, tid)


def _worker() -> None:
    while True:
        tid = Q.get()
        with LOCK:
            t = TASKS.get(tid)
            if not t or t["status"] == "canceled":
                if t:
                    t["status"] = "canceled"
                continue
            t["status"] = "running"
            s = t["settings"]
        job_dir = _job_dir(tid)
        os.makedirs(job_dir, exist_ok=True)
        run_job.set_status(job_dir, stage="queued", percent=0, message="开始…",
                           done=False, error=None, saved_path=None, video_url=None)
        cmd = [sys.executable, RUN_JOB_PY, t["text"], tid,
               s["voice_path"], str(s["speed"]), config.STYLE_DEFAULT, s["output_dir"]]
        try:
            proc = subprocess.Popen(cmd, cwd=config.WEBAPP_DIR, start_new_session=True)
        except Exception as e:
            with LOCK:
                t["status"] = "error"; t["error"] = f"启动失败：{e}"
            Q.task_done(); continue
        with LOCK:
            CURRENT["id"] = tid; CURRENT["proc"] = proc
        proc.wait()
        st = run_job.get_status(job_dir)
        with LOCK:
            CURRENT["id"] = None; CURRENT["proc"] = None
            if t["status"] == "canceled":
                pass
            elif st.get("stage") == "done" and st.get("saved_path"):
                t["status"] = "done"; t["saved_path"] = st.get("saved_path")
            elif st.get("error"):
                t["status"] = "error"; t["error"] = st.get("error")
            else:
                t["status"] = "error"; t["error"] = "任务中断（进程异常退出）"
        Q.task_done()


threading.Thread(target=_worker, daemon=True).start()


class TaskIn(BaseModel):
    text: str


def _public(t: dict) -> dict:
    d = {"id": t["id"], "text": t["text"], "short": t["short"],
         "status": t["status"], "created": t["created"],
         "percent": 0, "message": "", "error": t.get("error"),
         "saved_path": t.get("saved_path"), "video_url": None}
    st = run_job.get_status(_job_dir(t["id"])) if os.path.isdir(_job_dir(t["id"])) else {}
    d["percent"] = st.get("percent", 0)
    d["message"] = st.get("message", "")
    if t["status"] == "done":
        d["percent"] = 100
        d["video_url"] = st.get("video_url")
        d["saved_path"] = t.get("saved_path") or st.get("saved_path")
    return d


@app.post("/api/tasks")
def api_add_task(body: TaskIn):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "文案不能为空")
    tid = uuid.uuid4().hex[:12]
    short = text.replace("\n", " ").strip()[:28]
    with LOCK:
        TASKS[tid] = {"id": tid, "text": text, "short": short, "status": "queued",
                      "created": time.time(), "error": None, "saved_path": None,
                      "settings": load_settings()}
        TASK_ORDER.append(tid)
    Q.put(tid)
    return {"id": tid}


@app.get("/api/tasks")
def api_list_tasks():
    with LOCK:
        items = [TASKS[i] for i in TASK_ORDER if i in TASKS]
    return {"tasks": [_public(t) for t in reversed(items)]}


@app.post("/api/tasks/{tid}/cancel")
def api_cancel_task(tid: str):
    with LOCK:
        t = TASKS.get(tid)
        if not t:
            raise HTTPException(404, "任务不存在")
        if t["status"] in ("done", "error", "canceled"):
            return {"ok": True, "status": t["status"]}
        t["status"] = "canceled"
        proc = CURRENT["proc"] if CURRENT["id"] == tid else None
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            time.sleep(0.4)
            if proc.poll() is None:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
    return {"ok": True, "status": "canceled"}


# ---------------- preview / reveal ----------------
@app.get("/api/jobs/{job_id}/preview")
def api_preview(job_id: str):
    mp4 = os.path.join(_job_dir(job_id), "final.mp4")
    if not os.path.isfile(mp4):
        raise HTTPException(404, "视频未就绪")
    return FileResponse(mp4, media_type="video/mp4")


class RevealIn(BaseModel):
    path: str


@app.post("/api/reveal")
def api_reveal(body: RevealIn):
    p = os.path.expanduser((body.path or "").strip())
    if not p or not os.path.isfile(p):
        raise HTTPException(404, "文件不存在")
    subprocess.run(["open", "-R", p], check=False)
    return {"ok": True}
