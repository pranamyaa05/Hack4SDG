"""Run the local ReFit app. Optional .env parsing never executes shell code."""

import argparse
import os
from pathlib import Path

KEYS = {
    "REFIT_AI_PROVIDER",
    "REFIT_OLLAMA_URL",
    "REFIT_OLLAMA_MODEL",
    "REFIT_GEMINI_MODEL",
    "GEMINI_API_KEY",
    "REFIT_AI_TIMEOUT_SECONDS",
    "REFIT_DATA_DIR",
}


def load_env(path):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key.strip() not in KEYS:
            continue
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in {chr(34), chr(39)}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description="Run ReFit on this computer")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    load_env(root / ".env")
    print(f"ReFit: http://127.0.0.1:{args.port}/app/")
    uvicorn.run(
        "backend.main:app", host="127.0.0.1", port=args.port, reload=args.reload
    )


if __name__ == "__main__":
    main()
