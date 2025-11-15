"""Utilities for cloning Living Shield GitHub repositories."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List

REPOS_TO_CLONE = ["ls-spec", "ls-backend", "ls-scheduler", "ls-devops"]


def get_github_token() -> str | None:
    """Return the GitHub token from the environment (if any)."""

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN is not set; cloning public-only.")
        return None
    return token


def _build_repo_url(repo: str, token: str | None) -> str:
    base = f"github.com/leejad123/{repo}.git"
    if token:
        return f"https://{token}:x-oauth-basic@{base}"
    return f"https://{base}"


def clone_repo(repo: str, dest: Path) -> bool:
    """Clone the given repo into dest; return True on success."""

    if dest.exists():
        print(f"Repo {repo} already present at {dest}, skipping clone.")
        return True

    token = get_github_token()
    url = _build_repo_url(repo, token)
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"Cloning {repo} into {dest}...")
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        print(f"Cloned {repo} successfully.")
        return True

    print(
        f"Failed to clone {repo} (exit {result.returncode}): {result.stderr.strip()}"
    )
    return False


def _resolve_workspace_root() -> Path:
    preferred = Path("/workspace/repos")
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError:
        fallback = Path.cwd() / "workspace" / "repos"
        fallback.mkdir(parents=True, exist_ok=True)
        print(
            "Warning: could not create /workspace/repos; using local workspace at"
            f" {fallback}"
        )
        return fallback


def clone_all() -> List[str]:
    """Clone all required repos and return the list that succeeded."""

    root = _resolve_workspace_root()
    cloned: List[str] = []
    for repo in REPOS_TO_CLONE:
        dest = root / repo
        if clone_repo(repo, dest):
            cloned.append(repo)
    return cloned
