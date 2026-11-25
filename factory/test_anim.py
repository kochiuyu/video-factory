"""Opt-in animated scenes. Slide lessons do not import Manim."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from anim import (
    ManimNotInstalled,
    anim_cache_dir,
    cache_key,
    frame_size,
    labels_for,
    pages_for_animated,
    require_manim,
    scene_problems,
    step_durations,
)
from mux import CAP_TIME_WORDS
from slides import LAYOUT_VERSION, STAGEABLE, lesson_stamp, stage_plan
from theme import load_theme
from validate import load_lesson, validate


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "factory" / "fixtures" / "still_image.yaml"
DEMO = ROOT / "examples" / "demo-ten-and-ones.yaml"
MUX = ROOT / "factory" / "mux.py"
FIXTURE_STAMP = "b3001b527aa6d8d5f62f"

THIRTEEN = {
    "id": "thirteen",
    "visual": "animated",
    "scene": "ten_and_ones",
    "count": 13,
    "s1_en": "Thirteen counters.",
    "s2_en": "One ten.",
    "s3_en": "Ten plus three.",
    "s1_zh": "十三个圆片。",
    "s2_zh": "一个十。",
    "s3_zh": "十加三。",
    "s1_zh_hk": "十三個圓片。",
    "s2_zh_hk": "一個十。",
    "s3_zh_hk": "十加三。",
}

MAKE = {
    "id": "make-ten",
    "visual": "animated",
    "scene": "make_ten",
    "a": 9,
    "b": 8,
    "s1_en": "Nine and eight.",
    "s2_en": "Nine plus one equals ten.",
    "s3_en": "Ten plus seven equals seventeen.",
    "s1_zh": "九和八。",
    "s2_zh": "九加一等于十。",
    "s3_zh": "十加七等于十七。",
    "s1_zh_hk": "九同八。",
    "s2_zh_hk": "九加一等於十。",
    "s3_zh_hk": "十加七等於十七。",
}


# Simplified forms whose traditional counterparts differ. Shared characters
# such as 十 and 一 are not in this set.
SIMPLIFIED_ONLY = set("凑个两还满这们边进绿圆东国学时间说话语对发经过门问为会后云块体只从来里")


def _label_text(labels) -> str:
    parts: list[str] = []

    def walk(value) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(labels)
    return "".join(parts)


class AnimatedSchemaTest(unittest.TestCase):
    def test_demo_numbers_and_valid_lesson(self):
        self.assertEqual(labels_for(THIRTEEN, "en")["equation"], ["13", "=", "10", "+", "3"])
        self.assertEqual(labels_for(THIRTEEN, "zh_hk")["one_ten"], "一個十")
        self.assertEqual(labels_for(THIRTEEN, "zh")["ones"], "3个一")
        made = labels_for(MAKE, "zh_hk")
        self.assertEqual(made["equation1"], ["9", "+", "1", "=", "10"])
        self.assertEqual(made["equation2"], ["10", "+", "7", "=", "17"])
        self.assertEqual(scene_problems(THIRTEEN), [])
        self.assertEqual(scene_problems(MAKE), [])
        lesson = load_lesson(DEMO)
        self.assertEqual(validate(lesson, source=DEMO), [])
        self.assertEqual(
            [beat["visual"] for beat in lesson["beats"]],
            ["title_card", "definition_card", "animated", "animated", "takeaway"],
        )
        by_id = {beat["id"]: beat for beat in lesson["beats"]}
        self.assertEqual(by_id["thirteen"]["count"], 13)
        self.assertEqual((by_id["make-ten"]["a"], by_id["make-ten"]["b"]), (9, 8))
        self.assertEqual(by_id["define"]["formula_zh_hk"], "一個十＝滿框")
        self.assertIn("q1_en", by_id["takeaway"])
        self.assertIn("q2_zh_hk", by_id["takeaway"])

    def test_zh_hk_demo_labels_have_no_simplified_only_characters(self):
        lesson = load_lesson(DEMO)
        animated = [beat for beat in lesson["beats"] if beat.get("visual") == "animated"]
        self.assertEqual(len(animated), 2)
        for beat in animated:
            traditional = _label_text(labels_for(beat, "zh_hk"))
            simplified = _label_text(labels_for(beat, "zh"))
            found = sorted({ch for ch in traditional if ch in SIMPLIFIED_ONLY})
            self.assertEqual(found, [], traditional)
            self.assertNotEqual(traditional, simplified)
            self.assertTrue(simplified)
        make = next(beat for beat in animated if beat["id"] == "make-ten")
        self.assertEqual(labels_for(make, "zh_hk")["title"], "湊成十")
        self.assertEqual(labels_for(make, "zh")["title"], "凑成十")
        self.assertIn("放入", make["s1_zh_hk"])
        self.assertNotIn("放進", make["s1_zh_hk"])

    def test_rejects_bad_scene_and_missing_cantonese(self):
        bad = dict(THIRTEEN, scene="graph")
        self.assertTrue(scene_problems(bad))
        short = dict(THIRTEEN, count=9)
        self.assertTrue(any("10 to 20" in msg for msg in scene_problems(short)))
        overflow = dict(MAKE, b=20)
        self.assertTrue(scene_problems(overflow))
        dropped = {key: value for key, value in THIRTEEN.items() if key != "s2_zh_hk"}
        self.assertTrue(any("Cantonese" in msg for msg in scene_problems(dropped)))
        no_hk = {key: value for key, value in THIRTEEN.items() if "zh_hk" not in key}
        self.assertEqual(scene_problems(no_hk), [])

    def test_animated_is_not_a_slide_stage(self):
        self.assertNotIn("animated", STAGEABLE)
        self.assertEqual(LAYOUT_VERSION, "2026-11-04-reveal-steps-type-v1")
        self.assertIn("scale=1920:1080", MUX.read_text(encoding="utf-8"))
        self.assertEqual(stage_plan(THIRTEEN, 12), [0])


class AnimatedTimingTest(unittest.TestCase):
    def test_short_beat_keeps_three_steps(self):
        pages, holds, _plan, still_idx, _how = pages_for_animated(
            THIRTEEN, "Thirteen counters. One ten. Ten plus three.", 2.5, "en", None, False
        )
        self.assertGreaterEqual(len(pages), 3)
        self.assertEqual(sorted(set(still_idx)), [0, 1, 2])
        durs = step_durations(holds, still_idx, 3)
        self.assertEqual(len(durs), 3)
        self.assertAlmostEqual(sum(durs), 2.5, places=6)
        self.assertTrue(all(d > 0 for d in durs))

    def test_language_durations_and_trailing_silence(self):
        en_pages, en_holds, _p, en_idx, _h = pages_for_animated(
            THIRTEEN, "Thirteen counters. One ten. Ten plus three.", 4.0, "en", None, False
        )
        hk_pages, hk_holds, _p2, hk_idx, _h2 = pages_for_animated(
            THIRTEEN, "十三個圓片。一個十。十加三。", 8.4, "zh_hk", None, False
        )
        en_steps = step_durations(en_holds, en_idx, 3)
        hk_steps = step_durations(hk_holds, hk_idx, 3)
        self.assertAlmostEqual(sum(en_steps), 4.0, places=6)
        self.assertAlmostEqual(sum(hk_steps), 8.4, places=6)
        self.assertNotEqual([round(x, 3) for x in en_steps], [round(x, 3) for x in hk_steps])
        self.assertTrue(en_pages and hk_pages)
        words = [
            {"text": "Thirteen", "start": 0.10, "end": 0.50},
            {"text": "counters", "start": 0.50, "end": 0.90},
            {"text": "One", "start": 1.20, "end": 1.50},
            {"text": "ten", "start": 1.50, "end": 1.90},
            {"text": "Ten", "start": 2.40, "end": 2.70},
            {"text": "plus", "start": 2.70, "end": 3.00},
            {"text": "three", "start": 3.00, "end": 3.40},
        ]
        _pages, holds, _plan, still_idx, how = pages_for_animated(
            THIRTEEN, "Thirteen counters. One ten. Ten plus three.", 4.0, "en", words, False
        )
        self.assertEqual(how, CAP_TIME_WORDS)
        timed = step_durations(holds, still_idx, 3)
        self.assertAlmostEqual(sum(timed), 4.0, places=6)
        self.assertGreater(timed[-1], 4.0 - 3.40)

    def test_frame_and_cache_key(self):
        self.assertEqual(frame_size({}), (1920, 1080))
        self.assertEqual(frame_size({"format": "16:9"}), (1920, 1080))
        self.assertEqual(frame_size({"format": "9:16"}), (1080, 1920))
        self.assertEqual(anim_cache_dir(Path("out"), {}), Path("out") / "anim")
        self.assertEqual(anim_cache_dir(Path("out"), {"format": "9:16"}), Path("out") / "9x16" / "anim")
        spec = {"scene": "ten_and_ones", "count": 13, "lang": "en"}
        base = cache_key(spec, [1, 1, 1], "en", (1920, 1080), "0.19.2")
        self.assertNotEqual(base, cache_key(spec, [1, 1, 2], "en", (1920, 1080), "0.19.2"))
        self.assertNotEqual(base, cache_key(spec, [1, 1, 1], "zh_hk", (1920, 1080), "0.19.2"))
        self.assertNotEqual(base, cache_key(spec, [1, 1, 1], "en", (1080, 1920), "0.19.2"))
        self.assertNotEqual(base, cache_key(spec, [1, 1, 1], "en", (1920, 1080), "0.18.1"))
        other = dict(spec, count=14)
        self.assertNotEqual(base, cache_key(other, [1, 1, 1], "en", (1920, 1080), "0.19.2"))

    def test_import_does_not_load_manim(self):
        proc = subprocess.run(
            [sys.executable, "-c", "import sys; import anim; raise SystemExit(0 if 'manim' not in sys.modules else 1)"],
            cwd=ROOT / "factory",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_manim_names_the_optional_file(self):
        saved = sys.modules.get("manim")
        sys.modules["manim"] = None
        try:
            with self.assertRaises(ManimNotInstalled) as caught:
                require_manim()
            self.assertIn("requirements-manim.txt", str(caught.exception))
        finally:
            if saved is None:
                sys.modules.pop("manim", None)
            else:
                sys.modules["manim"] = saved


class StillLessonUnchangedTest(unittest.TestCase):
    def test_fixture_stamp_is_unchanged(self):
        os.environ.pop("VF_LEGACY_REVEAL", None)
        os.environ.pop("VF_TYPOGRAPHY", None)
        lesson = load_lesson(FIXTURE)
        theme = load_theme("cuhk-navy")
        self.assertEqual(lesson_stamp(lesson, theme, "en", None, True), FIXTURE_STAMP)

    def test_slides_only_build_does_not_import_manim(self):
        script = textwrap.dedent(
            """
            import sys
            from pathlib import Path
            root = Path(sys.argv[1])
            sys.path.insert(0, str(root / "factory"))
            from build import build
            out = Path(sys.argv[2])
            build(
                root / "factory" / "fixtures" / "still_image.yaml",
                out,
                "en",
                tts=False,
                slides_only=True,
                write_pdfs=False,
                theme_name="cuhk-navy",
            )
            if "manim" in sys.modules or "anim" in sys.modules:
                raise SystemExit("animated renderer was imported for a still lesson")
            from PIL import Image
            pngs = list((out).rglob("*.png"))
            slides = [p for p in pngs if "slides" in p.parts]
            if not slides:
                raise SystemExit("no slide pngs")
            for path in slides:
                if Image.open(path).size != (1920, 1080):
                    raise SystemExit(f"unexpected size {path}")
            if (out / "anim").exists() or (out / "9x16").exists():
                raise SystemExit("animated cache was created")
            """
        )
        with tempfile.TemporaryDirectory(prefix="vf-still-") as tmp:
            proc = subprocess.run(
                [sys.executable, "-c", script, str(ROOT), tmp],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)


@unittest.skipUnless(importlib.util.find_spec("manim") is not None, "Manim is optional")
class AnimatedRenderTest(unittest.TestCase):
    def test_tiny_scenes_match_the_frame_and_reuse_the_cache(self):
        from ff import check_call, probe_duration
        from anim import render_animated_clip

        with tempfile.TemporaryDirectory(prefix="vf-anim-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            check_call(
                [
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=48000:cl=stereo",
                    "-t",
                    "1.2",
                    "-c:a",
                    "pcm_s16le",
                    str(audio),
                ],
                timeout=60,
            )
            self.assertGreater(probe_duration(audio), 1.0)
            frame = (640, 360)
            durs = [0.35, 0.35, 0.35]
            holds = durs
            still_idx = [0, 1, 2]
            cache = root / "anim"
            jobs = (
                (THIRTEEN, "zh_hk", ["十三個圓片。", "一個十。", "十加三。"]),
                (MAKE, "en", ["Nine and eight.", "Nine plus one equals ten.", "Ten plus seven equals seventeen."]),
            )
            for beat, lang, pages in jobs:
                dest = root / f"{beat['id']}-{lang}.mp4"
                render_animated_clip(
                    beat,
                    {},
                    label_lang_code=lang,
                    holds=holds,
                    still_idx=still_idx,
                    pages=pages,
                    audio=audio,
                    dest=dest,
                    cache_dir=cache,
                    captions=True,
                    progress_bar=False,
                    frame=frame,
                    fps=10,
                )
                silent = next((cache / lang).glob(f"{beat['id']}-*.mp4"))
                first = silent.stat().st_mtime_ns
                render_animated_clip(
                    beat,
                    {},
                    label_lang_code=lang,
                    holds=holds,
                    still_idx=still_idx,
                    pages=pages,
                    audio=audio,
                    dest=dest,
                    cache_dir=cache,
                    captions=True,
                    progress_bar=False,
                    frame=frame,
                    fps=10,
                )
                self.assertEqual(silent.stat().st_mtime_ns, first)
                probe = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=width,height",
                        "-of",
                        "csv=p=0",
                        str(dest),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(probe.stdout.strip(), "640,360", probe.stderr)
                shot = root / f"{beat['id']}-{lang}.png"
                check_call(["-y", "-ss", "0.2", "-i", str(dest), "-frames:v", "1", str(shot)], timeout=60)
                from PIL import Image

                colors = Image.open(shot).convert("RGB").getcolors(maxcolors=200000)
                self.assertNotEqual(colors, [(shot.stat().st_size, (247, 244, 238))])
                self.assertTrue(colors is None or len(colors) > 1)


if __name__ == "__main__":
    unittest.main()
