#!/usr/bin/env python3
"""Build silent master from slides + durations; burn captions; attach audio."""

from __future__ import annotations

import os
from pathlib import Path

from ff import atomic_replace, check_call, concat_escape, probe_duration  # noqa: F401


def write_concat(slides: list[Path], durations: list[float], concat_path: Path) -> None:
    lines = []
    for slide, dur in zip(slides, durations):
        lines.append(f"file '{concat_escape(slide)}'")
        lines.append(f"duration {dur:.3f}")
    lines.append(f"file '{concat_escape(slides[-1])}'")
    concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def beat_progress_graph(durations: list[float]) -> str:
    """Gold rail plus a fill that wipes left to right over each beat."""
    total = max(sum(max(float(d), 0.05) for d in durations), 0.05)
    n = max(1, len(durations))
    parts = [
        f"[0:v]fps={clip_fps()},format=yuv420p[base]",
        f"color=c=0xC4A35A@0.28:s=1920x8:d={total:.3f},format=rgba[rail]",
        f"color=c=0xC4A35A:s=1920x8:d={total:.3f},format=rgba[gold]",
    ]
    if n == 1:
        parts.append("[gold]copy[g0]")
    else:
        labels = "".join(f"[g{i}]" for i in range(n))
        parts.append(f"[gold]split={n}{labels}")
    parts.append("[base][rail]overlay=0:0[v0]")
    t0 = 0.0
    for i, dur in enumerate(durations):
        span = max(float(dur), 0.05)
        t1 = t0 + span
        nxt = "vout" if i == n - 1 else f"v{i + 1}"
        parts.append(
            f"[v{i}][g{i}]overlay=x='-1920+1920*(t-{t0:.3f})/{span:.3f}':y=0:"
            f"enable='between(t,{t0:.3f},{t1:.3f})'[{nxt}]"
        )
        t0 = t1
    parts.append("[vout]format=yuv420p[vout2]")
    return ";".join(parts)


def make_silent_master(
    slides: list[Path],
    durations: list[float],
    out_path: Path,
    progress_bar: bool = True,
    beat_durations: list[float] | None = None,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    concat_path = out_path.with_suffix(".concat.txt")
    write_concat(slides, durations, concat_path)
    tmp = out_path.with_suffix(".tmp.mp4")
    cmd = ["-y", "-f", "concat", "-safe", "0", "-i", str(concat_path)]
    bar_times = beat_durations or durations
    if progress_bar and bar_times:
        cmd += ["-filter_complex", beat_progress_graph(bar_times), "-map", "[vout2]"]
    else:
        cmd += ["-vf", f"fps={clip_fps()},format=yuv420p"]
    cmd += [
        "-c:v",
        "libx264",
        "-crf",
        "20",
        "-preset",
        "medium",
        "-threads",
        "4",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    check_call(cmd)
    return atomic_replace(tmp, out_path)


def write_srt(cues: list[tuple[float, float, str]], path: Path) -> Path:
    def ts(t: float) -> str:
        if t < 0:
            t = 0
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int(round((t - int(t)) * 1000))
        if ms == 1000:
            s += 1
            ms = 0
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    chunks = []
    for i, (start, end, text) in enumerate(cues, start=1):
        wrapped = text if "\n" in text else _break_caption(text)
        chunks.append(f"{i}\n{ts(start)} --> {ts(end)}\n{wrapped}\n")
    path.write_text("\n".join(chunks) + "\n", encoding="utf-8")
    return path


CAPTION_SIZE_DEFAULT = "42"
CAPTION_LINES_DEFAULT = "1"
CAPTION_PILL_MAX = 1180
CAPTION_PAD_X = 28


def _caption_font(text: str, size: int):
    from PIL import ImageFont

    from paths import cjk_regular, latin_regular

    cjk = any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))
    path = cjk_regular() if cjk else latin_regular()
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default()
    except OSError:
        return ImageFont.load_default()


