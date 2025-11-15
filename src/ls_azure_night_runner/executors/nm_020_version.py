"""Local executor for NM-020 (ls-backend version constant)."""

from __future__ import annotations

import subprocess
from pathlib import Path
import sys
from typing import Dict

from ..git_sandbox import branch_name_for_mission

Result = Dict[str, object]


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def run_nm_020(repo_root: Path, mission: Dict[str, object]) -> Result:
    repo = "ls-backend"
    branch = branch_name_for_mission(mission)
    result: Result = {
        "mission": mission.get("mission_id"),
        "repo": repo,
        "branch": branch,
        "version_file": "ls_backend/version.py",
        "success": False,
        "message": "",
        "committed": False,
    }

    git_dir = repo_root / ".git"
    if not git_dir.exists():
        result["message"] = "not a git repo"
        return result

    checkout = _run(["git", "checkout", branch], cwd=repo_root)
    if checkout.returncode != 0:
        result["message"] = (
            f"git checkout failed: {checkout.stderr.strip()}"
        )
        return result

    package_dir = repo_root / "ls_backend"
    if not package_dir.is_dir():
        result["message"] = "ls_backend package not found"
        return result

    version_path = package_dir / "version.py"
    if not version_path.exists():
        version_path.write_text(
            '"""Package version constant for ls-backend (Night Runner NM-020)."""\n'
            'version = "0.1.0"\n'
        )

    python_exec = Path(sys.executable)
    cmd = [python_exec.as_posix(), "-m", "compileall", "."]
    compile_run = _run(cmd, cwd=repo_root)
    if compile_run.returncode != 0:
        result["message"] = (
            f"compileall failed: {compile_run.stderr.strip()}"
        )
        return result

    status = _run(["git", "status", "--porcelain"], cwd=repo_root)
    if status.returncode != 0:
        result["message"] = f"git status failed: {status.stderr.strip()}"
        return result

    if not status.stdout.strip():
        result["success"] = True
        result["message"] = "NM-020 version check succeeded (no changes to commit)"
        return result

    add_run = _run(["git", "add", "ls_backend/version.py"], cwd=repo_root)
    if add_run.returncode != 0:
        result["message"] = f"git add failed: {add_run.stderr.strip()}"
        return result

    commit_run = _run(
        ["git", "commit", "-m", "NM-020: Night Runner version setup"],
        cwd=repo_root,
    )
    if commit_run.returncode != 0:
        result["message"] = f"git commit failed: {commit_run.stderr.strip()}"
        return result

    result["success"] = True
    result["committed"] = True
    result["message"] = "NM-020 version change committed locally"
    return result
