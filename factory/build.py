#!/usr/bin/env python3
"""Assemble a lesson into a silent master and, if audio exists, four language cells.

Once the YAML is valid, this script is the entire production job:
slides, TTS (if audio is missing), shared clock, four cells.
"""

from __future__ import annotations

import sys
from pathlib import Path as _PathForBoot

_FACTORY = _PathForBoot(__file__).resolve().parent
sys.path.insert(0, str(_FACTORY))
try:
    from utf8io import force_utf8  # noqa: E402
except ModuleNotFoundError:
    import os as _os

    def force_utf8() -> None:
        _os.environ.setdefault("PYTHONUTF8", "1")
        _os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            reconf = getattr(stream, "reconfigure", None)
            if reconf is None:
                continue
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass

force_utf8()

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
)
from mux import (  # noqa: E402
    CAP_TIME_WEIGHT,
    CAP_TIME_WORDS,
    caption_pages,
    concat_clips,
    holds_for_pages,
    make_beat_clip,
    pages_for_stages,
    probe_duration,
    caption_orphans,
    stage_scripts,
    stamp_caption,
    write_srt,
)
from paths import fonts_dir  # noqa: E402
from modules import build_minicourse, build_module, is_minicourse, is_module, load_module  # noqa: E402
from catalog import lesson_path, migrate_out_layout, out_dir as lesson_out_dir, out_root as resolve_out_root  # noqa: E402
from pack import pack_videos, parse_speeds, write_experiment_pack  # noqa: E402
from quiz import export_lesson_quiz  # noqa: E402
from cover import font as cover_font, write_cover  # noqa: E402
from build_report import BuildReport  # noqa: E402
from cache import digest_obj, file_fingerprint, stamp_ok, write_mark  # noqa: E402
from preview import render_caption_previews  # noqa: E402
from pdfexport import export_preview_pdfs  # noqa: E402
from slides import (  # noqa: E402
    apply_theme_fonts,
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
from youtube import load_series_links, write_youtube_sidecars, youtube_warnings  # noqa: E402
from tts import google_api_key, load_word_times, synthesize_lesson, tts_backend, tts_pitch, tts_rate, tts_volume, voice_for  # noqa: E402
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
    default = "1" if sys.platform.startswith("win") else "3"
    raw = os.environ.get("VF_CLIP_JOBS", default)
    try:
        n = int(str(raw).strip() or default)
    except ValueError:
        n = int(default)
    cpu = os.cpu_count() or 2
    return max(1, min(n, 4, cpu))


def _clip_key(
    stills: list[Path],
    holds: list[float],
    audio: Path,
    progress_bar: bool,
    cap: str,
    cap_time: str = CAP_TIME_WEIGHT,
) -> str:
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
        "cap_time": cap_time,
    }
    return digest_obj(payload)


def _run_one_clip(stills, holds, audio, clip, key, bar: bool) -> Path:
    print(f"clip: start {clip.name} ({len(stills)} stills)", flush=True)
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