def _wrap_caption_line(text: str, font, max_w: float) -> list[str]:
    from PIL import Image, ImageDraw

    from slides import _cjk_tokens

    body = (text or "").replace("\n", " ").strip()
    if not body:
        return [" "]
    draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    lines: list[str] = []
    if any("\u4e00" <= ch <= "\u9fff" for ch in body):
        buf = ""
        for tok in _cjk_tokens(body):
            trial = buf + tok
            if buf and draw.textlength(trial, font=font) > max_w:
                lines.append(buf)
                buf = tok
            else:
                buf = trial
        if buf:
            lines.append(buf)
    else:
        buf = ""
        for word in body.split():
            trial = (buf + " " + word).strip()
            if buf and draw.textlength(trial, font=font) > max_w:
                lines.append(buf)
                buf = word
            else:
                buf = trial
        if buf:
            lines.append(buf)
    return lines or [body]


def caption_pages(text: str) -> list[str]:
    """Sentence-first cards. Default one line; extra wrap pieces become new cards."""
    size = int(os.environ.get("VF_CAPTION_SIZE", CAPTION_SIZE_DEFAULT) or CAPTION_SIZE_DEFAULT)
    size = max(24, min(72, size))
    max_lines = int(os.environ.get("VF_CAPTION_LINES", CAPTION_LINES_DEFAULT) or CAPTION_LINES_DEFAULT)
    max_lines = max(1, min(3, max_lines))
    body = (text or "").replace("\n", " ").strip()
    if not body:
        return [" "]
    font = _caption_font(body, size)
    max_w = CAPTION_PILL_MAX - 2 * CAPTION_PAD_X
    pages: list[str] = []
    for sent in _sentences(body):
        bits = _wrap_caption_line(sent, font, max_w)
        if max_lines <= 1:
            pages.extend(bits)
        else:
            for i in range(0, len(bits), max_lines):
                pages.append("\n".join(bits[i : i + max_lines]))
    glued: list[str] = []
    punct = set("，。、．；：？！…—～,.;:!?")
    for page in pages:
        piece = page.strip()
        if not piece:
            continue
        if glued and all(ch in punct for ch in piece):
            glued[-1] = glued[-1] + piece
        else:
            glued.append(page)
    return glued or [body]


def _is_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _sentences(text: str) -> list[str]:
    import re

    body = (text or "").replace("\n", " ").strip()
    if not body:
        return [""]
    parts = re.split(r"(?<=[。？！.?!])\s*", body)
    return [p.strip() for p in parts if p.strip()] or [body]


def _halve(text: str) -> list[str]:
    import re

    body = (text or "").strip()
    if len(body) < 8:
        return [body]
    bits = [p.strip() for p in re.split(r"(?<=[，,;；、])\s*", body) if p.strip()]
    if len(bits) >= 2:
        mid = max(1, len(bits) // 2)
        join = "" if _is_cjk(body) else " "
        return [join.join(bits[:mid]).strip(), join.join(bits[mid:]).strip()]
    cut = max(1, len(body) // 2)
    if not _is_cjk(body):
        sp = body.rfind(" ", 0, cut)
        if sp >= 4:
            cut = sp
    left, right = body[:cut].strip(), body[cut:].strip()
    return [p for p in (left, right) if p] or [body]


def script_chunks(text: str, n: int) -> list[str]:
    """Cut a spoken line into n pieces with similar content weight.

    Used so each stage card gets its own caption, and English / Chinese
    advance through the argument together instead of by pixel wrap.
    """
    body = (text or "").replace("\n", " ").strip()
    n = max(1, int(n))
    if n == 1:
        return [body or " "]
    parts = _sentences(body)
    while len(parts) < n:
        i = max(range(len(parts)), key=lambda k: len(parts[k]))
        split = _halve(parts[i])
        if len(split) < 2:
            break
        parts[i : i + 1] = split
    join = "" if _is_cjk(body) else " "
    if len(parts) <= n:
        while len(parts) < n:
            i = max(range(len(parts)), key=lambda k: len(parts[k]))
            split = _halve(parts[i])
            if len(split) < 2:
                parts.append(parts[-1])
                break
            parts[i : i + 1] = split
        while len(parts) < n:
            parts.append(parts[-1] if parts else " ")
        return [p.strip() or " " for p in parts[:n]]
    q, r = divmod(len(parts), n)
    out: list[str] = []
    k = 0
    for i in range(n):
        take = q + (1 if i < r else 0)
        out.append(join.join(parts[k : k + take]).strip() or " ")
        k += take
    return out


def split_beat_cues(
    start: float,
    duration: float,
    text: str,
    pages: list[str] | None = None,
    holds: list[float] | None = None,
) -> list[tuple[float, float, str]]:
    """One cue per caption page, timed across the beat or given stage holds."""
    pages = list(pages) if pages else caption_pages(text)
    if holds and len(holds) == len(pages):
        t = start
        out = []
        for hold, page in zip(holds, pages):
            span = max(float(hold) - 0.02, 0.35)
            out.append((t, t + span, page))
            t += float(hold)
        return out
    usable = max(float(duration) - 0.05, 0.4 * len(pages))
    if len(pages) == 1:
        return [(start, start + usable, pages[0])]
    weights = [max(len(p.replace("\n", "")), 1) for p in pages]
    total_w = sum(weights)
    t = start
    out: list[tuple[float, float, str]] = []
    for i, (page, weight) in enumerate(zip(pages, weights)):
        if i == len(pages) - 1:
            end = start + usable
        else:
            end = t + usable * weight / total_w
        if end <= t:
            end = t + 0.4
        out.append((t, end, page))
        t = end
    return out


def _break_caption(text: str, width: int = 22) -> str:
    text = text.strip()
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        lines = []
        buf = ""
        for ch in text:
            buf += ch
            if len(buf) >= width:
                lines.append(buf)
                buf = ""
        if buf:
            lines.append(buf)
        return "\n".join(lines[:3])
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) <= 42:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines[:3])


