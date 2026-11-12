"""Central configuration. Override any value with an environment variable."""
from __future__ import annotations

import logging
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "google/gemma-4-e4b")
LLM_CONTEXT_TOKENS = int(os.getenv("LLM_CONTEXT_TOKENS", "16000"))  # model context window configured in LM Studio
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "180"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "3500"))      # output budget per call
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))       # extra attempts after the first
LOG_DIR = Path(os.getenv("LOG_DIR", ROOT / "logs"))
LOG_FULL_PROMPT = os.getenv("LOG_FULL_PROMPT", "0") == "1"      # else only the last user message is logged
CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "6000"))     # draft text per extraction call

DRAFTS_DIR = Path(os.getenv("DRAFTS_DIR", ROOT / "data" / "drafts"))
CORPUS_PATH = Path(os.getenv("CORPUS_PATH", ROOT / "data" / "corpus" / "corpus.json"))


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
