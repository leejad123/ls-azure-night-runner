"""Minimal GitHub PR helper for Night Runner."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests


def get_github_token() -> Optional[str]:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not set; cannot open PRs.")
        return None
    return token


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _existing_pr(owner: str, repo: str, head: str, token: str) -> Optional[Dict[str, Any]]:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    params = {"head": f"{owner}:{head}", "state": "open"}
    resp = requests.get(url, headers=_headers(token), params=params, timeout=15)
    if resp.status_code == 200:
        prs = resp.json()
        if prs:
            return prs[0]
    return None


def create_pr(owner: str, repo: str, head: str, base: str, title: str, body: str) -> Dict[str, Any]:
    token = get_github_token()
    if not token:
        return {"success": False, "message": "GITHUB_TOKEN not set"}

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    payload = {"title": title, "head": head, "base": base, "body": body}
    resp = requests.post(url, headers=_headers(token), json=payload, timeout=15)

    if resp.status_code == 201:
        pr = resp.json()
        return {
            "success": True,
            "number": pr.get("number"),
            "url": pr.get("html_url"),
            "message": "PR created",
        }

    if resp.status_code == 422:
        existing = _existing_pr(owner, repo, head, token)
        if existing:
            return {
                "success": True,
                "number": existing.get("number"),
                "url": existing.get("html_url"),
                "message": "PR already existed",
            }
        return {"success": False, "message": resp.text}

    return {
        "success": False,
        "message": f"GitHub PR API failed ({resp.status_code}): {resp.text}",
    }
