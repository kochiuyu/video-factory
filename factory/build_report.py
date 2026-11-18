"""Structured results for one CLI build or preflight invocation."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4


class BuildReport:
    def __init__(self, root: Path, mode: str, settings: dict) -> None:
        self.root = root.resolve()
        self.started = perf_counter()
        self.run_id = uuid4().hex
        self.items = []
        self.active = []
        self.data = {
            "schema_version": 1,
            "run_id": self.run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "settings": settings,
            "items": self.items,
        }

    @property
    def item(self) -> dict:
        return self.active[-1]

    def run(self, source: Path, runner, *args, **kwargs):
        row = {
            "source": source.name,
            "source_sha256": None,
            "parent": self.item["source"] if self.active else None,
            "warnings": [],
            "phases": [],
            "cuts": {},
            "artifacts": [],
        }
        self.items.append(row)
        self.active.append(row)
        started = perf_counter()
        try:
            if source.is_file():
                row["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            result = runner(source, *args, report=self, **kwargs)
            row["status"] = "passed" if self.data["mode"] == "preflight" else "complete"
            return result
        except Exception as exc:
            row["status"] = "failed"
            row["error"] = str(exc)
            for cut in row["cuts"].values():
                if cut["status"] in {"pending", "checked", "preview"}:
                    cut["status"] = "failed"
            raise
        finally:
            row["elapsed_s"] = round(perf_counter() - started, 3)
            self.active.pop()

    def cuts(self, cuts: dict) -> None:
        state = {"preflight": "checked", "video": "pending"}.get(self.data["mode"], "preview")
        for name, (voice, captions, slides) in cuts.items():
            self.item["cuts"][name] = {
                "voice": voice, "captions": captions, "slides": slides, "status": state,
            }

    def phase(self, name: str, seconds: float) -> None:
        self.item["phases"].append({"phase": name, "elapsed_s": round(seconds, 3)})

    def warn(self, message: str) -> None:
        self.item["warnings"].append(message)

    def artifact(self, path: Path, kind: str) -> str:
        if not path.is_file():
            raise FileNotFoundError(path)
        relative = path.resolve().relative_to(self.root).as_posix()
        self.item["artifacts"].append({"kind": kind, "path": relative})
        return relative

    def video(self, name: str, path: Path, duration: float, reused: bool = False) -> None:
        relative = self.artifact(path, "video")
        self.item["cuts"].setdefault(name, {}).update(
            status="reused" if reused else "built", path=relative, duration_s=duration,
        )
        print("build-video:", json.dumps(relative), flush=True)

    def write(self, failures: list[str]) -> Path:
        self.data.update(
            status="failed" if failures else "complete",
            failed_sources=failures,
            elapsed_s=round(perf_counter() - self.started, 3),
        )
        destination = self.root / "reports" / f"{self.run_id}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix(".tmp")
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(destination)
        return destination
