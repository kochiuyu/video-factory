#!/usr/bin/env python3
"""Assemble a lesson into a silent master and, if audio exists, four language cells.

Once the YAML is valid, this script is the entire production job:
slides, TTS (if audio is missing), shared clock, four cells.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ff import audio_ok, atomic_replace, check_call, concat_escape, require as require_ffmpeg  # noqa: E402
from langs import (  # noqa: E402
    beat_text,
    bilingual_pair,
    label_code,
    parse_wanted,
    script_langs,
    selected_cells,
    selected_langs,
)
from mux import (  # noqa: E402
    caption_pages,
    concat_clips,
    make_beat_clip,
    page_holds,
    pages_for_stages,
    probe_duration,
    stamp_caption,
    write_srt,
)
from paths import fonts_dir  # noqa: E402
from modules import build_module, is_module  # noqa: E402
from pack import parse_speeds, write_experiment_pack  # noqa: E402
from quiz import export_lesson_quiz  # noqa: E402
from cache import digest_obj, file_fingerprint, stamp_ok, write_mark  # noqa: E402
from preview import render_caption_previews  # noqa: E402
from slides import (  # noqa: E402
    lesson_stamp,
    list_slide_pngs,
    render_lesson_slides,
    slice_durations,
    stage_plan,
    stamp_matches,
    stills_for_beat,
    write_stamp,
    write_stage_slides,
)
from theme import load_theme  # noqa: E402
from tts import synthesize_lesson  # noqa: E402
from validate import load_lesson, validate  # noqa: E402

FONTSDIR = fonts_dir()


def _preview_stem(still: Path, page_i: int, n_pages: int) -> str:
    stem = still.stem
    if n_pages <= 1:
        return stem
    return f"{stem}_c{page_i}"


def _publish_caption_preview(stamped: Path, still: Path, preview_dir: Path, page_i: int, n_pages: int) -> None:
    """Reuse the mux caption PNG as the Captions-tab preview. No second paint."""
    preview_dir.mkdir(parents=True, exist_ok=True)
    dest = preview_dir / f"{_preview_stem(still, page_i, n_pages)}.png"
    if dest.exists() and dest.stat().st_mtime >= stamped.stat().st_mtime and dest.stat().st_size == stamped.stat().st_size:
        return
    try:
        dest.unlink(missing_ok=True)
        os.link(stamped, dest)
    except OSError:
        shutil.copy2(stamped, dest)


def _clip_workers() -> int:
    raw = os.environ.get("VF_CLIP_JOBS", "3")
    try:
        n = int(str(raw).strip() or "3")
    except ValueError:
        n = 3
    cpu = os.cpu_count() or 2
    return max(1, min(n, 4, cpu))


def _clip_key(stills: list[Path], holds: list[float], audio: Path, progress_bar: bool, cap: str) -> str:
    from mux import clip_fps

    payload = {
        "stills": [file_fingerprint(p) for p in stills],
        "holds": [round(float(h), 3) for h in holds],
        "audio": file_fingerprint(audio),
        "bar": progress_bar,
        "cap": cap,
        "still_fade": os.environ.get("VF_STILL_FADE", "0.18"),
        "beat_fade": os.environ.get("VF_BEAT_FADE", "0"),
        "fps": clip_fps(),
        "join": "concat",
        "cap_time": "speech-weight",
    }
    return digest_obj(payload)


def _run_one_clip(stills, holds, audio, clip, key, bar: bool) -> Path:
    make_beat_clip(stills, holds, audio, clip, progress_bar=bar)
    write_mark(clip, key)
    return clip


def _encode_clips(pending: list[tuple], workers: int, cell_i: int, n_cells: int, n_beats: int) -> None:
    done = 0
    total = max(1, len(pending))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(_run_one_clip, stills, holds, audio, clip, key, bar): label
            for clip, stills, holds, audio, key, label, bar in pending
        }
        for fut in as_completed(futures):
            label = futures[fut]
            fut.result()
            done += 1
            print(f"clip: encoded {label}")
            print(f"progress: clip {cell_i}/{n_cells} {done}/{total} {label}")


class _Tee:
    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        text = data if isinstance(data, str) else data.decode("utf-8", "replace")
        for stream in self.streams:
            try:
                stream.write(text)
            except UnicodeEncodeError:
                raw = text.encode("utf-8", "replace")
                buf = getattr(stream, "buffer", None)
                if buf is not None:
                    buf.write(raw)
                else:
                    stream.write(text.encode("ascii", "backslashreplace").decode("ascii"))
            try:
                stream.flush()
            except Exception:
                pass
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def _attach_log(out_dir: Path, lesson_id: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    lesson_log = out_dir / "build.log"
    latest = ROOT / "out" / "last_build.log"
    latest.parent.mkdir(parents=True, exist_ok=True)
    handle = lesson_log.open("a", encoding="utf-8")
    latest_handle = latest.open("a", encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = f"\n===== {lesson_id}  {stamp} =====\n"
    handle.write(header)
    latest_handle.write(header)
    sys.stdout = _Tee(sys.__stdout__, handle, latest_handle)
    sys.stderr = _Tee(sys.__stderr__, handle, latest_handle)
    print("log file:", lesson_log)
    print("latest  :", latest)
    return lesson_log


def pad_audio(src: Path, seconds: float, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.stem}.{os.getpid()}.tmp.mp3")
    check_call(
        [
            "-y",
            "-i",
            str(src),
            "-af",
            f"apad=whole_dur={seconds:.3f}",
            "-t",
            f"{seconds:.3f}",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(tmp),
        ]
    )
    return atomic_replace(tmp, dest)


def concat_audio(parts: list[Path], out_path: Path) -> Path:
    lst = out_path.with_suffix(".concat.txt")
    lst.write_text("".join(f"file '{concat_escape(p)}'\n" for p in parts), encoding="utf-8")
    tmp = out_path.with_suffix(".tmp.mp3")
    check_call(
        [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(tmp),
        ]
    )
    return atomic_replace(tmp, out_path)


def estimate_seconds(beat: dict) -> float:
    if beat.get("seconds"):
        return float(beat["seconds"])
    n_en = max(len((beat.get("en") or "").split()), 1)
    return max(8.0, min(28.0, n_en / 2.3))


def write_narration_pack(lesson: dict, out_dir: Path) -> Path:
    """Sidecar the Voice connector needs: one record per beat per language."""
    jobs = []
    for lang in script_langs(lesson):
        for beat in lesson["beats"]:
            jobs.append(
                {
                    "lesson_id": lesson["id"],
                    "beat_id": beat["id"],
                    "language": lang,
                    "text": beat_text(beat, lang),
                    "dest_path": str(out_dir / "audio" / lang / f"{beat['id']}.mp3"),
                    "with_timestamps": True,
                }
            )
    path = out_dir / "narration_jobs.json"
    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def fmt_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {rem:.1f}s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}h {minutes}m {rem:.1f}s"


class StepClock:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.mark = self.t0
        self.rows: list[tuple[str, float]] = []

    def lap(self, name: str) -> float:
        now = time.perf_counter()
        dt = now - self.mark
        self.mark = now
        self.rows.append((name, dt))
        print(f"timing: {name} {fmt_duration(dt)}")
        return dt

    def total(self) -> float:
        dt = time.perf_counter() - self.t0
        print(f"timing: total {fmt_duration(dt)}")
        if self.rows:
            bits = ", ".join(f"{name} {fmt_duration(sec)}" for name, sec in self.rows)
            print(f"timing: breakdown {bits}")
        return dt


def collect_audio(lesson: dict, audio_root: Path, lang: str) -> list[Path] | None:
    parts = []
    for beat in lesson["beats"]:
        p = audio_root / lang / f"{beat['id']}.mp3"
        if not audio_ok(p):
            return None
        parts.append(p)
    return parts


def build(
    lesson_path: Path,
    out_root: Path,
    label_lang: str,
    tts: bool = True,
    force_tts: bool = False,
    slides_only: bool = False,
    caption_preview: bool = False,
    wanted_cells: list[str] | None = None,
    match_titles: bool = False,
    theme_name: str | None = None,
    progress_bar: bool = True,
    stage_cards: bool = True,
    experiment_pack: bool = False,
    pack_speeds: list[float] | None = None,
    pack_nocap: bool = False,
) -> None:
    lesson = load_lesson(lesson_path)
    out_dir = out_root / lesson.get("id", lesson_path.stem)
    _attach_log(out_dir, lesson.get("id", lesson_path.stem))
    errors = validate(lesson)
    fatal = [e for e in errors if not e.startswith("Beat seconds")]
    if fatal:
        print("INVALID lesson:")
        for e in fatal:
            print(" -", e)
        raise SystemExit(1)
    for e in errors:
        print("note:", e)

    langs = selected_langs(lesson, wanted_cells)
    cells = selected_cells(lesson, wanted_cells)
    if not match_titles:
        shared = label_code(label_lang)
        matched = {"en", "zhcn", "zhhk", "en-en", "en-zh", "zh-en", "zh-zh"}
        cells = {
            name: (voice, cap, slide if name not in matched else shared)
            for name, (voice, cap, slide) in cells.items()
        }
    export_lesson_quiz(lesson, out_dir)
    print("tracks:", ", ".join(langs) or "(none)")
    print("cells:", ", ".join(cells) or "(none)")
    print("titles:", "match cell language" if match_titles else f"shared {label_lang}")
    clock = StepClock()
    theme = load_theme(theme_name)
    cell_slides: dict[str, tuple[str, str | None]] = {}
    for name, (voice, cap, slide) in cells.items():
        cell_slides[name] = bilingual_pair(voice, cap, slide)
    codes: list[tuple[str, str | None]] = []
    for pair in cell_slides.values():
        if pair not in codes:
            codes.append(pair)
    if not codes:
        fallback = label_code(label_lang)
        codes = [(fallback, None)]
    slide_sets: dict[tuple[str, str | None], list[Path]] = {}
    preview_holds = [float(beat.get("seconds") or 12) for beat in lesson["beats"]]
    keep_folders = {code if not second else f"{code}+{second}" for code, second in codes}
    slides_root = out_dir / "slides"
    if slides_root.is_dir():
        for child in slides_root.iterdir():
            if child.is_dir() and child.name not in keep_folders:
                shutil.rmtree(child, ignore_errors=True)
    print("slide folders:", ", ".join(sorted(keep_folders)) or "(none)")
    print(f"progress: slides 0/{max(1, len(codes))} start")
    for slide_i, (code, second) in enumerate(codes, start=1):
        folder = code if not second else f"{code}+{second}"
        slide_dir = out_dir / "slides" / folder
        stamp = lesson_stamp(lesson, theme, code, second, stage_cards)
        if stamp_matches(slide_dir, stamp):
            slide_sets[(code, second)] = list_slide_pngs(slide_dir)
            print("slides: reuse", slide_dir, f"({len(slide_sets[(code, second)])} png)")
            print(f"progress: slides {slide_i}/{len(codes)} {folder} reuse")
            continue
        slide_sets[(code, second)] = render_lesson_slides(
            lesson,
            slide_dir,
            label_lang=code,
            theme=theme,
            second_lang=second,
        )
        if stage_cards:
            write_stage_slides(
                lesson,
                slide_dir,
                code,
                preview_holds,
                theme=theme,
                force=True,
                second_lang=second,
            )
        write_stamp(slide_dir, stamp)
        print("slides:", slide_dir, "bilingual" if second else "single")
        print(f"progress: slides {slide_i}/{len(codes)} {folder}")
    slides = slide_sets[codes[0]]
    jobs_path = write_narration_pack(lesson, out_dir)
    print("narration jobs:", jobs_path)
    clock.lap("slides")
    if caption_preview:
        preview_kw = dict(
            langs=langs,
            match_titles=match_titles,
            shared_slides=slides,
            theme=theme,
            stage_cards=stage_cards,
            cells=cells,
        )
        accepted = set(inspect.signature(render_caption_previews).parameters)
        preview_kw = {k: v for k, v in preview_kw.items() if k in accepted}
        try:
            previews = render_caption_previews(lesson, slides, out_dir, **preview_kw)
        except Exception as exc:  # noqa: BLE001
            print(f"caption-preview failed: {exc}")
            raise SystemExit(1) from exc
        if not previews:
            print("caption-preview failed: no frames written")
            raise SystemExit(1)
        print(f"caption-preview: wrote {len(previews)} stamped frames; skipped TTS and mux")
        clock.lap("caption preview")
        clock.total()
        return
    if slides_only:
        print(f"slides-only: wrote {sum(len(v) for v in slide_sets.values())} PNG files; skipped TTS and mux")
        clock.total()
        return
    require_ffmpeg()

    audio_root = out_dir / "audio"
    if tts:
        print("tts: synthesizing missing beat audio" + (" (overwrite)" if force_tts else ""))
        synthesize_lesson(lesson, audio_root, overwrite=force_tts, langs=langs)
    clock.lap("speech")
    tracks = {lang: collect_audio(lesson, audio_root, lang) for lang in langs}
    if all(tracks.values()):
        durations = []
        for i in range(len(lesson["beats"])):
            durations.append(max(probe_duration(tracks[lang][i]) for lang in langs))
        pad_dir = out_dir / "audio" / "padded"
        padded: dict[str, list[Path]] = {lang: [] for lang in langs}
        for lang in langs:
            for beat, src, dur in zip(lesson["beats"], tracks[lang], durations):
                padded[lang].append(pad_audio(src, dur, pad_dir / lang / f"{beat['id']}.mp3"))
            concat_audio(padded[lang], out_dir / "audio" / f"{lang}.mp3")
        tracks = padded
    elif tracks.get("en"):
        durations = [probe_duration(p) for p in tracks["en"]]
        concat_audio(tracks["en"], out_dir / "audio" / "en.mp3")
    else:
        durations = [estimate_seconds(b) for b in lesson["beats"]]
        print("EN audio missing; beat clips will use target beat lengths.")

    for code, second in codes:
        folder = code if not second else f"{code}+{second}"
        if stage_cards:
            write_stage_slides(
                lesson,
                out_dir / "slides" / folder,
                code,
                durations,
                theme=theme,
                second_lang=second,
            )
        print("stage stills:", out_dir / "slides" / folder)
    clock.lap("stage stills")

    def beat_pages_and_holds(beat: dict, dur: float, sub_lang: str) -> tuple[list[str], list[float], list[int], list[int]]:
        plan = stage_plan(beat, dur) if stage_cards else [0]
        text = beat_text(beat, sub_lang)
        if plan == [0]:
            pages = caption_pages(text)
            return pages, page_holds(dur, pages), plan, [0] * max(1, len(pages))
        pages, page_durs, still_idx = pages_for_stages(text, dur, len(plan))
        return pages, page_durs, plan, still_idx

    def cues(lang: str) -> list[tuple[float, float, str]]:
        t = 0.0
        out = []
        for beat, d in zip(lesson["beats"], durations):
            pages, holds, _plan, _idx = beat_pages_and_holds(beat, d, lang)
            for page, hold in zip(pages, holds):
                out.append((t, t + max(hold - 0.02, 0.35), page))
                t += hold
        return out

    from mux import clip_fps

    workers = _clip_workers()
    print(
        "motion: dissolve",
        os.environ.get("VF_STILL_FADE", "0.18"),
        "beat-fade",
        os.environ.get("VF_BEAT_FADE", "0"),
        "fps",
        clip_fps(),
        "clip-jobs",
        workers,
    )
    if all(tracks.values()):
        srt_dir = out_dir / "srt"
        srt_dir.mkdir(parents=True, exist_ok=True)
        n_beats = len(lesson["beats"])
        n_cells = max(1, len(cells))
        for cell_i, (name, (audio_lang, sub_lang, slide_lang)) in enumerate(cells.items(), start=1):
            code, second = cell_slides.get(name, (slide_lang, None))
            folder = code if not second else f"{code}+{second}"
            slide_dir = out_dir / "slides" / folder
            stamp_dir = out_dir / "captions" / name
            clip_dir = out_dir / "clips" / name
            clips: list[Path] = []
            nocap_clips: list[Path] = []
            parts = tracks[audio_lang]
            pending: list[tuple] = []
            for i, (beat, dur, audio) in enumerate(zip(lesson["beats"], durations, parts), start=1):
                pages, holds, plan, still_idx = beat_pages_and_holds(beat, dur, sub_lang)
                print(f"captions {name}/{beat['id']}: {len(pages)} cards")
                base = stills_for_beat(slide_dir, i, beat, plan)
                if not base:
                    continue
                stills = [base[min(k, len(base) - 1)] for k in still_idx]
                stamped: list[Path] = []
                for j, (still, page) in enumerate(zip(stills, pages), start=1):
                    dest = stamp_dir / f"{i:02d}_{beat['id']}_{j:02d}.png"
                    stamp_caption(still, page, dest)
                    stamped.append(dest)
                    _publish_caption_preview(dest, still, out_dir / "preview" / folder, j, len(pages))
                clip = clip_dir / f"{i:02d}_{beat['id']}.mp4"
                clip_key = _clip_key(stamped, holds, audio, progress_bar, cap="on")
                clips.append(clip)
                if stamp_ok(clip, clip_key):
                    print(f"clip: reuse {clip.name}")
                else:
                    pending.append((clip, stamped, holds, audio, clip_key, f"{name}/{beat['id']}", progress_bar))
                if experiment_pack and pack_nocap:
                    raw_clip = clip_dir / f"{i:02d}_{beat['id']}_nocap.mp4"
                    raw_key = _clip_key(stills[: len(holds)], holds, audio, progress_bar, cap="off")
                    nocap_clips.append(raw_clip)
                    if stamp_ok(raw_clip, raw_key):
                        print(f"clip: reuse {raw_clip.name}")
                    else:
                        pending.append(
                            (
                                raw_clip,
                                stills[: len(holds)],
                                holds,
                                audio,
                                raw_key,
                                f"{name}/{beat['id']}_nocap",
                                progress_bar,
                            )
                        )
            if pending:
                print(f"progress: clip {cell_i}/{n_cells} 0/{n_beats} {name} encode {len(pending)}")
                _encode_clips(pending, workers, cell_i, n_cells, n_beats)
            dest = out_dir / "cells" / f"{lesson['id']}_{name}.mp4"
            print(f"concat: {name} ({len(clips)} beats)")
            print(f"progress: concat {cell_i}/{n_cells} {name}")
            join_key = digest_obj({"clips": [file_fingerprint(p) for p in clips]})
            if stamp_ok(dest, join_key):
                print(f"concat: reuse {dest.name}")
            else:
                concat_clips(clips, dest)
                write_mark(dest, join_key)
            write_srt(cues(sub_lang), srt_dir / f"{name}.srt")
            print("cell:", dest, f"({probe_duration(dest):.1f}s)")
            if experiment_pack and pack_nocap and nocap_clips:
                off = out_dir / "cells" / f"{lesson['id']}_{name}_nocap.mp4"
                print(f"concat: {name}_nocap ({len(nocap_clips)} beats)")
                off_key = digest_obj({"clips": [file_fingerprint(p) for p in nocap_clips], "cap": "off"})
                if stamp_ok(off, off_key):
                    print(f"concat: reuse {off.name}")
                else:
                    concat_clips(nocap_clips, off)
                    write_mark(off, off_key)
                print("cell:", off, f"({probe_duration(off):.1f}s)")
            clock.lap(f"video {name}")
    else:
        missing = [lang for lang, parts in tracks.items() if not parts]
        print("Skip cell mux; missing audio for", ", ".join(missing) or "unknown")
        clock.lap("skip videos")
    if experiment_pack:
        csv_path = write_experiment_pack(out_dir, lesson["id"], cells, pack_speeds)
        print("experiment-pack:", csv_path)
        clock.lap("experiment pack")
    clock.total()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("lesson", type=Path, nargs="?", help="Lesson YAML, or omit with --all.")
    p.add_argument("--out", type=Path, default=ROOT / "out")
    p.add_argument("--labels", choices=("en", "zh"), default="en")
    p.add_argument("--no-tts", action="store_true", help="Do not call TTS; require existing MP3s.")
    p.add_argument("--force-tts", action="store_true", help="Regenerate all beat audio.")
    p.add_argument("--slides-only", action="store_true", help="Paint PNGs and stop.")
    p.add_argument(
        "--caption-preview",
        action="store_true",
        help="Paint slides and stamp caption bars; no TTS or mux.",
    )
    p.add_argument(
        "--cells",
        default="",
        help="Matched names (en,zhcn,zhhk) or mixes voice-caption-slide (en-zh-hk).",
    )
    p.add_argument(
        "--match-titles",
        action="store_true",
        help="Paint slide titles in the cell language (EN / 简体 / 繁體).",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Build every YAML in lessons/ with the same flags.",
    )
    p.add_argument(
        "--theme",
        default="cuhk-navy",
        help="Palette in themes/<name>.yaml (preview with --slides-only).",
    )
    p.add_argument(
        "--no-progress-bar",
        action="store_true",
        help="Do not draw the gold beat bar on the silent master.",
    )
    p.add_argument(
        "--no-stage-cards",
        action="store_true",
        help="Hold the finished slide for the whole beat; do not reveal cards in order.",
    )
    p.add_argument(
        "--experiment-pack",
        action="store_true",
        help="After cells, write speed variants, optional no-caption twins, and treatments.csv.",
    )
    p.add_argument(
        "--pack-speeds",
        default="",
        help="Comma list of playback speeds, e.g. 1,1.25,1.5,2",
    )
    p.add_argument(
        "--pack-nocap",
        action="store_true",
        help="Also mux a caption-off twin of each cell before speeding.",
    )
    p.add_argument(
        "--bundle",
        default="",
        help="Write CUHK-VF-<ECON|ACC|GBA>.zip from existing out/ files and exit.",
    )
    args = p.parse_args()
    off = {"0", "false", "no", "off"}
    progress_bar = not args.no_progress_bar and os.environ.get("VF_PROGRESS_BAR", "1").lower() not in off
    stage_cards = not args.no_stage_cards and os.environ.get("VF_STAGE_CARDS", "1").lower() not in off
    experiment_pack = args.experiment_pack or os.environ.get("VF_EXPERIMENT_PACK", "").lower() not in {"", "0", "false", "no", "off"}
    pack_nocap = args.pack_nocap or os.environ.get("VF_PACK_NOCAP", "").lower() not in {"", "0", "false", "no", "off"}
    pack_speeds = parse_speeds(args.pack_speeds or os.environ.get("VF_PACK_SPEEDS", ""))
    if args.bundle:
        from bundle import write_course_zip
        path = write_course_zip(args.bundle.strip().upper(), args.out)
        print("bundle:", path)
        return
    if args.all:
        from catalog import LESSONS, iter_lesson_paths

        paths = iter_lesson_paths()
        if not paths:
            raise SystemExit(f"No YAML files in {LESSONS}")
        failed = 0
        for path in paths:
            print(f"\n######## {path.name} ########")
            try:
                if is_module(path):
                    build_module(
                        path,
                        args.out,
                        label_lang=args.labels,
                        tts=not args.no_tts,
                        force_tts=args.force_tts,
                        wanted_cells=parse_wanted(args.cells),
                        match_titles=args.match_titles,
                        theme_name=args.theme,
                        progress_bar=progress_bar,
                        stage_cards=stage_cards,
                        experiment_pack=experiment_pack,
                        pack_speeds=pack_speeds,
                        pack_nocap=pack_nocap,
                        slides_only=args.slides_only,
                        caption_preview=args.caption_preview,
                    )
                    continue
                build(
                    path,
                    args.out,
                    args.labels,
                    tts=not args.no_tts,
                    force_tts=args.force_tts,
                    slides_only=args.slides_only,
                    caption_preview=args.caption_preview,
                    wanted_cells=parse_wanted(args.cells),
                    match_titles=args.match_titles,
                    theme_name=args.theme,
                    progress_bar=progress_bar,
                    stage_cards=stage_cards,
                    experiment_pack=experiment_pack,
                    pack_speeds=pack_speeds,
                    pack_nocap=pack_nocap,
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAILED {path.name}: {exc}")
        if failed:
            raise SystemExit(f"{failed} lesson(s) failed")
        print(f"batch: finished {len(paths)} lessons")
        return
    if args.lesson is None:
        raise SystemExit("Pass a lesson YAML or use --all")
    if is_module(args.lesson):
        build_module(
            args.lesson,
            args.out,
            label_lang=args.labels,
            tts=not args.no_tts,
            force_tts=args.force_tts,
            wanted_cells=parse_wanted(args.cells),
            match_titles=args.match_titles,
            theme_name=args.theme,
            progress_bar=progress_bar,
            stage_cards=stage_cards,
            experiment_pack=experiment_pack,
            pack_speeds=pack_speeds,
            pack_nocap=pack_nocap,
            slides_only=args.slides_only,
            caption_preview=args.caption_preview,
        )
        return
    build(
        args.lesson,
        args.out,
        args.labels,
        tts=not args.no_tts,
        force_tts=args.force_tts,
        slides_only=args.slides_only,
        caption_preview=args.caption_preview,
        wanted_cells=parse_wanted(args.cells),
        match_titles=args.match_titles,
        theme_name=args.theme,
        progress_bar=progress_bar,
        stage_cards=stage_cards,
        experiment_pack=experiment_pack,
        pack_speeds=pack_speeds,
        pack_nocap=pack_nocap,
    )


if __name__ == "__main__":
    main()
