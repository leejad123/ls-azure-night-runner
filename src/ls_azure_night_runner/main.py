"""Dry-run Night Runner orchestrator entry point."""

from __future__ import annotations

import sys

from pathlib import Path

from .config import PlannerConfig, get_spec_root
from .github_clone import clone_all
from .git_sandbox import create_local_sandbox_branches
from .missions import format_plan, load_missions, select_ready_missions
from .dispatcher import run_mission_executor
from .results import make_run_id, write_mission_result


def main() -> None:
    """Generate and print a dry-run Night Plan from local missions."""

    try:
        spec_root = get_spec_root()
    except RuntimeError as exc:  # surface misconfiguration cleanly
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)

    run_id = make_run_id()
    print(f"Night Runner run_id: {run_id}")

    config = PlannerConfig(spec_root=spec_root)
    missions = load_missions(config.spec_root)
    ready_missions = select_ready_missions(missions, config.max_missions)
    cloned_repos = clone_all()
    print(f"Cloned repos: {cloned_repos}")
    repos_root = Path("/workspace/repos")
    if not repos_root.exists():
        repos_root = Path(__file__).resolve().parents[2] / "workspace" / "repos"
    created = create_local_sandbox_branches(ready_missions, repos_root)
    print(f"Created sandbox branches (local only): {created}")

    for mission in ready_missions:
        exec_result = run_mission_executor(mission, repos_root)
        print(f"Executor result for {mission.get('mission_id')}: {exec_result}")
        write_mission_result(run_id, exec_result)
    plan_text = format_plan(ready_missions)
    print(plan_text)


if __name__ == "__main__":
    main()