def _attach_log(out_dir: Path, lesson_id: str, root: Path | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    lesson_log = out_dir / "build.log"
    latest = (Path(root) if root is not None else resolve_out_root()) / "last_build.log"
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


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def pad_cap() -> float | None:
    """VF_PAD_CAP=1.0 caps the silence added after each beat in a language
    to about that many seconds. Unset = old behaviour (pad to the longest
    language, so every cell has the same beat lengths)."""
    cap = _env_float("VF_PAD_CAP")
    return None if cap is None or cap < 0 else cap


# What-is lessons time each language on its own speech. This breath is the
# only silence after a line. It is not applied to STAT or other courses.
OWN_BREATH_S = 0.4


def owns_speech_clock(lesson: dict) -> bool:
    """Per-language timing for a What-is lesson. Other lessons stay on the
    shared clock. `clock: own` opts a lesson in; `clock: shared` opts out."""
    flag = str(lesson.get("clock") or "").strip().lower()
    if flag == "shared":
        return False
    if flag == "own":
        return True
    visuals = [str(beat.get("visual") or "") for beat in (lesson.get("beats") or [])]
    return bool(visuals) and all(visual.startswith("whatis_") for visual in visuals)


def speech_breath_durations(raw: dict[str, list[float]], breath: float = OWN_BREATH_S) -> dict[str, list[float]]:
    """Each language keeps its own speech length, plus one short breath."""
    return {lang: [float(d) + breath for d in vals] for lang, vals in raw.items()}


def capped_durations(raw: dict[str, list[float]], shared: list[float], cap: float | None) -> dict[str, list[float]]:
    if cap is None:
        return {lang: list(shared) for lang in raw}
    return {lang: [min(d, r + cap) for r, d in zip(vals, shared)] for lang, vals in raw.items()}


def hold_limits() -> tuple[float, float, bool]:
    warn = _env_float("VF_HOLD_WARN") or 20.0
    fail = _env_float("VF_HOLD_FAIL") or 30.0
    strict = os.environ.get("VF_STRICT_HOLD", "").strip().lower() in {"1", "true", "yes", "on"}
    return warn, fail, strict


def still_holds(plan: list[int], still_idx: list[int], holds: list[float]) -> list[tuple[str, float]]:
    """(stage label, seconds on screen) per still, from the caption page holds."""
    totals: dict[int, float] = {}
    for k, h in zip(still_idx, holds):
        totals[k] = totals.get(k, 0.0) + float(h)
    out = []
    for k in sorted(totals):
        label = "base" if plan == [0] else f"s{plan[min(k, len(plan) - 1)]}"
        out.append((label, totals[k]))
    return out


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
    def __init__(self, report: BuildReport | None = None) -> None:
        self.report = report
        self.t0 = time.perf_counter()
        self.mark = self.t0
        self.rows: list[tuple[str, float]] = []

    def lap(self, name: str) -> float:
        now = time.perf_counter()
        dt = now - self.mark
        self.mark = now
        self.rows.append((name, dt))
        if self.report:
            self.report.phase(name, dt)
        print(f"timing: {name} {fmt_duration(dt)}")
        return dt

    def total(self) -> float:
        dt = time.perf_counter() - self.t0
        print(f"timing: total {fmt_duration(dt)}")
        if self.rows:
            bits = ", ".join(f"{name} {fmt_duration(sec)}" for name, sec in self.rows)
            print(f"timing: breakdown {bits}")
        return dt


def sweep_intermediates(out_dir: Path, *, videos: bool = False) -> None:
    """Drop build leftovers once the deliverables are on disk.

    Keep cells, slides, caption previews, PDFs, quizzes, SRT, covers, and
    the raw speech. Remove beat videos, caption overlays, padded audio,
    bar frames, and concat lists. Set VF_KEEP_INTERMEDIATES=1 to skip.
    """
    if os.environ.get("VF_KEEP_INTERMEDIATES", "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    if not out_dir.is_dir():
        return
    removed = 0

    def drop_tree(path: Path) -> None:
        nonlocal removed
        if not path.is_dir():
            return
        shutil.rmtree(path, ignore_errors=True)
        removed += 1

    if videos:
        drop_tree(out_dir / "clips")
        drop_tree(out_dir / "captions")
        drop_tree(out_dir / "audio" / "padded")
    drop_tree(out_dir / "preview" / "_bars")
    for path in out_dir.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if name.endswith(".concat.txt") or ".tmp." in name or name.endswith(".tmp.mp4") or name.endswith(".tmp.mp3"):
            path.unlink(missing_ok=True)
            removed += 1
    if removed:
        print(f"cleanup: removed {removed} intermediate item(s)")


def _write_preview_pdfs(lid: str, out_root: Path, kinds: tuple[str, ...]) -> None:
    try:
        written = export_preview_pdfs(lid, out_root, kinds)
    except Exception as exc:  # noqa: BLE001
        print(f"pdf skip: {exc}")
        return
    if written:
        print("pdf:", ", ".join(p.name for p in written))


def load_audio_tracks(lesson: dict, audio_root: Path, required: list[str]) -> dict[str, list[Path]]:
    """Include each complete narration track in the shared timeline."""
    tracks = {}
    missing = []
    for lang in script_langs(lesson):
        parts = [audio_root / lang / f"{beat['id']}.mp3" for beat in lesson["beats"]]
        unusable = [part for part in parts if not audio_ok(part)]
        if not unusable:
            tracks[lang] = parts
        elif lang in required:
            missing.extend(part.relative_to(audio_root).as_posix() for part in unusable)
    if missing:
        raise RuntimeError("Missing or unreadable audio: " + ", ".join(missing))
    return tracks


def write_cell_covers(lesson_path: Path, lesson: dict, cells: dict, cell_slides: dict, out_dir: Path) -> None:
    """One 1920x1080 cover per cell: topic, slide language, speech language.

    Cover titles follow the cell name (en / zh / hk / en+zh / …), not the
    shared --labels override used when painting video slides.
    """
    cover_dir = out_dir / "covers"
    for name, (audio_lang, _sub, _slide) in cells.items():
        # Cell name already encodes mono/bilingual slide language; do not use
        # cell_slides (those follow the shared --labels override for video slides).
        slide_key = name
        dest = cover_dir / f"{lesson['id']}_{name}.png"
        write_cover(lesson_path, slide_key, audio_lang, dest)
        print("cover:", dest)


def check_holds_and_orphans(lesson, cells, lang_durations, durations, pages_fn) -> list[str]:
    """C4b: warn when one still stays on screen > VF_HOLD_WARN (20 s); with
    VF_STRICT_HOLD=1 (or --strict-hold) fail above VF_HOLD_FAIL (30 s).
    Also warn about caption sentences that would end on a 1-2 word card."""
    warn, fail, strict = hold_limits()
    seen: set = set()
    msgs: list[str] = []
    fatal: list[str] = []
    for name, (audio_lang, sub_lang, _slide) in cells.items():
        for beat, dur in zip(lesson["beats"], lang_durations.get(audio_lang, durations)):
            _pages, holds, plan, still_idx, _how = pages_fn(beat, dur, sub_lang, audio_lang, quiet=True)
            if plan != [0] and len(set(still_idx)) != len(plan):
                key = ("count", audio_lang, sub_lang, beat["id"])
                if key not in seen:
                    seen.add(key)
                    msgs.append(f"stills: {lesson['id']} {beat['id']} ({audio_lang}/{sub_lang}): {len(plan)} stages but captions reach {len(set(still_idx))} stills")
            for label, secs in still_holds(plan, still_idx, holds):
                key = (audio_lang, beat["id"], label)
                if secs <= warn or key in seen:
                    continue
                seen.add(key)
                line = (
                    f"hold: {lesson['id']} beat {beat['id']} stage {label} ({audio_lang} voice) "
                    f"stays {secs:.1f}s on one still (> {warn:.0f}s); split that stage's script "
                    f"into two chunks or add a stage so the slide changes sooner"
                )
                msgs.append(line)
                if secs > fail:
                    fatal.append(line)
    for code in sorted({sub for _a, sub, _s in cells.values()}):
        n = 0
        for beat in lesson["beats"]:
            bad = caption_orphans(beat_text(beat, code))
            n += len(bad)
            for row in bad[:1]:
                msgs.append(f"orphan: {lesson['id']} {beat['id']} ({code}) last caption card is short: {row}")
        if n:
            msgs.append(f"orphan: {lesson['id']} ({code}) {n} sentence(s) end on a 1-2 word card")
    for m in msgs:
        print("warn:", m)
    if strict and fatal:
        print(f"FAIL (VF_STRICT_HOLD): {len(fatal)} still(s) over {fail:.0f}s")
        raise RuntimeError(f"{len(fatal)} still(s) exceed the strict hold limit")
    return msgs


def prepare_short(
    source: Path, root: Path, *, label_lang: str, tts: bool,
    slides_only: bool, caption_preview: bool, wanted_cells: list[str] | None,
    match_titles: bool, theme_name: str | None, report: BuildReport | None,
):
    """Validate the selected inputs before painting, encoding or calling TTS."""
    started = time.perf_counter()
    lesson = load_lesson(source)
    out_dir = lesson_out_dir(lesson.get("id", source.stem), root=root)
    errors = validate(lesson)
    fatal = [error for error in errors if not error.startswith("Beat seconds")]
    if fatal:
        raise ValueError("Invalid lesson:\n - " + "\n - ".join(fatal))
    for note in errors:
        print("note:", note)
        if report:
            report.warn(note)

    cells = selected_cells(lesson, wanted_cells)
    if not match_titles:
        shared = label_code(label_lang)
        cells = {
            name: (voice, captions, shared if name in {"en", "zh", "hk"} else slides)
            for name, (voice, captions, slides) in cells.items()
        }
    if report:
        report.item["lesson_id"] = lesson.get("id", source.stem)
        report.cuts(cells)
    theme = load_theme(theme_name)
    if report:
        report.item["theme"] = theme["id"]
    for label, cjk in (("Latin bold", False), ("CJK", True)):
        try:
            cover_font(32, cjk=cjk)
        except OSError as exc:
            raise RuntimeError(
                f"Cannot load the {label} cover font. Restore the bundled fonts/ files and run diagnose.py."
            ) from exc
    tracks = {}
    if not (slides_only or caption_preview):
        require_ffmpeg()
        if tts:
            backend = tts_backend()
            if backend == "google":
                google_api_key()
            if report:
                report.item["narration"] = {
                    "backend": backend,
                    "rate": tts_rate(), "pitch": tts_pitch(), "volume": tts_volume(),
                    "voices": {lang: voice_for(lang) for lang in script_langs(lesson)},
                }
        else:
            required = list(dict.fromkeys(voice for voice, _, _ in cells.values()))
            tracks = load_audio_tracks(lesson, out_dir / "audio", required)
            if report:
                report.item["narration"] = {"backend": "local", "tracks": list(tracks)}
    if report:
        report.phase("preflight", time.perf_counter() - started)
    return lesson, out_dir, cells, theme, tracks


def preflight(source: Path, root: Path, *, report: BuildReport, **options) -> list[Path]:
    is_collection = is_minicourse(source) or is_module(source)
    if is_collection:
        collection = load_module(source)
        ids = collection.get("lessons")
        if not isinstance(ids, list) or len(ids) < 2 or not all(isinstance(lid, str) for lid in ids):
            raise ValueError("A collection needs at least two lesson IDs.")
        if len(set(ids)) != len(ids):
            raise ValueError("Collection contains duplicate lesson IDs.")
        failed = []
        for lid in ids:
            child = lesson_path(lid)
            if child is None:
                failed.append(f"{lid}: lesson file missing")
                continue
            try:
                report.run(child, check_short, root, **options)
            except Exception as exc:
                failed.append(f"{lid}: {exc}")
        if failed:
            raise ValueError("Collection preflight failed:\n - " + "\n - ".join(failed))
    else:
        check_short(source, root, report=report, **options)
    print("preflight: passed", source.name)
    return []


def check_short(source: Path, root: Path, *, report: BuildReport, **options) -> None:
    keys = ("label_lang", "tts", "slides_only", "caption_preview", "wanted_cells", "match_titles", "theme_name")
    prepare_short(source, root, report=report, **{key: options[key] for key in keys})


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
    write_pdfs: bool = True,
    report: BuildReport | None = None,
) -> list[Path]:
    lesson, out_dir, cells, theme, tracks = prepare_short(
        lesson_path, out_root, label_lang=label_lang, tts=tts, slides_only=slides_only,
        caption_preview=caption_preview, wanted_cells=wanted_cells, match_titles=match_titles,
        theme_name=theme_name, report=report,
    )
    langs = list(dict.fromkeys(voice for voice, _, _ in cells.values()))
    audio_root = out_dir / "audio"
    _attach_log(out_dir, lesson.get("id", lesson_path.stem), out_root)
    export_lesson_quiz(lesson, out_dir)
    print("tracks:", ", ".join(langs) or "(none)")
    print("cells:", ", ".join(cells) or "(none)")
    print("titles:", "match cell language" if match_titles else f"shared {label_lang}")
    series_links = load_series_links(lesson_path, str(lesson.get("id") or ""))
    for warning in youtube_warnings(lesson, cells, series_links):
        print("warn:", warning)
        if report:
            report.warn(warning)
    for path in write_youtube_sidecars(lesson, cells, out_dir, series_links):
        print("youtube:", path)
    clock = StepClock(report)
    for note in apply_theme_fonts(theme):
        print("theme:", note)
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
        fold_t0 = time.perf_counter()
        if stamp_matches(slide_dir, stamp):
            slide_sets[(code, second)] = list_slide_pngs(slide_dir)
            print("slides: reuse", slide_dir, f"({len(slide_sets[(code, second)])} png)")
            print(f"progress: slides {slide_i}/{len(codes)} {folder} reuse")
            print(f"timing: slides {folder} {fmt_duration(time.perf_counter() - fold_t0)}")
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
        print(f"timing: slides {folder} {fmt_duration(time.perf_counter() - fold_t0)}")
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
            raise RuntimeError(f"caption-preview failed: {exc}") from exc
        if not previews:
            raise RuntimeError("caption-preview failed: no frames written")
        if report:
            for preview in previews:
                report.artifact(preview, "caption_preview")
        print(f"caption-preview: wrote {len(previews)} stamped frames; skipped TTS and mux")
        clock.lap("caption preview")
        if write_pdfs:
            _write_preview_pdfs(lesson["id"], out_root, ("captions",))
        write_cell_covers(lesson_path, lesson, cells, cell_slides, out_dir)
        sweep_intermediates(out_dir)
        clock.lap("covers")
        clock.total()
        return []
    if slides_only:
        if not any(slide_sets.values()):
            raise RuntimeError("No slides were rendered.")
        if report:
            for images in slide_sets.values():
                for image in images:
                    report.artifact(image, "slide")
        print(f"slides-only: wrote {sum(len(v) for v in slide_sets.values())} PNG files; skipped TTS and mux")
        if write_pdfs:
            _write_preview_pdfs(lesson["id"], out_root, ("slides",))
        write_cell_covers(lesson_path, lesson, cells, cell_slides, out_dir)
        sweep_intermediates(out_dir)
        clock.lap("covers")
        clock.total()
        return []
    if tts:
        audio_langs = script_langs(lesson)
        print("tts: preparing narration for the shared clock")
        synthesize_lesson(lesson, audio_root, overwrite=force_tts, langs=audio_langs)
        tracks = load_audio_tracks(lesson, audio_root, audio_langs)
    clock.lap("speech")
    raw_len = {lang: [probe_duration(path) for path in parts] for lang, parts in tracks.items()}
    durations = [max(values) for values in zip(*raw_len.values())]
    cap = pad_cap()
    if owns_speech_clock(lesson):
        lang_durations = speech_breath_durations(raw_len)
        durations = [max(values) for values in zip(*lang_durations.values())]
        print(f"clock: own speech + {OWN_BREATH_S:.1f}s breath (no shared pad)")
        for lang, raws in raw_len.items():
            held = ", ".join(
                f"{beat['id']} {raw:.1f}+{OWN_BREATH_S:.1f}s"
                for beat, raw in zip(lesson["beats"], raws)
            )
            print(f"clock: {lang} {held}")
    else:
        lang_durations = capped_durations(raw_len, durations, cap)
        if cap is not None:
            saved = {lang: sum(durations) - sum(lang_durations[lang]) for lang in langs}
            print("pad-cap:", cap, "s;", ", ".join(f"{k} -{v:.1f}s" for k, v in saved.items()))
    padded = {}
    for lang in langs:
        pad_dir = audio_root / "padded" / lang
        padded[lang] = [
            pad_audio(src, duration, pad_dir / src.name)
            for src, duration in zip(tracks[lang], lang_durations[lang])
        ]
        concat_audio(padded[lang], audio_root / f"{lang}.mp3")
    tracks = padded

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

    def beat_pages_and_holds(
        beat: dict,
        dur: float,
        sub_lang: str,
        spoken_lang: str | None = None,
        quiet: bool = False,
    ) -> tuple[list[str], list[float], list[int], list[int], str]:
        # Captions are sub_lang. Word times come from the spoken MP3 so a
        # bilingual cell follows that cell's voice. A mismatch falls back.
        spoken = spoken_lang or sub_lang
        words = load_word_times(audio_root / spoken / f"{beat['id']}.mp3")
        plan = stage_plan(beat, dur) if stage_cards else [0]
        text = beat_text(beat, sub_lang)
        keep_units = bool(lesson.get("caption_keep"))
        if plan == [0]:
            pages = caption_pages(text, keep_units)
            holds, how = holds_for_pages(dur, pages, words)
            still_idx = [0] * max(1, len(pages))
        else:
            chunks = stage_scripts(beat, sub_lang, len(plan))
            pages, holds, still_idx, how = pages_for_stages(
                text, dur, len(plan), chunks=chunks, words=words, keep_units=keep_units
            )
        if words and how != CAP_TIME_WORDS and not quiet:
            print(f"caption timing: {spoken}/{beat['id']} word match failed; speech-weight")
        return pages, holds, plan, still_idx, how

    def cues(spoken_lang: str, caption_lang: str) -> list[tuple[float, float, str]]:
        t = 0.0
        out = []
        for beat, d in zip(lesson["beats"], lang_durations.get(spoken_lang, durations)):
            pages, holds, _plan, _idx, _how = beat_pages_and_holds(beat, d, caption_lang, spoken_lang)
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
    videos = []
    warnings = check_holds_and_orphans(lesson, cells, lang_durations, durations, beat_pages_and_holds)
    if report:
        for warning in warnings:
            report.warn(warning)
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
        cell_durs = lang_durations.get(audio_lang, durations)
        for i, (beat, dur, audio) in enumerate(zip(lesson["beats"], cell_durs, parts), start=1):
            pages, holds, plan, still_idx, cap_time = beat_pages_and_holds(
                beat, dur, sub_lang, audio_lang
            )
            print(f"captions {name}/{beat['id']}: {len(pages)} cards ({cap_time})")
            base = stills_for_beat(slide_dir, i, beat, plan)
            if not base:
                raise RuntimeError(f"Missing slide for {name}/{beat['id']}")
            stills = [base[min(k, len(base) - 1)] for k in still_idx]
            stamped: list[Path] = []
            for j, (still, page) in enumerate(zip(stills, pages), start=1):
                dest = stamp_dir / f"{i:02d}_{beat['id']}_{j:02d}.png"
                stamp_caption(still, page, dest)
                stamped.append(dest)
                _publish_caption_preview(dest, still, out_dir / "preview" / folder, j, len(pages))
            clip = clip_dir / f"{i:02d}_{beat['id']}.mp4"
            clip_key = _clip_key(stamped, holds, audio, progress_bar, cap="on", cap_time=cap_time)
            clips.append(clip)
            if stamp_ok(clip, clip_key):
                print(f"clip: reuse {clip.name}")
            else:
                pending.append((clip, stamped, holds, audio, clip_key, f"{name}/{beat['id']}", progress_bar))
            if experiment_pack and pack_nocap:
                raw_clip = clip_dir / f"{i:02d}_{beat['id']}_nocap.mp4"
                raw_key = _clip_key(
                    stills[: len(holds)], holds, audio, progress_bar, cap="off", cap_time=cap_time
                )
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
        reused = stamp_ok(dest, join_key)
        if reused:
            print(f"concat: reuse {dest.name}")
        else:
            concat_clips(clips, dest)
            write_mark(dest, join_key)
        write_srt(cues(audio_lang, sub_lang), srt_dir / f"{name}.srt")
        duration = probe_duration(dest)
        print("cell:", dest, f"({duration:.1f}s)")
        if report:
            report.video(name, dest, duration, reused)
        videos.append(dest)
        if experiment_pack and pack_nocap and nocap_clips:
            off = out_dir / "cells" / f"{lesson['id']}_{name}_nocap.mp4"
            print(f"concat: {name}_nocap ({len(nocap_clips)} beats)")
            off_key = digest_obj({"clips": [file_fingerprint(p) for p in nocap_clips], "cap": "off"})
            reused = stamp_ok(off, off_key)
            if reused:
                print(f"concat: reuse {off.name}")
            else:
                concat_clips(nocap_clips, off)
                write_mark(off, off_key)
            duration = probe_duration(off)
            print("cell:", off, f"({duration:.1f}s)")
            if report:
                report.video(f"{name}_nocap", off, duration, reused)
            videos.append(off)
        clock.lap(f"video {name}")
    if experiment_pack:
        csv_path = write_experiment_pack(out_dir, lesson["id"], cells, pack_speeds, sources=videos)
        packed = pack_videos(csv_path)
        if report:
            for path in packed:
                report.video(path.stem, path, probe_duration(path))
        videos.extend(packed)
        print("experiment-pack:", csv_path)
        clock.lap("experiment pack")
    write_cell_covers(lesson_path, lesson, cells, cell_slides, out_dir)
    sweep_intermediates(out_dir, videos=True)
    clock.lap("covers")
    clock.total()
    return videos


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("lesson", type=Path, nargs="?", help="Lesson YAML, or omit with --all.")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Lesson output root. Default: $VF_OUT if set, otherwise <Downloads>/video-factory-out (fallback <repo>/out).",
    )
    p.add_argument(
        "--migrate-output",
        action="store_true",
        help="Move verified legacy output folders into lessons/ or modules/ and exit.",
    )
    p.add_argument("--labels", choices=("en", "zh"), default="en")
    p.add_argument("--no-tts", action="store_true", help="Do not call TTS; require existing MP3s.")
    p.add_argument("--force-tts", action="store_true", help="Regenerate all beat audio.")
    p.add_argument("--preflight", action="store_true", help="Check inputs without rendering or contacting a speech provider.")
    p.add_argument("--slides-only", action="store_true", help="Paint PNGs and stop.")
    p.add_argument(
        "--caption-preview",
        action="store_true",
        help="Paint slides and stamp caption bars; no TTS or mux.",
    )
    p.add_argument(
        "--cells",
        default="",
        help="Primary language (en, zh, hk) or primary+second for bilingual slides (en+zh, zh+en).",
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
    p.add_argument(
        "--strict-hold",
        action="store_true",
        help="Fail when one still holds longer than VF_HOLD_FAIL (30 s). Same as VF_STRICT_HOLD=1.",
    )
    p.add_argument(
        "--pad-cap",
        default="",
        help="Cap silence added after each beat per language, in seconds (e.g. 1.0). Same as VF_PAD_CAP.",
    )
    args = p.parse_args()
    if args.strict_hold:
        os.environ["VF_STRICT_HOLD"] = "1"
    if args.pad_cap:
        os.environ["VF_PAD_CAP"] = args.pad_cap
    args.out = resolve_out_root(args.out)
    print("output root:", args.out)
    if args.migrate_output:
        if args.lesson or args.all or args.bundle:
            p.error("--migrate-output is a standalone operation")
        for row in migrate_out_layout(args.out):
            print("out-migrate:", row)
        return
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
    opts = dict(
        label_lang=args.labels,
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
    if args.all:
        from catalog import LESSONS, iter_lesson_paths

        paths = iter_lesson_paths()
        if not paths:
            raise SystemExit(f"No YAML files in {LESSONS}")
    elif args.lesson is not None:
        paths = [args.lesson]
    else:
        p.error("Pass a lesson YAML or use --all")

    mode = ("preflight" if args.preflight else "caption_preview" if args.caption_preview
            else "slides" if args.slides_only else "video")
    report = BuildReport(args.out, mode, {**opts, "pad_cap": pad_cap()})
    failures = []
    for path in paths:
        if args.all:
            print(f"\n######## {path.name} ########")
        try:
            if args.preflight:
                runner = preflight
            elif is_minicourse(path):
                runner = build_minicourse
            elif is_module(path):
                runner = build_module
            else:
                runner = build
            report.run(path, runner, args.out, **opts)
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED {path.name}: {exc}", flush=True)
            failures.append(path.name)
    report_path = report.write(failures)
    print("build-report:", json.dumps(report_path.relative_to(args.out).as_posix()), flush=True)
    if failures:
        raise SystemExit(f"{len(failures)} lesson build(s) failed: {', '.join(failures)}")
    if args.all:
        print(f"batch: finished {len(paths)} lessons")


if __name__ == "__main__":
    main()
