"""Cycle driver CLI that wraps a full Night Runner execution."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .dispatcher import run_nm_910_memory_probe
from .secrets_bootstrap import log_night_runner_secret_status
from .results import make_run_id
from grok_rag_ingest import ingest_execution
from memory_probe_summary import write_memory_probe_summary
from run_memory_summary import write_run_memory_summary
from worker_memory_summary import write_worker_memory_summary
from worker_results import (
    extract_worker_result_records_from_lines,
    write_worker_results_jsonl,
)


MISSION_RESULT_PREFIX = "MISSION_RESULT_JSON:"


def _env_flag(name: str) -> bool:
    value = os.getenv(name, "")
    return value.lower() in {"1", "true", "yes", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an end-to-end Night Runner cycle and collect artifacts."
    )
    parser.add_argument(
        "--resource-group",
        default="ls-night-runner-rg",
        help="Azure resource group containing the job (default: ls-night-runner-rg).",
    )
    parser.add_argument(
        "--job-name",
        default="ls-night-runner-job",
        help="Azure Container Apps job name (default: ls-night-runner-job).",
    )
    parser.add_argument(
        "--image-tag",
        default="dev",
        help="Container image tag to run (default: dev).",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip docker build/push step before running the job.",
    )
    parser.add_argument(
        "--max-log-lines",
        type=int,
        default=1000,
        help="Maximum log lines to capture from Azure (default: 1000).",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repo root containing runs/ (default: current working directory).",
    )
    parser.add_argument(
        "--local-cycle",
        action="store_true",
        help="Generate cycle artifacts locally using LS_EXECUTION_DIR or the latest run directory (skip Azure job).",
    )
    parser.add_argument(
        "--run-local-nm910",
        action="store_true",
        help="Run NM-910 memory probe locally and then generate cycle artifacts (implies --local-cycle).",
    )
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_subprocess(cmd: List[str], capture: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess, printing stdout/stderr when failures occur."""

    printable = " ".join(cmd)
    print(f"$ {printable}")
    completed = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
    )
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout)
        if completed.stderr:
            print(completed.stderr)
        raise SystemExit(completed.returncode)
    return completed


def run_cycle_job(
    resource_group: str, job_name: str, image_tag: str, skip_build: bool
) -> None:
    """Invoke run_night to build/push, update the job image, and run it."""

    if skip_build:
        print(
            "[Cycle] LS_NIGHT_SKIP_BUILD=on or --skip-build set; "
            "invoking run_night without Docker build/push."
        )

    cmd = [
        sys.executable,
        "-m",
        "ls_azure_night_runner.run_night",
        "--image-tag",
        image_tag,
        "--resource-group",
        resource_group,
        "--job-name",
        job_name,
    ]
    if skip_build:
        cmd.append("--skip-build")
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def list_job_executions(resource_group: str, job_name: str) -> List[Dict[str, Any]]:
    cmd = [
        "az",
        "containerapp",
        "job",
        "execution",
        "list",
        "--name",
        job_name,
        "--resource-group",
        resource_group,
        "-o",
        "json",
    ]
    completed = run_subprocess(cmd)
    data = json.loads(completed.stdout or "[]")
    if not isinstance(data, list):
        raise SystemExit("Unexpected response from az ... execution list")
    return data


def latest_execution_name(resource_group: str, job_name: str) -> str:
    executions = list_job_executions(resource_group, job_name)
    if not executions:
        raise SystemExit("No executions found for job.")

    def parse_start(item: Dict[str, Any]) -> datetime:
        start = item.get("properties", {}).get("startTime")
        if not start:
            return datetime.min
        clean = start.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(clean)
        except ValueError:
            return datetime.min

    latest = max(executions, key=parse_start)
    execution_name = latest.get("name")
    if not execution_name:
        raise SystemExit("Could not determine execution name.")
    return execution_name


def fetch_logs(
    resource_group: str,
    job_name: str,
    execution_name: str,
    max_lines: int,
) -> str:
    cmd = [
        "az",
        "containerapp",
        "job",
        "logs",
        "show",
        "--name",
        job_name,
        "--resource-group",
        resource_group,
        "--job-execution-name",
        execution_name,
        "--format",
        "text",
        "--tail",
        str(max_lines),
    ]
    completed = run_subprocess(cmd)
    return completed.stdout or ""


def fetch_execution_metadata(
    resource_group: str, job_name: str, execution_name: str
) -> Dict[str, Any]:
    cmd = [
        "az",
        "containerapp",
        "job",
        "execution",
        "show",
        "--name",
        job_name,
        "--resource-group",
        resource_group,
        "--job-execution-name",
        execution_name,
        "-o",
        "json",
    ]
    completed = run_subprocess(cmd)
    payload = completed.stdout or "{}"
    return json.loads(payload)


