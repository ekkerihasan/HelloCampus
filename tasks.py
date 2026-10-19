"""Cross-platform task runner. The Makefile delegates here so Windows laptops without make work too.

Usage: python tasks.py <dev|backend|frontend|scrape|ingest|rag-eval|verify-models|validate-locality|test|smoke|tunnel>
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY = str(VENV_PY if VENV_PY.exists() else Path(sys.executable))
NPM = "npm.cmd" if os.name == "nt" else "npm"
BACKEND = [PY, "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]


def run(cmd: list[str], **kw) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=kw.pop("cwd", ROOT), **kw)


def dev() -> int:
    """Backend with reload plus the Vite dev server. Ctrl+C stops both."""
    procs = [
        subprocess.Popen(BACKEND + ["--reload", "--reload-dir", "backend"], cwd=ROOT),
        subprocess.Popen([NPM, "run", "dev"], cwd=ROOT / "frontend"),
    ]
    try:
        return procs[0].wait()
    except KeyboardInterrupt:
        return 0
    finally:
        for p in procs:
            p.terminate()


TASKS = {
    "dev": dev,
    "backend": lambda: run(BACKEND),
    "frontend": lambda: run([NPM, "run", "dev"], cwd=ROOT / "frontend"),
    "scrape": lambda: run([PY, "-m", "scraper.scrape_web"]) or run([PY, "-m", "scraper.scrape_github"]),
    "ingest": lambda: run([PY, "-m", "backend.rag.ingest"]),
    "rag-eval": lambda: run([PY, "-m", "scripts.rag_eval"]),
    "verify-models": lambda: run([PY, "-m", "scripts.verify_models"]),
    "validate-locality": lambda: run([PY, "-m", "backend.rag.locality"]),
    "validate-posts": lambda: run([PY, "-m", "backend.rag.posts"]),
    "test": lambda: run([PY, "-m", "pytest", "backend/tests", "-q"]),
    "smoke": lambda: run([PY, "-m", "scripts.smoke"]),
    "tunnel": lambda: run([PY, "-m", "scripts.tunnel"]),
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        print(__doc__)
        sys.exit(2)
    sys.exit(TASKS[sys.argv[1]]())
