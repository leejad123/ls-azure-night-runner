"""Executor for NM-011: ensure Night Runner section in ls-scheduler README."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict

BLOCK = (
    "## Night Runner (Autonomous Night Work)\n\n"
    "- This service participates in the Living Shield Night Runner system, "
    "which runs in sandbox branches (`night/YYYYMMDD/...`) overnight and ships "
    "PRs for daytime review.\n"
    "- Night Runner operates under doctrine such as `ls-d100-night-v1-scope` "
    "and `ls-d101-night-sandbox-only`, ensuring factory/ops-scope work with "
    "no direct pushes to `main`, deployments, or release branches.\n"
    "- Every Night Runner change is small (capped files/LOC), validated in CI, "
    "reviewed/merged by humans, and auditable via Proof Chain entries and Night Reports.\n"
)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def sync_with_remote_sandbox(repo_root: Path, branch_name: str) -> tuple[bool, str]:
    fetch = _run(["git", "fetch", "origin", branch_name], cwd=repo_root)
    missing_remote = False
    if fetch.returncode != 0:
        err = fetch.stderr.strip().lower()
        if "couldn't find remote ref" in err or "could not find remote ref" in err:
            missing_remote = True
        else:
            return False, fetch.stderr.strip() or "git fetch failed"

    checkout = _run(["git", "checkout", branch_name], cwd=repo_root)
    if checkout.returncode != 0:
        return False, checkout.stderr.strip() or "git checkout failed"

    if missing_remote:
        return True, "no remote branch; using local sandbox"

    reset = _run([
        "git",
        "reset",
        "--hard",
        f"origin/{branch_name}",
    ], cwd=repo_root)
    if reset.returncode != 0:
        err = reset.stderr.strip().lower()
        if "unknown revision" in err or "not a valid object" in err:
            return True, "remote branch missing after fetch; using local only"
        return False, reset.stderr.strip() or "git reset failed"

    return True, "synced with remote sandbox"


def run_nm_011(repo_root: Path, branch_name: str) -> Dict[str, object]:
    result: Dict[str, object] = {
        "mission": "NM-011",
        "repo": "ls-scheduler",
        "branch": branch_name,
        "readme_file": "README.md",
        "success": False,
        "message": "",
        "committed": False,
        "pushed": False,
    }

    if not (repo_root / ".git").exists():
        result["message"] = "not a git repo"
        return result

    sync_ok, sync_msg = sync_with_remote_sandbox(repo_root, branch_name)
    if not sync_ok:
        result["message"] = f"NM-011 failed to sync sandbox branch: {sync_msg}"
        return result

    readme_path = repo_root / "README.md"
    if not readme_path.exists():
        readme_path.write_text("# ls-scheduler\n\n")

    content = readme_path.read_text()
    if "## Night Runner (Autonomous Night Work)" in content:
        result["success"] = True
        result["message"] = "NM-011 README already contains Night Runner section"
        return result

    with readme_path.open("a") as fh:
        if not content.endswith("\n\n"):
            fh.write("\n")
        fh.write("\n" + BLOCK + "\n")

    status = _run(["git", "status", "--porcelain", "README.md"], cwd=repo_root)
    if status.returncode != 0:
        result["message"] = f"git status failed: {status.stderr.strip()}"
        return result

    if not status.stdout.strip():
        result["success"] = True
        result["message"] = "NM-011 README unchanged"
        return result

    add_run = _run(["git", "add", "README.md"], cwd=repo_root)
    if add_run.returncode != 0:
        result["message"] = f"git add failed: {add_run.stderr.strip()}"
        return result

    commit_run = _run(
        ["git", "commit", "-m", "NM-011: add Night Runner section to ls-scheduler README"],
        cwd=repo_root,
    )
    if commit_run.returncode != 0:
        result["message"] = f"git commit failed: {commit_run.stderr.strip()}"
        return result

    result["committed"] = True
    result["success"] = True
    result["message"] = "NM-011 README section committed locally"

    if not branch_name.startswith("night/") or "NM-011" not in branch_name:
        result["message"] += " (push skipped: unexpected branch name)"
        return result

    push_run = _run(["git", "push", "origin", branch_name], cwd=repo_root)
    if push_run.returncode == 0:
        result["pushed"] = True
        result["message"] += f" and pushed origin/{branch_name}"
    else:
        result["message"] += f" but git push failed: {push_run.stderr.strip()}"

    return result
