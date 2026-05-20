"""Anthropic API client setup."""

import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

DEFAULT_MODEL = "claude-sonnet-4-6"


def _load_env() -> None:
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")


def get_client() -> Anthropic:
    _load_env()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or key == "your-key-here":
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key "
            "from https://console.anthropic.com/."
        )
    return Anthropic(api_key=key)


def get_model() -> str:
    _load_env()
    return os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)
