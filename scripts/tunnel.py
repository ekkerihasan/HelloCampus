"""Expose Vite over HTTPS using an installed native cloudflared or ngrok CLI."""
import os
import shutil
import subprocess


def main() -> int:
    port = int(os.getenv("PORT", "5173"))
    cloudflared = shutil.which("cloudflared")
    ngrok = shutil.which("ngrok.exe" if os.name == "nt" else "ngrok")
    if cloudflared:
        command = [cloudflared, "tunnel", "--url", f"http://localhost:{port}"]
    elif ngrok:
        command = [ngrok, "http", str(port)]
    else:
        print("Install the native cloudflared or ngrok CLI, then run python tasks.py tunnel.")
        print("Use the HTTPS URL printed by the tunnel on your phone and grant microphone/camera permissions.")
        return 1
    print("Starting HTTPS tunnel to the local app. Ctrl+C stops the tunnel.", flush=True)
    try:
        return subprocess.call(command)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
