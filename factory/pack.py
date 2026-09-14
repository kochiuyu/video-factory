#!/usr/bin/env python3
"""Write a labelled experiment pack: speed variants, caption-off twins, CSV."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

from ff import atomic_replace, check_call, probe_duration

DEFAULT_SPEEDS = (1.0, 1.25, 1.5, 2.0)
VOICE_LABEL = {
    "en": "en",
    "zh_cn": "zhcn",
    "zh": "zhcn",
    "zh_hk": "zhhk",
}
SLIDE_LABEL = {
    "en": "en",
    "zh": "zh",
    "zh_cn": "zh",
    "zh_hk": "zhhk",
}


def parse_speeds(raw: str | None) -> list[float]:
    if not raw:
        return list(DEFAULT_SPEEDS)
    out: list[float] = []
    for part in str(raw).replace(";", ",").split(","):
        part = part.strip().lower().replace("×", "").replace("x", "")
        if not part:
            continue
        try:
            val = float(part)
        except ValueError:
            continue
        if 0.5 <= val <= 2.0:
            out.append(val)
    return out or list(DEFAULT_SPEEDS)


def speed_tag(speed: float) -> str:
    return f"{speed:.2f}".replace(".", "p") + "x"


def pack_stem(lesson_id: str, cell: str, caption_mode: str, speed: float) -> str:
    cap = "cap-burn" if caption_mode == "burned" else "cap-off"
    return f"{lesson_id}__{cell}__{cap}__{speed_tag(speed)}"


def describe_cell(name: str, triple: tuple[str, str, str] | None) -> dict:
    nocap = name.endswith("_nocap")
    base = name[:-6] if nocap else name
    if triple:
        voice, cap, slide = triple
    else:
        voice = cap = slide = base.split("-")[0] if base else "en"
    return {
        "cell": base,
        "voice": VOICE_LABEL.get(voice, voice),
        "captions": "" if nocap else VOICE_LABEL.get(cap, cap),
        "slides": SLIDE_LABEL.get(slide, slide),
        "caption_mode": "none" if nocap else "burned",
    }


def speed_copy(src: Path, dest: Path, speed: float) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    from cache import digest_obj, file_fingerprint, stamp_ok, write_mark

    key = digest_obj({"src": file_fingerprint(src), "speed": round(float(speed), 4)})
    if stamp_ok(dest, key):
        print(f"pack: reuse {dest.name}")
        return dest
    if abs(speed - 1.0) < 1e-6:
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        write_mark(dest, key)
        return dest
    tmp = dest.with_suffix(".tmp.mp4")
    check_call(
        [
            "-y",
            "-i",
            str(src),
            "-filter:v",
            f"setpts=PTS/{speed:.4f}",
            "-filter:a",
            f"atempo={speed:.4f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(tmp),
        ]
    )
    out = atomic_replace(tmp, dest)
    write_mark(out, key)
    return out


def scale_srt(src: Path, dest: Path, speed: float) -> Path | None:
    if not src.is_file():
        return None
    if abs(speed - 1.0) < 1e-6:
        dest.write_bytes(src.read_bytes())
        return dest
    text = src.read_text(encoding="utf-8")

    def shift(stamp: str) -> str:
        hh, mm, rest = stamp.split(":")
        ss, ms = rest.split(",")
        total = int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0
        total = max(0.0, total / speed)
        h = int(total // 3600)
        m = int(total % 3600 // 60)
        s = int(total % 60)
        milli = int(round((total - int(total)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"

    lines = []
    for line in text.splitlines():
        if " --> " in line:
            a, b = line.split(" --> ", 1)
            lines.append(f"{shift(a.strip())} --> {shift(b.strip())}")
        else:
            lines.append(line)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def write_experiment_pack(
    out_dir: Path,
    lesson_id: str,
    cells: dict[str, tuple[str, str, str]],
    speeds: list[float] | None = None,
) -> Path:
    """Copy each built cell at each speed into out/<id>/pack/ plus treatments.csv."""
    speeds = [s for s in (speeds or list(DEFAULT_SPEEDS)) if 0.5 <= s <= 2.0]
    pack_dir = out_dir / "pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    cell_dir = out_dir / "cells"
    srt_dir = out_dir / "srt"
    sources = sorted(cell_dir.glob("*.mp4")) if cell_dir.is_dir() else []
    rows: list[dict] = []
    total = max(1, len(sources) * max(1, len(speeds)))
    done = 0
    for src in sources:
        raw = src.stem
        prefix = f"{lesson_id}_"
        name = raw[len(prefix) :] if raw.startswith(prefix) else raw
        base = name[:-6] if name.endswith("_nocap") else name
        meta = describe_cell(name, cells.get(base))
        srt_src = srt_dir / f"{base}.srt"
        for speed in speeds:
            done += 1
            stem = pack_stem(lesson_id, meta["cell"], meta["caption_mode"], speed)
            dest = pack_dir / f"{stem}.mp4"
            print(f"progress: pack {done}/{total} {dest.name}")
            print(f"pack: {dest.name}")
            speed_copy(src, dest, speed)
            srt_path = ""
            if meta["caption_mode"] == "burned" and srt_src.is_file():
                written = scale_srt(srt_src, pack_dir / f"{stem}.srt", speed)
                srt_path = written.name if written else ""
            try:
                dur = probe_duration(dest)
            except Exception:
                dur = 0.0
            rows.append(
                {
                    "cell_id": stem,
                    "file": dest.name,
                    "lesson": lesson_id,
                    "voice": meta["voice"],
                    "captions": meta["captions"],
                    "slides": meta["slides"],
                    "caption_mode": meta["caption_mode"],
                    "speed": f"{speed:.2f}",
                    "duration_s": f"{dur:.2f}",
                    "srt": srt_path,
                    "source_cell": src.name,
                }
            )
    csv_path = pack_dir / "treatments.csv"
    fields = [
        "cell_id",
        "file",
        "lesson",
        "voice",
        "captions",
        "slides",
        "caption_mode",
        "speed",
        "duration_s",
        "srt",
        "source_cell",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"pack: wrote {len(rows)} treatments -> {csv_path}")
    return csv_path
