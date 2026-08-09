#!/usr/bin/env python3
"""Always-on host for the canonical StegVerse single-heartbeat runtime.

Canonical runtime code is cloned from StegVerse-Labs/.github on every process
start. Mutable heartbeat state is restored from and checkpointed to the
dedicated master-records Render Key Value resource. The host/provider never
becomes heartbeat timing or execution authority.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import redis

SOURCE_REPO = os.getenv("SHWP_SOURCE_REPO", "https://github.com/StegVerse-Labs/.github.git")
SOURCE_REF = os.getenv("SHWP_SOURCE_REF", "main")
WORK_ROOT = Path(os.getenv("SHWP_WORK_ROOT", "/tmp/stegverse-shwp-runtime"))
REDIS_URL = os.environ["REDIS_URL"]
STATE_KEY = os.getenv("SHWP_STATE_KEY", "master-records:shwp:runtime-state:v1")
RECEIPT_PREFIX = os.getenv("SHWP_RECEIPT_PREFIX", "master-records:shwp:receipt:v1:")
INTERVAL_MS = float(os.getenv("SHWP_INTERVAL_MS", "250"))
PORT = int(os.getenv("PORT", "10000"))

EXACT_MUTABLE_FILES = {
    "control/heartbeat-state.json",
    "control/worker-registry.json",
    "control/worker-cost-observations.json",
    "control/worker-status.json",
}
MUTABLE_ROOTS = ("events/", "checkpoints/", "receipts/", "heartbeats/")

health: dict[str, Any] = {
    "status": "STARTING",
    "source_repo": SOURCE_REPO,
    "source_ref": SOURCE_REF,
    "source_sha": None,
    "heartbeat_epoch": None,
    "last_cycle_result": None,
    "last_snapshot_sha256": None,
    "persistent_state": "UNVERIFIED",
    "execution_authority_from_host": False,
    "heartbeat_timing_authority_from_provider": False,
}
stop_requested = threading.Event()


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(args, cwd=str(cwd) if cwd else None, text=True).strip()


def clone_runtime() -> str:
    if WORK_ROOT.exists():
        shutil.rmtree(WORK_ROOT)
    WORK_ROOT.parent.mkdir(parents=True, exist_ok=True)
    run("git", "clone", "--depth", "1", "--branch", SOURCE_REF, SOURCE_REPO, str(WORK_ROOT))
    return run("git", "rev-parse", "HEAD", cwd=WORK_ROOT)


def encode_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def all_mutable_files(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for rel in sorted(EXACT_MUTABLE_FILES):
        path = root / rel
        if path.is_file():
            files[rel] = encode_file(path)
    for prefix in MUTABLE_ROOTS:
        base = root / prefix
        if not base.exists():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            files[path.relative_to(root).as_posix()] = encode_file(path)
    return files


def decode_json_file(payload: str) -> dict[str, Any]:
    return json.loads(base64.b64decode(payload).decode("utf-8"))


def write_encoded(root: Path, rel: str, payload: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = base64.b64decode(payload)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as stream:
        stream.write(raw)
        tmp = Path(stream.name)
    os.replace(tmp, path)


def merge_registry(root: Path, persisted_payload: str) -> None:
    path = root / "control/worker-registry.json"
    current = json.loads(path.read_text(encoding="utf-8"))
    persisted = decode_json_file(persisted_payload)
    current_tasks = {item["task_id"]: item for item in current.get("tasks", [])}
    persisted_tasks = {item["task_id"]: item for item in persisted.get("tasks", [])}
    tasks = []
    for task_id in sorted(set(current_tasks) | set(persisted_tasks)):
        if task_id in current_tasks and task_id in persisted_tasks:
            tasks.append({**current_tasks[task_id], **persisted_tasks[task_id]})
        else:
            tasks.append(persisted_tasks.get(task_id) or current_tasks[task_id])
    current_workers = {item["worker_id"]: item for item in current.get("workers", [])}
    persisted_workers = {item["worker_id"]: item for item in persisted.get("workers", [])}
    workers = []
    for worker_id in sorted(set(current_workers) | set(persisted_workers)):
        if worker_id in current_workers and worker_id in persisted_workers:
            merged = dict(persisted_workers[worker_id])
            merged.update(current_workers[worker_id])
            for field in ("status", "last_seen_at"):
                if field in persisted_workers[worker_id]:
                    merged[field] = persisted_workers[worker_id][field]
            workers.append(merged)
        else:
            workers.append(persisted_workers.get(worker_id) or current_workers[worker_id])
    current["generation"] = max(int(current.get("generation", 0)), int(persisted.get("generation", 0)))
    current["tasks"] = tasks
    current["workers"] = workers
    path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def restore_snapshot(client: redis.Redis) -> dict[str, Any] | None:
    raw = client.get(STATE_KEY)
    if not raw:
        return None
    snapshot = json.loads(raw)
    if snapshot.get("schema") != "stegverse.master-records-heartbeat-host-state/v1":
        raise RuntimeError("unsupported persisted heartbeat state schema")
    files = snapshot.get("files", {})
    registry_payload = files.get("control/worker-registry.json")
    for rel, payload in files.items():
        if rel == "control/worker-registry.json":
            continue
        if rel in EXACT_MUTABLE_FILES or rel.startswith(MUTABLE_ROOTS):
            write_encoded(WORK_ROOT, rel, payload)
    if registry_payload:
        merge_registry(WORK_ROOT, registry_payload)
    return snapshot


def make_snapshot(source_sha: str) -> tuple[dict[str, Any], str]:
    files = all_mutable_files(WORK_ROOT)
    hb = json.loads((WORK_ROOT / "control/heartbeat-state.json").read_text(encoding="utf-8"))
    canonical = {
        "schema": "stegverse.master-records-heartbeat-host-state/v1",
        "source_repo": SOURCE_REPO,
        "source_ref": SOURCE_REF,
        "source_sha": source_sha,
        "heartbeat_epoch": int(hb.get("epoch", 0)),
        "files": files,
        "provider_is_timing_authority": False,
        "host_grants_execution_authority": False,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    snapshot = dict(canonical)
    snapshot["snapshot_sha256"] = digest
    return snapshot, digest


def persist_snapshot(client: redis.Redis, source_sha: str) -> dict[str, Any]:
    snapshot, digest = make_snapshot(source_sha)
    epoch = snapshot["heartbeat_epoch"]
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    pipe = client.pipeline(transaction=True)
    pipe.set(STATE_KEY, payload)
    pipe.set(f"{RECEIPT_PREFIX}{epoch}", json.dumps({
        "schema": "stegverse.master-records-heartbeat-host-receipt/v1",
        "heartbeat_epoch": epoch,
        "source_sha": source_sha,
        "snapshot_sha256": digest,
        "execution_authority_effect": "NONE",
        "provider_timing_authority": False,
    }, sort_keys=True))
    pipe.execute()
    health["heartbeat_epoch"] = epoch
    health["last_snapshot_sha256"] = digest
    health["persistent_state"] = "PASS"
    return snapshot


def load_adapters(root: Path):
    sys.path.insert(0, str(root))
    from heartbeat_runtime import ProcessWorkerAdapter  # type: ignore
    registry_path = root / "control/process-worker-adapters.json"
    if not registry_path.exists():
        return {}
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if registry.get("schema") != "stegverse.process-worker-adapters/v0.1":
        raise RuntimeError("unsupported process worker adapter registry")
    adapters = {}
    for entry in registry.get("adapters", []):
        if not entry.get("enabled"):
            continue
        cwd = Path(entry["cwd"])
        if not cwd.is_absolute():
            cwd = root / cwd
        adapters[entry["adapter_ref"]] = ProcessWorkerAdapter(
            list(entry["command"]), cwd=cwd,
            timeout_seconds=float(entry["timeout_seconds"]),
            env_allowlist=tuple(entry.get("env_allowlist", [])),
        )
    return adapters


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path not in ("/", "/health", "/ready"):
            self.send_response(404); self.end_headers(); return
        body = json.dumps(health, sort_keys=True).encode("utf-8")
        code = 200 if health.get("status") == "RUNNING" and health.get("persistent_state") == "PASS" else 503
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("http", fmt % args, flush=True)


def serve_health() -> None:
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever(poll_interval=0.5)


def main() -> int:
    source_sha = clone_runtime()
    health["source_sha"] = source_sha
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
    client.ping()
    prior = restore_snapshot(client)
    persist_snapshot(client, source_sha)
    sys.path.insert(0, str(WORK_ROOT))
    from heartbeat_runtime import HeartbeatRuntime  # type: ignore
    runtime = HeartbeatRuntime(WORK_ROOT, adapters=load_adapters(WORK_ROOT))
    health["restored_previous_snapshot"] = bool(prior)
    health["status"] = "RUNNING"
    threading.Thread(target=serve_health, daemon=True).start()

    def stop(_signum, _frame): stop_requested.set()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    while not stop_requested.is_set():
        try:
            result = runtime.cycle(write=True)
            persist_snapshot(client, source_sha)
            health["last_cycle_result"] = result
        except Exception as exc:
            health["status"] = "FAIL_CLOSED"
            health["persistent_state"] = "FAIL_CLOSED"
            health["error"] = f"{type(exc).__name__}: {exc}"
            print(json.dumps(health, sort_keys=True), flush=True)
            return 1
        if INTERVAL_MS > 0:
            stop_requested.wait(INTERVAL_MS / 1000.0)

    try:
        persist_snapshot(client, source_sha)
    finally:
        health["status"] = "STOPPED"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
