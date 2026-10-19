#!/usr/bin/env python3
"""TTS backends.

Default is Microsoft Edge neural voices via edge-tts.
Google Cloud TTS is selected with VF_TTS=google.

Edge writes ``<beat>.mp3.words.json`` beside each MP3: word start/end in
seconds. Caption timing prefers that file and falls back to speech-weight
when it is missing or does not match the cards. Google does not write one.

Edge voices can be overridden:
  VF_VOICE_EN=en-US-GuyNeural
  VF_VOICE_ZH=zh-CN-YunxiNeural
  VF_VOICE_ZH_CN=zh-CN-YunxiNeural
  VF_VOICE_ZH_HK=zh-HK-WanLungNeural

Google Cloud TTS:
  VF_TTS=google
  VF_GOOGLE_TTS_KEY=<API key>   (or GOOGLE_API_KEY)
  VF_VOICE_EN=en-US-Neural2-D
  VF_VOICE_ZH_CN=cmn-CN-Neural2-C
  VF_VOICE_ZH_HK=yue-HK-Neural2-D
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from cache import digest_obj, stamp_ok, write_mark
from ff import audio_ok
from langs import beat_text, script_langs
from paths import replace_file

TTS_TRIES = max(1, int(os.environ.get("VF_TTS_TRIES", "4")))
TTS_WAIT = float(os.environ.get("VF_TTS_WAIT", "2"))

GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
GOOGLE_VOICES = {
    "en": "en-US-Neural2-D",
    "zh": "cmn-CN-Neural2-C",
    "zh_cn": "cmn-CN-Neural2-C",
    "zh_hk": "yue-HK-Neural2-D",
}


def tts_backend() -> str:
    raw = os.environ.get("VF_TTS", "edge").strip().lower()
    if raw in {"google", "gcloud", "google-cloud", "gcp"}:
        return "google"
    if raw in {"edge-then-google", "edge+google", "fallback"}:
        return "edge-then-google"
    return "edge"


def tts_jobs() -> int:
    raw = os.environ.get("VF_TTS_JOBS", "3")
    try:
        n = int(str(raw).strip() or "3")
    except ValueError:
        n = 3
    return max(1, min(n, 4))


def google_api_key() -> str:
    key = _read_google_key()
    if not key:
        looked = (
            "VF_GOOGLE_TTS_KEY, GOOGLE_API_KEY, GOOGLE_CLOUD_API_KEY, "
            "a .env in the video-factory root, or secrets/google-tts-key.txt"
        )
        raise RuntimeError(
            "Google Cloud TTS is selected but no API key was found. "
            f"Looked in: {looked}. "
            "An API key is not the same as a service-account JSON. "
            "Create a key in Google Cloud Console, enable Cloud Text-to-Speech, "
            "then put the key in one of those places and restart the console."
        )
    return key


def _read_google_key() -> str:
    for name in ("VF_GOOGLE_TTS_KEY", "GOOGLE_API_KEY", "GOOGLE_CLOUD_API_KEY"):
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    _load_dotenv()
    for name in ("VF_GOOGLE_TTS_KEY", "GOOGLE_API_KEY", "GOOGLE_CLOUD_API_KEY"):
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    for path in _key_file_candidates():
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text.splitlines()[0].strip().strip('"').strip("'")
    return ""


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _key_file_candidates() -> list[Path]:
    named = (os.environ.get("VF_GOOGLE_TTS_KEY_FILE") or "").strip()
    root = _project_root()
    paths = []
    if named:
        paths.append(Path(named))
    paths.extend([
        root / "secrets" / "google-tts-key.txt",
        root / ".google-tts-key",
        root / "google-tts-key.txt",
    ])
    return paths


def _load_dotenv() -> None:
    path = _project_root() / ".env"
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def voice_for(language: str) -> str:
    backend = tts_backend()
    if language == "zh_hk":
        env = os.environ.get("VF_VOICE_ZH_HK")
        if env:
            return env
        return GOOGLE_VOICES["zh_hk"] if backend == "google" else "zh-HK-WanLungNeural"
    if language.startswith("zh"):
        env = os.environ.get("VF_VOICE_ZH_CN") or os.environ.get("VF_VOICE_ZH")
        if env:
            return env
        return GOOGLE_VOICES["zh"] if backend == "google" else "zh-CN-YunxiNeural"
    env = os.environ.get("VF_VOICE_EN")
    if env:
        return env
    return GOOGLE_VOICES["en"] if backend == "google" else "en-US-GuyNeural"


def language_code_for(language: str, voice: str) -> str:
    if voice and "-" in voice:
        parts = voice.split("-")
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1]}"
    if language == "zh_hk":
        return "yue-HK"
    if language.startswith("zh"):
        return "cmn-CN"
    return "en-US"


def tts_rate() -> str:
    return os.environ.get("VF_TTS_RATE", "+0%")


def tts_volume() -> str:
    return os.environ.get("VF_TTS_VOLUME", "+0%")


def tts_pitch() -> str:
    return os.environ.get("VF_TTS_PITCH", "+0Hz")


def _speaking_rate() -> float:
    raw = tts_rate().strip().rstrip("%")
    try:
        pct = float(raw)
    except ValueError:
        return 1.0
    return max(0.25, min(4.0, 1.0 + pct / 100.0))


def _pitch_semitones() -> float:
    raw = tts_pitch().strip().lower().rstrip("hz")
    try:
        hz = float(raw)
    except ValueError:
        return 0.0
    # Rough map: Edge pitch is in Hz; Google expects semitones.
    return max(-20.0, min(20.0, hz / 10.0))


# Edge WordBoundary offset/duration are in 100 ns ticks.
EDGE_TICKS_PER_SECOND = 10_000_000


def words_sidecar(audio: Path) -> Path:
    """Word times for audio/en/beat.mp3 live at audio/en/beat.mp3.words.json."""
    return audio.with_name(audio.name + ".words.json")


def word_times_required() -> bool:
    """Edge speech is not reusable without the sidecar. Google stays weight-timed."""
    return tts_backend() == "edge"


def words_from_edge_ndjson(path: Path) -> list[dict]:
    """Normalize edge-tts WordBoundary NDJSON into seconds."""
    words: list[dict] = []
    if not path.is_file():
        return words
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        row = json.loads(raw)
        if not isinstance(row, dict) or row.get("type") != "WordBoundary":
            continue
        start = round(float(row["offset"]) / EDGE_TICKS_PER_SECOND, 3)
        end = round(start + float(row["duration"]) / EDGE_TICKS_PER_SECOND, 3)
        words.append({"text": str(row.get("text") or ""), "start": start, "end": end})
    return words


def write_words_sidecar(audio: Path, words: list[dict], backend: str = "edge") -> Path:
    dest = words_sidecar(audio)
    payload = {
        "words": [
            {
                "text": str(word.get("text") or ""),
                "start": round(float(word["start"]), 3),
                "end": round(float(word["end"]), 3),
            }
            for word in words
        ],
        "backend": backend,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.tmp.json")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return replace_file(tmp, dest)


def _load_words_payload(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("backend") != "edge":
        return None
    words = data.get("words")
    if not isinstance(words, list):
        return None
    for word in words:
        if not isinstance(word, dict):
            return None
        if "text" not in word or "start" not in word or "end" not in word:
            return None
        try:
            float(word["start"])
            float(word["end"])
        except (TypeError, ValueError):
            return None
    return data


def words_sidecar_ok(audio: Path) -> bool:
    return _load_words_payload(words_sidecar(audio)) is not None


def load_word_times(audio: Path) -> list[dict] | None:
    """Word timings for this MP3, or None when the sidecar is missing or unusable."""
    data = _load_words_payload(words_sidecar(audio))
    if data is None:
        return None
    return [
        {"text": str(word["text"]), "start": float(word["start"]), "end": float(word["end"])}
        for word in data["words"]
    ]


async def _save_edge(text: str, voice: str, dest: Path) -> None:
    import edge_tts
    import edge_tts.communicate as edge_communicate
    import edge_tts.constants as edge_constants

    token = getattr(edge_constants, "TRUSTED_CLIENT_TOKEN", "6A5AA1D4EAFF4E9FB37E23D68491D6F4")
    new_wss = (
        "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
        f"?Ocp-Apim-Subscription-Key={token}"
    )
    # communicate.py binds WSS_URL at import time, so patching constants alone
    # leaves the old host in the request that actually gets sent.
    edge_constants.WSS_URL = new_wss
    edge_communicate.WSS_URL = new_wss
    print("tts: using api.msedgeservices.com")

    dest.parent.mkdir(parents=True, exist_ok=True)
    meta = dest.with_name(dest.name + ".boundary.ndjson")
    try:
        comm = edge_tts.Communicate(
            text,
            voice,
            rate=tts_rate(),
            volume=tts_volume(),
            pitch=tts_pitch(),
            boundary="WordBoundary",
        )
        await comm.save(str(dest), str(meta))
        words = words_from_edge_ndjson(meta)
        write_words_sidecar(dest, words)
    finally:
        try:
            meta.unlink(missing_ok=True)
        except OSError:
            pass


async def _save_google(text: str, voice: str, dest: Path, language: str) -> None:
    key = google_api_key()
    payload = {
        "input": {"text": text},
        "voice": {
            "languageCode": language_code_for(language, voice),
            "name": voice,
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": _speaking_rate(),
            "pitch": _pitch_semitones(),
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GOOGLE_TTS_URL,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Goog-Api-Key": key,
        },
        method="POST",
    )
    dest.parent.mkdir(parents=True, exist_ok=True)

    def _call() -> bytes:
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Google Cloud TTS HTTP {exc.code}: {detail[:400]}"
            ) from exc
        audio = body.get("audioContent")
        if not audio:
            raise RuntimeError("Google Cloud TTS returned no audioContent")
        return base64.b64decode(audio)

    audio = await asyncio.to_thread(_call)
    dest.write_bytes(audio)


async def _save(text: str, voice: str, dest: Path, language: str = "en") -> None:
    backend = tts_backend()
    if backend == "google":
        await _save_google(text, voice, dest, language)
        return
    if backend == "edge-then-google":
        try:
            await _save_edge(text, voice, dest)
            return
        except Exception as exc:  # noqa: BLE001
            print(f"tts: Edge failed ({type(exc).__name__}); trying Google")
            google_voice = _google_voice(language)
            await _save_google(text, google_voice, dest, language)
            return
    await _save_edge(text, voice, dest)


def _google_voice(language: str) -> str:
    if language == "zh_hk":
        return os.environ.get("VF_VOICE_ZH_HK_GOOGLE") or GOOGLE_VOICES["zh_hk"]
    if language.startswith("zh"):
        return os.environ.get("VF_VOICE_ZH_CN_GOOGLE") or GOOGLE_VOICES["zh"]
    return os.environ.get("VF_VOICE_EN_GOOGLE") or GOOGLE_VOICES["en"]


def _tmp_mp3(dest: Path, attempt: int) -> Path:
    return dest.with_name(f"{dest.stem}.{os.getpid()}.{attempt}.part.mp3")


def _drop_tmp(path: Path) -> None:
    for extra in (path, words_sidecar(path), path.with_name(path.name + ".boundary.ndjson")):
        try:
            extra.unlink(missing_ok=True)
        except OSError:
            pass


def _commit_audio(tmp: Path, dest: Path) -> Path:
    """Move the MP3 into place, and the word sidecar with it.

    A Google take has no sidecar, so any previous Edge timings are removed
    before the new audio replaces the old file.
    """
    side_tmp = words_sidecar(tmp)
    side_dest = words_sidecar(dest)
    if side_tmp.is_file():
        replace_file(side_tmp, side_dest)
    else:
        try:
            side_dest.unlink(missing_ok=True)
        except OSError:
            pass
    return replace_file(tmp, dest)


def synthesize(text: str, language: str, dest: Path) -> Path:
    voice = voice_for(language)
    last: Exception | None = None
    for attempt in range(1, TTS_TRIES + 1):
        tmp = _tmp_mp3(dest, attempt)
        try:
            _drop_tmp(tmp)
            asyncio.run(_save(text, voice, tmp, language))
            if not tmp.exists() or tmp.stat().st_size < 256:
                raise RuntimeError(f"TTS produced no audio: {dest}")
            return _commit_audio(tmp, dest)
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"tts retry {attempt}/{TTS_TRIES} {language} {dest.stem}: {type(exc).__name__}")
            _drop_tmp(tmp)
            time.sleep(TTS_WAIT * attempt)
    raise RuntimeError(_fail_message(last)) from last


def _speech_payload(text: str, lang: str) -> dict:
    payload = {
        "backend": tts_backend(),
        "text": text,
        "voice": voice_for(lang),
        "rate": tts_rate(),
        "volume": tts_volume(),
        "pitch": tts_pitch(),
    }
    if word_times_required():
        payload["timestamps"] = "edge-words"
    return payload


def _speech_key(text: str, lang: str) -> str:
    return digest_obj(_speech_payload(text, lang))


def _reuse_speech(dest: Path, key: str) -> bool:
    if not dest.exists() or not audio_ok(dest) or not stamp_ok(dest, key):
        return False
    if word_times_required() and not words_sidecar_ok(dest):
        return False
    return True


def _fail_message(last: Exception | None) -> str:
    if tts_backend() == "google":
        return (
            "Google Cloud TTS failed. Check VF_GOOGLE_TTS_KEY, that the "
            "Text-to-Speech API is enabled, and that the voice name is valid. "
            f"Last error: {last}"
        )
    return (
        "Speech service refused the connection (403). "
        "Microsoft moved the Edge TTS host in October 2026; "
        "the factory now points at api.msedgeservices.com. "
        "If this still fails, wait a minute and rebuild without Regenerate speech, "
        f"or set VF_TTS=google. Last error: {last}"
    )


async def _save_with_retries(text: str, lang: str, dest: Path) -> Path:
    voice = voice_for(lang)
    last: Exception | None = None
    for attempt in range(1, TTS_TRIES + 1):
        tmp = _tmp_mp3(dest, attempt)
        try:
            _drop_tmp(tmp)
            await _save(text, voice, tmp, lang)
            if not tmp.exists() or tmp.stat().st_size < 256:
                raise RuntimeError(f"TTS produced no audio: {dest}")
            if os.name == "nt":
                await asyncio.sleep(0.2)
            return _commit_audio(tmp, dest)
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"tts retry {attempt}/{TTS_TRIES} {lang} {dest.stem}: {type(exc).__name__}")
            _drop_tmp(tmp)
            await asyncio.sleep(TTS_WAIT * attempt)
    raise RuntimeError(_fail_message(last)) from last


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
    print(f"tts backend: {tts_backend()}")
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
            if _reuse_speech(dest, key) and not overwrite:
                print(f"progress: speech {done}/{total} {lang}/{beat['id']} reuse")
                continue
            if (
                dest.exists()
                and not overwrite
                and audio_ok(dest)
                and stamp_ok(dest, key)
                and word_times_required()
                and not words_sidecar_ok(dest)
            ):
                print(f"tts: word times missing {lang}/{beat['id']}")
            elif dest.exists() and not overwrite and audio_ok(dest) and not stamp_ok(dest, key):
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
                words = load_word_times(dest)
                if words:
                    print(f"tts: {lang}/{beat['id']} {len(words)} word times")
                elif word_times_required():
                    print(f"tts: {lang}/{beat['id']} no word times")
                write_mark(dest, key)
                finished += 1
                print(f"progress: speech {finished}/{len(pending)} {lang}/{beat['id']}")

        await asyncio.gather(*(one(*job) for job in pending))

    asyncio.run(_run())
    return out
