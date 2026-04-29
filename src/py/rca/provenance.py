"""
Provenance helpers — config_id / params_hash / run_id + logs/runs.jsonl writer.

Per DNA v2.2 §2.1 запрет 12: «Не выдавать Run без полного config snapshot».
Каждый Run (baseline build, detection run, comparison run) должен записать:
  * `config_id` — human-readable preset name (default | schuit_eq | ...)
  * `params_hash` — SHA-256 от sorted-keys JSON serialization config dict
  * `run_id` — `<config_id>_<period>_<sha8>` (sha8 = first 8 chars params_hash)

Plus lifecycle log entry в `logs/runs.jsonl`:
  * append-only JSONL (one line per Run)
  * fields: run_id, config_id, params_hash, gas, period, started_at, ended_at,
    asset_id, status, algorithm_version, rna_version, schema_version

Per RNA v1.2 §9 logging requirements.

Usage::

    from rca.provenance import compute_provenance, write_run_log

    config = {
        "algorithm_version": "2.3",
        "schema_version": "1.1",
        "config_preset": "default",
        "gas": "CH4",
        # ... все параметры Configuration ...
    }
    prov = compute_provenance(config, period="2019_2025")
    # prov = {"config_id": "default", "params_hash": "...", "run_id": "default_2019_2025_..."}

    write_run_log(
        run_id=prov["run_id"],
        config_id=prov["config_id"],
        params_hash=prov["params_hash"],
        gas="CH4",
        period="2019_2025",
        started_at="2026-04-29T10:00:00",
        ended_at="2026-04-29T18:00:00",
        asset_id="projects/.../baselines/regional_CH4_2019_2025",
        status="SUCCEEDED",
    )
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


# logs/runs.jsonl path — anchored to repo root (not cwd-dependent)
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _logs_path() -> Path:
    return _repo_root() / "logs" / "runs.jsonl"


def compute_params_hash(config: dict[str, Any]) -> str:
    """
    SHA-256 от sorted-keys JSON serialization. Deterministic.

    Different configs (e.g. industrial_buffer_exclude_km=30 vs 60) produce
    different params_hash → run_id → Asset path. Bit-identical reproducibility:
    same config produces same hash → same run_id.
    """
    serialized = json.dumps(config, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def compute_provenance(config: dict[str, Any], period: str | None = None) -> dict[str, str]:
    """
    Compute full provenance triple для Run.

    Args:
        config: full Configuration dict (algorithm params, gas, period, etc.)
        period: optional period string (e.g. "2019_2025"). If None, derives
            from config["history_year_min"]/["history_year_max"] OR
            ["target_year"].

    Returns:
        dict with keys: config_id, params_hash, run_id.
    """
    config_id = config.get("config_preset") or config.get("config_id") or "default"

    if period is None:
        if "history_year_min" in config and "history_year_max" in config:
            period = f"{config['history_year_min']}_{config['history_year_max']}"
        elif "target_year" in config:
            year = config["target_year"]
            period = f"2019_{year - 1 if isinstance(year, int) else year}"
        else:
            period = "unknown_period"

    params_hash = compute_params_hash(config)
    run_id = f"{config_id}_{period}_{params_hash[:8]}"

    return {
        "config_id": config_id,
        "params_hash": params_hash,
        "run_id": run_id,
    }


def write_run_log(
    run_id: str,
    config_id: str,
    params_hash: str,
    gas: str | None = None,
    period: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    asset_id: str | None = None,
    status: str = "STARTED",
    extra: dict[str, Any] | None = None,
) -> Path:
    """
    Append run lifecycle log entry в `logs/runs.jsonl`.

    Per RNA §9 logging spec. JSONL — append-only (одна строка per Run).
    Не overwrite существующие entries — каждый Run permanent record.

    Returns: path to logs/runs.jsonl.
    """
    log_path = _logs_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "run_id": run_id,
        "config_id": config_id,
        "params_hash": params_hash,
        "gas": gas,
        "period": period,
        "started_at": started_at or datetime.utcnow().isoformat(),
        "ended_at": ended_at,
        "asset_id": asset_id,
        "status": status,
        "log_timestamp": datetime.utcnow().isoformat(),
    }
    if extra:
        entry.update(extra)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    return log_path


def read_run_log(run_id: str | None = None) -> list[dict[str, Any]]:
    """
    Read `logs/runs.jsonl`. Optionally filter by run_id.

    Returns: list of log entries. Empty list если файл не exists.
    """
    log_path = _logs_path()
    if not log_path.exists():
        return []
    entries = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if run_id is None or e.get("run_id") == run_id:
                entries.append(e)
    return entries
