#!/bin/bash
# 一键启动本机网页应用（uv 起 uvicorn）。
set -euo pipefail
cd "$(dirname "$0")"

# uv 解析：环境变量 UV_BIN > 常见安装位置 > PATH
UV="${UV_BIN:-}"
if [ -z "$UV" ]; then
  for c in "$HOME/.hermes/bin/uv" "$HOME/.local/bin/uv"; do
    [ -x "$c" ] && UV="$c" && break
  done
fi
[ -z "$UV" ] && UV="$(command -v uv || true)"
[ -z "$UV" ] && { echo "错误：找不到 uv，请安装或设 UV_BIN 环境变量"; exit 1; }
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
