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
from scene_registry import REGISTRY, count_event, count_marks, crosses_ten, schedule_marks, step_count, track_columns
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
            ["title_card", "animated", "animated", "animated", "takeaway"],
        )
        by_id = {beat["id"]: beat for beat in lesson["beats"]}
        self.assertEqual(by_id["hook"]["visual"], "title_card")
        self.assertEqual(by_id["takeaway"]["visual"], "takeaway")
        self.assertEqual(by_id["define"]["scene"], "one_ten")
        self.assertEqual(by_id["define"]["count"], 13)
        self.assertEqual(labels_for(by_id["define"], "en")["one_ten"], "one ten")
        self.assertEqual(labels_for(by_id["define"], "zh_hk")["ones"], "3個一")
        self.assertEqual(labels_for(by_id["define"], "zh")["title"], "满框就是一个十")
        self.assertEqual(by_id["define"]["s4_en"], "Three.")
        self.assertEqual(by_id["define"]["s4_zh"], "三个。")
        self.assertEqual(by_id["define"]["s4_zh_hk"], "三個。")
        self.assertEqual(by_id["takeaway"]["title_zh_hk"], "先搵十")
        self.assertEqual(by_id["thirteen"]["count"], 13)
        self.assertEqual((by_id["make-ten"]["a"], by_id["make-ten"]["b"]), (9, 8))
        self.assertIn("q1_en", by_id["takeaway"])
        self.assertIn("q2_zh_hk", by_id["takeaway"])

    def test_zh_hk_demo_labels_have_no_simplified_only_characters(self):
        lesson = load_lesson(DEMO)
        animated = [beat for beat in lesson["beats"] if beat.get("visual") == "animated"]
        self.assertEqual(len(animated), 3)
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
        self.assertEqual(make["s1_zh_hk"], "九個喺框入面。八個喺隔籬等緊。")
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

    def test_takeaway_breaks_only_at_punctuation_or_spaces(self):
        from anim import takeaway_pieces

        self.assertEqual(takeaway_pieces("先找十，再数剩下的。"), ["先找十，", "再数剩下的。"])
        self.assertEqual(takeaway_pieces("一個滿框，就係一個十。"), ["一個滿框，", "就係一個十。"])
        self.assertEqual(takeaway_pieces("再数剩下的"), ["再数剩下的"])
        self.assertEqual(takeaway_pieces("就係一個十"), ["就係一個十"])
        self.assertEqual(
            takeaway_pieces("Ten and three more make thirteen."),
            ["Ten", "and", "three", "more", "make", "thirteen."],
        )

    def test_takeaway_grid_is_equal_cells(self):
        from anim import (
            TAKEAWAY_ROW_GAP,
            TAKEAWAY_SIDE,
            TAKEAWAY_TEXT_SHARE,
            TAKEAWAY_VISUAL_FIT,
            TAKEAWAY_VISUAL_SHARE,
            takeaway_grid,
        )

        for pw, ph, n in ((1920, 1080, 4), (1920, 1080, 3), (1080, 1920, 4), (1080, 1920, 3)):
            grid = takeaway_grid(pw, ph, n)
            cells = grid["cells"]
            self.assertEqual(len(cells), n)
            heights = [cell["top"] - cell["bottom"] for cell in cells]
            self.assertTrue(all(abs(height - heights[0]) < 1e-9 for height in heights))
            for earlier, later in zip(cells, cells[1:]):
                self.assertAlmostEqual(earlier["bottom"], later["top"], places=6)
                self.assertGreater(earlier["bottom"], later["bottom"])
            self.assertAlmostEqual(grid["left"], -grid["fw"] / 2 + TAKEAWAY_SIDE * grid["fw"], places=6)
            self.assertAlmostEqual(grid["visual_of_cell"], min(TAKEAWAY_VISUAL_FIT, 1.0 - TAKEAWAY_ROW_GAP), places=6)
            self.assertLessEqual(grid["visual_of_cell"], 1.0 - TAKEAWAY_ROW_GAP)
            span = grid["rows_top"] - grid["rows_bottom"]
            self.assertAlmostEqual(sum(heights), span, places=6)
            self.assertGreaterEqual(span / grid["fh"], 0.75)
            if grid["portrait"]:
                self.assertAlmostEqual(grid["floor_px"], 52 * ph / 1920, places=4)
                self.assertAlmostEqual(grid["vis_w"], grid["text_w"], places=6)
            else:
                self.assertAlmostEqual(grid["floor_px"], 44 * ph / 1080, places=4)
                safe = grid["right"] - grid["left"]
                self.assertAlmostEqual(grid["vis_w"], TAKEAWAY_VISUAL_SHARE * safe, places=6)
                self.assertAlmostEqual(grid["text_w"], TAKEAWAY_TEXT_SHARE * safe, places=6)
            self.assertGreaterEqual(grid["preferred_px"], grid["floor_px"])

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
            cache = root / "anim"
            define = {
                "id": "define",
                "visual": "animated",
                "scene": "one_ten",
                "count": 13,
                "s1_en": "Ten single counters.",
                "s2_en": "A full frame is one ten.",
                "s3_en": "How many are outside?",
                "s4_en": "Three.",
                "s1_zh": "十个圆片。",
                "s2_zh": "满框就是一个十。",
                "s3_zh": "外面有几个？",
                "s4_zh": "三个。",
                "s1_zh_hk": "十個圓片。",
                "s2_zh_hk": "滿框就係一個十。",
                "s3_zh_hk": "出面有幾多個？",
                "s4_zh_hk": "三個。",
            }
            jobs = (
                (define, "zh_hk", ["十個圓片。", "滿框就係一個十。", "出面有幾多個？", "三個。"]),
                (THIRTEEN, "zh_hk", ["十三個圓片。", "一個十。", "十加三。"]),
                (MAKE, "en", ["Nine and eight.", "Nine plus one equals ten.", "Ten plus seven equals seventeen."]),
                (
                    {
                        "id": "count",
                        "visual": "animated",
                        "scene": "count_objects",
                        "mode": "count",
                        "count": 5,
                        "s1_en": "Point once.",
                        "s2_en": "One two three four five.",
                        "s3_en": "Five.",
                        "s1_zh": "点一次。",
                        "s2_zh": "一二三四五。",
                        "s3_zh": "五个。",
                        "s1_zh_hk": "指一次。",
                        "s2_zh_hk": "一二三四五。",
                        "s3_zh_hk": "五個。",
                    },
                    "zh_hk",
                    ["指一次。", "一二三四五。", "五個。"],
                ),
                (
                    {
                        "id": "empty",
                        "visual": "animated",
                        "scene": "count_objects",
                        "mode": "zero",
                        "count": 0,
                        "s1_en": "Empty.",
                        "s2_en": "How many?",
                        "s3_en": "Zero.",
                        "s1_zh": "空的。",
                        "s2_zh": "几个？",
                        "s3_zh": "零。",
                        "s1_zh_hk": "空嘅。",
                        "s2_zh_hk": "幾多個？",
                        "s3_zh_hk": "零。",
                    },
                    "en",
                    ["Empty.", "How many?", "Zero."],
                ),
                (
                    {
                        "id": "track",
                        "visual": "animated",
                        "scene": "number_track",
                        "low": 0,
                        "high": 20,
                        "start": 12,
                        "end": 9,
                        "s1_en": "Start at twelve.",
                        "s2_en": "Eleven ten nine.",
                        "s3_en": "Nine.",
                        "s1_zh": "由十二。",
                        "s2_zh": "十一十。",
                        "s3_zh": "九。",
                        "s1_zh_hk": "由十二。",
                        "s2_zh_hk": "十一十。",
                        "s3_zh_hk": "九。",
                    },
                    "zh_hk",
                    ["由十二。", "十一十。", "九。"],
                ),
                (
                    dict(THIRTEEN, id="twenty", count=20),
                    "en",
                    ["Two frames.", "Two tens.", "Twenty."],
                ),
            )
            for beat, lang, pages in jobs:
                n = len(pages)
                holds = [1.2 / n] * n
                still_idx = list(range(n))
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
                if beat.get("scene") in {"count_objects", "number_track"}:
                    img = Image.open(shot).convert("RGB")
                    cream = (247, 244, 238)

                    def near(px):
                        return all(abs(px[i] - cream[i]) <= 10 for i in range(3))

                    width, height = img.size
                    top = [img.getpixel((x, 1)) for x in range(0, width, 4)]
                    side = [img.getpixel((1, y)) for y in range(0, int(height * 0.7), 4)]
                    self.assertGreater(sum(map(near, top)) / len(top), 0.85, beat["id"])
                    self.assertGreater(sum(map(near, side)) / len(side), 0.85, beat["id"])
            tall = {
                "id": "track-tall",
                "visual": "animated",
                "scene": "number_track",
                "low": 0,
                "high": 20,
                "start": 9,
                "end": 12,
                "s1_en": "Start at nine.",
                "s2_en": "Ten eleven twelve.",
                "s3_en": "Twelve.",
                "s1_zh": "从九开始。",
                "s2_zh": "十十一十二。",
                "s3_zh": "十二。",
                "s1_zh_hk": "由九開始。",
                "s2_zh_hk": "十十一十二。",
                "s3_zh_hk": "十二。",
            }
            tall_pages = ["由九開始。", "十十一十二。", "十二。"]
            tall_dest = root / "track-tall.mp4"
            render_animated_clip(
                tall,
                {"format": "9:16"},
                label_lang_code="zh_hk",
                holds=[0.4, 0.4, 0.4],
                still_idx=[0, 1, 2],
                pages=tall_pages,
                audio=audio,
                dest=tall_dest,
                cache_dir=cache,
                captions=True,
                progress_bar=False,
                frame=(360, 640),
                fps=10,
            )
            tall_probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height", "-of", "csv=p=0", str(tall_dest),
                ],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(tall_probe.stdout.strip(), "360,640", tall_probe.stderr)
            self._frames_inside(root / "define-zh_hk.mp4")
            self._frames_inside(root / "thirteen-zh_hk.mp4")
            for beat, frame_px, name, pages in (
                (define, (360, 640), "define-tall", ["Ten.", "One ten.", "Outside?", "Three."]),
                (THIRTEEN, (360, 640), "thirteen-tall", ["Count.", "Ten.", "Thirteen."]),
            ):
                dest = root / f"{name}.mp4"
                holds = [1.2 / len(pages)] * len(pages)
                render_animated_clip(
                    beat, {"format": "9:16"}, label_lang_code="en",
                    holds=holds, still_idx=list(range(len(pages))), pages=pages,
                    audio=audio, dest=dest, cache_dir=cache, captions=False,
                    progress_bar=False, frame=frame_px, fps=10,
                )
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=width,height", "-of", "csv=p=0", str(dest)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(probe.stdout.strip(), f"{frame_px[0]},{frame_px[1]}", probe.stderr)
                self._frames_inside(dest)

    def _frames_inside(self, video, frac=0.025):
        """Every decoded frame keeps the outer margin cream. Counters must not enter it."""
        from PIL import Image

        from ff import check_call

        folder = Path(str(video) + "-frames")
        folder.mkdir(exist_ok=True)
        check_call(["-y", "-i", str(video), str(folder / "f%03d.png")], timeout=60)
        cream = (247, 244, 238)
        frames = sorted(folder.glob("f*.png"))
        self.assertGreaterEqual(len(frames), 4, video.name)

        def near(px):
            return all(abs(px[i] - cream[i]) <= 14 for i in range(3))

        for path in frames:
            img = Image.open(path).convert("RGB")
            w, h = img.size
            mx = max(2, int(round(w * frac)))
            my = max(2, int(round(h * frac)))
            samples = [img.getpixel((x, y)) for y in range(my) for x in range(0, w, 3)]
            samples += [img.getpixel((x, y)) for x in range(mx) for y in range(0, h, 5)]
            samples += [img.getpixel((w - 1 - x, y)) for x in range(mx) for y in range(0, h, 5)]
            ratio = sum(map(near, samples)) / len(samples)
            self.assertGreater(ratio, 0.90, f"{video.name} {path.name} margin {ratio:.2f}")

    def test_track_hops_land_on_each_spoken_number(self):
        """The gold box sits on 9, then 10, then 11, then 12 as those words are spoken."""
        import subprocess
        import tempfile

        from PIL import Image

        from anim import render_animated_clip

        beat = {
            "id": "hop",
            "visual": "animated",
            "scene": "number_track",
            "low": 0,
            "high": 20,
            "start": 9,
            "end": 12,
            "s1_en": "Start at nine.",
            "s2_en": "Nine. Ten. Eleven. Twelve.",
            "s3_en": "Twelve.",
            "s1_zh": "从九开始。",
            "s2_zh": "九。十。十一。十二。",
            "s3_zh": "十二。",
            "s1_zh_hk": "由九開始。",
            "s2_zh_hk": "九。十。十一。十二。",
            "s3_zh_hk": "十二。",
        }
        words = [
            {"text": "Start", "start": 0.1, "end": 0.4},
            {"text": "Nine", "start": 1.15, "end": 1.5},
            {"text": "Ten", "start": 2.05, "end": 2.4},
            {"text": "Eleven", "start": 2.95, "end": 3.3},
            {"text": "Twelve", "start": 3.85, "end": 4.2},
            {"text": "Twelve", "start": 5.1, "end": 5.4},
        ]
        with tempfile.TemporaryDirectory(prefix="vf-hop-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            subprocess.check_call(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", "6", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            dest = root / "hop.mp4"
            render_animated_clip(
                beat, {}, label_lang_code="en",
                holds=[1.0, 4.0, 1.0], still_idx=[0, 1, 2],
                pages=["Start at nine.", "Nine. Ten. Eleven. Twelve.", "Twelve."],
                audio=audio, dest=dest, cache_dir=root / "cache",
                captions=False, progress_bar=False, frame=(640, 360), fps=10,
                words=words,
            )
            silent = next((root / "cache" / "en").glob("hop-*.mp4"))
            xs = []
            for n, t in enumerate((1.35, 2.25, 3.15, 4.05)):
                shot = root / f"hop-{n}.png"
                subprocess.check_call(
                    ["ffmpeg", "-y", "-i", str(silent), "-vf", f"select=eq(n\\,{int(t * 10)})",
                     "-frames:v", "1", str(shot)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                xs.append(self._gold_x(shot))
            self.assertTrue(all(xs[i] < xs[i + 1] - 4 for i in range(3)), xs)

    def test_takeaway_grid_fills_cells_in_both_aspects(self):
        """Each takeaway row stays in its cell, pictures stay apart, and the type meets the floor.

        Checked for the ten-frame recap, the counters recap, and the three-line
        track recap, in English, 简体, and Cantonese, at 16:9 and 9:16.
        """
        import subprocess
        import tempfile

        from PIL import Image

        from anim import render_animated_clip, takeaway_grid

        beat = {
            "id": "takeaway",
            "visual": "animated",
            "scene": "lesson_takeaway",
            "motif": "ten_frame",
            "title_en": "Find the ten first",
            "s1_en": "One full frame is one ten.",
            "s2_en": "Ten and three more make thirteen.",
            "s3_en": "Two full frames make twenty.",
            "s4_en": "Find the ten first. Then count the rest.",
            "title_zh": "先找十",
            "s1_zh": "一个满框，就是一个十。",
            "s2_zh": "十再多三个，就是十三。",
            "s3_zh": "两个满框，就是二十。",
            "s4_zh": "先找十，再数剩下的。",
            "title_zh_hk": "先搵十",
            "s1_zh_hk": "一個滿框，就係一個十。",
            "s2_zh_hk": "十再多三個，就係十三。",
            "s3_zh_hk": "兩個滿框，就係二十。",
            "s4_zh_hk": "先搵十，再數剩低嘅。",
        }
        counted = {
            "id": "takeaway",
            "visual": "animated",
            "scene": "lesson_takeaway",
            "motif": "counters",
            "count": 5,
            "title_en": "Count carefully",
            "s1_en": "Touch each one once. One, two, three, four, five.",
            "s2_en": "The last number tells how many. Five.",
            "s3_en": "Move them around. Still five.",
            "s4_en": "Nothing there? That is zero.",
            "title_zh": "逐个数清楚",
            "s1_zh": "每个只点一次。一，二，三，四，五。",
            "s2_zh": "最后说的数，就是有多少。五个。",
            "s3_zh": "搬一搬，还是五个。",
            "s4_zh": "什么都没有？就是零。",
            "title_zh_hk": "逐個數清楚",
            "s1_zh_hk": "每個只係指一次。一，二，三，四，五。",
            "s2_zh_hk": "最後講嘅數，就係有幾多。五個。",
            "s3_zh_hk": "搬吓佢哋，都係五個。",
            "s4_zh_hk": "乜都冇？就係零。",
        }
        track = {
            "id": "takeaway",
            "visual": "animated",
            "scene": "lesson_takeaway",
            "motif": "track",
            "title_en": "One at a time",
            "s1_en": "Count on means one more each time.",
            "s2_en": "Count back means one less each time.",
            "s3_en": "You can count back across ten.",
            "title_zh": "一次一个",
            "s1_zh": "顺着数，就是每次多一个。",
            "s2_zh": "倒着数，就是每次少一个。",
            "s3_zh": "倒着数，也可以跨过十。",
            "title_zh_hk": "一次一個",
            "s1_zh_hk": "順住數，就係每次多一個。",
            "s2_zh_hk": "倒轉數，就係每次少一個。",
            "s3_zh_hk": "倒轉數，都可以跨過十。",
        }
        cards = (("ten", beat, 4), ("count", counted, 4), ("track", track, 3))

        def pix_y(grid, manim_y):
            return (grid["fh"] / 2 - manim_y) / grid["fh"] * grid["ph"]

        def pix_x(grid, manim_x):
            return (manim_x + grid["fw"] / 2) / grid["fw"] * grid["pw"]

        with tempfile.TemporaryDirectory(prefix="vf-recap-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            subprocess.check_call(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", "3", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            for motif, card, steps in cards:
                holds = [0.3] * (steps - 1) + [0.5]
                for lang, frame in (
                    ("en", (1280, 720)),
                    ("zh", (1280, 720)),
                    ("zh_hk", (1280, 720)),
                    ("en", (720, 1280)),
                    ("zh", (720, 1280)),
                    ("zh_hk", (720, 1280)),
                ):
                    dest = root / f"{motif}-{lang}-{frame[0]}x{frame[1]}.mp4"
                    render_animated_clip(
                        card, {"format": "9:16" if frame[1] > frame[0] else "16:9"},
                        label_lang_code=lang, holds=holds, still_idx=list(range(steps)),
                        pages=["a"] * steps, audio=audio, dest=dest,
                        cache_dir=root / "cache", captions=False, progress_bar=False,
                        frame=frame, fps=8,
                    )
                    shot = root / f"{motif}-{lang}-{frame[0]}x{frame[1]}.png"
                    duration = float(subprocess.check_output(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "csv=p=0", str(dest)],
                        text=True,
                    ))
                    last = max(0, int(duration * 8) - 1)
                    subprocess.check_call(
                        ["ffmpeg", "-y", "-i", str(dest), "-vf", f"select=eq(n\\,{last})",
                         "-frames:v", "1", str(shot)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    self._takeaway_frame_matches_grid(shot, steps)

    def _takeaway_frame_matches_grid(self, path, steps: int):
        """Ink sits in its cell, pictures do not meet, and the body type meets the floor."""
        from PIL import Image

        from anim import takeaway_grid

        img = Image.open(path).convert("RGB")
        px = img.load()
        w, h = img.size
        grid = takeaway_grid(w, h, steps)

        def ink(x, y):
            r, g, b = px[x, y]
            return not (r > 232 and g > 226 and b > 216)

        def py(manim_y):
            return (grid["fh"] / 2 - manim_y) / grid["fh"] * h

        def px_of(manim_x):
            return (manim_x + grid["fw"] / 2) / grid["fw"] * w

        left = int(px_of(grid["left"]))
        right = int(px_of(grid["right"]))
        top = int(py(grid["top"]))
        bottom = int(py(grid["rows_bottom"]))
        outside = 0
        ys = []
        for y in range(h):
            for x in range(0, w, 2):
                if not ink(x, y):
                    continue
                ys.append(y)
                if x < left - 3 or x > right + 3 or y < top - 3 or y > bottom + 3:
                    outside += 1
        self.assertEqual(outside, 0, f"{path.name} outside {outside}")
        self.assertTrue(ys, path.name)
        safe_span = bottom - top
        self.assertGreaterEqual(max(ys) - min(ys), int(safe_span * 0.75), path.name)

        cell_px = []
        for cell in grid["cells"]:
            cell_px.append((int(py(cell["top"])), int(py(cell["bottom"]))))
        for index, (cell_top, cell_bottom) in enumerate(cell_px):
            if index + 1 < len(cell_px):
                self.assertLessEqual(cell_bottom, cell_px[index + 1][0] + 1, path.name)
            stray = 0
            for y in range(max(0, cell_top), min(h, cell_bottom)):
                for x in range(0, w, 3):
                    if ink(x, y) and (x < left - 2 or x > right + 2):
                        stray += 1
            self.assertEqual(stray, 0, f"{path.name} row {index} outside")

        # Pictures live in the visual slot. The empty band between those slots
        # is at least a quarter of the row, so two pictures cannot touch.
        vis_left = int(px_of(grid["vis_left"]))
        vis_right = int(px_of(grid["vis_left"] + grid["vis_w"]))
        cell_h = cell_px[0][1] - cell_px[0][0]
        visual_rows = []
        for cell_top, cell_bottom in cell_px:
            zone_bottom = cell_bottom
            if grid["portrait"]:
                zone_bottom = cell_top + int(0.50 * (cell_bottom - cell_top))
            found = [
                y for y in range(max(0, cell_top), min(h, zone_bottom))
                if sum(1 for x in range(max(0, vis_left), min(w, vis_right), 3) if ink(x, y)) > 1
            ]
            self.assertTrue(found, f"{path.name} empty visual {cell_top}-{cell_bottom}")
            visual_rows.append((min(found), max(found)))
        for earlier, later in zip(visual_rows, visual_rows[1:]):
            gap = later[0] - earlier[1]
            # The picture is fitted to 75% of the cell, so the layout gap is 25%.
            # Strokes sit a few pixels outside that box; 22% still rejects frames that touch.
            self.assertGreaterEqual(gap, int(cell_h * 0.22), f"{path.name} gap {gap} cell {cell_h} {visual_rows}")

        floor = float(grid["floor_px"])
        text_left = int(px_of(grid["text_left"]))
        text_bands = []
        if grid["portrait"]:
            for cell_top, cell_bottom in cell_px:
                zone = cell_top + int((1.0 - 0.55) * (cell_bottom - cell_top))
                rows = [y for y in range(zone, cell_bottom) if sum(1 for x in range(left, right, 3) if ink(x, y)) > 2]
                if not rows:
                    continue
                text_bands.append(max(rows) - min(rows) + 1)
        else:
            rows = [
                y for y in range(cell_px[0][0], cell_px[-1][1])
                if sum(1 for x in range(text_left, right, 3) if ink(x, y)) > 2
            ]
            start = prev = None
            for y in rows:
                if start is None:
                    start = prev = y
                elif y - prev > 3:
                    if prev - start >= 8:
                        text_bands.append(prev - start + 1)
                    start = prev = y
                else:
                    prev = y
            if start is not None and prev - start >= 8:
                text_bands.append(prev - start + 1)
        self.assertTrue(text_bands, path.name)
        for band in text_bands:
            line_h = band / max(1, round(band / max(floor, 1)))
            self.assertGreaterEqual(line_h, floor * 0.78, f"{path.name} font {line_h:.1f} vs {floor:.1f}")

    def _gold_x(self, path):
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        pts = []
        for y in range(h):
            for x in range(w):
                r, g, b = img.getpixel((x, y))
                if r > 190 and r > g + 12 and g > b + 30:
                    pts.append(x)
        self.assertGreater(len(pts), 8, path.name)
        return sum(pts) / len(pts)


P1 = ROOT / "lessons" / "P1"
# Simplified forms whose traditional counterparts differ. Shared glyphs are omitted.
LEAK = set(
    "凑个两还满这们边进绿圆东国学时间说话语对发经过门问为会后云块体从来里"
    "数点几盘顺转开现样长头关动电车无万么着贝风鱼鸟页观"
)


def _beat_lines(lesson, suffix: str) -> str:
    parts = []
    for beat in lesson["beats"]:
        for key, value in beat.items():
            if str(key).endswith(suffix) and isinstance(value, str):
                parts.append(value)
    return "".join(parts)


class SceneRegistryTest(unittest.TestCase):
    def test_registry_order_and_step_counts(self):
        self.assertEqual(
            list(REGISTRY),
            [
                "one_ten", "ten_and_ones", "make_ten", "count_objects", "number_track",
                "lesson_hook", "lesson_takeaway",
            ],
        )
        self.assertEqual(REGISTRY["one_ten"].steps, 4)
        self.assertEqual(REGISTRY["count_objects"].steps, 3)
        self.assertEqual(REGISTRY["number_track"].steps, 3)
        self.assertEqual(scene_problems({"visual": "title_card", "scene": "nope"}), [])

    def test_twenty_is_two_full_frames(self):
        beat = dict(THIRTEEN, count=20)
        labels = labels_for(beat, "zh_hk")
        self.assertEqual(labels["equation"], ["20", "=", "10", "+", "10"])
        self.assertEqual(labels["one_ten"], "兩個十")
        self.assertEqual(labels_for(beat, "zh")["one_ten"], "两个十")
        self.assertEqual(scene_problems(beat), [])

    def test_count_objects_validation_and_timing(self):
        good = {
            "visual": "animated",
            "scene": "count_objects",
            "mode": "count",
            "count": 5,
            "s1_en": "Point once.",
            "s2_en": "One. Two. Three. Four. Five.",
            "s3_en": "Five.",
            "s1_zh": "点一次。",
            "s2_zh": "一。",
            "s3_zh": "五个。",
            "s1_zh_hk": "指一次。",
            "s2_zh_hk": "一。",
            "s3_zh_hk": "五個。",
        }
        self.assertEqual(scene_problems(good), [])
        self.assertEqual(labels_for(good, "en")["answer"], "5")
        self.assertEqual(labels_for(good, "zh_hk")["note"], "最後嘅數")
        self.assertIn("mode", scene_problems(dict(good, mode="scatter"))[0])
        self.assertTrue(scene_problems(dict(good, mode="zero", count=5)))
        empty = dict(good, mode="zero", count=0)
        self.assertEqual(scene_problems(empty), [])
        self.assertEqual(labels_for(empty, "zh_hk")["answer"], "0")
        self.assertEqual(labels_for(empty, "zh_hk")["title"], "空盤")
        _pages, holds, _plan, still_idx, _how = pages_for_animated(
            good, "Point once. One. Two. Three. Four. Five. Five.", 6.0, "en", None, False
        )
        durs = step_durations(holds, still_idx, 3)
        self.assertEqual(len(durs), 3)
        self.assertAlmostEqual(sum(durs), 6.0, places=6)

    def test_number_track_validation_crossing_and_timing(self):
        beat = {
            "visual": "animated",
            "scene": "number_track",
            "low": 0,
            "high": 20,
            "start": 12,
            "end": 9,
            "s1_en": "Can we cross ten?",
            "s2_en": "Twelve. Eleven. Ten. Nine.",
            "s3_en": "Yes. Nine.",
            "s1_zh": "能跨过十吗？",
            "s2_zh": "十二。",
            "s3_zh": "可以。",
            "s1_zh_hk": "可唔可以跨過十呀？",
            "s2_zh_hk": "十二。",
            "s3_zh_hk": "可以。",
        }
        self.assertEqual(scene_problems(beat), [])
        self.assertTrue(crosses_ten(12, 9))
        self.assertTrue(crosses_ten(9, 12))
        self.assertFalse(crosses_ten(20, 17))
        labels = labels_for(beat, "zh_hk")
        self.assertEqual(labels["title"], "倒轉數")
        self.assertEqual(labels["cross"], "跨過十")
        self.assertEqual(labels["answer"], "9")
        onward = dict(beat, start=9, end=12)
        self.assertEqual(labels_for(onward, "en")["title"], "Count on")
        self.assertEqual(labels_for(onward, "zh")["step"], "多一个")
        self.assertFalse(labels_for(dict(beat, start=20, end=17), "en")["cross"])
        self.assertTrue(any("different" in msg for msg in scene_problems(dict(beat, end=12))))
        self.assertTrue(scene_problems(dict(beat, start=21)))
        self.assertTrue(scene_problems(dict(beat, high=80)))
        _pages, holds, _plan, still_idx, _how = pages_for_animated(
            beat, "Can we cross ten? Twelve. Eleven. Ten. Nine. Yes. Nine.", 7.5, "en", None, False
        )
        durs = step_durations(holds, still_idx, 3)
        self.assertEqual(len(durs), 3)
        self.assertAlmostEqual(sum(durs), 7.5, places=6)
        self.assertTrue(all(d > 0 for d in durs))

    def test_p1_lessons_validate_and_keep_traditional_labels(self):
        expected = {
            "P1-NUM-01": ["lesson_hook", "count_objects", "count_objects", "count_objects", "lesson_takeaway"],
            "P1-NUM-02": ["lesson_hook", "one_ten", "ten_and_ones", "ten_and_ones", "lesson_takeaway"],
            "P1-NUM-03": ["lesson_hook", "number_track", "number_track", "number_track", "lesson_takeaway"],
        }
        for name, visuals in expected.items():
            path = P1 / f"{name}.yaml"
            lesson = load_lesson(path)
            self.assertEqual(validate(lesson, source=path), [], name)
            got = []
            for beat in lesson["beats"]:
                got.append(beat["scene"] if beat.get("visual") == "animated" else beat.get("visual"))
            self.assertEqual(got, visuals, name)
            trad_yaml = _beat_lines(lesson, "_zh_hk") + _beat_lines(lesson, "zh_hk")
            # title_zh_hk is caught by endswith zh_hk; speech keys end with _zh_hk.
            found = sorted({ch for ch in trad_yaml if ch in LEAK})
            self.assertEqual(found, [], f"{name} yaml {trad_yaml}")
            for beat in lesson["beats"]:
                if beat.get("visual") != "animated":
                    continue
                traditional = _label_text(labels_for(beat, "zh_hk"))
                leaked = sorted({ch for ch in traditional if ch in LEAK})
                self.assertEqual(leaked, [], traditional)
                self.assertNotEqual(traditional, _label_text(labels_for(beat, "zh")))
        two = load_lesson(P1 / "P1-NUM-02.yaml")
        twenty = next(beat for beat in two["beats"] if beat["id"] == "twenty")
        self.assertEqual(twenty["count"], 20)
        self.assertNotIn("make_ten", [beat.get("scene") for beat in two["beats"]])
        track = load_lesson(P1 / "P1-NUM-03.yaml")
        hops = [beat for beat in track["beats"] if beat.get("scene") == "number_track"]
        self.assertEqual([(b["start"], b["end"]) for b in hops], [(9, 12), (20, 17), (12, 9)])
        one = load_lesson(P1 / "P1-NUM-01.yaml")
        recap = next(beat for beat in one["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap), 4)
        self.assertEqual(count_event(recap), (0, 5))
        self.assertEqual(labels_for(recap, "en")["title"], "Count carefully")
        self.assertEqual(labels_for(recap, "zh")["title"], "逐个数清楚")
        self.assertEqual(labels_for(recap, "zh_hk")["title"], "逐個數清楚")
        self.assertEqual(
            labels_for(recap, "en")["lines"],
            [
                "Touch each one once. One, two, three, four, five.",
                "The last number tells how many. Five.",
                "Move them around. Still five.",
                "Nothing there? That is zero.",
            ],
        )
        self.assertEqual(
            labels_for(recap, "zh_hk")["lines"][0],
            "每個只係指一次。一，二，三，四，五。",
        )
        kept = next(beat for beat in two["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(kept), 4)
        self.assertEqual(count_event(kept), (3, 3))
        self.assertEqual(kept["title_en"], "Find the ten first")
        self.assertEqual(kept["title_zh"], "先找十")
        self.assertEqual(kept["title_zh_hk"], "先搵十")
        self.assertEqual(
            labels_for(kept, "en")["lines"],
            [
                "One full frame is one ten.",
                "Ten and three more make thirteen.",
                "Two full frames make twenty.",
                "Find the ten first. Then count the rest.",
            ],
        )
        self.assertEqual(labels_for(kept, "zh_hk")["lines"][3], "先搵十，再數剩低嘅。")
        three = load_lesson(P1 / "P1-NUM-03.yaml")
        still3 = next(beat for beat in three["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(still3), 3)
        self.assertEqual(still3["s1_en"], "Count on means one more each time.")

    def test_track_stays_one_row_in_landscape_and_snakes_in_portrait(self):
        self.assertEqual(track_columns(21, 1920, 1080), 21)
        self.assertLess(track_columns(21, 1080, 1920), 21)
        self.assertGreaterEqual(track_columns(21, 1080, 1920), 4)

    def test_count_marks_follow_the_spoken_numbers(self):
        words = [
            {"text": "Start", "start": 0.05},
            {"text": "nine", "start": 0.62},
            {"text": "one", "start": 3.01},
            {"text": "Nine", "start": 4.237},
            {"text": "Ten", "start": 5.612},
            {"text": "Eleven", "start": 7.0},
            {"text": "Twelve", "start": 8.588},
            {"text": "Twelve", "start": 10.062},
        ]
        marks = count_marks(words, 4.24, 5.82, 4)
        self.assertIsNotNone(marks)
        self.assertAlmostEqual(marks[0], 0.0, places=2)
        self.assertAlmostEqual(marks[1], 5.612 - 4.24, places=2)
        self.assertAlmostEqual(marks[2], 7.0 - 4.24, places=2)
        self.assertAlmostEqual(marks[3], 8.588 - 4.24, places=2)
        beat = {
            "visual": "animated",
            "scene": "number_track",
            "low": 0,
            "high": 20,
            "start": 9,
            "end": 12,
        }
        scheduled = schedule_marks(beat, [4.24, 5.82, 4.31], words)
        self.assertEqual(scheduled[0], [])
        self.assertEqual(len(scheduled[1]), 4)
        # Not enough words for a 1..13 count: leave the step evenly spaced.
        few = count_marks(words, 0.0, 4.0, 13)
        self.assertIsNone(few)

    def test_xiao_yi_kicker_is_two_separated_marks(self):
        from PIL import Image, ImageDraw

        from slides import _paint_title_kicker

        image = Image.new("RGB", (1920, 200), (247, 244, 238))
        _paint_title_kicker(ImageDraw.Draw(image), "小一", 32, 30, (92, 107, 122))
        pix = image.load()
        cols = []
        for x in range(image.width):
            ink = any(pix[x, y][0] < 180 for y in range(image.height))
            cols.append(ink)
        runs = []
        on = False
        for x, ink in enumerate(cols):
            if ink and not on:
                start = x
                on = True
            elif on and not ink:
                runs.append((start, x - 1))
                on = False
        if on:
            runs.append((start, len(cols) - 1))
        # 小's own strokes leave a narrow hole. Merge those, and keep the gap before 一.
        merged = [runs[0]]
        for start, end in runs[1:]:
            if start - merged[-1][1] <= 10:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        self.assertEqual(len(merged), 2, runs)
        gap = merged[1][0] - merged[0][1] - 1
        self.assertGreaterEqual(gap, 12, merged)


if __name__ == "__main__":
    unittest.main()
