#!/usr/bin/env python3
"""Local TTS backend. Default is Microsoft Edge neural voices via edge-tts.

Voices can be overridden:
  VF_VOICE_EN=en-US-GuyNeural
  VF_VOICE_ZH=zh-CN-YunxiNeural
  VF_VOICE_ZH_CN=zh-CN-YunxiNeural
  VF_VOICE_ZH_HK=zh-HK-WanLungNeural
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from cache import digest_obj, stamp_ok, write_mark
from ff import audio_ok
from langs import beat_text, script_langs
from paths import replace_file

TTS_TRIES = max(1, int(os.environ.get("VF_TTS_TRIES", "4")))
TTS_WAIT = float(os.environ.get("VF_TTS_WAIT", "2"))


def tts_jobs() -> int:
    raw = os.environ.get("VF_TTS_JOBS", "3")
    try:
        n = int(str(raw).strip() or "3")
    except ValueError:
        n = 3
    return max(1, min(n, 4))


def voice_for(language: str) -> str:
    if language == "zh_hk":
        return os.environ.get("VF_VOICE_ZH_HK", "zh-HK-WanLungNeural")
    if language.startswith("zh"):
        return os.environ.get("VF_VOICE_ZH_CN") or os.environ.get("VF_VOICE_ZH", "zh-CN-YunxiNeural")
    return os.environ.get("VF_VOICE_EN", "en-US-GuyNeural")


def tts_rate() -> str:
    return os.environ.get("VF_TTS_RATE", "+0%")


def tts_volume() -> str:
    return os.environ.get("VF_TTS_VOLUME", "+0%")


def tts_pitch() -> str:
    return os.environ.get("VF_TTS_PITCH", "+0Hz")


async def _save(text: str, voice: str, dest: Path) -> None:
    import edge_tts

    dest.parent.mkdir(parents=True, exist_ok=True)
    comm = edge_tts.Communicate(
        text,
        voice,
        rate=tts_rate(),
        volume=tts_volume(),
        pitch=tts_pitch(),
    )
    await comm.save(str(dest))


def _tmp_mp3(dest: Path, attempt: int) -> Path:
    return dest.with_name(f"{dest.stem}.{os.getpid()}.{attempt}.part.mp3")


def _drop_tmp(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def synthesize(text: str, language: str, dest: Path) -> Path:
    voice = voice_for(language)
    last: Exception | None = None
    for attempt in range(1, TTS_TRIES + 1):
        tmp = _tmp_mp3(dest, attempt)
        try:
            _drop_tmp(tmp)
            asyncio.run(_save(text, voice, tmp))
            if not tmp.exists() or tmp.stat().st_size < 256:
                raise RuntimeError(f"TTS produced no audio: {dest}")
            replace_file(tmp, dest)
            return dest
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"tts retry {attempt}/{TTS_TRIES} {language} {dest.stem}: {type(exc).__name__}")
            _drop_tmp(tmp)
            time.sleep(TTS_WAIT * attempt)
    raise RuntimeError(
        "Speech service dropped the connection. "
        "Keep existing audio and run Build cells again without Regenerate speech, "
        f"or retry in a minute. Last error: {last}"
    ) from last


def _speech_key(text: str, lang: str) -> str:
    return digest_obj(
        {
            "text": text,
            "voice": voice_for(lang),
            "rate": tts_rate(),
            "volume": tts_volume(),
            "pitch": tts_pitch(),
        }
    )


async def _save_with_retries(text: str, lang: str, dest: Path) -> Path:
    voice = voice_for(lang)
    last: Exception | None = None
    for attempt in range(1, TTS_TRIES + 1):
        tmp = _tmp_mp3(dest, attempt)
        try:
            _drop_tmp(tmp)
            await _save(text, voice, tmp)
            if not tmp.exists() or tmp.stat().st_size < 256:
                raise RuntimeError(f"TTS produced no audio: {dest}")
            if os.name == "nt":
                await asyncio.sleep(0.2)
            replace_file(tmp, dest)
            return dest
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"tts retry {attempt}/{TTS_TRIES} {lang} {dest.stem}: {type(exc).__name__}")
            _drop_tmp(tmp)
            await asyncio.sleep(TTS_WAIT * attempt)
    raise RuntimeError(
        "Speech service dropped the connection. "
        "Keep existing audio and run Build cells again without Regenerate speech, "
        f"or retry in a minute. Last error: {last}"
    ) from last


def synthesize_lesson(
    lesson: dict,
    audio_root: Path,
    overwrite: bool = False,
    langs: list[str] | None = None,
) -> dict[str, list[Path]]:
    langs = list(langs) if langs else script_langs(lesson)
    out: dict[str, list[Path]] = {lang: [] for lang in langs}
    pending: list[tuple[str, dict, Path, str, str]] = []
    planned = [(lang, beat) for lang in langs for beat in lesson["beats"]]
    total = max(1, len(planned))
    done = 0
    for lang in langs:
        print(
            f"tts voice {lang}: {voice_for(lang)} "
            f"rate={tts_rate()} volume={tts_volume()} pitch={tts_pitch()}"
        )
        for beat in lesson["beats"]:
            dest = audio_root / lang / f"{beat['id']}.mp3"
            done += 1
            text = beat_text(beat, lang)
            key = _speech_key(text, lang)
            out[lang].append(dest)
            if dest.exists() and not overwrite and audio_ok(dest) and stamp_ok(dest, key):
                print(f"progress: speech {done}/{total} {lang}/{beat['id']} reuse")
                continue
            if dest.exists() and not overwrite and audio_ok(dest) and not stamp_ok(dest, key):
                print(f"tts: script changed {lang}/{beat['id']}")
            elif dest.exists() and not overwrite:
                print(f"tts: replacing broken {lang}/{beat['id']}")
            pending.append((lang, beat, dest, text, key))
    if not pending:
        return out
    workers = tts_jobs()
    print(f"tts jobs: {len(pending)} to speak, {workers} in flight")

    async def _run() -> None:
        sem = asyncio.Semaphore(workers)
        finished = 0

        async def one(lang: str, beat: dict, dest: Path, text: str, key: str) -> None:
            nonlocal finished
            async with sem:
                print(f"tts: {lang}/{beat['id']}")
                await _save_with_retries(text, lang, dest)
                write_mark(dest, key)
                finished += 1
                print(f"progress: speech {finished}/{len(pending)} {lang}/{beat['id']}")

        await asyncio.gather(*(one(*job) for job in pending))

    asyncio.run(_run())
    return out
