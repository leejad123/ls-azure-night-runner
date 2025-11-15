"""Mission result logging utilities."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def get_results_root() -> Path:
    preferred = Path("/workspace/results")
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError:
        fallback = Path(__file__).resolve().parents[2] / "workspace" / "results"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def make_run_id() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def write_mission_result(run_id: str, mission_result: Dict[str, Any]) -> None:
    results_root = get_results_root()
    path = results_root / f"mission_results_{run_id}.jsonl"
    enriched = dict(mission_result)
    enriched["run_id"] = run_id
    enriched["timestamp"] = datetime.utcnow().isoformat() + "Z"
    with path.open("a") as fh:
        fh.write(json.dumps(enriched) + "\n")
