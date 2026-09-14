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

    body = (text or "").replace("\n", " ").strip()
    if not body:
        return [" "]
    draw = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    lines: list[str] = []
    if any("\u4e00" <= ch <= "\u9fff" for ch in body):
        buf = ""
        for ch in body:
            trial = buf + ch
            if buf and draw.textlength(trial, font=font) > max_w:
                lines.append(buf)
                buf = ch
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
    return pages or [body]


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
    raw = (text or "").strip() or " "
    given = [ln.strip() for ln in raw.split("\n") if ln.strip()] or [" "]
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    font = _caption_font(raw, size)
    # Pages from caption_pages are already one spoken piece. Draw them all.
    # Shrink the type until each given line fits the pill; never drop a line.
    fitted = list(given)
    while size > 24:
        font = _caption_font(raw, size)
        if all(probe.textlength(ln, font=font) <= max_w for ln in fitted):
            break
        size -= 2
        line_h = max(30, int(size * 1.28))
    text_w = max(probe.textlength(ln, font=font) for ln in fitted)
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
        tw = draw.textlength(ln, font=font)
        if align == "left":
            x = x0 + pad_x
        elif align == "right":
            x = x0 + pill_w - pad_x - tw
        else:
            x = x0 + (pill_w - tw) / 2
        draw.text((x, y), ln, font=font, fill=(255, 255, 255, 255))
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
            "v": "2026-09-13-full-script",
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
    return "".join(ch for ch in (text or "") if not ch.isspace())


def pages_for_stages(text: str, total_dur: float, n_stages: int = 1) -> tuple[list[str], list[float], list[int]]:
    """Caption cards follow the spoken line across the whole beat.

    Stage stills change when the script reaches that chunk. Timing is not
    trapped inside the visual stage clock, which made captions race ahead.
    """
    n = max(1, int(n_stages))
    chunks = script_chunks(text, n) if n > 1 else [text]
    pages: list[str] = []
    stills: list[int] = []
    for i, chunk in enumerate(chunks):
        bits = caption_pages(chunk)
        pages.extend(bits)
        stills.extend([i] * len(bits))
    src = _caption_letters(text)
    got = _caption_letters("".join(pages))
    if src and got != src:
        print("caption coverage miss:", len(got), "of", len(src), "chars")
    holds = page_holds(total_dur, pages or [" "])
    return pages or [" "], holds, stills or [0]


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
    """Encode one beat: captioned stills + gold bar + that beat's audio."""
    import os

    out_path.parent.mkdir(parents=True, exist_ok=True)
    durations = [max(float(d), 0.05) for d in durations]
    total = max(sum(durations), 0.05)
    fade = _env_seconds("VF_STILL_FADE", 0.18, 0.5)
    beat_fade = _env_seconds("VF_BEAT_FADE", 0.0, 0.5)
    tmp = out_path.with_suffix(".tmp.mp4")
    cmd: list[str] = ["-y"]
    for slide, dur in zip(slides, durations):
        cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(slide)]
    cmd += ["-i", str(audio)]
    audio_idx = len(slides)
    chain, last = _still_chain(len(slides), durations, fade)
    vout = "vout2"
    extra = ""
    if beat_fade > 0 and total > 2 * beat_fade + 0.25:
        start_out = max(total - beat_fade, beat_fade)
        extra = (
            f";[{vout}]fade=t=in:st=0:d={beat_fade:.3f},"
            f"fade=t=out:st={start_out:.3f}:d={beat_fade:.3f}[vout3]"
        )
        vout = "vout3"
    if progress_bar:
        graph = (
            f"{chain};"
            f"[{last}]format=yuv420p[base];"
            f"color=c=0xC4A35A@0.28:s=1920x8:d={total:.3f},format=rgba[rail];"
            f"color=c=0xC4A35A:s=1920x8:d={total:.3f},format=rgba[gold];"
            f"[base][rail]overlay=0:0[v0];"
            f"[v0][gold]overlay=x='-1920+1920*t/{total:.3f}':y=0[vout2]"
            f"{extra}"
        )
        cmd += ["-filter_complex", graph, "-map", f"[{vout}]", "-map", f"{audio_idx}:a:0"]
    else:
        cmd += [
            "-filter_complex",
            f"{chain};[{last}]format=yuv420p[vout2]{extra}",
            "-map",
            f"[{vout}]",
            "-map",
            f"{audio_idx}:a:0",
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
