"""Mission loading and planning helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml

Mission = Dict[str, object]


def load_missions(spec_root: Path) -> List[Mission]:
    """Load all mission YAML files from ls-spec."""

    missions_dir = spec_root / "ops" / "night_missions"
    missions: List[Mission] = []
    for mission_path in sorted(missions_dir.glob("NM-*.yaml")):
        mission_data = yaml.safe_load(mission_path.read_text()) or {}
        if not isinstance(mission_data, dict):
            mission_data = {}
        mission_data.setdefault("mission_id", mission_path.stem)
        mission_data["_source"] = mission_path
        missions.append(mission_data)
    return missions


def select_ready_missions(missions: List[Mission], max_missions: int) -> List[Mission]:
    """Filter and prioritize ready, low-risk missions."""

    ready: List[tuple[int, str, Mission]] = []
    for mission in missions:
        status = mission.get("status")
        risk = mission.get("risk") or {}
        tier = risk.get("tier") if isinstance(risk, dict) else None
        if status != "ready" or tier != "L1":
            continue
        priority_value = mission.get("priority")
        priority = priority_value if isinstance(priority_value, int) else 50
        mission_id = mission.get("mission_id") or ""
        ready.append((priority, mission_id, mission))

    ready.sort(key=lambda item: (item[0], item[1]))
    return [entry[2] for entry in ready[:max_missions]]


def format_plan(missions: List[Mission]) -> str:
    """Return a multi-line string describing the dry-run plan."""

    lines = ["Night Plan (dry-run)"]
    if not missions:
        lines.append("  (no ready missions)")
        return "\n".join(lines)

    for mission in missions:
        mission_id = mission.get("mission_id", "UNKNOWN")
        title = mission.get("title") or "Untitled mission"
        priority_value = mission.get("priority")
        priority = priority_value if isinstance(priority_value, int) else 50
        repos = mission.get("repos")
        if isinstance(repos, list) and repos:
            repo_names = []
            for repo in repos:
                if isinstance(repo, dict):
                    repo_names.append(str(repo.get("name") or repo.get("repo") or "repo"))
                else:
                    repo_names.append(str(repo))
            repo_list = ", ".join(repo_names)
        else:
            repo_list = "no repos listed"
        lines.append(
            f"  - {mission_id} (priority={priority}) — {title} [{repo_list}]"
        )

    return "\n".join(lines)
