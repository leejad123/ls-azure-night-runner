"""Mission executor dispatcher."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .executors.nm_010_backend_readme import run_nm_010
from .executors.nm_011_scheduler_readme import run_nm_011
from .executors.nm_020_version import run_nm_020
from .executors.nm_900_grok_stub import run_nm_900
from .executors.nm_901_grok_api import run_nm_901
from .executors.nm_902_grok_review import run_nm_902
from .executors.nm_903_grok_apply import run_nm_903
from .executors.nm_904_grok_pr import run_nm_904
from .git_sandbox import branch_name_for_mission
from grok_worker import GrokWorker, GrokWorkerConfig
from worker_logging import print_worker_result_log_record
from worker_protocol import DoctrineSnapshot, MissionBundle, WorkerLimits, WorkerResult


def _grok_credentials_from_env() -> Dict[str, object]:
    api_key = os.getenv("GROK_API_KEY")
    base_url = os.getenv("GROK_API_BASE_URL")
    model = os.getenv("GROK_MODEL")
    missing = []
    if not api_key:
        missing.append("GROK_API_KEY")
    return {
        "api_key": api_key,
        "api_base_url": base_url,
        "model": model,
        "missing": missing,
    }


def _resolve_repo_path(provided_repo_root: Path) -> Path:
    """Use provided repo path when it looks valid, else fall back to local source checkout."""

    if (provided_repo_root / ".git").exists():
        return provided_repo_root
    return Path(__file__).resolve().parents[3]


def _resolve_execution_dir(repo_path: Path) -> Optional[Tuple[Path, str]]:
    env_dir = os.getenv("LS_EXECUTION_DIR")
    if env_dir:
        path = Path(env_dir)
        if not path.is_absolute():
            path = repo_path / path
        if path.is_dir():
            return path, path.name
    runs_root = repo_path / "runs"
    if not runs_root.exists():
        return None
    date_dirs = sorted([d for d in runs_root.iterdir() if d.is_dir()], reverse=True)
    for date_dir in date_dirs:
        exec_dirs = sorted([d for d in date_dir.iterdir() if d.is_dir()], reverse=True)
        if exec_dirs:
            return exec_dirs[0], exec_dirs[0].name
    return None


def _load_snapshot_records(snapshot_dir: Path) -> list[dict]:
    """
    Load snapshot records from a directory.

    Supports:
    - *.csv files parsed with csv.DictReader
    - *.json files containing either a list[dict] or an object with a "rows" list.
    """
    records: list[dict] = []
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        return records

    for path in sorted(snapshot_dir.iterdir()):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        try:
            if suffix == ".csv":
                with path.open("r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if isinstance(row, dict):
                            records.append(row)
            elif suffix == ".json":
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            records.append(item)
                elif isinstance(data, dict):
                    rows = data.get("rows")
                    if isinstance(rows, list):
                        for item in rows:
                            if isinstance(item, dict):
                                records.append(item)
        except Exception:
            # Tolerate bad files; skip on error.
            continue

    return records


def run_nm_910_memory_probe(
    repo_root: Path, mission: Dict[str, object], branch_name: str
) -> Dict[str, object]:
    """
    Run Grok in read-only memory probe mode and capture answers for ingestion.
    """

    repo_path = _resolve_repo_path(repo_root)
    doctrine_version = (
        str(mission.get("doctrine_version"))
        if isinstance(mission.get("doctrine_version"), str)
        else "unknown"
    )

    mission_id = "NM-910"
    mission_title = "Development Process Probe – Night Runner & Doctrine"
    goal_text = "\n".join(
        [
            "You are running NM-910: a read-only development-process probe for the Living Shield Night Runner.",
            "",
            "Your job is to analyze recent Night Runner / Grok activity and doctrine alignment; do not change code.",
            "",
            "Use all available memory blocks (recent_context, topic_context, worker_context, trend_context, thread_context) and RAG (if present) to answer. You also have spec_decisions (ls-spec/Decisions_Log_Short.md) and sprint_log (ls-spec/ops/SPRINT_LOG_*.md); treat them as primary context alongside worker history.",
            "",
            "1) Recent behavior:",
            "   - Summarize what happened in the most recent Night Runner execution(s).",
            "   - Note which missions ran (e.g., NM-900..NM-904) and whether they appear to have succeeded or failed.",
            "   - Incorporate any recent sprint_log/spec_decisions entries that capture shipped changes (especially around Grok/NM-910 or pipeline behavior).",
            "",
            "2) Failures and anomalies:",
            "   - Identify recurring errors, anomalies, or edge cases visible in worker_results or logs (e.g., repeated HTTP errors, doctrine validation failures, or other patterns).",
            "   - Cross-check anomalies against sprint_log/spec_decisions to see if they were noted or partially addressed.",
            "",
            "3) Doctrine and spec alignment:",
            "   - Call out behavior that suggests missing or unclear doctrine rules, or possible drift from the current spec.",
            "   - Use spec_decisions and sprint_log to ground which doctrines/decisions are active (e.g., offline_first, scheduler_authoritative) and whether current behavior aligns or drifts.",
            "   - If there are gaps, describe them as concrete, testable observations, not as invented features.",
            "",
            "4) Next safe steps:",
            "   - Propose 1–3 safe, small, concrete next steps for the development process (such as a validation mission, a spec clarification, or a specific test to add).",
            "   - Keep these suggestions within the existing scope and doctrine; do not expand the mission or invent new features.",
            "",
            "5) Candidate doctrine lesson:",
            "   - Suggest one candidate doctrine lesson or decision that might be worth logging (as plain text) based on what you observed.",
            "",
            "Hard constraints:",
            "- Read-only: do NOT propose or apply patches, edit files, or create PRs.",
            "- No spec invention or scope expansion: refine behavior, do not invent features.",
            "- Do not make claims about real client/building/treatment/profit data; focus on Night Runner, doctrine, and the development pipeline itself.",
        ]
    )

    limits = WorkerLimits(
        max_patch_bytes=4000,
        max_files=0,
        max_runtime_seconds=120,
        max_tokens=None,
    )

    bundle = MissionBundle(
        mission_id=mission_id,
        mission_title=mission_title,
        repo_name="ls-azure-night-runner",
        repo_path=repo_path,
        branch_name=branch_name,
        goal=goal_text,
        doctrine=DoctrineSnapshot(
            source="ls-spec/DOCTRINE.yaml",
            version=doctrine_version,
            digest=None,
            text=None,
        ),
        files=[],
        limits=limits,
        metadata={
            "mission_id": mission_id,
            "branch_name": branch_name,
            "read_only": True,
            "memory_probe": True,
        },
    )

    creds = _grok_credentials_from_env()
    if creds["missing"]:
        worker_result = WorkerResult(
            mission_id=mission_id,
            worker_name="grok",
            status="error",
            success=False,
            patch=None,
            tests_run=[],
            tests_passed=[],
            tests_failed={},
            error_message="probe_unavailable",
            raw_response=None,
            metadata={
                "probe_unavailable": True,
                "missing_credentials": creds["missing"],
                "api_base_url": creds.get("api_base_url"),
                "model": creds.get("model"),
            },
        )
        print_worker_result_log_record(bundle, worker_result)
        return {
            "mission": mission_id,
            "repo": "ls-azure-night-runner",
            "branch": branch_name,
            "success": False,
            "message": "Grok credentials missing; probe_unavailable recorded.",
            "worker_name": worker_result.worker_name,
            "worker_status": worker_result.status,
            "worker_success": worker_result.success,
            "worker_mode": "api",
        }

    config = GrokWorkerConfig.from_env()
    config.mode = "api"
    config.enable_api = True

    worker = GrokWorker(config)
    worker_result = worker.run(bundle)
    if worker_result.error_message and any(code in worker_result.error_message for code in {"401", "403"}):
        if not isinstance(worker_result.metadata, dict):
            worker_result.metadata = {}
        worker_result.metadata["probe_unavailable"] = True
        worker_result.metadata["missing_credentials"] = creds.get("missing") or []
        worker_result.metadata["auth_error"] = True
        worker_result.error_message = "probe_unavailable"
        worker_result.status = "error"
        worker_result.success = False
    print_worker_result_log_record(bundle, worker_result)

    message = "Memory probe executed in read-only mode."
    if worker_result.error_message:
        message += f" Details: {worker_result.error_message}"

    return {
        "mission": mission_id,
        "repo": "ls-azure-night-runner",
        "branch": branch_name,
        "success": bool(worker_result.success),
        "message": message,
        "worker_name": worker_result.worker_name,
        "worker_status": worker_result.status,
        "worker_success": worker_result.success,
        "worker_mode": config.mode,
    }


def run_nm_920_profit_snapshot(
    repo_root: Path, mission: Dict[str, object], branch_name: str
) -> Dict[str, object]:
    """
    Read profit snapshot files and write a cohort-level margin summary for NM-920.

    This mission is read-only with respect to repos and external systems.
    It only writes a summary JSON file into the execution run directory.
    """

    repo_path = _resolve_repo_path(repo_root)
    exec_info = _resolve_execution_dir(repo_path)
    if exec_info is None:
        message = "NM-920: no execution directory found; skipping profit snapshot summary."
        return {
            "mission": "NM-920",
            "repo": str(repo_path.name),
            "branch": branch_name,
            "success": False,
            "message": message,
        }

    run_dir, execution_name = exec_info

    snapshot_dir = repo_path / "profit_snapshots"
    records = _load_snapshot_records(snapshot_dir)
    if not records:
        message = "NM-920: no profit snapshots found; nothing to summarize."
        return {
            "mission": "NM-920",
            "repo": str(repo_path.name),
            "branch": branch_name,
            "success": True,
            "message": message,
        }

    cohorts: Dict[str, Dict[str, float]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        cohort = str(rec.get("cohort") or "").strip() or "unknown"
        revenue_raw = rec.get("revenue", 0)
        cost_raw = rec.get("direct_cost", 0)
        try:
            revenue = float(revenue_raw)
        except Exception:
            revenue = 0.0
        try:
            direct_cost = float(cost_raw)
        except Exception:
            direct_cost = 0.0

        agg = cohorts.setdefault(
            cohort,
            {"revenue": 0.0, "direct_cost": 0.0},
        )
        agg["revenue"] += revenue
        agg["direct_cost"] += direct_cost

    summary_cohorts: list[Dict[str, object]] = []
    for cohort, agg in cohorts.items():
        revenue = float(agg.get("revenue") or 0.0)
        direct_cost = float(agg.get("direct_cost") or 0.0)
        gross_margin = revenue - direct_cost
        summary_cohorts.append(
            {
                "cohort": cohort,
                "total_revenue": revenue,
                "total_direct_cost": direct_cost,
                "gross_margin": gross_margin,
            }
        )

    summary: Dict[str, object] = {
        "mission_id": "NM-920",
        "execution": execution_name,
        "cohorts": summary_cohorts,
    }

    output_name = f"profit_snapshot_{execution_name}.json"
    output_path = run_dir / output_name
    try:
        output_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        message = f"NM-920: wrote profit snapshot summary to {output_name}."
        success = True
    except Exception as exc:
        message = f"NM-920: failed to write profit snapshot summary: {exc}"
        success = False

    return {
        "mission": "NM-920",
        "repo": str(repo_path.name),
        "branch": branch_name,
        "success": success,
        "message": message,
        "summary_file": str(output_path) if success else None,
    }


def run_nm_930_treatment_summary(
    repo_root: Path, mission: Dict[str, object], branch_name: str
) -> Dict[str, object]:
    """
    Read treatment history snapshots and write a cohort-level efficacy summary for NM-930.

    This mission is read-only and must not recommend or rely on heat treatments.
    """

    repo_path = _resolve_repo_path(repo_root)
    exec_info = _resolve_execution_dir(repo_path)
    if exec_info is None:
        message = "NM-930: no execution directory found; skipping treatment summary."
        return {
            "mission": "NM-930",
            "repo": str(repo_path.name),
            "branch": branch_name,
            "success": False,
            "message": message,
        }

    run_dir, execution_name = exec_info

    snapshot_dir = repo_path / "treatment_history"
    records = _load_snapshot_records(snapshot_dir)
    if not records:
        message = "NM-930: no treatment history snapshots found; nothing to summarize."
        return {
            "mission": "NM-930",
            "repo": str(repo_path.name),
            "branch": branch_name,
            "success": True,
            "message": message,
        }

    stats: Dict[tuple, Dict[str, float]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue

        cohort = str(rec.get("cohort") or "").strip() or "unknown"
        material = str(rec.get("material") or "").strip() or "unknown"
        outcome = str(rec.get("outcome") or "").strip().lower()

        if "heat" in material.lower():
            pass

        key = (cohort, material)
        agg = stats.setdefault(
            key,
            {"total": 0.0, "success": 0.0, "failure": 0.0},
        )

        agg["total"] += 1.0
        if outcome in {"success", "resolved"}:
            agg["success"] += 1.0
        elif outcome in {"failed", "retreat_required", "retreat", "repeat"}:
            agg["failure"] += 1.0

    summary_rows: list[Dict[str, object]] = []
    for (cohort, material), agg in stats.items():
        total = float(agg.get("total") or 0.0)
        success = float(agg.get("success") or 0.0)
        failure = float(agg.get("failure") or 0.0)
        success_rate = (success / total) if total > 0 else 0.0

        summary_rows.append(
            {
                "cohort": cohort,
                "material": material,
                "total_treatments": total,
                "success_count": success,
                "failure_count": failure,
                "success_rate": success_rate,
            }
        )

    summary: Dict[str, object] = {
        "mission_id": "NM-930",
        "execution": execution_name,
        "cohort_material_stats": summary_rows,
    }

    output_name = f"treatment_snapshot_{execution_name}.json"
    output_path = run_dir / output_name
    try:
        output_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        message = f"NM-930: wrote treatment summary to {output_name}."
        success = True
    except Exception as exc:
        message = f"NM-930: failed to write treatment summary: {exc}"
        success = False

    return {
        "mission": "NM-930",
        "repo": str(repo_path.name),
        "branch": branch_name,
        "success": success,
        "message": message,
        "summary_file": str(output_path) if success else None,
    }


EXECUTORS = {
    "NM-010": lambda repo_path, mission, branch: run_nm_010(repo_path, branch),
    "NM-011": lambda repo_path, mission, branch: run_nm_011(repo_path, branch),
    "NM-020": lambda repo_path, mission, branch: run_nm_020(repo_path, mission),
    "NM-900": lambda repo_path, mission, branch: run_nm_900(repo_path, mission, branch),
    "NM-901": lambda repo_path, mission, branch: run_nm_901(repo_path, mission, branch),
    "NM-902": lambda repo_path, mission, branch: run_nm_902(repo_path, mission, branch),
    "NM-903": lambda repo_path, mission, branch: run_nm_903(repo_path, mission, branch),
    "NM-904": lambda repo_path, mission, branch: run_nm_904(repo_path, mission, branch),
    "NM-910": lambda repo_path, mission, branch: run_nm_910_memory_probe(
        repo_path, mission, branch
    ),
    "NM-920": lambda repo_path, mission, branch: run_nm_920_profit_snapshot(
        repo_path, mission, branch
    ),
    "NM-930": lambda repo_path, mission, branch: run_nm_930_treatment_summary(
        repo_path, mission, branch
    ),
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

    branch = branch_name_for_mission(mission)
    results = []
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        repo_name = repo.get("name")
        if not repo_name:
            continue
        repo_path = repos_root / repo_name
        result = executor(repo_path, mission, branch)
        results.append(result)

    if not results:
        return {"mission": mission_id, "skipped": True, "reason": "no valid repos"}
    return results[0]
