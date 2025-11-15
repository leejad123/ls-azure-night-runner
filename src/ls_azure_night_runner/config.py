"""Configuration helpers for the Night Runner orchestrator."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlannerConfig:
    """Minimal configuration for the dry-run planner."""

    spec_root: Path
    max_missions: int = 5


def get_spec_root() -> Path:
    """Resolve the ls-spec path from env or default relative location."""

    env_override = os.getenv("LS_SPEC_ROOT")
    if env_override:
        candidate = Path(env_override).expanduser().resolve()
    else:
        here = Path(__file__).resolve()
        candidates = [here.parents[2] / "ls-spec"]
        if len(here.parents) >= 4:
            candidates.append(here.parents[3] / "ls-spec")
        candidate = next((path for path in candidates if path.exists()), candidates[0])

    missions_dir = candidate / "ops" / "night_missions"
    if not candidate.exists():
        raise RuntimeError(
            f"ls-spec repo not found at {candidate}. Set LS_SPEC_ROOT to override."
        )
    if not missions_dir.is_dir():
        raise RuntimeError(
            f"ls-spec at {candidate} missing ops/night_missions; check your workspace."
        )

    return candidate
