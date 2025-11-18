from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


def _read_jsonl(path: Path) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    records.append(obj)
    except FileNotFoundError:
        return []
    except Exception:
        return []
    return records


def _extract_probe_answer(record: Dict[str, object]) -> Optional[str]:
    worker_payload = record.get("worker") if isinstance(record, dict) else None
    candidate_fields = [
        record.get("content"),
        record.get("message"),
        worker_payload.get("message") if isinstance(worker_payload, dict) else None,
        worker_payload.get("patch") if isinstance(worker_payload, dict) else None,
        worker_payload.get("error_message") if isinstance(worker_payload, dict) else None,
    ]
    for value in candidate_fields:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def write_memory_probe_summary(run_dir: Path, mission_id: str = "NM-910") -> Optional[Path]:
    """
    Collect Grok responses for NM-910 and write a markdown probe summary.
    """

    execution_name = run_dir.name
    answers: List[str] = []
    probe_unavailable = False
    missing_credentials: List[str] = []

    for path in run_dir.glob("worker_results_*.jsonl"):
        for record in _read_jsonl(path):
            if record.get("mission_id") != mission_id:
                continue
            worker_name = (record.get("worker_name") or "").lower()
            nested_worker = record.get("worker") if isinstance(record.get("worker"), dict) else {}
            nested_worker_name = (nested_worker.get("worker_name") or "").lower() if nested_worker else ""
            if worker_name not in {"grok", ""} and nested_worker_name != "grok":
                continue
            metadata = nested_worker.get("metadata") if isinstance(nested_worker, dict) else {}
            if isinstance(metadata, dict) and metadata.get("probe_unavailable"):
                probe_unavailable = True
                creds = metadata.get("missing_credentials")
                if isinstance(creds, list):
                    missing_credentials = [str(c) for c in creds if str(c)]
            answer = _extract_probe_answer(record)
            if answer:
                answers.append(answer)

    if not answers and not probe_unavailable:
        return None

    lines = [
        f"# Memory Probe – {execution_name}",
        "",
        f"Mission: {mission_id}",
        "",
        "## Probe responses",
        "",
    ]
    if probe_unavailable:
        lines.extend(
            [
                "probe_unavailable: true",
                f"missing_credentials: {', '.join(missing_credentials) if missing_credentials else 'unknown'}",
                "",
            ]
        )
    if answers:
        lines.append("\n\n".join(answers))

    output_path = run_dir / f"memory_probe_{execution_name}.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
