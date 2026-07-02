"""Sessioned ontology build with an append-only audit log.

A BuildSession wraps an ontology directory and records every build step —
imports, hand edits, validation runs — into `.build/log.jsonl`, together
with a content snapshot so each event carries which files changed and the
before/after hash of the whole pack.

The log is append-only: corrections are new events, never edits.

Reconstructed to the contract of tests/test_build_session.py and
tests/test_cli.py (the original module was lost in a repo extraction).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

# The steps a pack is expected to go through before release.
# `roboonto build status` shows progress against this list.
RECOMMENDED_STEPS = [
    "import_urdf",
    "import_sdk",
    "hand_edit",
    "validate",
    "readiness",
]

SESSION_DIRNAME = ".build"


class BuildSession:
    def __init__(self, dir: Path | str):
        self.dir = Path(dir)
        self.session_dir = self.dir / SESSION_DIRNAME
        self.manifest_path = self.session_dir / "manifest.json"
        self.log_path = self.session_dir / "log.jsonl"

    # ── lifecycle ────────────────────────────────────────────────────

    def exists(self) -> bool:
        return self.manifest_path.exists()

    def init(self, operator: str = "") -> None:
        if not self.dir.is_dir():
            raise FileNotFoundError(f"ontology dir not found: {self.dir}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        snapshot = self._snapshot()
        overall = self._overall_hash(snapshot)
        manifest = {
            "operator": operator,
            "created_at": self._now(),
            "recommended_steps": RECOMMENDED_STEPS,
            "completed_steps": [],
            "snapshot": snapshot,
        }
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        self.log_path.touch()
        self._append_event({
            "ts": self._now(),
            "step": "init",
            "operator": operator,
            "note": "",
            "command": None,
            "exit_code": 0,
            "duration_s": None,
            "files_changed": [],
            "inputs_hash": overall,
            "outputs_hash": overall,
        })

    # ── audit recording ──────────────────────────────────────────────

    def run_step(self, step: str, cmd: list[str] | None = None, note: str = "") -> int:
        """Record a build step; optionally run `cmd` under audit.

        Files changed since the previous event are diffed against the stored
        snapshot, so hand edits made before calling run_step are captured too.
        Returns the command's exit code (0 for note-only steps).
        """
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        prev_snapshot: dict[str, str] = manifest.get("snapshot", {})
        inputs_hash = self._overall_hash(prev_snapshot)

        exit_code = 0
        command = None
        duration_s = None
        if cmd:
            # argparse.REMAINDER keeps the leading "--" separator — drop it.
            if cmd and cmd[0] == "--":
                cmd = cmd[1:]
            command = " ".join(cmd)
            t0 = time.monotonic()
            exit_code = subprocess.run(cmd).returncode
            duration_s = round(time.monotonic() - t0, 3)

        cur_snapshot = self._snapshot()
        outputs_hash = self._overall_hash(cur_snapshot)
        files_changed = self._diff(prev_snapshot, cur_snapshot)

        self._append_event({
            "ts": self._now(),
            "step": step,
            "note": note,
            "command": command,
            "exit_code": exit_code,
            "duration_s": duration_s,
            "files_changed": files_changed,
            "inputs_hash": inputs_hash,
            "outputs_hash": outputs_hash,
        })

        # Snapshot always advances to reality; only successful steps count
        # as completed.
        manifest["snapshot"] = cur_snapshot
        if exit_code == 0 and step not in manifest["completed_steps"]:
            manifest["completed_steps"].append(step)
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return exit_code

    # ── inspection ───────────────────────────────────────────────────

    def tail(self, limit: int = 50) -> list[dict]:
        if not self.log_path.exists():
            return []
        lines = [ln for ln in self.log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return [json.loads(ln) for ln in lines[-limit:]]

    def status(self) -> dict:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        events = self.tail(10_000)
        steps_seen: list[str] = []
        for e in events:
            if e["step"] not in steps_seen:
                steps_seen.append(e["step"])
        return {
            "operator": manifest.get("operator", ""),
            "created_at": manifest.get("created_at"),
            "recommended_steps": manifest.get("recommended_steps", []),
            "completed_steps": manifest.get("completed_steps", []),
            "steps_seen": steps_seen,
            "events": len(events),
            "last_event": events[-1] if events else None,
        }

    # ── internals ────────────────────────────────────────────────────

    def _append_event(self, event: dict) -> None:
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _snapshot(self) -> dict[str, str]:
        """Hash every file in the ontology dir, excluding the session dir."""
        files: dict[str, str] = {}
        for p in sorted(self.dir.rglob("*")):
            if not p.is_file() or SESSION_DIRNAME in p.parts:
                continue
            rel = p.relative_to(self.dir).as_posix()
            files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        return files

    @staticmethod
    def _overall_hash(snapshot: dict[str, str]) -> str:
        h = hashlib.sha256()
        for rel in sorted(snapshot):
            h.update(rel.encode("utf-8"))
            h.update(snapshot[rel].encode("ascii"))
        return h.hexdigest()

    @staticmethod
    def _diff(before: dict[str, str], after: dict[str, str]) -> list[dict]:
        changed = []
        for rel in sorted(set(before) | set(after)):
            b, a = before.get(rel), after.get(rel)
            if b != a:
                changed.append({"file": rel, "before": b, "after": a})
        return changed

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
