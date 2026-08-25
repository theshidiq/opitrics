"""Check that configuration and hardware are ready.

Reports whether each key is present and whether it works, without
ever printing the key itself.

    python scripts/doctor.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opitrics.config import ConfigError, settings  # noqa: E402

OK = "\033[32m✓\033[0m"
BAD = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"


def mask(key: str) -> str:
    """Show enough to identify a key, never enough to use it."""
    if not key:
        return "not set"
    if len(key) < 12:
        return "set (short — is it complete?)"
    return f"set — {key[:4]}…{key[-4:]} ({len(key)} chars)"


def check_env_file() -> bool:
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        print(f"{BAD} .env missing — copy .env.example to .env")
        return False
    print(f"{OK} .env found")
    return True


def check_youtube() -> bool:
    key = settings.youtube_api_key
    print(f"{OK if key else BAD} YOUTUBE_API_KEY  {mask(key)}")
    if not key:
        print("    → console.cloud.google.com → enable YouTube Data API v3 → API key")
        return False

    try:
        from googleapiclient.discovery import build

        yt = build("youtube", "v3", developerKey=key, cache_discovery=False)
        # Cheapest possible call (1 unit) that proves the key is live.
        yt.videos().list(part="id", id="dQw4w9WgXcQ").execute()
        print(f"{OK} YouTube API responded")
        return True
    except ImportError:
        print(f"{WARN} google-api-python-client not installed — skipped live check")
        return True
    except Exception as exc:  # noqa: BLE001 - surface whatever the API says
        print(f"{BAD} YouTube API rejected the key: {type(exc).__name__}")
        detail = str(exc)
        print(f"    {detail[:200]}")
        return False


def check_llm() -> bool:
    llm = settings.llm
    print(f"\n  provider: {llm.provider}")
    print(f"  model:    {llm.model}")
    print(f"  base_url: {llm.base_url}")

    if llm.provider == "ollama":
        print(f"{OK} Ollama needs no key (ensure `ollama serve` is running)")
    else:
        key_name = f"{llm.provider.upper()}_API_KEY"
        ok = bool(llm.api_key)
        print(f"{OK if ok else BAD} {key_name}  {mask(llm.api_key)}")
        if not ok:
            return False

    try:
        from openai import OpenAI

        client = OpenAI(api_key=llm.api_key, base_url=llm.base_url)
        resp = client.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": "Reply with the single word: ready"}],
            max_tokens=5,
        )
        reply = (resp.choices[0].message.content or "").strip()
        print(f"{OK} LLM responded: {reply!r}")
        return True
    except ImportError:
        print(f"{WARN} openai package not installed — skipped live check")
        return True
    except Exception as exc:  # noqa: BLE001 - surface whatever the API says
        print(f"{BAD} LLM call failed: {type(exc).__name__}")
        print(f"    {str(exc)[:200]}")
        return False


def check_torch() -> bool:
    try:
        import torch
    except ImportError:
        print(f"{WARN} torch not installed yet — run: pip install -r requirements.txt")
        return True

    want = settings.torch_device
    if want == "mps":
        if torch.backends.mps.is_available():
            print(f"{OK} torch MPS available (Apple silicon acceleration on)")
            return True
        print(f"{WARN} TORCH_DEVICE=mps but MPS unavailable — will fall back to CPU")
        return True
    if want == "cuda":
        avail = torch.cuda.is_available()
        print(f"{OK if avail else WARN} torch CUDA available: {avail}")
        return True
    print(f"{OK} torch device: {want}")
    return True


def main() -> int:
    print("\n\033[1mOpitrics\033[0m \033[2m· opinion metrics\033[0m\n\033[1mconfiguration check\033[0m\n")

    if not check_env_file():
        return 1

    print()
    yt_ok = check_youtube()

    try:
        llm_ok = check_llm()
    except ConfigError as exc:
        print(f"{BAD} {exc}")
        llm_ok = False

    print()
    check_torch()

    print()
    if yt_ok and llm_ok:
        print("\033[32mAll set.\033[0m Ready to fetch comments.\n")
        return 0
    print("\033[33mSome checks failed — see above.\033[0m\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
