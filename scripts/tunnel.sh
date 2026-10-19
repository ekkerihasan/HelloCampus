#!/usr/bin/env bash
# Exposes the Vite dev server (which proxies /api and /ws to the backend) over HTTPS,
# so a phone can grant camera and mic. Prefers cloudflared quick tunnels, falls back to ngrok.
set -euo pipefail
PORT="${PORT:-5173}"

if command -v cloudflared >/dev/null 2>&1; then
  echo "Starting cloudflared quick tunnel to http://localhost:${PORT}"
  exec cloudflared tunnel --url "http://localhost:${PORT}"
elif command -v ngrok >/dev/null 2>&1; then
  echo "Starting ngrok tunnel to http://localhost:${PORT} (needs: ngrok config add-authtoken <token>)"
  exec ngrok http "${PORT}"
else
  echo "Neither cloudflared nor ngrok found. Install one, or use the laptop browser (BUILD.md section 8)." >&2
  exit 1
fi