def ensure_run_dir(execution_name: str) -> Path:
    return ensure_run_dir_at(repo_root(), execution_name)


def ensure_run_dir_at(base: Path, execution_name: str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    run_dir = base / "runs" / today / execution_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def resolve_execution_dir(base: Path, override: Optional[str] = None) -> tuple[Path, str]:
    if override:
        candidate = Path(override)
        if not candidate.is_absolute():
            candidate = base / candidate
        if candidate.is_dir():
            return candidate, candidate.name
        raise SystemExit(f"Execution directory not found: {candidate}")

    env_dir = os.getenv("LS_EXECUTION_DIR")
    if env_dir:
        candidate = Path(env_dir)
        if not candidate.is_absolute():
            candidate = base / candidate
        if candidate.is_dir():
            return candidate, candidate.name

    runs_root = base / "runs"
    if not runs_root.exists():
        raise SystemExit("No runs/ directory found for local cycle.")

    date_dirs = sorted([d for d in runs_root.iterdir() if d.is_dir()], reverse=True)
    for date_dir in date_dirs:
        exec_dirs = sorted([d for d in date_dir.iterdir() if d.is_dir()], reverse=True)
        if exec_dirs:
            return exec_dirs[0], exec_dirs[0].name

    raise SystemExit("No execution directories found under runs/.")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def parse_mission_results(log_path: Path) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not log_path.exists():
        return results
    with log_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line.startswith(MISSION_RESULT_PREFIX):
                continue
            payload = line[len(MISSION_RESULT_PREFIX) :].strip()
            if not payload:
                continue
            try:
                results.append(json.loads(payload))
            except json.JSONDecodeError as exc:
                print(f"Warning: failed to parse mission result JSON: {exc}")
    return results


def write_results_jsonl(path: Path, results: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for result in results:
            fh.write(json.dumps(result) + "\n")


def generate_night_report(results_path: Path, report_path: Path) -> None:
    if not results_path.exists() or results_path.stat().st_size == 0:
        print("No mission results to report; skipping night_report.")
        return
    cmd = [
        sys.executable,
        "-m",
        "ls_azure_night_runner.night_report",
        "--results",
        str(results_path),
        "--output",
        str(report_path),
    ]
    run_subprocess(cmd, capture=False)


def summarize_missions(results: List[Dict[str, Any]]) -> List[str]:
    summaries: List[str] = []
    for result in results:
        mission_id = (
            result.get("mission")
            or result.get("mission_id")
            or result.get("id")
            or "unknown-mission"
        )
        success = result.get("success")
        detail = result.get("reason") or result.get("message") or result.get("details")
        line = f"- {mission_id}: success={success}"
        if detail:
            line += f" ({detail})"
        summaries.append(line)
    if not summaries:
        summaries.append("- (no mission results found)")
    return summaries


def run_nm910_locally(repo_root_path: Path, run_dir: Path) -> str:
    """Run NM-910 locally and capture worker result logs."""

    os.environ["LS_EXECUTION_DIR"] = str(run_dir)
    branch_name = os.getenv("LS_BRANCH_NAME") or "local-cycle"
    mission = {"mission_id": "NM-910", "repos": [{"name": repo_root_path.name}]}
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        # Diagnostic-only: log Grok secret configuration status into the captured logs.
        log_night_runner_secret_status()
        run_nm_910_memory_probe(repo_root_path, mission, branch_name)
    return buffer.getvalue()


def process_cycle_artifacts(
    run_dir: Path,
    execution_name: str,
    logs_text: Optional[str],
    execution: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    logs_path = run_dir / f"logs_{execution_name}.txt"
    if logs_text is None and logs_path.exists():
        logs_text = logs_path.read_text(encoding="utf-8")
    if logs_text is None:
        logs_text = ""
    write_text(logs_path, logs_text)
    print(f"[cycle] Logs written to: {logs_path}")

    exec_path = run_dir / f"exec_{execution_name}.json"
    if execution:
        write_json(exec_path, execution)
    elif exec_path.exists():
        try:
            execution = json.loads(exec_path.read_text(encoding="utf-8"))
        except Exception:
            execution = {}
    else:
        execution = {}
    print(f"[cycle] Execution metadata path: {exec_path}")

    mission_results = parse_mission_results(logs_path)
    mission_results_path = run_dir / f"mission_results_{execution_name}.jsonl"
    write_results_jsonl(mission_results_path, mission_results)
    print(f"[cycle] Mission results JSONL: {mission_results_path}")

    worker_results_path: Optional[Path] = run_dir / f"worker_results_{execution_name}.jsonl"
    worker_records = extract_worker_result_records_from_lines(logs_text.splitlines())
    if worker_records:
        write_worker_results_jsonl(worker_records, worker_results_path)
        print(f"[cycle] Worker results JSONL: {worker_results_path}")
    elif not worker_results_path.exists():
        worker_results_path = None
        print("[cycle] Worker results JSONL: (not generated)")

    report_path = run_dir / f"night_report_{execution_name}.md"
    generate_night_report(mission_results_path, report_path)
    summary_path = write_run_memory_summary(run_dir)
    worker_summary_path = write_worker_memory_summary(run_dir)
    probe_summary_path = write_memory_probe_summary(run_dir)
    print(f"[cycle] Run memory summary: {summary_path}")
    print(f"[cycle] Worker memory summary (grok): {worker_summary_path}")
    if probe_summary_path:
        print(f"[cycle] Memory probe summary: {probe_summary_path}")
    else:
        print("[cycle] Memory probe summary: (not generated)")
    if report_path.exists() and report_path.stat().st_size > 0:
        print(f"[cycle] Night report: {report_path}")
    else:
        print("[cycle] Night report: (not generated)")

    print(f"[cycle] Ingesting execution directory into RAG index: {run_dir}")
    ingest_ok = ingest_execution(run_dir)
    print(f"[cycle] Ingest execution result: {ingest_ok}")

    status = execution.get("properties", {}).get("status", "unknown") if execution else "unknown"

    return {
        "execution_name": execution_name,
        "status": status,
        "logs_path": logs_path,
        "exec_path": exec_path,
        "mission_results_path": mission_results_path,
        "mission_results": mission_results,
        "worker_results_path": worker_results_path,
        "summary_path": summary_path,
        "worker_summary_path": worker_summary_path,
        "probe_summary_path": probe_summary_path,
        "report_path": report_path,
    }


def print_cycle_summary(data: Dict[str, Any]) -> None:
    print("")
    print("[Cycle Summary]")
    print("")
    print(f"Execution: {data['execution_name']}")
    print(f"Status: {data['status']}")
    print("Missions:")
    for line in summarize_missions(data.get("mission_results") or []):
        print(f"  {line}")
    print("")
    print("Artifacts:")
    print(f"  - Logs: {data['logs_path']}")
    print(f"  - Exec JSON: {data['exec_path']}")
    print(f"  - Mission results: {data['mission_results_path']}")
    worker_results_path = data.get("worker_results_path")
    if worker_results_path and Path(worker_results_path).exists():
        print(f"  - Worker results: {worker_results_path}")
    else:
        print("  - Worker results: (not generated)")
    print(f"  - Memory summary: {data['summary_path']}")
    print(f"  - Worker memory summary: {data['worker_summary_path']}")
    probe_summary_path = data.get("probe_summary_path")
    if probe_summary_path:
        print(f"  - Memory probe summary: {probe_summary_path}")
    else:
        print("  - Memory probe summary: (not generated)")
    report_path = data.get("report_path")
    if report_path and Path(report_path).exists() and Path(report_path).stat().st_size > 0:
        print(f"  - Night report: {report_path}")
    else:
        print("  - Night report: (not generated)")


def main() -> None:
    args = parse_args()
    if args.run_local_nm910 or args.local_cycle:
        repo_root_path = Path(args.repo_root).resolve()
        local_execution_name: Optional[str] = None
        run_dir: Optional[Path] = None

        if args.run_local_nm910:
            local_execution_name = make_run_id()
            run_dir = ensure_run_dir_at(repo_root_path, local_execution_name)
            logs_text = run_nm910_locally(repo_root_path, run_dir)
            execution = {"name": local_execution_name, "properties": {"status": "local"}}
        else:
            run_dir, local_execution_name = resolve_execution_dir(repo_root_path)
            logs_text = None
            execution = None

        result = process_cycle_artifacts(
            run_dir,
            local_execution_name,
            logs_text,
            execution,
        )
        print_cycle_summary(result)
        return

    run_id = make_run_id()
    print(f"Starting Night Runner cycle (run_id={run_id})...")
    skip_build = args.skip_build or _env_flag("LS_NIGHT_SKIP_BUILD")
    run_cycle_job(args.resource_group, args.job_name, args.image_tag, skip_build)

    execution_name = latest_execution_name(args.resource_group, args.job_name)
    print(f"Latest execution detected: {execution_name}")
    run_dir = ensure_run_dir(execution_name)

    logs_text = fetch_logs(
        args.resource_group,
        args.job_name,
        execution_name,
        args.max_log_lines,
    )
    execution = fetch_execution_metadata(args.resource_group, args.job_name, execution_name)

    result = process_cycle_artifacts(
        run_dir,
        execution_name,
        logs_text,
        execution,
    )
    print_cycle_summary(result)


if __name__ == "__main__":
    main()
