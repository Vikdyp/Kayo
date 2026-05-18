#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_CONTAINER_NAME = "kayo-bot"
DEFAULT_STATE_PATH = "/var/lib/kayo/bot-healthcheck-state.json"
DEFAULT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ContainerSnapshot:
    name: str
    exists: bool
    running: bool = False
    status: str = "missing"
    health: str = ""
    restart_count: int = 0
    started_at: str = ""
    finished_at: str = ""
    exit_code: int | None = None
    container_id: str = ""
    image: str = ""
    inspect_error: str = ""

    def status_key(self) -> str:
        if not self.exists:
            return "missing"
        if not self.running:
            exit_code = "" if self.exit_code is None else f":{self.exit_code}"
            return f"not_running:{self.status}{exit_code}"
        if self.health and self.health != "healthy":
            return f"health:{self.health}"
        return "ok"


@dataclass(frozen=True)
class AlertDecision:
    should_notify: bool
    level: str
    title: str
    detail: str


def inspect_container(container_name: str) -> ContainerSnapshot:
    command = ["docker", "inspect", container_name]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout).strip()
        return ContainerSnapshot(name=container_name, exists=False, inspect_error=error)

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return ContainerSnapshot(name=container_name, exists=False, inspect_error=str(exc))

    return parse_docker_inspect(container_name, payload)


def parse_docker_inspect(container_name: str, payload: object) -> ContainerSnapshot:
    if not isinstance(payload, list) or not payload:
        return ContainerSnapshot(name=container_name, exists=False, inspect_error="empty docker inspect result")

    item = payload[0]
    if not isinstance(item, dict):
        return ContainerSnapshot(name=container_name, exists=False, inspect_error="invalid docker inspect result")

    state = item.get("State") or {}
    if not isinstance(state, dict):
        state = {}

    health = state.get("Health") or {}
    health_status = ""
    if isinstance(health, dict):
        health_status = str(health.get("Status") or "")

    raw_id = str(item.get("Id") or "")
    raw_image = str(item.get("Image") or "")

    return ContainerSnapshot(
        name=container_name,
        exists=True,
        running=bool(state.get("Running")),
        status=str(state.get("Status") or ""),
        health=health_status,
        restart_count=int(item.get("RestartCount") or 0),
        started_at=str(state.get("StartedAt") or ""),
        finished_at=str(state.get("FinishedAt") or ""),
        exit_code=state.get("ExitCode") if isinstance(state.get("ExitCode"), int) else None,
        container_id=raw_id[:12],
        image=raw_image[:12],
    )


def decide_alert(
    snapshot: ContainerSnapshot,
    previous_state: dict[str, str],
    *,
    notify_recovery: bool = True,
) -> AlertDecision:
    current_status = snapshot.status_key()
    previous_status = previous_state.get("status_key", "")
    previous_started_at = previous_state.get("started_at", "")
    previous_restart_count = previous_state.get("restart_count", "")

    if current_status != "ok":
        if current_status == previous_status:
            return AlertDecision(False, "critical", "Kayo bot toujours en alerte", describe_snapshot(snapshot))
        return AlertDecision(True, "critical", "Kayo bot en alerte", describe_snapshot(snapshot))

    if notify_recovery and previous_status and previous_status != "ok":
        return AlertDecision(True, "info", "Kayo bot revenu OK", describe_snapshot(snapshot))

    if previous_started_at and previous_started_at != snapshot.started_at:
        return AlertDecision(
            True,
            "warning",
            "Kayo bot redemarre",
            f"started_at: {snapshot.started_at}; precedent: {previous_started_at}",
        )

    current_restart_count = str(snapshot.restart_count)
    if previous_restart_count and previous_restart_count != current_restart_count:
        return AlertDecision(
            True,
            "warning",
            "Kayo bot restart count change",
            f"restart_count: {current_restart_count}; precedent: {previous_restart_count}",
        )

    return AlertDecision(False, "ok", "Kayo bot OK", describe_snapshot(snapshot))


def describe_snapshot(snapshot: ContainerSnapshot) -> str:
    if not snapshot.exists:
        return f"container absent; docker inspect: {snapshot.inspect_error or 'no details'}"
    if not snapshot.running:
        return (
            f"status: {snapshot.status}; exit_code: {snapshot.exit_code}; "
            f"finished_at: {snapshot.finished_at or 'unknown'}"
        )
    if snapshot.health:
        return f"status: {snapshot.status}; health: {snapshot.health}; started_at: {snapshot.started_at}"
    return f"status: {snapshot.status}; started_at: {snapshot.started_at}"


def state_from_snapshot(snapshot: ContainerSnapshot, checked_at: str) -> dict[str, str]:
    return {
        "status_key": snapshot.status_key(),
        "container_id": snapshot.container_id,
        "started_at": snapshot.started_at,
        "restart_count": str(snapshot.restart_count),
        "checked_at": checked_at,
    }


def load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def save_state(path: Path, state: dict[str, str]) -> None:
    default_state_dir = Path(DEFAULT_STATE_PATH).parent
    parent_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not parent_existed or path.parent == default_state_dir:
        path.parent.chmod(0o700)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)
    path.chmod(0o600)


def build_discord_payload(
    *,
    decision: AlertDecision,
    snapshot: ContainerSnapshot,
    hostname: str,
    checked_at: str,
) -> dict[str, object]:
    lines = [
        f"**{decision.title}**",
        f"Niveau: `{decision.level}`",
        f"Host: `{hostname}`",
        f"Conteneur: `{snapshot.name}`",
        f"Etat: `{snapshot.status_key()}`",
        f"Heure UTC: `{checked_at}`",
        f"Details: {decision.detail}",
    ]
    return {
        "content": "\n".join(lines)[:1900],
        "allowed_mentions": {"parse": []},
    }


def send_webhook(url: str, payload: dict[str, object], *, timeout_seconds: int) -> None:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if response.status >= 400:
                raise RuntimeError(f"webhook returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"webhook returned HTTP {exc.code}: {body}") from exc


def env_bool(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    container_name = os.getenv("KAYO_BOT_CONTAINER", DEFAULT_CONTAINER_NAME)
    state_path = Path(os.getenv("KAYO_ALERT_STATE_PATH", DEFAULT_STATE_PATH))
    webhook_url = os.getenv("KAYO_ALERT_WEBHOOK_URL", "").strip()
    timeout_seconds = int(os.getenv("KAYO_ALERT_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    notify_recovery = env_bool("KAYO_ALERT_NOTIFY_RECOVERY", default=True)

    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot = inspect_container(container_name)
    previous_state = load_state(state_path)
    decision = decide_alert(snapshot, previous_state, notify_recovery=notify_recovery)

    if decision.should_notify:
        payload = build_discord_payload(
            decision=decision,
            snapshot=snapshot,
            hostname=socket.gethostname(),
            checked_at=checked_at,
        )
        if webhook_url:
            send_webhook(webhook_url, payload, timeout_seconds=timeout_seconds)
        else:
            print("KAYO_ALERT_WEBHOOK_URL is not configured; notification skipped.", file=sys.stderr)

    save_state(state_path, state_from_snapshot(snapshot, checked_at))
    print(f"{decision.level}: {decision.title} - {decision.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
