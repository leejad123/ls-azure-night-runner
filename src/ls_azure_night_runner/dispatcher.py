"""Mission executor dispatcher."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .executors.nm_020_version import run_nm_020
from .git_sandbox import branch_name_for_mission

EXECUTORS = {
    "NM-020": run_nm_020,
}


def get_executor(mission_id: str):
    return EXECUTORS.get(mission_id)


def run_mission_executor(mission: Dict[str, Any], repos_root: Path):
    mission_id = mission.get("mission_id")
    executor = get_executor(mission_id)
    if executor is None:
        return {"mission": mission_id, "skipped": True, "reason": "no executor"}

    repos = mission.get("repos") or []
    if not isinstance(repos, list):
        return {"mission": mission_id, "skipped": True, "reason": "invalid repos"}

    results = []
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        repo_name = repo.get("name")
        if not repo_name:
            continue
        repo_path = repos_root / repo_name
        result = executor(repo_path, mission)
        results.append(result)

    if not results:
        return {"mission": mission_id, "skipped": True, "reason": "no valid repos"}
    return results[0]
