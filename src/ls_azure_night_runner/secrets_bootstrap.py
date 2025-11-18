"""Diagnostic bootstrap for Night Runner secret configuration."""

from __future__ import annotations

import json
import os
from typing import Dict, List


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _has_value(name: str) -> bool:
    value = os.getenv(name)
    return bool(value and value.strip())


def log_night_runner_secret_status() -> Dict[str, object]:
    """
    Inspect Grok-related env vars and print a tagged status line.
    Returns the status dict.
    """

    api_enabled = _env_flag("GROK_ENABLE_API")
    has_key = _has_value("GROK_API_KEY")

    missing: List[str] = []
    # We record missing GROK_API_KEY even when the API flag is off to aid diagnostics,
    # but config_ok only fails if the API is enabled without a key.
    if not has_key:
        missing.append("GROK_API_KEY")

    status: Dict[str, object] = {
        "config_ok": not (api_enabled and not has_key),
        "api_enabled": api_enabled,
        "missing": missing,
        "has_key": has_key,
    }

    print(f"BOOTSTRAP_SECRETS_STATUS: {json.dumps(status, sort_keys=True)}")
    return status