def mux_cell(
    silent: Path,
    audio: Path,
    srt: Path,
    out_path: Path,
    fontsdir: str,
    cues: list[tuple[float, float, str]] | None = None,
) -> Path:
    """Mux audio onto the silent master and burn captions via PNG overlays.

    Avoids ffmpeg's subtitles filter. imageio-ffmpeg on Windows often
    ships without libass, and Windows path escaping for subtitles= fails.
    """
    del fontsdir
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if cues is None:
        cues = _parse_srt(srt)
    cap_dir = out_path.parent.parent / "captions" / out_path.stem
    cap_dir.mkdir(parents=True, exist_ok=True)
    cards = [_caption_card(text, cap_dir / f"{i:02d}.png") for i, (*_, text) in enumerate(cues)]
    tmp = out_path.with_suffix(".tmp.mp4")
    cmd: list[str] = ["-y", "-i", str(silent), "-i", str(audio)]
    for card in cards:
        cmd += ["-loop", "1", "-i", str(card)]
    filter_parts = []
    last = "0:v"
    for i, (start, end, _text) in enumerate(cues):
        src = f"{i + 2}:v"
        nxt = "vout" if i == len(cues) - 1 else f"v{i}"
        filter_parts.append(
            f"[{last}][{src}]overlay=0:H-h:enable='between(t,{start:.3f},{end:.3f})'[{nxt}]"
        )
        last = nxt
    cmd += [
        "-filter_complex",
        ";".join(filter_parts) if filter_parts else "null",
        "-map",
        "[vout]" if filter_parts else "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-crf",
        "20",
        "-preset",
        "medium",
        "-threads",
        "4",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    check_call(cmd)
    return atomic_replace(tmp, out_path)


def _caption_card(text: str, dest: Path) -> Path:
    """Full-frame transparent overlay with a compact caption chip at the bottom."""
    from PIL import Image, ImageDraw, ImageFont

    from paths import cjk_regular, latin_regular

    import os

    size = int(os.environ.get("VF_CAPTION_SIZE", CAPTION_SIZE_DEFAULT) or CAPTION_SIZE_DEFAULT)
    size = max(24, min(56, size))
    align = (os.environ.get("VF_CAPTION_ALIGN", "center") or "center").lower()
    max_lines = int(os.environ.get("VF_CAPTION_LINES", CAPTION_LINES_DEFAULT) or CAPTION_LINES_DEFAULT)
    max_lines = max(1, min(3, max_lines))
    opacity = int(os.environ.get("VF_CAPTION_OPACITY", "72") or 72)
    opacity = max(30, min(90, opacity))
    line_h = max(30, int(size * 1.28))
    frame_w, frame_h = 1920, 1080
    pad_x, pad_y = CAPTION_PAD_X, 12
    max_pill_w = CAPTION_PILL_MAX
    max_w = max_pill_w - 2 * pad_x
    from slides import draw_mixed, mixed_length

    raw = (text or "").strip() or " "
    given = [ln.strip() for ln in raw.splitlines() if ln.strip()] or [" "]
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    fitted = list(given)
    while size > 24:
        if all(mixed_length(probe, ln, size) <= max_w for ln in fitted):
            break
        size -= 2
        line_h = max(30, int(size * 1.28))
    text_w = max(mixed_length(probe, ln, size) for ln in fitted)
    pill_w = int(min(max_pill_w, max(280, text_w + 2 * pad_x)))
    pill_h = int(2 * pad_y + line_h * len(fitted))
    img = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x0 = (frame_w - pill_w) // 2
    y0 = frame_h - pill_h - 28
    alpha = int(round(255 * opacity / 100))
    draw.rounded_rectangle([x0, y0, x0 + pill_w, y0 + pill_h], radius=18, fill=(16, 15, 10, alpha))
    y = y0 + pad_y
    for ln in fitted:
        tw = mixed_length(draw, ln, size)
        if align == "left":
            x = x0 + pad_x
        elif align == "right":
            x = x0 + pill_w - pad_x - tw
        else:
            x = x0 + (pill_w - tw) / 2
        draw_mixed(draw, (x, y), ln, size, (255, 255, 255, 255), False)
        y += line_h

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def _parse_srt(path: Path) -> list[tuple[float, float, str]]:
    def to_s(stamp: str) -> float:
        left, ms = stamp.replace(",", ".").rsplit(".", 1)
        h, m, s = left.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    cues: list[tuple[float, float, str]] = []
    for block in path.read_text(encoding="utf-8").strip().split("\n\n"):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        start_s, end_s = [p.strip() for p in lines[1].split("-->")]
        cues.append((to_s(start_s), to_s(end_s), " ".join(lines[2:])))
    return cues


def clip_fps() -> int:
    """Still slides do not need 30 fps. Default 15; set VF_FPS=30 for the old look."""
    raw = os.environ.get("VF_FPS", "15")
    try:
        fps = int(float(str(raw).strip() or "15"))
    except ValueError:
        fps = 15
    if fps < 10:
        return 15
    if fps > 30:
        return 30
    return fps


def clip_v_args() -> list[str]:
    fps = clip_fps()
    return [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-r",
        str(fps),
        "-pix_fmt",
        "yuv420p",
        "-video_track_timescale",
        str(fps * 1000),
    ]


# Prefer clip_v_args() so VF_FPS is read at encode time.
CLIP_A = [
    "-c:a",
    "aac",
    "-ar",
    "48000",
    "-ac",
    "2",
    "-b:a",
    "128k",
]


def stamp_caption(slide: Path, text: str, dest: Path) -> Path:
    from PIL import Image

    import os

    from cache import digest_obj, file_fingerprint, stamp_ok, write_mark

    key = digest_obj(
        {
            "slide": file_fingerprint(slide),
            "text": text,
            "size": os.environ.get("VF_CAPTION_SIZE", CAPTION_SIZE_DEFAULT),
            "align": os.environ.get("VF_CAPTION_ALIGN", "center"),
            "lines": os.environ.get("VF_CAPTION_LINES", CAPTION_LINES_DEFAULT),
            "pill": CAPTION_PILL_MAX,
            "opacity": os.environ.get("VF_CAPTION_OPACITY", "72"),
            "bar": os.environ.get("VF_CAPTION_BAR", ""),
            "v": "2026-09-19-mixed-caption",
        }
    )
    if stamp_ok(dest, key):
        return dest

    overlay_path = dest.with_name(dest.stem + "_bar.png")
    bar = _caption_card(text, overlay_path)
    base = Image.open(slide).convert("RGBA")
    overlay = Image.open(bar).convert("RGBA")
    if overlay.size != base.size:
        overlay = overlay.resize(base.size)
    base.alpha_composite(overlay)
    dest.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(dest, "PNG")
    write_mark(dest, key)
    return dest


def page_speech_weight(page: str) -> float:
    """Same units as the voice estimate: English words / CJK characters."""
    body = (page or "").replace("\n", " ").strip()
    if not body:
        return 1.0
    if any("\u4e00" <= ch <= "\u9fff" for ch in body):
        return max(len(body), 1) / 4.2
    return max(len(body.split()), 1) / 2.3


def page_holds(duration: float, pages: list[str]) -> list[float]:
    """Split the beat audio across pages by spoken weight. Holds sum to duration."""
    duration = max(float(duration), 0.05)
    n = max(1, len(pages))
    if n == 1:
        return [duration]
    weights = [page_speech_weight(p) for p in pages]
    raw = [duration * w / sum(weights) for w in weights]
    floor = min(0.9, duration / (n * 1.2))
    raw = [max(h, floor) for h in raw]
    scale = duration / max(sum(raw), 0.05)
    holds = [h * scale for h in raw]
    holds[-1] = duration - sum(holds[:-1])
    return holds


def _caption_letters(text: str) -> str:
    """Alphanumerics used to align caption cards with spoken words.

    Edge WordBoundary text drops punctuation, so a script comma or period
    must not fail the match. CJK characters count as alphanumeric.
    """
    return "".join(ch for ch in (text or "") if ch.isalnum())


CAP_TIME_WORDS = "tts-words"
CAP_TIME_WEIGHT = "speech-weight"


def _letter_starts(words: list[dict]) -> list[tuple[str, float]] | None:
    """One (character, start-second) per spoken letter.

    Letters inside a single Edge word share that word's span evenly, so a
    caption wrap can cut a CJK token without losing the match.
    """
    out: list[tuple[str, float]] = []
    for word in words:
        if not isinstance(word, dict):
            return None
        try:
            start = float(word["start"])
            end = float(word["end"])
        except (KeyError, TypeError, ValueError):
            return None
        if start < 0 or end < start:
            return None
        letters = _caption_letters(str(word.get("text") or ""))
        if not letters:
            continue
        step = (end - start) / len(letters)
        for i, ch in enumerate(letters):
            out.append((ch, start + i * step))
    return out


def holds_from_word_times(duration: float, pages: list[str], words: list[dict]) -> list[float] | None:
    """Tile `duration` by caption pages using word times.

    Returns None when the word letter stream does not match the pages.
    The first card owns any leading silence. The last card runs through
    trailing and pad silence to the full beat length.
    """
    if not pages or not words:
        return None
    letters = _letter_starts(words)
    if not letters:
        return None
    cursor = 0
    page_starts: list[float] = []
    for page in pages:
        chars = _caption_letters(page)
        if not chars:
            return None
        first_t: float | None = None
        for ch in chars:
            if cursor >= len(letters) or letters[cursor][0] != ch:
                return None
            if first_t is None:
                first_t = letters[cursor][1]
            cursor += 1
        if first_t is None:
            return None
        page_starts.append(first_t)
    if cursor != len(letters):
        return None
    duration = max(float(duration), 0.05)
    if any(t < -0.02 for t in page_starts):
        return None
    if any(page_starts[i] + 1e-3 < page_starts[i - 1] for i in range(1, len(page_starts))):
        return None
    if len(pages) == 1:
        return [duration]
    if any(t > duration + 1e-3 for t in page_starts[1:]):
        return None
    bounds = [0.0]
    for raw in page_starts[1:]:
        t = min(max(raw, bounds[-1]), duration)
        if t <= bounds[-1] + 1e-3:
            return None
        bounds.append(t)
    holds = [bounds[i + 1] - bounds[i] for i in range(len(bounds) - 1)]
    holds.append(duration - bounds[-1])
    if holds[-1] <= 1e-3 or any(h < 0 for h in holds):
        return None
    return holds


def holds_for_pages(
    duration: float,
    pages: list[str],
    words: list[dict] | None = None,
) -> tuple[list[float], str]:
    """Prefer Edge word times. Fall back to speech-weight when they do not fit."""
    if words:
        timed = holds_from_word_times(duration, pages, words)
        if timed is not None:
            return timed, CAP_TIME_WORDS
    return page_holds(duration, pages), CAP_TIME_WEIGHT


def _split_sentences(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    parts: list[str] = []
    buf = []
    for ch in raw:
        buf.append(ch)
        if ch in ".!?。！？":
            bit = "".join(buf).strip()
            if bit:
                parts.append(bit)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts or [raw]


def stage_scripts(beat: dict, lang: str, n: int) -> list[str]:
    """One spoken chunk per visual stage. Uses s1/s2/… when present.

    A series card with reveal: cells has one stage per cell, then the
    later speech. Every sentence of the first chunk stays in the captions.
    Extra sentences land on the last cell, so the voice and the bar match.
    """
    from langs import beat_text, stage_lines

    n = max(1, int(n))
    written = [p for p in stage_lines(beat, lang, n) if p]
    reveal = (
        beat.get("visual") == "series"
        and str(beat.get("reveal") or "").strip().lower() == "cells"
    )
    if reveal and written and n > len(written):
        try:
            cols = int(beat.get("cols") or 4)
        except (TypeError, ValueError):
            cols = 4
        cols = max(2, min(cols, n - 1))
        lead = _split_sentences(written[0]) or [written[0]]
        buckets = [[] for _ in range(cols)]
        for i, sent in enumerate(lead):
            buckets[min(i, cols - 1)].append(sent)
        cells = [" ".join(bits) for bits in buckets]
        rest = written[1:]
        out = cells + rest
        while len(out) < n:
            out.append(" ")
        return out[:n]
    if any(stage_lines(beat, lang, n)):
        out = []
        full = stage_lines(beat, lang, n)
        for i in range(n):
            line = full[i] if i < len(full) else ""
            out.append((line or " ").strip() or " ")
        return out
    body = beat_text(beat, lang)
    return script_chunks(body, n) if n > 1 else [body or " "]


def pages_for_stages(
    text: str,
    total_dur: float,
    n_stages: int = 1,
    chunks: list[str] | None = None,
    words: list[dict] | None = None,
) -> tuple[list[str], list[float], list[int], str]:
    """Caption cards follow the spoken line across the whole beat.

    Stage stills change when the script reaches that chunk. Timing is not
    trapped inside the visual stage clock, which made captions race ahead.
    Word timestamps time the pages when `words` matches; otherwise the
    holds stay on speech-weight.
    """
    n = max(1, int(n_stages))
    chunks = list(chunks) if chunks else (script_chunks(text, n) if n > 1 else [text])
    pages: list[str] = []
    stills: list[int] = []
    for i, chunk in enumerate(chunks):
        bits = caption_pages(chunk)
        pages.extend(bits)
        stills.extend([i] * len(bits))
    src = _caption_letters(text or "".join(chunks))
    got = _caption_letters("".join(pages))
    if src and got != src:
        print("caption coverage miss:", len(got), "of", len(src), "chars")
    shown = pages or [" "]
    holds, how = holds_for_pages(total_dur, shown, words)
    return shown, holds, stills or [0], how


def _env_seconds(name: str, default: float, cap: float) -> float:
    import os

    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        val = float(raw)
    except ValueError:
        return default
    return max(0.0, min(cap, val))


def _still_chain(n: int, durations: list[float], fade: float) -> tuple[str, str]:
    """Join caption cards inside a beat.

    xfade drops later inputs once a beat has more than a couple of pages.
    Concat keeps every card and lasts exactly sum(durations).
    A short fade is only used when there are two stills.
    """
    prepared = []
    for i in range(n):
        prepared.append(f"[{i}:v]fps={clip_fps()},scale=1920:1080,format=yuv420p,setsar=1[s{i}]")
    if n == 1:
        return ";".join(prepared), "s0"
    if fade > 0 and n == 2:
        hold = max(float(durations[0]), 0.05)
        span = min(fade, max(0.06, hold - 0.08))
        offset = max(hold - span, 0.0)
        prepared.append(f"[s0][s1]xfade=transition=fade:duration={span:.3f}:offset={offset:.3f}[scat]")
        return ";".join(prepared), "scat"
    labels = "".join(f"[s{i}]" for i in range(n))
    prepared.append(f"{labels}concat=n={n}:v=1:a=0[scat]")
    return ";".join(prepared), "scat"


def make_beat_clip(
    slides: list[Path],
    durations: list[float],
    audio: Path,
    out_path: Path,
    progress_bar: bool = True,
) -> Path:
    """Encode one beat: captioned stills + gold bar + that beat's audio.

    Many stills as separate -loop inputs hang imageio-ffmpeg on Windows
    (GAME-APP-01 compare, 8 caption pages). Concat demuxer is one video input.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pair = list(zip(slides, durations))
    if not pair:
        raise RuntimeError(f"no stills for {out_path}")
    durations = [max(float(d), 0.05) for _, d in pair]
    slides = [p for p, _ in pair]
    total = max(sum(durations), 0.05)
    beat_fade = _env_seconds("VF_BEAT_FADE", 0.0, 0.5)
    concat_path = out_path.with_suffix(".concat.txt")
    write_concat(slides, durations, concat_path)
    tmp = out_path.with_suffix(".tmp.mp4")
    cmd: list[str] = [
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-i",
        str(audio),
    ]
    extra = ""
    vout = "vout2"
    if beat_fade > 0 and total > 2 * beat_fade + 0.25:
        start_out = max(total - beat_fade, beat_fade)
        extra = (
            f";[vout2]fade=t=in:st=0:d={beat_fade:.3f},"
            f"fade=t=out:st={start_out:.3f}:d={beat_fade:.3f}[vout3]"
        )
        vout = "vout3"
    fps = clip_fps()
    if progress_bar:
        graph = (
            f"[0:v]fps={fps},scale=1920:1080,format=yuv420p,setsar=1[base];"
            f"color=c=0xC4A35A@0.28:s=1920x8:d={total:.3f},format=rgba[rail];"
            f"color=c=0xC4A35A:s=1920x8:d={total:.3f},format=rgba[gold];"
            f"[base][rail]overlay=0:0[v0];"
            f"[v0][gold]overlay=x='-1920+1920*t/{total:.3f}':y=0[vout2]"
            f"{extra}"
        )
        cmd += ["-filter_complex", graph, "-map", f"[{vout}]", "-map", "1:a:0"]
    elif extra:
        cmd += [
            "-filter_complex",
            f"[0:v]fps={fps},scale=1920:1080,format=yuv420p,setsar=1[vout2]{extra}",
            "-map",
            f"[{vout}]",
            "-map",
            "1:a:0",
        ]
    else:
        cmd += [
            "-vf",
            f"fps={fps},scale=1920:1080,format=yuv420p",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]
    af = f"aresample=48000,aformat=channel_layouts=stereo,apad=pad_dur={total:.3f}"
    if beat_fade > 0 and total > 2 * beat_fade + 0.25:
        start_out = max(total - beat_fade, beat_fade)
        af += f",afade=t=in:st=0:d={beat_fade:.3f},afade=t=out:st={start_out:.3f}:d={beat_fade:.3f}"
    cmd += [
        "-af",
        af,
        *clip_v_args(),
        *CLIP_A,
        "-t",
        f"{total:.3f}",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    check_call(cmd)
    return atomic_replace(tmp, out_path)


def concat_clips(clips: list[Path], out_path: Path) -> Path:
    """Join beat MP4s with stream copy — no second encode."""
    if not clips:
        raise ValueError("No beat clips to concatenate")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(clips) == 1:
        return atomic_replace(clips[0], out_path) if clips[0] != out_path else clips[0]
    listing = out_path.with_suffix(".concat.txt")
    listing.write_text(
        "".join(f"file '{concat_escape(p)}'\n" for p in clips),
        encoding="utf-8",
    )
    tmp = out_path.with_suffix(".tmp.mp4")
    try:
        check_call(
            [
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(tmp),
            ]
        )
    except RuntimeError:
        check_call(
            [
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                *clip_v_args(),
                *CLIP_A,
                "-movflags",
                "+faststart",
                str(tmp),
            ]
        )
    return atomic_replace(tmp, out_path)
