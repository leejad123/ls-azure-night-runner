"""Helpers to ensure ls-spec is available locally."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Tuple


def get_github_token() -> str | None:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not set; cannot auto-clone ls-spec.")
        return None
    return token


def _clone_ls_spec(token: str, target: Path) -> Tuple[bool, str]:
    url = f"https://{token}:x-oauth-basic@github.com/leejad123/ls-spec.git"
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False, result.stderr.strip() or "git clone failed"
    return True, "ls-spec cloned"


def ensure_spec_repo(spec_root: Path) -> None:
    """Ensure the ls-spec repo exists with night missions."""

    missions_dir = spec_root / "ops" / "night_missions"
    if missions_dir.is_dir():
        return

    parent = spec_root.parent
    parent.mkdir(parents=True, exist_ok=True)

    if spec_root.exists():
        print(f"Removing existing ls-spec at {spec_root} before bootstrap...")
        try:
            shutil.rmtree(spec_root)
        except OSError as exc:
            print(f"Warning: failed to clear existing ls-spec at {spec_root}: {exc}")
            return

    token = get_github_token()
    if not token:
        return

    print(f"Bootstrapping ls-spec into {spec_root}...")
    ok, message = _clone_ls_spec(token, spec_root)
    if not ok:
        print(f"Warning: {message}")
        return

    print("ls-spec clone completed.")
    if not missions_dir.is_dir():
        print(
            f"Warning: ls-spec cloned into {spec_root} but ops/night_missions missing."
        )
