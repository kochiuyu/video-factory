#!/usr/bin/env python3
"""Caption holds from Edge word times, with speech-weight fallback."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cache import digest_obj, write_mark
from mux import (
    CAP_TIME_WEIGHT,
    CAP_TIME_WORDS,
    _caption_letters,
    holds_for_pages,
    holds_from_word_times,
    page_holds,
    pages_for_stages,
)
from tts import (
    _reuse_speech,
    _speech_payload,
    load_word_times,
    words_from_edge_ndjson,
    words_sidecar,
    words_sidecar_ok,
    write_words_sidecar,
    _commit_audio,
)


def _word(text: str, start: float, end: float) -> dict:
    return {"text": text, "start": start, "end": end}


class WordHoldMapping(unittest.TestCase):
    def test_english_pages_follow_word_starts_and_pad_the_last_card(self) -> None:
        pages = ["The mean", "is the total"]
        words = [
            _word("The", 0.20, 0.40),
            _word("mean", 0.40, 0.80),
            _word("is", 1.00, 1.20),
            _word("the", 1.20, 1.40),
            _word("total", 1.40, 1.90),
        ]
        holds, how = holds_for_pages(4.0, pages, words)
        self.assertEqual(how, CAP_TIME_WORDS)
        self.assertAlmostEqual(holds[0], 1.0)
        # Last card stays up through the silence after the last word.
        self.assertAlmostEqual(holds[-1], 3.0)
        self.assertGreater(holds[-1], 1.90 - 1.00)
        self.assertAlmostEqual(sum(holds), 4.0)

    def test_cjk_wrap_splits_inside_one_edge_word(self) -> None:
        pages = ["平均", "数"]
        words = [_word("平均数", 0.0, 0.9)]
        holds = holds_from_word_times(2.0, pages, words)
        self.assertIsNotNone(holds)
        assert holds is not None
        self.assertAlmostEqual(holds[0], 0.6)
        self.assertAlmostEqual(holds[1], 1.4)
        self.assertAlmostEqual(sum(holds), 2.0)

    def test_cjk_pages_match_character_words(self) -> None:
        pages = ["平均数", "是总和"]
        words = [
            _word("平均", 0.10, 0.40),
            _word("数", 0.40, 0.70),
            _word("是", 0.80, 1.00),
            _word("总", 1.00, 1.20),
            _word("和", 1.20, 1.40),
        ]
        holds, how = holds_for_pages(3.0, pages, words)
        self.assertEqual(how, CAP_TIME_WORDS)
        self.assertAlmostEqual(holds[0], 0.80)
        self.assertAlmostEqual(holds[1], 2.20)
        self.assertAlmostEqual(sum(holds), 3.0)

    def test_punctuation_and_spaces_still_match(self) -> None:
        pages = ["Hello,", "world"]
        words = [_word("Hello,", 0.10, 0.40), _word(" world", 0.50, 0.90)]
        holds, how = holds_for_pages(2.5, pages, words)
        self.assertEqual(how, CAP_TIME_WORDS)
        self.assertAlmostEqual(holds[0], 0.50)
        self.assertAlmostEqual(holds[1], 2.0)

    def test_script_punctuation_matches_words_without_it(self) -> None:
        """Edge WordBoundary text has no .,!? while the caption script does."""
        self.assertEqual(_caption_letters("Hello, world!? 平均数。"), "Helloworld平均数")
        pages = ["Hello, world.", "Next! Done?"]
        words = [
            _word("Hello", 0.20, 0.40),
            _word("world", 0.40, 0.80),
            _word("Next", 1.00, 1.30),
            _word("Done", 1.30, 1.60),
        ]
        holds, how = holds_for_pages(4.0, pages, words)
        self.assertEqual(how, CAP_TIME_WORDS)
        self.assertAlmostEqual(holds[0], 1.0)
        self.assertAlmostEqual(holds[-1], 3.0)
        self.assertAlmostEqual(sum(holds), 4.0)

        cjk_pages = ["平均数。", "是总和！"]
        cjk_words = [
            _word("平均", 0.10, 0.40),
            _word("数", 0.40, 0.70),
            _word("是", 0.80, 1.00),
            _word("总", 1.00, 1.20),
            _word("和", 1.20, 1.40),
        ]
        cjk_holds, cjk_how = holds_for_pages(3.0, cjk_pages, cjk_words)
        self.assertEqual(cjk_how, CAP_TIME_WORDS)
        self.assertAlmostEqual(cjk_holds[0], 0.80)
        self.assertAlmostEqual(cjk_holds[1], 2.20)
        self.assertAlmostEqual(sum(cjk_holds), 3.0)

    def test_one_page_uses_the_full_beat_when_words_match(self) -> None:
        holds, how = holds_for_pages(3.5, ["Hello world"], [_word("Hello", 0.2, 0.5), _word("world", 0.5, 0.9)])
        self.assertEqual(how, CAP_TIME_WORDS)
        self.assertEqual(holds, [3.5])

    def test_mismatch_falls_back_to_speech_weight(self) -> None:
        pages = ["The mean", "is wrong"]
        words = [_word("The", 0.1, 0.2), _word("mean", 0.2, 0.4), _word("is", 0.5, 0.7), _word("right", 0.7, 1.0)]
        holds, how = holds_for_pages(4.0, pages, words)
        self.assertEqual(how, CAP_TIME_WEIGHT)
        self.assertEqual(holds, page_holds(4.0, pages))
        self.assertIsNone(holds_from_word_times(4.0, pages, words))

    def test_missing_or_blank_words_fall_back(self) -> None:
        pages = ["The mean", "is the total"]
        for words in (None, [], [{"text": " ", "start": 0.0, "end": 0.2}]):
            holds, how = holds_for_pages(4.0, pages, words)
            self.assertEqual(how, CAP_TIME_WEIGHT)
            self.assertEqual(holds, page_holds(4.0, pages))

    def test_blank_page_and_leftover_letters_fall_back(self) -> None:
        words = [_word("Hello", 0.1, 0.4), _word("world", 0.5, 0.9)]
        self.assertIsNone(holds_from_word_times(2.0, ["Hello", " "], words))
        self.assertIsNone(holds_from_word_times(2.0, ["Hello"], words))
        self.assertEqual(holds_for_pages(2.0, ["Hello"], words)[1], CAP_TIME_WEIGHT)

    def test_stage_pages_use_the_same_word_holds(self) -> None:
        text = "The mean is the total."
        words = [
            _word("The", 0.20, 0.40),
            _word("mean", 0.40, 0.80),
            _word("is", 1.00, 1.20),
            _word("the", 1.20, 1.40),
            _word("total.", 1.40, 1.90),
        ]
        pages, holds, stills, how = pages_for_stages(
            text, 4.0, 2, chunks=["The mean is", "the total."], words=words
        )
        self.assertEqual(how, CAP_TIME_WORDS)
        self.assertGreaterEqual(len(pages), 2)
        self.assertEqual(len(stills), len(pages))
        self.assertAlmostEqual(sum(holds), 4.0)
        again_holds, again_how = holds_for_pages(4.0, pages, words)
        self.assertEqual(again_how, how)
        self.assertEqual(again_holds, holds)
        fallback_pages, fallback_holds, _, fallback_how = pages_for_stages(
            text, 4.0, 2, chunks=["The mean is", "the total."], words=[_word("nope", 0.0, 1.0)]
        )
        self.assertEqual(fallback_how, CAP_TIME_WEIGHT)
        self.assertEqual(fallback_holds, page_holds(4.0, fallback_pages))

    def test_page_start_past_the_beat_falls_back(self) -> None:
        words = [_word("Hello", 0.1, 0.4), _word("world", 5.0, 5.4)]
        holds, how = holds_for_pages(2.0, ["Hello", "world"], words)
        self.assertEqual(how, CAP_TIME_WEIGHT)
        self.assertEqual(holds, page_holds(2.0, ["Hello", "world"]))


class WordSidecar(unittest.TestCase):
    def test_edge_ndjson_ticks_become_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "meta.ndjson"
            path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {"type": "WordBoundary", "offset": 2_000_000, "duration": 3_000_000, "text": "The"}
                        ),
                        json.dumps(
                            {"type": "SentenceBoundary", "offset": 0, "duration": 5_000_000, "text": "The"}
                        ),
                        json.dumps(
                            {"type": "WordBoundary", "offset": 5_000_000, "duration": 4_000_000, "text": "平均数"}
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            words = words_from_edge_ndjson(path)
        self.assertEqual(
            words,
            [
                {"text": "The", "start": 0.2, "end": 0.5},
                {"text": "平均数", "start": 0.5, "end": 0.9},
            ],
        )

    def test_sidecar_roundtrip_and_spoken_language_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            en = root / "en" / "intro.mp3"
            zh = root / "zh" / "intro.mp3"
            en.parent.mkdir(parents=True)
            zh.parent.mkdir(parents=True)
            en.write_bytes(b"en")
            zh.write_bytes(b"zh")
            write_words_sidecar(en, [_word("Hello", 0.2, 0.5)])
            write_words_sidecar(zh, [_word("你好", 0.1, 0.4)])
            en_side = words_sidecar(en)
            self.assertEqual(en_side.name, "intro.mp3.words.json")
            payload = json.loads(en_side.read_text(encoding="utf-8"))
            self.assertEqual(payload["backend"], "edge")
            self.assertEqual(payload["words"], [{"text": "Hello", "start": 0.2, "end": 0.5}])
            self.assertEqual(load_word_times(zh), [{"text": "你好", "start": 0.1, "end": 0.4}])
            self.assertTrue(words_sidecar_ok(en))
            en_side.write_text("{", encoding="utf-8")
            self.assertFalse(words_sidecar_ok(en))
            self.assertIsNone(load_word_times(en))

    def test_commit_keeps_sidecar_with_the_mp3_and_drops_a_stale_one(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dest = root / "beat.mp3"
            dest.write_bytes(b"old-audio")
            write_words_sidecar(dest, [_word("Old", 0.0, 1.0)])
            tmp = root / "beat.part.mp3"
            tmp.write_bytes(b"new-audio")
            _commit_audio(tmp, dest)
            self.assertEqual(dest.read_bytes(), b"new-audio")
            self.assertFalse(words_sidecar(dest).exists())

            tmp = root / "beat.part.mp3"
            tmp.write_bytes(b"edge-audio")
            write_words_sidecar(tmp, [_word("New", 0.2, 0.6)])
            _commit_audio(tmp, dest)
            self.assertEqual(dest.read_bytes(), b"edge-audio")
            self.assertEqual(load_word_times(dest), [{"text": "New", "start": 0.2, "end": 0.6}])
            self.assertFalse(tmp.exists())
            self.assertFalse(words_sidecar(tmp).exists())


class SpeechAndClipCache(unittest.TestCase):
    def setUp(self) -> None:
        self._tts = os.environ.get("VF_TTS")

    def tearDown(self) -> None:
        if self._tts is None:
            os.environ.pop("VF_TTS", None)
        else:
            os.environ["VF_TTS"] = self._tts

    def test_edge_speech_key_changes_when_word_times_are_required(self) -> None:
        os.environ["VF_TTS"] = "edge"
        payload = _speech_payload("Hello there", "en")
        self.assertEqual(payload["timestamps"], "edge-words")
        bare = dict(payload)
        bare.pop("timestamps")
        self.assertNotEqual(digest_obj(payload), digest_obj(bare))
        os.environ["VF_TTS"] = "google"
        google = _speech_payload("Hello there", "en")
        self.assertNotIn("timestamps", google)

    def test_edge_cache_misses_when_sidecar_is_missing(self) -> None:
        os.environ["VF_TTS"] = "edge"
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "beat.mp3"
            subprocess.check_call(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=24000:cl=mono",
                    "-t",
                    "0.4",
                    "-q:a",
                    "9",
                    str(dest),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            key = digest_obj(_speech_payload("Hello", "en"))
            write_mark(dest, key)
            self.assertFalse(_reuse_speech(dest, key))
            write_words_sidecar(dest, [_word("Hello", 0.0, 0.4)])
            self.assertTrue(_reuse_speech(dest, key))
            os.environ["VF_TTS"] = "google"
            google_key = digest_obj(_speech_payload("Hello", "en"))
            write_mark(dest, google_key)
            words_sidecar(dest).unlink()
            self.assertTrue(_reuse_speech(dest, google_key))

    def test_clip_key_distinguishes_word_timing_from_speech_weight(self) -> None:
        from build import _clip_key

        audio = Path("missing.mp3")
        holds = [1.0, 3.0]
        weight = _clip_key([], holds, audio, True, "on", cap_time=CAP_TIME_WEIGHT)
        words = _clip_key([], holds, audio, True, "on", cap_time=CAP_TIME_WORDS)
        self.assertNotEqual(weight, words)
        self.assertEqual(weight, _clip_key([], holds, audio, True, "on"))


if __name__ == "__main__":
    unittest.main()
