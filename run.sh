#!/bin/bash
# 一键启动本机网页应用（uv 起 uvicorn）。
set -euo pipefail
cd "$(dirname "$0")"

UV="/Users/Admin/.hermes/bin/uv"
HOST="127.0.0.1"
PORT="${PORT:-8000}"

echo "文案→视频 · 启动中……"
echo "打开浏览器访问： http://${HOST}:${PORT}"
echo "（首次生成会加载 IndexTTS 2.0 模型，请耐心等待）"
echo

exec "$UV" run \
  --with fastapi \
  --with "uvicorn[standard]" \
  --with python-multipart \
  uvicorn server:app --host "$HOST" --port "$PORT"
