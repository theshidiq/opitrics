"""Configuration loaded from the environment.

Values come from `.env` (git-ignored). See `.env.example` for the
template and notes on where each key comes from.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or inconsistent."""


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _get_int(name: str, default: int) -> int:
    raw = _get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class LLMConfig:
    """Which LLM answers the narrative stage, and how to reach it.

    Every supported provider speaks the OpenAI chat-completions
    dialect, so the client code is identical across all three.
    """

    provider: str
    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> LLMConfig:
        provider = _get("LLM_PROVIDER", "deepseek").lower()

        if provider == "deepseek":
            return cls(
                provider=provider,
                api_key=_get("DEEPSEEK_API_KEY"),
                base_url=_get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                model=_get("DEEPSEEK_MODEL", "deepseek-chat"),
            )
        if provider == "openrouter":
            return cls(
                provider=provider,
                api_key=_get("OPENROUTER_API_KEY"),
                base_url=_get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                model=_get("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash"),
            )
        if provider == "ollama":
            # Local — no key needed, but the OpenAI client insists on one.
            return cls(
                provider=provider,
                api_key="ollama",
                base_url=_get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
                model=_get("OLLAMA_MODEL", "qwen2.5:7b"),
            )

        raise ConfigError(
            f"LLM_PROVIDER must be one of deepseek, openrouter, ollama — got {provider!r}"
        )


@dataclass(frozen=True)
class Settings:
    youtube_api_key: str
    llm: LLMConfig

    # Local models — downloaded on first use, no credentials.
    embedding_model: str
    sentiment_model: str
    zeroshot_model: str
    irony_model: str
    torch_device: str

    # Tuning
    embed_batch_size: int
    min_comment_words: int
    min_cluster_size: int
    samples_per_cluster: int
    max_llm_summaries: int

    # Paths
    database_path: Path
    output_dir: Path

    @classmethod
    def load(cls) -> Settings:
        return cls(
            youtube_api_key=_get("YOUTUBE_API_KEY"),
            llm=LLMConfig.from_env(),
            embedding_model=_get("EMBEDDING_MODEL", "BAAI/bge-m3"),
            sentiment_model=_get(
                "SENTIMENT_MODEL", "cardiffnlp/twitter-xlm-roberta-base-sentiment"
            ),
            zeroshot_model=_get(
                "ZEROSHOT_MODEL", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
            ),
            irony_model=_get("IRONY_MODEL", "cardiffnlp/twitter-roberta-base-irony"),
            torch_device=_get("TORCH_DEVICE", "mps"),
            embed_batch_size=_get_int("EMBED_BATCH_SIZE", 32),
            min_comment_words=_get_int("MIN_COMMENT_WORDS", 4),
            min_cluster_size=_get_int("MIN_CLUSTER_SIZE", 15),
            samples_per_cluster=_get_int("SAMPLES_PER_CLUSTER", 25),
            max_llm_summaries=_get_int("MAX_LLM_SUMMARIES", 40),
            database_path=ROOT / _get("DATABASE_PATH", "data/cache/opitrics.db"),
            output_dir=ROOT / _get("OUTPUT_DIR", "data/output"),
        )

    def require_youtube(self) -> str:
        """Return the YouTube key, or explain how to get one."""
        if not self.youtube_api_key:
            raise ConfigError(
                "YOUTUBE_API_KEY is not set.\n"
                "  1. console.cloud.google.com → create a project\n"
                "  2. Enable 'YouTube Data API v3'\n"
                "  3. Credentials → Create credentials → API key\n"
                "  4. Paste it into .env as YOUTUBE_API_KEY=..."
            )
        return self.youtube_api_key

    @property
    def workspace(self):
        """The output tree, as structured paths rather than raw strings."""
        from opitrics.paths import Workspace

        return Workspace(root=self.output_dir)

    def require_llm(self) -> LLMConfig:
        """Return the LLM config, or explain what is missing."""
        if self.llm.provider != "ollama" and not self.llm.api_key:
            key_name = f"{self.llm.provider.upper()}_API_KEY"
            raise ConfigError(
                f"{key_name} is not set (LLM_PROVIDER={self.llm.provider}).\n"
                f"Paste your key into .env as {key_name}=..."
            )
        return self.llm


settings = Settings.load()
