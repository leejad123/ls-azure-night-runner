"""Local git sandbox helpers."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

Mission = Dict[str, object]


def run_git(args: List[str], cwd: Path) -> bool:
    """Run a git command and report success."""

    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()}"
        )
        return False
    return True


def branch_name_for_mission(
    mission: Mission, agent: str = "codex", date: str | None = None
) -> str:
    mission_id = mission.get("mission_id", "mission")
    day = date or datetime.utcnow().strftime("%Y%m%d")
    return f"night/{day}/{mission_id}-{agent}"


def _checkout_default_branch(repo_path: Path) -> bool:
    for branch in ("main", "master"):
        if run_git(["checkout", branch], cwd=repo_path):
            return True
    print(f"Could not checkout main/master in {repo_path}; skipping sandbox branch.")
    return False


def create_local_sandbox_branches(
    missions: List[Mission], repos_root: Path
) -> List[Tuple[str, str]]:
    created: List[Tuple[str, str]] = []
    for mission in missions:
        branch = branch_name_for_mission(mission)
        repos = mission.get("repos")
        if not isinstance(repos, list):
            continue
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            repo_name = repo.get("name")
            if not repo_name:
                continue
            repo_path = repos_root / str(repo_name)
            if not (repo_path / ".git").exists():
                print(f"Repo {repo_name} missing under {repo_path}; clone skipped?")
                continue
            print(f"Preparing branch {branch} in {repo_path}...")
            run_git(["fetch", "--all", "--prune"], cwd=repo_path)
            if not _checkout_default_branch(repo_path):
                continue
            if run_git(["checkout", "-B", branch], cwd=repo_path):
                created.append((str(repo_name), branch))
    return created
