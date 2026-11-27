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
from scene_registry import (
    REGISTRY,
    DEFAULT_TRACK_CUES,
    count_event,
    count_marks,
    crosses_ten,
    labels_for,
    messy_spots,
    ordinal_visits,
    scene_problems,
    removal_marks,
    schedule_marks,
    step_count,
    takeaway_cue_picture,
    ordinal_columns,
    group_columns,
    track_columns,
    track_slots,
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


def _label_row_centres(path, clearance: int = 6) -> list[list[float]]:
    """Vertical ink centre of each count label, grouped by the row it sits on.

    The centre is the middle of the ink, so a thin 一 is measured the same way as 三.
    """
    from PIL import Image

    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()

    def dark(x, y):
        r, g, b = px[x, y]
        return r < 90 and g < 110 and b < 130 and (r + g + b) < 280

    def green(x, y):
        r, g, b = px[x, y]
        return g > 120 and g > r + 40 and g > b + 20

    rows = []
    y = 0
    while y < h:
        if sum(1 for x in range(0, w, 3) if green(x, y)) < 4:
            y += 1
            continue
        y0 = y
        while y < h and sum(1 for x in range(0, w, 3) if green(x, y)) >= 3:
            y += 1
        rows.append((y0, y - 1))
        y += 1
    centres = []
    # The labels sit in the gap above each counter row. Stop at the previous
    # row so its outline is not read as another numeral.
    window = max(24, int(46 * h / 720))
    prev_bottom = 0
    for y0, y1 in rows:
        band_bot = max(0, y0 - clearance)
        band_top = max(prev_bottom + 3, y0 - window)
        prev_bottom = y1
        if band_bot <= band_top:
            continue
        runs = []
        x = 0
        while x < w:
            if not any(dark(x, yy) for yy in range(band_top, band_bot + 1)):
                x += 1
                continue
            x0 = x
            while x < w and any(dark(x, yy) for yy in range(band_top, band_bot + 1)):
                x += 1
            runs.append((x0, x - 1))
        merged = []
        for run in runs:
            # One glyph can be two strokes with a gap, as in 八.
            if merged and run[0] - merged[-1][1] <= 16:
                merged[-1] = (merged[-1][0], run[1])
            else:
                merged.append(run)
        row = []
        for x0, x1 in merged:
            ys = [
                yy for yy in range(band_top, band_bot + 1)
                for xx in range(x0, x1 + 1)
                if dark(xx, yy)
            ]
            if len(ys) < 8:
                continue
            row.append((min(ys) + max(ys)) / 2.0)
        if len(row) >= 2:
            centres.append(row)
    return centres


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

    def test_ordinal_box_moves_with_the_spoken_place(self):
        import subprocess
        import tempfile

        from anim import render_animated_clip

        beat = {
            "id": "from-left",
            "visual": "animated",
            "scene": "ordinal_row",
            "mode": "ordinal",
            "direction": "left",
            "n": 6,
            "mark": 3,
            "s1_en": "Start at the left.",
            "s2_en": "First. Second. Third.",
            "s3_en": "The star is third.",
            "s1_zh": "从左边数。",
            "s2_zh": "第一，第二，第三。",
            "s3_zh": "星星是第三。",
        }
        words = [
            {"text": "Start", "start": 0.1, "end": 0.4},
            {"text": "First", "start": 1.15, "end": 1.5},
            {"text": "Second", "start": 1.85, "end": 2.2},
            {"text": "Third", "start": 2.55, "end": 2.9},
            {"text": "The", "start": 3.4, "end": 3.6},
        ]
        with tempfile.TemporaryDirectory(prefix="vf-ord-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            subprocess.check_call(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", "5", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            dest = root / "ord.mp4"
            render_animated_clip(
                beat, {}, label_lang_code="en",
                holds=[0.8, 2.4, 1.0], still_idx=[0, 1, 2],
                pages=["Start at the left.", "First. Second. Third.", "The star is third."],
                audio=audio, dest=dest, cache_dir=root / "cache",
                captions=False, progress_bar=False, frame=(640, 360), fps=10,
                words=words,
            )
            silent = next((root / "cache" / "en").glob("from-left-*.mp4"))
            xs = []
            for n, t in enumerate((1.2, 1.9, 2.6)):
                shot = root / f"ord-{n}.png"
                subprocess.check_call(
                    ["ffmpeg", "-y", "-i", str(silent), "-vf", f"select=eq(n\\,{int(t * 10)})",
                     "-frames:v", "1", str(shot)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                xs.append(self._gold_x(shot))
            self.assertTrue(all(xs[i] < xs[i + 1] - 2 for i in range(2)), xs)
            back = dict(beat, id="from-right", direction="right")
            back["s2_en"] = "First. Second. Third. Fourth."
            back_words = [
                {"text": "Now", "start": 0.1, "end": 0.3},
                {"text": "First", "start": 1.1, "end": 1.3},
                {"text": "Second", "start": 1.6, "end": 1.8},
                {"text": "Third", "start": 2.1, "end": 2.3},
                {"text": "Fourth", "start": 2.6, "end": 2.8},
                {"text": "Same", "start": 3.4, "end": 3.6},
            ]
            dest2 = root / "back.mp4"
            render_animated_clip(
                back, {}, label_lang_code="en",
                holds=[0.8, 2.6, 1.0], still_idx=[0, 1, 2],
                pages=["Now.", "First. Second. Third. Fourth.", "Fourth."],
                audio=audio, dest=dest2, cache_dir=root / "cache",
                captions=False, progress_bar=False, frame=(640, 360), fps=10,
                words=back_words,
            )
            silent2 = next((root / "cache" / "en").glob("from-right-*.mp4"))
            back_xs = []
            for n, t in enumerate((1.15, 1.65, 2.15, 2.65)):
                shot = root / f"back-{n}.png"
                subprocess.check_call(
                    ["ffmpeg", "-y", "-i", str(silent2), "-vf", f"select=eq(n\\,{int(t * 10)})",
                     "-frames:v", "1", str(shot)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                back_xs.append(self._gold_x(shot))
            self.assertTrue(all(back_xs[i] > back_xs[i + 1] + 2 for i in range(3)), back_xs)

    def test_ordinal_labels_and_hook_read_at_phone_size(self):
        """Count labels clear the pixel floor, the hook row is about twice as tall, and takeaway rows share a left edge."""
        import subprocess
        import tempfile

        from PIL import Image

        from anim import render_animated_clip

        how = {
            "id": "how-many",
            "visual": "animated",
            "scene": "ordinal_row",
            "mode": "total",
            "direction": "left",
            "n": 6,
            "mark": 3,
            "s1_zh": "六个图案排成一行。",
            "s2_zh": "一，二，三，四，五，六。",
            "s3_zh": "六个。",
        }
        hook = {
            "id": "hook",
            "visual": "animated",
            "scene": "lesson_hook",
            "motif": "ordinal",
            "n": 6,
            "mark": 3,
            "title_en": "Which place? How many?",
            "s1_en": "Which place is the star?",
        }
        takeaway = {
            "id": "takeaway",
            "visual": "animated",
            "scene": "lesson_takeaway",
            "motif": "ordinal",
            "n": 6,
            "mark": 3,
            "title_zh": "从哪头数？",
            "s1_en": "How many stays six.",
            "s2_en": "From the left, the star is third.",
            "s3_en": "From the right, the same star is fourth.",
            "s4_en": "Which place depends on the end you start from.",
            "s1_zh": "有多少个，还是六个。",
            "s2_zh": "从左边数，星星是第三。",
            "s3_zh": "从右边数，同一颗星星是第四。",
            "s4_zh": "第几个，要看从哪一头数。",
        }
        with tempfile.TemporaryDirectory(prefix="vf-ord-size-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            subprocess.check_call(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", "4", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            render_animated_clip(
                how, {"format": "16:9"}, label_lang_code="zh",
                holds=[0.4, 1.6, 0.5], still_idx=[0, 1, 2],
                pages=["六个。", "一，二，三，四，五，六。", "六个。"],
                audio=audio, dest=root / "how.mp4", cache_dir=root / "cache",
                captions=False, progress_bar=False, frame=(1280, 720), fps=8,
            )
            how_png = root / "how.png"
            subprocess.check_call(
                ["ffmpeg", "-y", "-i", str(next((root / "cache" / "zh").glob("how-many-*.mp4"))),
                 "-vf", "select=eq(n\\,14)", "-frames:v", "1", str(how_png)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            # 48px at 1080p, scaled to 720. The old cap sat near 25px.
            self.assertGreaterEqual(self._label_band_height(how_png), 48 * 720 / 1080 * 0.9)
            for row in _label_row_centres(how_png):
                self.assertGreaterEqual(len(row), 2, how_png.name)
                self.assertLessEqual(max(row) - min(row), 1.0, f"how-many centres {row}")

            render_animated_clip(
                hook, {"format": "16:9"}, label_lang_code="en",
                holds=[1.2], still_idx=[0], pages=["Which place is the star?"],
                audio=audio, dest=root / "hook.mp4", cache_dir=root / "cache",
                captions=False, progress_bar=False, frame=(1280, 720), fps=8,
            )
            hook_png = root / "hook.png"
            subprocess.check_call(
                ["ffmpeg", "-y", "-i", str(next((root / "cache" / "en").glob("hook-*.mp4"))),
                 "-vf", "select=eq(n\\,8)", "-frames:v", "1", str(hook_png)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            # The old hook row was about 40px tall at 1280x720. Twice that is 80.
            self.assertGreaterEqual(self._token_box_height(hook_png), 70)

            render_animated_clip(
                takeaway, {"format": "16:9"}, label_lang_code="zh",
                holds=[0.3, 0.3, 0.3, 0.5], still_idx=[0, 1, 2, 3],
                pages=["a", "b", "c", "d"],
                audio=audio, dest=root / "take.mp4", cache_dir=root / "cache",
                captions=False, progress_bar=False, frame=(1280, 720), fps=8,
            )
            take_png = root / "take.png"
            duration = float(subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(root / "take.mp4")],
                text=True,
            ))
            last = max(0, int(duration * 8) - 1)
            subprocess.check_call(
                ["ffmpeg", "-y", "-i", str(root / "take.mp4"),
                 "-vf", f"select=eq(n\\,{last})", "-frames:v", "1", str(take_png)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            lefts, heights = self._token_row_edges(take_png)
            self.assertEqual(len(lefts), 4, lefts)
            self.assertLessEqual(max(lefts) - min(lefts), 4, lefts)
            self.assertLessEqual(max(heights) - min(heights), 8, heights)

    def test_ordinal_labels_keep_a_gap(self):
        """Adjacent place labels stay at least 12px apart, in every language and aspect."""
        import subprocess
        import tempfile

        from anim import render_animated_clip

        speech = {
            "en": ("Start at the left.", "First. Second. Third.", "The star is third.",
                   "First. Second. Third. Fourth."),
            "zh": ("从左边数。", "第一，第二，第三。", "星星是第三。", "第一，第二，第三，第四。"),
            "zh_hk": ("由左邊數。", "第一，第二，第三。", "星星係第三。", "第一，第二，第三，第四。"),
        }
        frames = ((1280, 720), (720, 1280))
        with tempfile.TemporaryDirectory(prefix="vf-ord-gap-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            subprocess.check_call(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", "4", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            for lang, lines in speech.items():
                for direction, spoken in (("left", lines[1]), ("right", lines[3])):
                    beat = {
                        "id": f"from-{direction}",
                        "visual": "animated",
                        "scene": "ordinal_row",
                        "mode": "ordinal",
                        "direction": direction,
                        "n": 6,
                        "mark": 3,
                        "s1_en": lines[0], "s2_en": spoken, "s3_en": lines[2],
                        "s1_zh": lines[0], "s2_zh": spoken, "s3_zh": lines[2],
                        "s1_zh_hk": lines[0], "s2_zh_hk": spoken, "s3_zh_hk": lines[2],
                    }
                    for frame in frames:
                        dest = root / f"{lang}-{direction}-{frame[0]}.mp4"
                        render_animated_clip(
                            beat, {"format": "9:16" if frame[1] > frame[0] else "16:9"},
                            label_lang_code=lang,
                            holds=[0.4, 1.6, 0.6], still_idx=[0, 1, 2],
                            pages=["a", "b", "c"],
                            audio=audio, dest=dest, cache_dir=root / "cache",
                            captions=False, progress_bar=False, frame=frame, fps=8,
                        )
                        silent = max((root / "cache" / lang).glob(f"from-{direction}-*.mp4"), key=lambda p: p.stat().st_mtime)
                        shot = root / f"{lang}-{direction}-{frame[0]}.png"
                        duration = float(subprocess.check_output(
                            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "csv=p=0", str(silent)],
                            text=True,
                        ))
                        last = max(0, int(duration * 8) - 1)
                        subprocess.check_call(
                            ["ffmpeg", "-y", "-i", str(silent),
                             "-vf", f"select=eq(n\\,{last})", "-frames:v", "1", str(shot)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        )
                        gaps = self._ordinal_label_gaps(shot)
                        portrait = frame[1] > frame[0]
                        need = 12.0 * frame[0] / (1080.0 if portrait else 1920.0)
                        self.assertGreaterEqual(len(gaps), 2, f"{shot.name} {gaps}")
                        self.assertTrue(
                            all(gap + 0.5 >= need for gap in gaps),
                            f"{shot.name} gaps {gaps} need {need:.1f}",
                        )

    def _ordinal_label_gaps(self, path) -> list[float]:
        """Pixel gaps between adjacent place labels sitting above the token row."""
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()

        def white_runs(y, min_w):
            runs = []
            x = 0
            while x < w:
                r, g, b = px[x, y]
                if r > 245 and g > 245 and b > 245:
                    x1 = x
                    while x1 + 1 < w and px[x1 + 1, y][0] > 245 and px[x1 + 1, y][1] > 245 and px[x1 + 1, y][2] > 245:
                        x1 += 1
                    if x1 - x >= min_w:
                        runs.append((x, x1))
                    x = x1 + 1
                else:
                    x += 1
            return runs

        candidates = []
        for y in range(int(h * 0.12), int(h * 0.8)):
            runs = white_runs(y, max(8, w // 90))
            # Six tokens. A dot can split one box into two runs, so ignore those rows.
            if not 4 <= len(runs) <= 8:
                continue
            widths = [b - a for a, b in runs]
            centres_y = [(a + b) / 2.0 for a, b in runs]
            pitches = [centres_y[i + 1] - centres_y[i] for i in range(len(centres_y) - 1)]
            if min(pitches) <= 0 or max(pitches) / min(pitches) > 1.2:
                continue
            if max(widths) / max(1, min(widths)) > 1.35:
                continue
            if min(widths) < min(pitches) * 0.45:
                continue
            below = white_runs(min(h - 1, y + 3), max(8, w // 90))
            if not 4 <= len(below) <= 8:
                continue
            candidates.append((min(widths), y, runs))
        self.assertTrue(candidates, path.name)
        widest = max(item[0] for item in candidates)
        # The top edge of the tokens: wide runs, and the highest such row.
        _width, box_top, boxes = min(
            (item for item in candidates if item[0] >= widest * 0.9),
            key=lambda item: item[1],
        )
        centres = [(a + b) / 2.0 for a, b in boxes]
        pitch = centres[1] - centres[0]

        def dark(x, y):
            r, g, b = px[x, y]
            return r < 80 and g < 90 and b < 120 and max(r, g, b) > 12

        rows = []
        for y in range(box_top - 8, max(0, box_top - int(pitch * 1.6)), -1):
            if any(dark(x, y) for x in range(0, w, 2)):
                rows.append(y)
        self.assertTrue(rows, path.name)
        # The place labels are the first tall dark band above the tokens. The
        # box stroke is only a few pixels, and the title sits higher.
        bands = []
        start = prev = rows[0]
        for y in rows[1:]:
            if prev - y > 6:
                bands.append((min(start, prev), max(start, prev)))
                start = y
            prev = y
        bands.append((min(start, prev), max(start, prev)))
        tall = [band for band in bands if band[1] - band[0] >= 8]
        self.assertTrue(tall, bands)
        label_lo, label_hi = tall[0]
        spans = []
        for centre in centres:
            xs = [
                x for y in range(label_lo, label_hi + 1)
                for x in range(max(0, int(centre - pitch * 0.49)), min(w, int(centre + pitch * 0.49)))
                if dark(x, y)
            ]
            spans.append((min(xs), max(xs)) if xs else None)
        gaps = []
        for i in range(len(spans) - 1):
            if spans[i] is None or spans[i + 1] is None:
                continue
            gaps.append(spans[i + 1][0] - spans[i][1])
        return gaps

    def _label_band_height(self, path) -> int:
        """Height of the dark text band that sits above the token row."""
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()
        rows = []
        for y in range(int(h * 0.2), int(h * 0.75)):
            dark = 0
            for x in range(w):
                r, g, b = px[x, y]
                if r < 70 and g < 80 and b < 110 and max(r, g, b) > 15:
                    dark += 1
            if dark > 12:
                rows.append(y)
        self.assertTrue(rows, path.name)
        # Split into bands and take the one just above the boxes (not the title).
        bands = []
        start = prev = rows[0]
        for y in rows[1:]:
            if y - prev > 4:
                bands.append((start, prev))
                start = y
            prev = y
        bands.append((start, prev))
        tall = [b for b in bands if b[1] - b[0] >= 8]
        self.assertGreaterEqual(len(tall), 1, bands)
        # The labels are the band closest above the token boxes, so the lower one
        # when a title is also in range. A lone count line is the only band.
        label = tall[-1] if len(tall) > 1 else tall[0]
        return label[1] - label[0] + 1

    def _token_box_height(self, path) -> int:
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()
        rows = []
        for y in range(h):
            boxes = 0
            for x in range(w):
                r, g, b = px[x, y]
                if r > 245 and g > 245 and b > 245:
                    boxes += 1
            if boxes > 30:
                rows.append(y)
        self.assertTrue(rows, path.name)
        start = prev = rows[0]
        best = (rows[0], rows[0])
        for y in rows[1:]:
            if y - prev > 3:
                if prev - start > best[1] - best[0]:
                    best = (start, prev)
                start = y
            prev = y
        if prev - start > best[1] - best[0]:
            best = (start, prev)
        return best[1] - best[0] + 1

    def _token_row_edges(self, path):
        """Left edge and height of each token row, from the white boxes."""
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()
        bands = []
        y = 0
        while y < h:
            xs = [
                x for x in range(w)
                if px[x, y][0] > 245 and px[x, y][1] > 245 and px[x, y][2] > 245
            ]
            if len(xs) > 20:
                y1 = y
                acc = list(xs)
                while y1 + 1 < h:
                    nxt = [
                        x for x in range(w)
                        if px[x, y1 + 1][0] > 245 and px[x, y1 + 1][1] > 245 and px[x, y1 + 1][2] > 245
                    ]
                    if len(nxt) < 20:
                        break
                    y1 += 1
                    acc.extend(nxt)
                if y1 - y > 8:
                    bands.append((min(acc), y1 - y + 1))
                y = y1 + 1
            else:
                y += 1
        lefts = [left for left, _ in bands]
        heights = [height for _, height in bands]
        return lefts, heights

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
        ordinal = {
            "id": "takeaway",
            "visual": "animated",
            "scene": "lesson_takeaway",
            "motif": "ordinal",
            "n": 6,
            "mark": 3,
            "title_en": "Which end?",
            "s1_en": "How many stays six.",
            "s2_en": "From the left, the star is third.",
            "s3_en": "From the right, the same star is fourth.",
            "s4_en": "Which place depends on the end you start from.",
            "title_zh": "从哪头数？",
            "s1_zh": "有多少个，还是六个。",
            "s2_zh": "从左边数，星星是第三。",
            "s3_zh": "从右边数，同一颗星星是第四。",
            "s4_zh": "第几个，要看从哪一头数。",
            "title_zh_hk": "由邊頭數？",
            "s1_zh_hk": "有幾多個，都係六個。",
            "s2_zh_hk": "由左邊數，星星係第三。",
            "s3_zh_hk": "由右邊數，同一粒星星係第四。",
            "s4_zh_hk": "第幾個，要睇由邊一頭數。",
        }
        pairs = {
            "id": "takeaway",
            "visual": "animated",
            "scene": "lesson_takeaway",
            "motif": "pairs",
            "n": 8,
            "also": 19,
            "title_en": "Even or odd?",
            "s1_en": "Eight makes four pairs. Eight is even.",
            "s2_en": "Nine leaves one. Nine is odd.",
            "s3_en": "A pair holds two, not three.",
            "s4_en": "Nineteen makes nine pairs, one left.",
            "title_zh": "单数还是双数？",
            "s1_zh": "八个配成四对，八是双数。",
            "s2_zh": "九个剩下一个，九是单数。",
            "s3_zh": "一对只放两个，不放三个。",
            "s4_zh": "十九个配成九对，单独剩一个。",
            "title_zh_hk": "單數定雙數？",
            "s1_zh_hk": "八個配成四對，八係雙數。",
            "s2_zh_hk": "九個剩低一個，九係單數。",
            "s3_zh_hk": "一對只放兩個，唔放三個。",
            "s4_zh_hk": "十九個配成九對，單獨剩一個。",
        }
        cards = (
            ("ten", beat, 4),
            ("count", counted, 4),
            ("track", track, 3),
            ("ordinal", ordinal, 4),
            ("pairs", pairs, 4),
        )

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

        from anim import TAKEAWAY_COLUMN_GAP_PX, takeaway_grid

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

        if not grid["portrait"]:
            # The picture, including a 13 or a 20, stays about 40px (at 1080p) clear of the text column.
            # Measure the first ink run that begins in the picture column, so the sentence itself does not count.
            need = TAKEAWAY_COLUMN_GAP_PX * h / 1080.0 - 2
            text_edge = int(px_of(grid["text_left"]))
            visual_right = left
            for y in range(max(0, cell_px[0][0]), min(h, cell_px[-1][1]), 2):
                seen = False
                last = None
                for x in range(max(0, left), min(w, text_edge + 40)):
                    if ink(x, y):
                        if not seen and x >= text_edge - 4:
                            break
                        seen = True
                        last = x
                    elif seen and last is not None and x > last + 6:
                        break
                if last is not None:
                    visual_right = max(visual_right, last)
            self.assertGreaterEqual(
                text_edge - visual_right, need,
                f"{path.name} column gap {text_edge - visual_right:.0f} vs {need:.0f}",
            )
        else:
            # Wrapped lines are centred, and the row block sits in the middle of the safe band.
            centre = w / 2.0
            for cell_top, cell_bottom in cell_px:
                zone = cell_top + int(0.58 * (cell_bottom - cell_top))
                rows_y = [
                    y for y in range(max(0, zone), min(h, cell_bottom))
                    if sum(1 for x in range(left, right, 3) if ink(x, y)) > 2
                ]
                start = prev = None
                for y in rows_y:
                    if start is None:
                        start = prev = y
                    elif y - prev > 4:
                        xs = [x for x in range(left, right) if any(ink(x, yy) for yy in range(start, prev + 1))]
                        if xs:
                            mid = (min(xs) + max(xs)) / 2.0
                            self.assertLess(abs(mid - centre), w * 0.08, f"{path.name} line at {start} mid {mid:.0f}")
                        start = prev = y
                    else:
                        prev = y
                if start is not None and prev is not None:
                    xs = [x for x in range(left, right) if any(ink(x, yy) for yy in range(start, prev + 1))]
                    if xs:
                        mid = (min(xs) + max(xs)) / 2.0
                        self.assertLess(abs(mid - centre), w * 0.08, f"{path.name} line at {start} mid {mid:.0f}")
            content = [
                y for y in range(max(0, cell_px[0][0]), min(h, cell_px[-1][1]))
                if sum(1 for x in range(left, right, 4) if ink(x, y)) > 2
            ]
            self.assertTrue(content, path.name)
            above = content[0] - cell_px[0][0]
            below = cell_px[-1][1] - content[-1]
            band = cell_px[-1][1] - cell_px[0][0]
            self.assertLess(abs(above - below), max(16, int(band * 0.12)), f"{path.name} above {above} below {below}")

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
                "ordinal_row", "pair_counters", "part_whole", "number_blocks",
                "estimate_group", "row_match", "place_sum",
                "shape_line", "flat_shape", "shape_join", "solid_shape",
                "lesson_hook", "lesson_takeaway",
            ],
        )
        self.assertEqual(REGISTRY["one_ten"].steps, 4)
        self.assertEqual(REGISTRY["count_objects"].steps, 3)
        self.assertEqual(REGISTRY["number_track"].steps, 3)
        self.assertEqual(scene_problems({"visual": "title_card", "scene": "nope"}), [])

    def test_number_blocks_bounds(self):
        def beat(**extra):
            row = {
                "visual": "animated",
                "scene": "number_blocks",
                "s1_en": "Tens.",
                "s2_en": "Ones.",
                "s3_en": "The number.",
                "s1_zh": "十。",
                "s2_zh": "个。",
                "s3_zh": "这个数。",
                "s1_zh_hk": "十。",
                "s2_zh_hk": "個。",
                "s3_zh_hk": "呢個數。",
            }
            row.update(extra)
            return row

        tens = beat(mode="tens", count=24)
        self.assertEqual(scene_problems(tens), [])
        self.assertEqual(count_event(tens), (0, 2))
        self.assertEqual(count_event(beat(mode="tens", count=40)), (0, 4))
        self.assertEqual(count_event(beat(mode="tens", count=100)), (0, 10))
        self.assertEqual(labels_for(tens, "zh")["title"], "十和个")
        self.assertEqual(labels_for(tens, "zh_hk")["title"], "十同個")
        self.assertTrue(scene_problems(beat(mode="tens", count=101)))
        compared = beat(mode="compare", a=24, b=42)
        self.assertEqual(scene_problems(compared), [])
        self.assertIsNone(count_event(compared))
        self.assertTrue(scene_problems(beat(mode="compare", a=24, b=24)))
        ordered = beat(mode="order", a=24, b=40, n=42)
        self.assertEqual(scene_problems(ordered), [])
        self.assertEqual(labels_for(ordered, "en")["values"], [24, 40, 42])
        self.assertTrue(scene_problems(beat(mode="order", a=24)))
        hop = beat(mode="hop", start=38, end=41)
        self.assertEqual(scene_problems(hop), [])
        self.assertEqual(count_event(hop), (1, 4))
        self.assertEqual(count_event(beat(mode="hop", start=41, end=38)), (1, 4))
        self.assertTrue(scene_problems(beat(mode="hop", start=38, end=50)))
        groups = beat(mode="groups", a=2, n=4)
        self.assertEqual(scene_problems(groups), [])
        self.assertEqual(count_event(groups), (1, 4))
        self.assertEqual(labels_for(groups, "en")["extra"], 0)
        loose = beat(mode="groups", a=2, n=5, b=1)
        self.assertEqual(scene_problems(loose), [])
        self.assertEqual(labels_for(loose, "zh_hk")["title"], "一組一組數")
        self.assertTrue(scene_problems(beat(mode="groups", a=2, n=6, b=2)))
        self.assertTrue(scene_problems(beat(mode="nope")))

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

    def test_takeaway_cues_do_not_fall_back_to_the_default_track(self):
        """A named line picture is never the track placeholder, and an unknown one is an error."""
        self.assertEqual(DEFAULT_TRACK_CUES[0], (9, 10, 11, 12))
        self.assertEqual(DEFAULT_TRACK_CUES[2], DEFAULT_TRACK_CUES[3])
        pictures = [
            takeaway_cue_picture({"kind": "tens", "count": 24}),
            takeaway_cue_picture({"kind": "compare", "a": 24, "b": 42}),
            takeaway_cue_picture({"kind": "tens_mark", "rods": 4}),
            takeaway_cue_picture({"kind": "tiles", "values": [39, 40]}),
            takeaway_cue_picture({"kind": "pairs", "n": 5, "extra": 1}),
            takeaway_cue_picture({"kind": "counters", "n": 12}),
        ]
        self.assertEqual(pictures[0], ("tens", 2, 4))
        self.assertEqual(pictures[1], ("compare", 24, 42, 42))
        for picture in pictures:
            self.assertIsNotNone(picture)
            self.assertNotIn(picture, DEFAULT_TRACK_CUES)
            if picture[0] == "tiles":
                self.assertNotIn(picture[1], DEFAULT_TRACK_CUES)
        self.assertIsNone(takeaway_cue_picture({"kind": "track"}))
        self.assertIsNone(takeaway_cue_picture({"kind": "placeholder"}))
        plain = {
            "visual": "animated",
            "scene": "lesson_takeaway",
            "motif": "track",
            "s1_en": "One.",
            "s2_en": "Two.",
            "s3_en": "Three.",
            "s4_en": "Four.",
            "s1_zh": "一。",
            "s2_zh": "二。",
            "s3_zh": "三。",
            "s4_zh": "四。",
            "s1_zh_hk": "一。",
            "s2_zh_hk": "二。",
            "s3_zh_hk": "三。",
            "s4_zh_hk": "四。",
        }
        self.assertEqual(scene_problems(plain), [])
        self.assertNotIn("cues", labels_for(plain, "en"))
        bad = dict(plain, cues=[{"kind": "placeholder"}, {"kind": "tens", "count": 24}, {"kind": "tens", "count": 40}, {"kind": "tens", "count": 4}])
        messages = scene_problems(bad)
        self.assertTrue(any("must not fall back to the default track" in msg for msg in messages))
        self.assertNotIn("cues", labels_for(bad, "en"))

    def test_estimate_group_renders_the_pile_and_keeps_the_number_large(self):
        """The ten leaves the pile, and 23 stays at the shared label floor."""
        try:
            require_manim()
        except ManimNotInstalled:
            self.skipTest("Manim is optional")
        from manim import tempconfig

        from anim import _make_scene, prepare_fonts

        prepare_fonts()

        def spec(part):
            return {
                "scene": "estimate_group",
                "lang": "en",
                "part": part,
                "labels": {
                    "title": "About how many?",
                    "count": 23,
                    "tens": 2,
                    "ones": 3,
                    "guess": 20,
                    "part": part,
                },
            }

        def inside(dot, frame):
            x, y = float(dot.get_center()[0]), float(dot.get_center()[1])
            return (
                float(frame.get_left()[0]) - 0.05 <= x <= float(frame.get_right()[0]) + 0.05
                and float(frame.get_bottom()[1]) - 0.05 <= y <= float(frame.get_top()[1]) + 0.05
            )

        with tempconfig({
            "pixel_width": 1920,
            "pixel_height": 1080,
            "frame_width": 8.0 * 16 / 9,
            "frame_height": 8.0,
            "frame_rate": 15,
            "disable_caching": True,
            "preview": False,
        }):
            pile = _make_scene(spec("pile"), [0.6], [[]])
            pile.render(preview=False)
            unit = 1080 / 8.0
            self.assertGreaterEqual(float(pile.vf_title.height) * unit, 47)
            self.assertGreaterEqual(float(pile.vf_title.get_fill_opacity()), 0.9)
            self.assertLess(float(pile.vf_frame.get_fill_opacity()), 0.05)
            ten = _make_scene(spec("ten"), [1.0], [[]])
            ten.render(preview=False)
            filled = [dot for dot in ten.vf_dots if inside(dot, ten.vf_frame)]
            self.assertEqual(len(filled), 10)
            for dot in ten.vf_dots:
                if dot in filled:
                    continue
                self.assertGreater(
                    float(dot.get_center()[0]),
                    float(ten.vf_frame.get_right()[0]) + 0.15,
                )
            count = _make_scene(spec("count"), [2.4], [[]])
            count.render(preview=False)
            self.assertGreaterEqual(float(count.vf_answer.height) * unit, 47)
            self.assertGreaterEqual(float(count.vf_answer.get_fill_opacity()), 0.9)
            self.assertEqual(len([dot for dot in count.vf_dots if inside(dot, count.vf_frame)]), 10)
            self.assertEqual(len([dot for dot in count.vf_dots if inside(dot, count.vf_frame2)]), 10)

    def test_groups_takeaway_picture_draws_each_counter(self):
        """A groups cue draws one counter per place, and skips when Manim is missing."""
        try:
            require_manim()
        except ManimNotInstalled:
            self.skipTest("Manim is optional")
        from manim import tempconfig

        from anim import _make_scene, prepare_fonts

        prepare_fonts()
        with tempconfig({"pixel_width": 1920, "pixel_height": 1080, "frame_width": 8 * 16 / 9, "frame_height": 8}):
            scene = _make_scene(
                {"scene": "lesson_takeaway", "lang": "en", "labels": {"title": "Groups", "lines": ["a"]}},
                [0.4],
            )
            group = scene._line_cue(("groups", 5, 4, 0), "Latin Modern Roman", "Noto Sans CJK SC")
        circles = [mob for mob in group.get_family() if mob.__class__.__name__ == "Circle"]
        self.assertEqual(len(circles), 20)

    def test_takeaway_blocks_share_a_scale_and_comparisons_stay_apart(self):
        """Rods keep one size, a comparison's blocks match the number, and the ring clears both digits."""
        try:
            require_manim()
        except ManimNotInstalled:
            self.skipTest("Manim is optional")
        from manim import Text, tempconfig

        from anim import _scene_types, cjk_family, latin_family, prepare_fonts

        prepare_fonts()
        cls = _scene_types()["lesson_takeaway"]

        def content_edges(card):
            mobs = [card.vf_number, card.vf_bundles]
            return (
                min(mob.get_left()[0] for mob in mobs),
                max(mob.get_right()[0] for mob in mobs),
                min(mob.get_bottom()[1] for mob in mobs),
                max(mob.get_top()[1] for mob in mobs),
            )

        def lay_out(pictures, w, h):
            lines = ["Line one.", "Line two.", "Line three.", "Line four."]
            with tempconfig({
                "pixel_width": w,
                "pixel_height": h,
                "frame_width": 8.0 * w / h,
                "frame_height": 8.0,
                "frame_rate": 8,
                "disable_caching": True,
                "preview": False,
                "write_to_movie": False,
            }):
                scene = cls()
                scene.vf_fonts = (latin_family(), cjk_family("en"))
                latin, cjk = scene.vf_fonts
                title = Text("Tens and ones", font=latin, font_size=48)
                cues = [scene._line_cue(picture, latin, cjk) for picture in pictures]
                scene._layout_takeaway(title, cues, lines, latin, cjk, fit_heading=True)
            return cues

        tens = lay_out([("tens", 2, 4), ("tens", 4, 0), ("tens", 0, 4), ("tens", 10, 0)], 1920, 1080)
        rod_h = [cue.vf_rods[0].height for cue in tens if cue.vf_rods]
        self.assertEqual(len(rod_h), 3)
        self.assertLess(max(rod_h) - min(rod_h), 1e-6)
        self.assertLess(tens[2].vf_cubes[0].height, rod_h[0] * 0.45)
        self.assertEqual((len(tens[0].vf_rods), len(tens[0].vf_cubes)), (2, 4))
        self.assertEqual(len(tens[1].vf_rods), 4)
        self.assertEqual(len(tens[2].vf_cubes), 4)
        self.assertEqual((len(tens[3].vf_rods), len(tens[3].vf_cubes)), (10, 0))
        self.assertLess(abs(tens[3].vf_rods[0].height - rod_h[0]), 1e-6)
        ten_ys = {round(float(rod.get_center()[1]), 3) for rod in tens[3].vf_rods}
        self.assertEqual(len(ten_ys), 2)
        six = lay_out([("tens", 6, 4), ("tens", 5, 2), ("tens", 2, 4), ("tens", 6, 4)], 1080, 1920)
        six_ys = {round(float(rod.get_center()[1]), 3) for rod in six[0].vf_rods}
        self.assertEqual(len(six_ys), 1)
        self.assertEqual(len(six[0].vf_cubes), 4)
        self.assertTrue(all(float(cube.get_center()[1]) < min(six_ys) for cube in six[0].vf_cubes))

        compared = [
            ("compare", 24, 42, 42),
            ("tens_mark", 24, 42),
            ("compare", 47, 43, 47),
            ("compare", 100, 99, 100),
        ]
        self.assertEqual(takeaway_cue_picture({"kind": "tens_mark", "a": 24, "b": 42}), ("tens_mark", 24, 42))
        for w, h in ((1920, 1080), (1080, 1920)):
            cues = lay_out(compared, w, h)
            for cue, picture in zip(cues, compared):
                left, right = cue.vf_compare_cards
                for card, number in ((left, picture[1]), (right, picture[2])):
                    self.assertEqual(len(card.vf_rods) * 10 + len(card.vf_cubes), number)
                _l0, r0, _b0, _t0 = content_edges(left)
                l1, _r1, _b1, _t1 = content_edges(right)
                self.assertLess(r0, l1)
                gap_px = (l1 - r0) / 8.0 * h
                self.assertGreaterEqual(gap_px, 40.0 * h / 1080.0 - 0.5)
                for card in (left, right):
                    ring = card.vf_highlight
                    if picture[0] == "compare":
                        if card.vf_value != picture[3]:
                            self.assertIsNone(ring)
                            continue
                        self.assertIsNotNone(ring)
                        cl, cr, cb, ct = content_edges(card)
                        self.assertLess(ring.get_left()[0], cl)
                        self.assertGreater(ring.get_right()[0], cr)
                        self.assertGreater(ring.get_top()[1], ct)
                        self.assertLess(ring.get_bottom()[1], cb)
                    else:
                        self.assertIsNotNone(ring)
                        for rod in card.vf_rods:
                            self.assertLessEqual(ring.get_left()[0], rod.get_left()[0] + 1e-6)
                            self.assertGreaterEqual(ring.get_right()[0], rod.get_right()[0] - 1e-6)
                            self.assertGreaterEqual(ring.get_top()[1], rod.get_top()[1] - 1e-6)
                            self.assertLessEqual(ring.get_bottom()[1], rod.get_bottom()[1] + 1e-6)
                        self.assertLess(ring.get_top()[1], card.vf_number.get_bottom()[1])
                        for cube in card.vf_cubes:
                            self.assertLessEqual(ring.get_right()[0], cube.get_left()[0] + 1e-4)


    def test_row_match_rings_the_unmatched_counters(self):
        """The gap rings only the extra counters, and equal rows show 0."""
        try:
            require_manim()
        except ManimNotInstalled:
            self.skipTest("Manim is optional")
        from manim import tempconfig

        from anim import _make_scene, prepare_fonts

        prepare_fonts()

        def spec(part, a, b):
            return {
                "scene": "row_match",
                "lang": "en",
                "a": a,
                "b": b,
                "part": part,
                "labels": {"title": "How many more?", "part": part, "a": a, "b": b},
            }

        with tempconfig({
            "pixel_width": 1920, "pixel_height": 1080,
            "frame_width": 8 * 16 / 9, "frame_height": 8, "frame_rate": 15,
        }):
            gap = _make_scene(spec("gap", 8, 5), [2.4], [[0.2, 0.9, 1.6]])
            gap.render(preview=False)
            unit = 1080 / 8
            self.assertGreaterEqual(float(gap.vf_title.height) * unit, 47)
            self.assertEqual(len(gap.vf_top), 8)
            self.assertEqual(len(gap.vf_bottom), 5)
            self.assertEqual(len(gap.vf_rings), 3)
            self.assertGreaterEqual(float(gap.vf_answer.get_fill_opacity()), 0.9)
            self.assertGreater(float(gap.vf_top.get_bottom()[1]), float(gap.vf_bottom.get_top()[1]))
            same = _make_scene(spec("equal", 6, 6), [1.2], [[]])
            same.render(preview=False)
            self.assertEqual(len(same.vf_rings), 0)
            self.assertEqual(same.vf_answer.text, "0")
            self.assertGreaterEqual(float(same.vf_answer.get_fill_opacity()), 0.9)
        with tempconfig({
            "pixel_width": 1080, "pixel_height": 1920,
            "frame_width": 8, "frame_height": 8 * 16 / 9, "frame_rate": 15,
        }):
            tall = _make_scene(spec("gap", 8, 5), [1.2], [[]])
            tall.render(preview=False)
            unit = 1920 / (8 * 16 / 9)
            self.assertGreaterEqual(float(tall.vf_title.height) * unit, 47)
            self.assertGreater(float(tall.vf_top.get_bottom()[1]), float(tall.vf_bottom.get_top()[1]))

    def test_place_sum_lines_up_ones_and_tens(self):
        """Ones stay in the ones column, and a new ten is a full-size digit."""
        try:
            require_manim()
        except ManimNotInstalled:
            self.skipTest("Manim is optional")
        from manim import tempconfig

        from anim import _make_scene, prepare_fonts

        prepare_fonts()

        def spec(op, values, title):
            return {
                "scene": "place_sum",
                "lang": "en",
                "op": op,
                "values": values,
                "labels": {"title": title, "op": op, "values": values},
            }

        with tempconfig({
            "pixel_width": 1920, "pixel_height": 1080,
            "frame_width": 8 * 16 / 9, "frame_height": 8, "frame_rate": 15,
        }):
            carry = _make_scene(spec("add", [27, 15], "Add the ones"), [0.6, 0.6, 0.6])
            carry.render(preview=False)
            unit = 1080 / 8
            self.assertGreaterEqual(float(carry.vf_title.height) * unit, 47)
            self.assertGreater(float(carry.vf_title.get_bottom()[1]), float(carry.vf_grid.get_top()[1]) - 0.05)
            self.assertEqual(carry.vf_carry.text, "1")
            self.assertGreaterEqual(float(carry.vf_carry.get_fill_opacity()), 0.9)
            self.assertGreaterEqual(float(carry.vf_answer_ones.get_fill_opacity()), 0.9)
            self.assertGreaterEqual(float(carry.vf_answer_tens.get_fill_opacity()), 0.9)
            self.assertEqual(carry.vf_answer_ones.text, "2")
            self.assertEqual(carry.vf_answer_tens.text, "4")
            six = _make_scene(spec("sub", [58, 6], "Take away"), [0.6, 0.6, 0.6])
            six.render(preview=False)
            self.assertNotIn((1, "tens"), six.vf_digits)
            self.assertGreater(
                float(six.vf_digits[(1, "ones")].get_center()[0]),
                float(six.vf_digits[(0, "tens")].get_center()[0]),
            )
            self.assertEqual(six.vf_answer_ones.text, "2")
            self.assertEqual(six.vf_answer_tens.text, "5")
            self.assertIsNone(six.vf_carry)
            trio = _make_scene(spec("add", [18, 7, 5], "Add the ones"), [0.6, 0.6, 0.6])
            trio.render(preview=False)
            self.assertEqual(trio.vf_carry.text, "2")
            self.assertEqual(trio.vf_answer_ones.text, "0")
            self.assertEqual(trio.vf_answer_tens.text, "3")
        with tempconfig({
            "pixel_width": 1080, "pixel_height": 1920,
            "frame_width": 8, "frame_height": 8 * 16 / 9, "frame_rate": 15,
        }):
            tall = _make_scene(spec("add", [18, 7, 5], "Add the ones"), [0.5, 0.5, 0.5])
            tall.render(preview=False)
            unit = 1920 / (8 * 16 / 9)
            self.assertGreaterEqual(float(tall.vf_title.height) * unit, 47)
            self.assertGreater(float(tall.vf_title.get_bottom()[1]), float(tall.vf_grid.get_top()[1]) - 0.05)

    def test_shape_scenes_draw_points_flats_joins_and_solids(self):
        """New shape scenes stay readable, and a circle has no straight sides."""
        try:
            require_manim()
        except ManimNotInstalled:
            self.skipTest("Manim is optional")
        from manim import tempconfig

        from anim import _make_scene, prepare_fonts

        prepare_fonts()

        def line_spec(part, n=3):
            return {
                "scene": "shape_line",
                "lang": "en",
                "part": part,
                "n": n,
                "labels": {
                    "title": "Points and lines",
                    "part": part,
                    "n": n,
                    "straight": "Straight",
                    "curve": "Curved",
                },
            }

        wide = {
            "pixel_width": 1920, "pixel_height": 1080,
            "frame_width": 8 * 16 / 9, "frame_height": 8, "frame_rate": 15,
        }
        with tempconfig(wide):
            marks = _make_scene(line_spec("marks"), [0.6, 0.8, 0.6], [[], [0.1, 0.35, 0.6], []])
            marks.render(preview=False)
            unit = 1080 / 8
            self.assertGreaterEqual(float(marks.vf_title.height) * unit, 47)
            self.assertEqual(len(marks.vf_dots), 3)
            self.assertGreaterEqual(float(marks.vf_count.get_fill_opacity()), 0.9)
            flat = _make_scene({
                "scene": "flat_shape",
                "lang": "en",
                "part": "one",
                "kind": "triangle",
                "labels": {"title": "Three straight sides", "part": "one", "kind": "triangle", "name": "Triangle", "turn": 20},
            }, [0.5, 0.8, 0.5], [[], [0.1, 0.35, 0.6], []])
            flat.render(preview=False)
            self.assertEqual(flat.vf_sides, 3)
            self.assertEqual(len(flat.vf_edges), 3)
            circle = _make_scene({
                "scene": "flat_shape",
                "lang": "en",
                "part": "one",
                "kind": "circle",
                "labels": {"title": "Round", "part": "one", "kind": "circle", "name": "Round", "turn": 0},
            }, [0.4, 0.4, 0.4])
            circle.render(preview=False)
            self.assertEqual(circle.vf_sides, 0)
            joined = _make_scene({
                "scene": "shape_join",
                "lang": "en",
                "result": "quad",
                "labels": {"title": "Put shapes together", "result": "quad"},
            }, [0.4, 0.5, 0.5])
            joined.render(preview=False)
            self.assertEqual(joined.vf_sides, 4)
            self.assertEqual(len(joined.vf_pieces), 2)
            solid = _make_scene({
                "scene": "solid_shape",
                "lang": "en",
                "part": "pair",
                "items": ["prism", "cylinder"],
                "labels": {
                    "title": "A box and a can",
                    "part": "pair",
                    "items": ["prism", "cylinder"],
                    "names": ["Prism", "Cylinder"],
                    "turn": 25,
                },
            }, [0.4, 0.4, 0.4])
            solid.render(preview=False)
            self.assertEqual(solid.vf_kinds, ["prism", "cylinder"])
            self.assertEqual(len(solid.vf_cards), 2)
        with tempconfig({
            "pixel_width": 1080, "pixel_height": 1920,
            "frame_width": 8, "frame_height": 8 * 16 / 9, "frame_rate": 15,
        }):
            tall = _make_scene(line_spec("lines"), [0.4, 0.4, 0.4])
            tall.render(preview=False)
            unit = 1920 / (8 * 16 / 9)
            self.assertGreaterEqual(float(tall.vf_title.height) * unit, 47)

    def test_p1_lessons_validate_and_keep_traditional_labels(self):
        expected = {
            "P1-NUM-01": ["lesson_hook", "count_objects", "count_objects", "count_objects", "lesson_takeaway"],
            "P1-NUM-02": ["lesson_hook", "one_ten", "ten_and_ones", "ten_and_ones", "lesson_takeaway"],
            "P1-NUM-03": ["lesson_hook", "number_track", "number_track", "number_track", "lesson_takeaway"],
            "P1-NUM-04": ["lesson_hook", "ordinal_row", "ordinal_row", "ordinal_row", "lesson_takeaway"],
            "P1-NUM-05": ["lesson_hook", "pair_counters", "pair_counters", "pair_counters", "lesson_takeaway"],
            "P1-NUM-06": ["lesson_hook", "part_whole", "part_whole", "part_whole", "lesson_takeaway"],
            "P1-NUM-07": ["lesson_hook", "part_whole", "part_whole", "part_whole", "lesson_takeaway"],
            "P1-NUM-08": [
                "lesson_hook", "part_whole", "part_whole", "part_whole", "part_whole", "lesson_takeaway",
            ],
            "P1-NUM-09": [
                "lesson_hook", "part_whole", "number_track", "number_track", "lesson_takeaway",
            ],
            "P1-NUM-10": [
                "lesson_hook", "part_whole", "part_whole", "part_whole", "lesson_takeaway",
            ],
            "P1-NUM-11": [
                "lesson_hook", "part_whole", "part_whole", "part_whole", "lesson_takeaway",
            ],
            "P1-NUM-12": [
                "lesson_hook",
                "part_whole", "part_whole", "part_whole", "part_whole", "part_whole", "part_whole",
                "lesson_takeaway",
            ],
            "P1-NUM-13": [
                "lesson_hook", "number_blocks", "number_blocks", "number_blocks", "lesson_takeaway",
            ],
            "P1-NUM-14": [
                "lesson_hook", "number_blocks", "number_blocks", "number_blocks", "lesson_takeaway",
            ],
            "P1-NUM-15": [
                "lesson_hook", "number_blocks", "number_blocks", "number_blocks", "lesson_takeaway",
            ],
            "P1-NUM-16": [
                "lesson_hook", "number_blocks", "number_blocks", "number_blocks", "lesson_takeaway",
            ],
            "P1-NUM-17": [
                "lesson_hook", "number_blocks", "number_blocks", "number_blocks", "lesson_takeaway",
            ],
            "P1-NUM-18": [
                "lesson_hook",
                "estimate_group", "estimate_group", "estimate_group", "estimate_group", "estimate_group",
                "lesson_takeaway",
            ],
            "P1-NUM-19": [
                "lesson_hook", "ordinal_row", "ordinal_row", "ordinal_row", "lesson_takeaway",
            ],
            "P1-NUM-20": [
                "lesson_hook", "pair_counters", "pair_counters", "number_blocks", "lesson_takeaway",
            ],
            "P1-NUM-21": [
                "lesson_hook", "row_match", "row_match", "row_match", "row_match",
                "row_match", "row_match", "lesson_takeaway",
            ],
            "P1-NUM-22": [
                "lesson_hook", "place_sum", "place_sum", "lesson_takeaway",
            ],
            "P1-NUM-23": [
                "lesson_hook", "place_sum", "place_sum", "place_sum", "lesson_takeaway",
            ],
            "P1-NUM-24": [
                "lesson_hook", "place_sum", "place_sum", "place_sum", "lesson_takeaway",
            ],
            "P1-SHP-01": [
                "lesson_hook", "shape_line", "shape_line", "shape_line", "lesson_takeaway",
            ],
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
        four = load_lesson(P1 / "P1-NUM-04.yaml")
        places = [beat for beat in four["beats"] if beat.get("scene") == "ordinal_row"]
        self.assertEqual(
            [(b["mode"], b["direction"], b["n"], b["mark"]) for b in places],
            [("total", "left", 6, 3), ("ordinal", "left", 6, 3), ("ordinal", "right", 6, 3)],
        )
        self.assertEqual(count_event(places[1]), (1, 3))
        self.assertEqual(count_event(places[2]), (1, 4))
        recap = next(beat for beat in four["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap), 4)
        self.assertEqual(labels_for(recap, "en")["left"], "3rd")
        self.assertEqual(labels_for(recap, "zh_hk")["right"], "第四")
        self.assertEqual(labels_for(recap, "zh")["total"], "六")
        five = load_lesson(P1 / "P1-NUM-05.yaml")
        paired = [beat for beat in five["beats"] if beat.get("scene") == "pair_counters"]
        self.assertEqual([b["n"] for b in paired], [8, 9, 19])
        self.assertEqual(count_event(paired[0]), (1, 4))
        self.assertEqual(count_event(paired[1]), (1, 4))
        self.assertEqual(count_event(paired[2]), (1, 9))
        self.assertEqual(labels_for(paired[0], "en")["answer"], "Even")
        self.assertEqual(labels_for(paired[1], "zh")["answer"], "单数")
        self.assertEqual(labels_for(paired[1], "zh_hk")["note"], "剩低一個")
        self.assertEqual(labels_for(paired[2], "zh_hk")["pairs"][-1], "九")
        recap5 = next(beat for beat in five["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap5), 4)
        self.assertEqual(labels_for(recap5, "en")["examples"], [8, 9, 2])
        self.assertEqual(labels_for(recap5, "zh_hk")["also_word"], "十九")
        self.assertIn("?", five["beats"][0]["s1_en"])
        self.assertIn("even", paired[0]["s3_en"].lower())
        self.assertIn("odd", paired[1]["s3_en"].lower())
        six = load_lesson(P1 / "P1-NUM-06.yaml")
        parts = [beat for beat in six["beats"] if beat.get("scene") == "part_whole"]
        self.assertEqual(
            [(b.get("a"), b.get("b"), b.get("also"), b.get("cover")) for b in parts],
            [(3, 4, None, None), (3, 4, 5, None), (4, 8, None, "b")],
        )
        self.assertEqual(count_event(parts[0]), (1, 2))
        self.assertEqual(count_event(parts[1]), (1, 2))
        self.assertEqual(labels_for(parts[0], "zh")["left"], "三")
        self.assertEqual(labels_for(parts[0], "zh")["right"], "四")
        self.assertEqual(labels_for(parts[0], "en")["equation"], ["7", "=", "3", "+", "4"])
        self.assertEqual(labels_for(parts[1], "zh_hk")["also_left"], "五")
        self.assertEqual(labels_for(parts[1], "zh_hk")["also_right"], "二")
        self.assertEqual(labels_for(parts[1], "en")["also_equation"], ["7", "=", "5", "+", "2"])
        self.assertEqual(labels_for(parts[2], "en")["covered_equation"], ["12", "-", "8", "=", "4"])
        self.assertEqual(labels_for(parts[0], "zh")["title"], "两部分")
        self.assertEqual(labels_for(parts[0], "zh_hk")["title"], "兩部分")
        recap6 = next(beat for beat in six["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap6), 4)
        self.assertEqual(
            labels_for(recap6, "en")["lines"],
            [
                "Three and four make seven.",
                "Five and two make seven too.",
                "Seven stays seven.",
                "Four and eight make twelve.",
            ],
        )
        self.assertEqual(labels_for(recap6, "zh")["lines"][0], "三和四合成七。")
        self.assertEqual(labels_for(recap6, "zh_hk")["lines"][3], "四同八合成十二。")
        self.assertEqual(labels_for(recap6, "en")["title"], "Two parts make a whole")
        self.assertEqual(labels_for(recap6, "zh")["title"], "两部分合成一个整体")
        self.assertEqual(labels_for(recap6, "zh_hk")["title"], "兩部分合埋做一個")
        self.assertEqual(labels_for(recap6, "en")["bonds"], [[3, 4], [5, 2], [7], [4, 8]])
        self.assertIn("seven", parts[0]["s3_en"].lower())
        self.assertIn("four", parts[2]["s3_en"].lower())
        seven = load_lesson(P1 / "P1-NUM-07.yaml")
        swapped = [beat for beat in seven["beats"] if beat.get("scene") == "part_whole"]
        self.assertEqual(
            [(b.get("a"), b.get("b"), b.get("leave")) for b in swapped],
            [(3, 2, None), (2, 3, None), (3, 2, "b")],
        )
        self.assertEqual(count_event(swapped[0]), (1, 2))
        self.assertEqual(labels_for(swapped[0], "en")["equation"], ["5", "=", "3", "+", "2"])
        self.assertEqual(labels_for(swapped[1], "en")["equation"], ["5", "=", "2", "+", "3"])
        self.assertEqual(labels_for(swapped[1], "zh")["left"], "二")
        self.assertEqual(labels_for(swapped[1], "zh_hk")["right"], "三")
        self.assertEqual(labels_for(swapped[2], "en")["covered_equation"], ["5", "-", "2", "=", "3"])
        self.assertEqual(swapped[0]["s3_en"], "Bring the two parts together. Three and two make five. Together they make five.")
        self.assertEqual(swapped[2]["s3_en"], "Take two away, three are left.")
        self.assertEqual(swapped[2]["s3_zh"], "拿走两个，剩下三个。")
        self.assertEqual(swapped[2]["s3_zh_hk"], "拿走兩個，剩低三個。")
        recap7 = next(beat for beat in seven["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap7), 4)
        self.assertEqual(labels_for(recap7, "en")["title"], "Five stays five?")
        self.assertEqual(labels_for(recap7, "zh")["title"], "五还是五吗？")
        self.assertEqual(labels_for(recap7, "zh_hk")["title"], "五係咪仲係五？")
        self.assertEqual(
            labels_for(recap7, "en")["lines"],
            [
                "Three and two make five.",
                "Two and three make five too.",
                "Yes. Five stays five.",
                "Five minus two is three.",
            ],
        )
        self.assertEqual(labels_for(recap7, "zh")["lines"][2], "是的。五还是五。")
        self.assertEqual(labels_for(recap7, "zh_hk")["lines"][3], "五減二係三。")
        self.assertEqual(labels_for(recap7, "en")["bonds"], [[3, 2], [2, 3], [5], [3, -2]])
        self.assertEqual(labels_for(recap7, "zh_hk")["lines"][2], "係。五仲係五。")
        eight = load_lesson(P1 / "P1-NUM-08.yaml")
        zeros = [beat for beat in eight["beats"] if beat.get("scene") == "part_whole"]
        self.assertEqual(
            [(b.get("a"), b.get("b"), b.get("leave")) for b in zeros],
            [(0, 4, None), (4, 0, None), (4, 0, "b"), (4, 0, "a")],
        )
        self.assertEqual(count_event(zeros[0]), (1, 2))
        self.assertEqual(labels_for(zeros[0], "en")["equation"], ["4", "=", "0", "+", "4"])
        self.assertEqual(labels_for(zeros[1], "en")["equation"], ["4", "=", "4", "+", "0"])
        self.assertEqual(labels_for(zeros[0], "zh")["left"], "零")
        self.assertEqual(labels_for(zeros[0], "zh_hk")["right"], "四")
        self.assertEqual(labels_for(zeros[2], "en")["covered_equation"], ["4", "-", "0", "=", "4"])
        self.assertEqual(labels_for(zeros[3], "en")["covered_equation"], ["4", "-", "4", "=", "0"])
        self.assertEqual(zeros[0]["s3_en"], "Bring them together. Zero and four make four. Together they make four.")
        self.assertEqual(zeros[2]["s3_en"], "Take away zero. Four are left.")
        self.assertEqual(zeros[2]["s3_zh"], "拿走零个，剩下四个。")
        self.assertEqual(zeros[2]["s3_zh_hk"], "攞走零個，剩返四個。")
        self.assertEqual(zeros[3]["s3_en"], "Take all four away. None are left.")
        self.assertEqual(zeros[3]["s3_zh_hk"], "攞走四個，剩返零個。")
        self.assertNotIn("sum", zeros[0]["s3_en"].lower())
        self.assertNotIn("difference", zeros[3]["s3_en"].lower())
        recap8 = next(beat for beat in eight["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap8), 4)
        self.assertEqual(labels_for(recap8, "en")["title"], "What does zero change?")
        self.assertEqual(labels_for(recap8, "zh")["title"], "零改变什么？")
        self.assertEqual(labels_for(recap8, "zh_hk")["title"], "零改變咗咩？")
        self.assertEqual(
            labels_for(recap8, "en")["lines"],
            [
                "Zero and four make four.",
                "Four and zero make four too.",
                "Take zero away. Nothing changes.",
                "Take all four away. None are left.",
            ],
        )
        self.assertEqual(labels_for(recap8, "zh")["lines"][2], "拿走零个，没有改变。")
        self.assertEqual(labels_for(recap8, "zh_hk")["lines"][2], "攞走零個，冇改變。")
        self.assertEqual(labels_for(recap8, "zh_hk")["lines"][3], "攞走四個，剩返零個。")
        self.assertEqual(labels_for(recap8, "en")["bonds"], [[0, 4], [4, 0], [4], [0, -4]])
        twelve = load_lesson(P1 / "P1-NUM-12.yaml")
        parts = [beat for beat in twelve["beats"] if beat.get("scene") == "part_whole"]
        self.assertEqual(
            [(b.get("a"), b.get("b"), b.get("leave")) for b in parts],
            [(3, 2, "b"), (3, 2, None), (4, 6, "b"), (4, 6, "a"), (5, 4, "b"), (5, 4, None)],
        )
        self.assertEqual(labels_for(parts[0], "en")["covered_equation"], ["5", "-", "2", "=", "3"])
        self.assertEqual(labels_for(parts[1], "en")["equation"], ["5", "=", "3", "+", "2"])
        self.assertEqual(labels_for(parts[2], "en")["covered_equation"], ["10", "-", "6", "=", "4"])
        self.assertEqual(labels_for(parts[3], "en")["covered_equation"], ["10", "-", "4", "=", "6"])
        self.assertEqual(labels_for(parts[4], "en")["covered_equation"], ["9", "-", "4", "=", "5"])
        self.assertEqual(labels_for(parts[5], "en")["equation"], ["9", "=", "5", "+", "4"])
        self.assertEqual(parts[0]["s3_en"], "Take two away. Three are left.")
        self.assertEqual(parts[0]["s3_zh_hk"], "攞走兩個，剩返三個。")
        self.assertEqual(parts[3]["s3_zh"], "拿走四个，剩下六个。")
        self.assertEqual(parts[4]["s3_en"], "Take four away. Five are left.")
        self.assertEqual(parts[5]["s3_zh_hk"], "五加四係九。合埋係九。")
        self.assertNotIn("difference", " ".join(str(b.get("s3_en") or "") for b in twelve["beats"]).lower())
        self.assertNotIn("cannot", " ".join(str(b.get("s1_en") or "") for b in twelve["beats"]).lower())
        self.assertNotIn("嗎", _beat_lines(twelve, "zh_hk"))
        self.assertNotIn("拿走", _beat_lines(twelve, "zh_hk"))
        self.assertNotIn("剩低", _beat_lines(twelve, "zh_hk"))
        recap = next(beat for beat in twelve["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap), 4)
        self.assertEqual(labels_for(recap, "en")["title"], "Can we put the parts back?")
        self.assertEqual(labels_for(recap, "zh")["title"], "两部分可以放回去吗？")
        self.assertEqual(labels_for(recap, "zh_hk")["title"], "兩部分可唔可以放返去？")
        self.assertEqual(
            labels_for(recap, "en")["lines"],
            [
                "Take two away. Three stay.",
                "Put two back with three. They make five.",
                "Take six away. Four stay.",
                "Put six back with four. They make ten.",
            ],
        )
        self.assertEqual(labels_for(recap, "zh")["lines"][1], "把两个放回三个旁边，是五。")
        self.assertEqual(labels_for(recap, "zh")["lines"][3], "把六个放回四个旁边，是十。")
        self.assertEqual(labels_for(recap, "zh_hk")["lines"][1], "將兩個放返三個旁邊，係五。")
        self.assertEqual(labels_for(recap, "zh_hk")["lines"][3], "將六個放返四個旁邊，係十。")
        self.assertEqual(labels_for(recap, "en")["bonds"], [[3, -2], [3, 2], [4, -6], [4, 6]])
        eleven = load_lesson(P1 / "P1-NUM-11.yaml")
        parts = [beat for beat in eleven["beats"] if beat.get("scene") == "part_whole"]
        self.assertEqual(
            [(b.get("a"), b.get("b"), b.get("leave")) for b in parts],
            [(5, 3, "b"), (6, 0, "a"), (7, 0, "b")],
        )
        self.assertEqual(labels_for(parts[0], "en")["covered_equation"], ["8", "-", "3", "=", "5"])
        self.assertEqual(labels_for(parts[1], "en")["covered_equation"], ["6", "-", "6", "=", "0"])
        self.assertEqual(labels_for(parts[2], "en")["covered_equation"], ["7", "-", "0", "=", "7"])
        self.assertEqual(parts[0]["s3_en"], "Take three away. Five are left.")
        self.assertEqual(parts[1]["s3_en"], "Take all six away. None are left.")
        self.assertEqual(parts[1]["s3_zh_hk"], "攞走六個，剩返零個。")
        self.assertEqual(parts[2]["s3_zh"], "拿走零个，剩下七个。")
        self.assertEqual(parts[2]["s3_zh_hk"], "攞走零個，剩返七個。")
        self.assertNotIn("difference", " ".join(b.get("s3_en", "") for b in eleven["beats"]).lower())
        self.assertNotIn("嗎", _beat_lines(eleven, "zh_hk"))
        self.assertNotIn("拿走", _beat_lines(eleven, "zh_hk"))
        self.assertNotIn("剩低", _beat_lines(eleven, "zh_hk"))
        recap = next(beat for beat in eleven["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap), 4)
        self.assertEqual(labels_for(recap, "en")["title"], "How many stay?")
        self.assertEqual(labels_for(recap, "zh")["title"], "还剩下多少个？")
        self.assertEqual(labels_for(recap, "zh_hk")["title"], "仲剩返幾多個呀？")
        self.assertEqual(
            labels_for(recap, "en")["lines"],
            [
                "Take three away. Five stay.",
                "Take all six away. None stay.",
                "Take zero away. Seven stay.",
                "Count the five that stay.",
            ],
        )
        self.assertEqual(labels_for(recap, "zh_hk")["lines"][0], "攞走三個，剩返五個。")
        self.assertEqual(labels_for(recap, "zh_hk")["lines"][3], "數一數剩返嘅五個。")
        self.assertEqual(labels_for(recap, "en")["bonds"], [[5, -3], [0, -6], [7, 0], [5]])
        ten = load_lesson(P1 / "P1-NUM-10.yaml")
        parts = [beat for beat in ten["beats"] if beat.get("scene") == "part_whole"]
        self.assertEqual(
            [(b.get("a"), b.get("b"), b.get("also"), b.get("cover")) for b in parts],
            [(3, 4, None, None), (3, 4, 5, None), (5, 7, None, "a")],
        )
        self.assertEqual(labels_for(parts[0], "en")["equation"], ["7", "=", "3", "+", "4"])
        self.assertEqual(labels_for(parts[1], "en")["also_equation"], ["7", "=", "5", "+", "2"])
        self.assertEqual(parts[1]["s1_en"], "Seven can be three and four. We can see both parts.")
        self.assertEqual(parts[1]["s1_zh"], "七可以是三和四。两部分都看得到。")
        self.assertEqual(parts[1]["s1_zh_hk"], "七可以係三同四。兩部分都睇到。")
        self.assertEqual(parts[1]["s3_en"], "Move two over. Now it is five and two. Seven stays seven.")
        self.assertEqual(parts[1]["s3_zh"], "移两个过去。现在是五和二。七还是七。")
        self.assertEqual(parts[1]["s3_zh_hk"], "搬兩個過去。而家係五同二。七仲係七。")
        self.assertEqual(labels_for(parts[2], "en")["covered_equation"], ["12", "-", "5", "=", "7"])
        self.assertEqual(parts[2]["s3_en"], "Twelve minus five is seven. The other part is seven.")
        self.assertEqual(parts[2]["s3_zh"], "十二减五是七。另一部分是七。")
        self.assertEqual(parts[2]["s3_zh_hk"], "十二減五係七。另一部分係七。")
        self.assertNotIn("sum", " ".join(b.get("s3_en", "") for b in ten["beats"]).lower())
        self.assertNotIn("嗎", _beat_lines(ten, "zh_hk"))
        self.assertNotIn("拿走", _beat_lines(ten, "zh_hk"))
        recap = next(beat for beat in ten["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap), 4)
        self.assertEqual(labels_for(recap, "en")["title"], "Two parts, one whole")
        self.assertEqual(labels_for(recap, "zh")["title"], "两部分，一个整体")
        self.assertEqual(labels_for(recap, "zh_hk")["title"], "兩部分，一個整體")
        self.assertEqual(
            labels_for(recap, "en")["lines"],
            [
                "Three and four make seven.",
                "Five and two make seven too.",
                "Five and seven make twelve.",
                "Take five away. Seven are left.",
            ],
        )
        self.assertEqual(labels_for(recap, "zh")["lines"][3], "拿走五个，剩下七个。")
        self.assertEqual(labels_for(recap, "zh_hk")["lines"][3], "攞走五個，剩返七個。")
        self.assertEqual(labels_for(recap, "en")["bonds"], [[3, 4], [5, 2], [5, 7], [7, -5]])
        nine = load_lesson(P1 / "P1-NUM-09.yaml")
        joined = [beat for beat in nine["beats"] if beat.get("scene") == "part_whole"]
        hops = [beat for beat in nine["beats"] if beat.get("scene") == "number_track"]
        self.assertEqual([(b.get("a"), b.get("b")) for b in joined], [(3, 2)])
        self.assertEqual([(b["start"], b["end"]) for b in hops], [(8, 11), (6, 10)])
        self.assertEqual(count_event(hops[0]), (1, 4))
        self.assertEqual(count_event(hops[1]), (1, 5))
        self.assertEqual(labels_for(joined[0], "en")["equation"], ["5", "=", "3", "+", "2"])
        self.assertEqual(joined[0]["s3_en"], "Put them together. Three and two make five. Together they make five.")
        self.assertEqual(hops[0]["s2_en"], "Eight. Nine. Ten. Eleven.")
        self.assertEqual(hops[0]["s3_zh"], "八加三是十一。合起来是十一。")
        self.assertEqual(hops[1]["s3_zh_hk"], "再加四個。六加四係十。合埋係十。")
        self.assertNotIn("sum", " ".join(b.get("s3_en", "") for b in nine["beats"]).lower())
        self.assertNotIn("嗎", _beat_lines(nine, "zh_hk"))
        recap9 = next(beat for beat in nine["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap9), 4)
        self.assertEqual(labels_for(recap9, "en")["title"], "What do the groups make?")
        self.assertEqual(labels_for(recap9, "zh")["title"], "合起来是多少？")
        self.assertEqual(labels_for(recap9, "zh_hk")["title"], "合埋係幾多呀？")
        self.assertEqual(
            labels_for(recap9, "en")["lines"],
            [
                "Three and two make five.",
                "Eight and three make eleven.",
                "Six and four make ten.",
                "Six needs four more to make ten.",
            ],
        )
        self.assertEqual(labels_for(recap9, "zh")["lines"][3], "六再加四个，就是十。")
        self.assertEqual(labels_for(recap9, "zh_hk")["lines"][3], "六再加四個，就係十。")
        self.assertEqual(nine["title_zh_hk"], "將兩組合埋")
        self.assertEqual(labels_for(recap9, "en")["bonds"], [[3, 2], [8, 3], [6, 4], [6, 4]])
        fifteen = load_lesson(P1 / "P1-NUM-15.yaml")
        blocks = [beat for beat in fifteen["beats"] if beat.get("scene") == "number_blocks"]
        self.assertEqual([b["mode"] for b in blocks], ["order", "order", "hop"])
        self.assertEqual(labels_for(blocks[0], "en")["values"], [24, 40, 42])
        self.assertEqual(labels_for(blocks[1], "en")["values"], [61, 60, 16])
        self.assertEqual((blocks[2]["start"], blocks[2]["end"]), (38, 41))
        self.assertEqual(count_event(blocks[2]), (1, 4))
        self.assertEqual(blocks[2]["s2_en"], "38. 39. 40. 41.")
        self.assertEqual(blocks[2]["s3_zh_hk"], "三十九後面係四十。")
        self.assertNotIn("嗎", _beat_lines(fifteen, "zh_hk"))
        self.assertNotIn("sum", " ".join(b.get("s3_en", "") for b in fifteen["beats"]).lower())
        recap = next(beat for beat in fifteen["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap), 4)
        self.assertEqual(labels_for(recap, "en")["title"], "How do we put numbers in order?")
        self.assertEqual(labels_for(recap, "zh")["title"], "怎样排好这些数？")
        self.assertEqual(labels_for(recap, "zh_hk")["title"], "點樣排好呢啲數？")
        self.assertEqual(
            labels_for(recap, "en")["lines"],
            [
                "24, 40, 42. Smallest first.",
                "61, 60, 16. Largest first.",
                "After 39 comes 40.",
                "Count back: 41, 40, 39, 38.",
            ],
        )
        self.assertEqual(labels_for(recap, "zh")["lines"][3], "倒着数，四十一，四十，三十九，三十八。")
        self.assertEqual(labels_for(recap, "zh_hk")["lines"][3], "倒返數，四十一，四十，三十九，三十八。")
        self.assertEqual(
            labels_for(recap, "en")["cues"],
            [
                ("tiles", (24, 40, 42)),
                ("tiles", (61, 60, 16)),
                ("tiles", (39, 40)),
                ("tiles", (41, 40, 39, 38)),
            ],
        )
        for picture in labels_for(recap, "en")["cues"]:
            self.assertNotIn(picture, DEFAULT_TRACK_CUES)
            self.assertNotIn(picture[1], DEFAULT_TRACK_CUES)
        self.assertIn("？", labels_for(recap, "zh")["title"])
        self.assertNotIn("?", labels_for(recap, "zh")["title"])
        self.assertNotIn("?", labels_for(recap, "zh_hk")["title"])
        sixteen = load_lesson(P1 / "P1-NUM-16.yaml")
        blocks = [beat for beat in sixteen["beats"] if beat.get("scene") == "number_blocks"]
        self.assertEqual([b["mode"] for b in blocks], ["groups", "groups", "groups"])
        self.assertEqual([(b["a"], b["n"], b.get("b")) for b in blocks], [(2, 4, None), (2, 6, None), (2, 5, 1)])
        self.assertEqual(count_event(blocks[0]), (1, 4))
        self.assertEqual(count_event(blocks[1]), (1, 6))
        self.assertEqual(count_event(blocks[2]), (1, 5))
        self.assertEqual(blocks[0]["s3_zh_hk"], "四對係八個。")
        self.assertEqual(blocks[2]["s3_en"], "One more makes eleven. One is left over.")
        self.assertEqual(blocks[2]["s3_zh"], "再加一个是十一。多了一个。")
        self.assertEqual(blocks[2]["s3_zh_hk"], "再加一個係十一。多咗一個。")
        self.assertNotIn("嗎", _beat_lines(sixteen, "zh_hk"))
        self.assertNotIn("sum", " ".join(b.get("s3_en", "") for b in sixteen["beats"]).lower())
        recap = next(beat for beat in sixteen["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap), 4)
        self.assertEqual(labels_for(recap, "en")["title"], "How many counters?")
        self.assertEqual(labels_for(recap, "zh")["title"], "有多少个圆片？")
        self.assertEqual(labels_for(recap, "zh_hk")["title"], "有幾多個圓片呀？")
        self.assertEqual(
            labels_for(recap, "en")["lines"],
            [
                "Four pairs make eight.",
                "Six pairs make twelve.",
                "There are twelve counters.",
                "Five pairs and one more is eleven.",
            ],
        )
        self.assertEqual(labels_for(recap, "zh")["lines"][2], "一共有十二个圆片。")
        self.assertEqual(labels_for(recap, "zh_hk")["lines"][2], "一共有十二個圓片。")
        self.assertEqual(
            labels_for(recap, "en")["cues"],
            [("pairs", 4, 0), ("pairs", 6, 0), ("counters", 12), ("pairs", 5, 1)],
        )
        for picture in labels_for(recap, "en")["cues"]:
            self.assertNotIn(picture, DEFAULT_TRACK_CUES)
        self.assertIn("？", labels_for(recap, "zh")["title"])
        self.assertNotIn("?", labels_for(recap, "zh")["title"])
        self.assertNotIn("?", labels_for(recap, "zh_hk")["title"])
        seventeen = load_lesson(P1 / "P1-NUM-17.yaml")
        blocks = [beat for beat in seventeen["beats"] if beat.get("scene") == "number_blocks"]
        self.assertEqual([b["mode"] for b in blocks], ["groups", "tens", "hop"])
        self.assertEqual((blocks[0]["a"], blocks[0]["n"]), (5, 4))
        self.assertEqual(blocks[1]["count"], 50)
        self.assertTrue(blocks[1].get("rods_only"))
        self.assertTrue(labels_for(blocks[1], "en").get("rods_only"))
        self.assertEqual(labels_for(blocks[1], "en")["title"], "Tens and ones")
        self.assertEqual(group_columns(4, 5, True), 2)
        self.assertEqual(group_columns(4, 2, True), 3)
        self.assertEqual((blocks[2]["start"], blocks[2]["end"]), (30, 33))
        self.assertEqual(count_event(blocks[0]), (1, 4))
        self.assertEqual(count_event(blocks[1]), (0, 5))
        self.assertEqual(count_event(blocks[2]), (1, 4))
        self.assertEqual(blocks[0]["s2_zh_hk"], "五，十，十五，二十。")
        self.assertNotIn("嗎", _beat_lines(seventeen, "zh_hk"))
        self.assertNotIn("sum", " ".join(b.get("s3_en", "") for b in seventeen["beats"]).lower())
        recap17 = next(beat for beat in seventeen["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap17), 4)
        self.assertEqual(labels_for(recap17, "en")["title"], "How do we count in groups?")
        self.assertEqual(labels_for(recap17, "zh")["title"], "怎样按组数？")
        self.assertEqual(labels_for(recap17, "zh_hk")["title"], "點樣按組數呀？")
        self.assertEqual(
            labels_for(recap17, "en")["lines"],
            [
                "Four groups of five make twenty.",
                "Five tens make fifty.",
                "Thirty is three tens.",
                "Count on, 31, 32, 33.",
            ],
        )
        self.assertEqual(labels_for(recap17, "zh")["lines"][0], "四组五个是二十。")
        self.assertEqual(labels_for(recap17, "zh_hk")["lines"][0], "四組五個係二十。")
        self.assertEqual(
            labels_for(recap17, "en")["cues"],
            [("groups", 5, 4, 0), ("tens", 5, 0), ("tens", 3, 0), ("tiles", (30, 31, 32, 33))],
        )
        self.assertEqual(takeaway_cue_picture({"kind": "groups", "a": 5, "n": 4}), ("groups", 5, 4, 0))
        self.assertIsNone(takeaway_cue_picture({"kind": "groups", "a": 6, "n": 4}))
        self.assertIsNone(takeaway_cue_picture({"kind": "groups", "a": 5, "n": 4, "extra": 1}))
        for picture in labels_for(recap17, "en")["cues"]:
            self.assertNotIn(picture, DEFAULT_TRACK_CUES)
        self.assertIn("？", labels_for(recap17, "zh")["title"])
        self.assertNotIn("?", labels_for(recap17, "zh")["title"])
        self.assertNotIn("?", labels_for(recap17, "zh_hk")["title"])
        rods = {"scene": "number_blocks", "mode": "tens", "count": 10, "rods_only": True}
        self.assertTrue(labels_for(rods, "en").get("rods_only"))
        self.assertEqual(labels_for(rods, "en")["title"], "Tens and ones")
        self.assertFalse(labels_for({"scene": "number_blocks", "mode": "tens", "count": 23}, "en").get("rods_only"))
        eighteen = load_lesson(P1 / "P1-NUM-18.yaml")
        hook = next(beat for beat in eighteen["beats"] if beat.get("scene") == "lesson_hook")
        self.assertTrue(labels_for(hook, "en").get("shown"))
        parts = [beat for beat in eighteen["beats"] if beat.get("scene") == "estimate_group"]
        self.assertEqual([beat["part"] for beat in parts], ["pile", "ten", "guess", "count", "close"])
        estimate = parts[0]
        self.assertEqual(estimate["count"], 23)
        self.assertEqual(labels_for(estimate, "en")["guess"], 20)
        self.assertEqual(labels_for(estimate, "en")["title"], "About how many?")
        self.assertEqual(labels_for(estimate, "zh")["title"], "大约有多少个？")
        self.assertEqual(labels_for(estimate, "zh_hk")["title"], "大約有幾多個呀？")
        self.assertIsNone(count_event(estimate))
        self.assertEqual(count_event(parts[3]), (0, 5))
        self.assertEqual(scene_problems(estimate), [])
        self.assertTrue(scene_problems(dict(estimate, count=20)))
        self.assertTrue(scene_problems(dict(estimate, count=10)))
        self.assertTrue(scene_problems(dict(estimate, part="rods")))
        spots = messy_spots(23, 4.0, 3.0, 0.3)
        self.assertEqual(len(spots), 23)
        self.assertEqual(spots, messy_spots(23, 4.0, 3.0, 0.3))
        for i, (x, y) in enumerate(spots):
            self.assertLessEqual(abs(x), 2.01)
            self.assertLessEqual(abs(y), 1.51)
            for other in spots[i + 1:]:
                self.assertGreaterEqual((x - other[0]) ** 2 + (y - other[1]) ** 2, 0.3 ** 2 - 1e-6)
        self.assertEqual(parts[3]["s1_zh_hk"], "十。二十。二十一。二十二。二十三。")
        self.assertEqual(parts[1]["s1_en"], "This is one ten.")
        self.assertNotIn("嗎", _beat_lines(eighteen, "zh_hk"))
        self.assertNotIn("sum", " ".join(b.get("s3_en", "") for b in eighteen["beats"]).lower())
        recap18 = next(beat for beat in eighteen["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap18), 4)
        self.assertEqual(labels_for(recap18, "en")["title"], "About how many?")
        self.assertEqual(labels_for(recap18, "zh")["title"], "大约有多少个？")
        self.assertEqual(labels_for(recap18, "zh_hk")["title"], "大約有幾多個呀？")
        self.assertEqual(
            labels_for(recap18, "en")["lines"],
            [
                "A group of ten helps us guess.",
                "Two groups of ten. About twenty.",
                "We count and find twenty-three.",
                "Twenty-three is about twenty.",
            ],
        )
        self.assertEqual(labels_for(recap18, "zh")["lines"][3], "二十三大约是二十。")
        self.assertEqual(labels_for(recap18, "zh_hk")["lines"][3], "二十三大約係二十。")
        self.assertEqual(
            labels_for(recap18, "en")["cues"],
            [("tens", 1, 0), ("tens", 2, 0), ("tens", 2, 3), ("tiles", (20, 23))],
        )
        for picture in labels_for(recap18, "en")["cues"]:
            self.assertNotIn(picture, DEFAULT_TRACK_CUES)
        self.assertIn("？", labels_for(recap18, "zh")["title"])
        self.assertNotIn("?", labels_for(recap18, "zh")["title"])
        self.assertNotIn("?", labels_for(recap18, "zh_hk")["title"])

        nineteen = load_lesson(P1 / "P1-NUM-19.yaml")
        rows = [beat for beat in nineteen["beats"] if beat.get("scene") == "ordinal_row"]
        self.assertEqual([(b["mode"], b["direction"], b["n"], b["mark"]) for b in rows], [
            ("total", "left", 8, 2),
            ("ordinal", "left", 8, 2),
            ("ordinal", "right", 8, 2),
        ])
        self.assertEqual(ordinal_visits(8, 2, "left", "total"), [0, 1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(ordinal_visits(8, 2, "left", "ordinal"), [0, 1])
        self.assertEqual(ordinal_visits(8, 2, "right", "ordinal"), [7, 6, 5, 4, 3, 2, 1])
        self.assertTrue(all(b.get("one_row") for b in rows))
        self.assertEqual(ordinal_columns(8, 1080, 1920, one_row=True), 8)
        self.assertLess(ordinal_columns(8, 1080, 1920), 8)
        self.assertEqual(rows[1]["s3_zh_hk"], "星星係第二。第二係星星嘅位置。")
        self.assertNotIn("嗎", _beat_lines(nineteen, "zh_hk"))
        self.assertNotIn("sum", " ".join(b.get("s3_en", "") for b in nineteen["beats"]).lower())
        recap19 = next(beat for beat in nineteen["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap19), 4)
        self.assertEqual(labels_for(recap19, "en")["title"], "Where is the star?")
        self.assertEqual(labels_for(recap19, "zh")["title"], "星星在第几？")
        self.assertEqual(labels_for(recap19, "zh_hk")["title"], "星星喺第幾呀？")
        self.assertEqual(labels_for(recap19, "en")["n"], 8)
        self.assertEqual(labels_for(recap19, "en")["mark"], 2)
        self.assertEqual(
            labels_for(recap19, "en")["lines"],
            [
                "There are eight tokens.",
                "From the left, the star is second.",
                "From the right, the same star is seventh.",
                "Eight is how many. Second is the star's place.",
            ],
        )
        self.assertEqual(labels_for(recap19, "zh")["lines"][3], "八是有多少个。第二是星星的位置。")
        self.assertEqual(labels_for(recap19, "zh_hk")["lines"][3], "八係有幾多個。第二係星星嘅位置。")
        self.assertTrue(labels_for(recap19, "en").get("one_row"))
        self.assertEqual(labels_for(recap19, "zh")["lines"][1], "从左边数，星星是第二。")
        self.assertEqual(labels_for(recap19, "zh_hk")["lines"][1], "由左邊數，星星係第二。")
        self.assertNotIn("cues", labels_for(recap19, "en"))
        self.assertIn("？", labels_for(recap19, "zh")["title"])
        self.assertNotIn("?", labels_for(recap19, "zh")["title"])
        self.assertNotIn("?", labels_for(recap19, "zh_hk")["title"])

        twenty = load_lesson(P1 / "P1-NUM-20.yaml")
        pairs = [beat for beat in twenty["beats"] if beat.get("scene") == "pair_counters"]
        self.assertEqual([b["n"] for b in pairs], [8, 9])
        self.assertEqual(count_event(pairs[0]), (1, 4))
        self.assertEqual(count_event(pairs[1]), (1, 4))
        blocks = [beat for beat in twenty["beats"] if beat.get("scene") == "number_blocks"]
        self.assertEqual(blocks[0]["count"], 23)
        self.assertEqual(count_event(blocks[0]), (0, 2))
        self.assertEqual(pairs[1]["s3_zh_hk"], "四對再加一個。九係單數。")
        self.assertNotIn("嗎", _beat_lines(twenty, "zh_hk"))
        self.assertNotIn("sum", " ".join(b.get("s3_en", "") for b in twenty["beats"]).lower())
        recap20 = next(beat for beat in twenty["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap20), 4)
        self.assertEqual(labels_for(recap20, "en")["title"], "Odd or even?")
        self.assertEqual(labels_for(recap20, "zh")["title"], "单数还是双数？")
        self.assertEqual(labels_for(recap20, "zh_hk")["title"], "單數定雙數呀？")
        self.assertTrue(blocks[0].get("pair_ones"))
        self.assertEqual(
            labels_for(recap20, "en")["lines"],
            [
                "Four pairs. Eight is even.",
                "Four pairs and one more. Nine is odd.",
                "Zero counters. Zero is even.",
                "Look at the ones. Two ones make a pair. Thirty-two is even.",
            ],
        )
        self.assertEqual(labels_for(recap20, "zh")["lines"][3], "看一看个位上的数。两个一配成一对。三十二是双数。")
        self.assertEqual(labels_for(recap20, "zh_hk")["lines"][3], "睇下個位上嘅數。兩個一配成一對。三十二係雙數。")
        self.assertEqual(labels_for(recap20, "zh")["lines"][2], "零个圆片。零是双数。")
        self.assertEqual(labels_for(recap20, "zh_hk")["lines"][2], "零個圓片。零係雙數。")
        self.assertEqual(
            labels_for(recap20, "en")["cues"],
            [("pairs", 4, 0), ("pairs", 4, 1), ("tiles", (0,)), ("tens", 3, 2)],
        )
        for picture in labels_for(recap20, "en")["cues"]:
            self.assertNotIn(picture, DEFAULT_TRACK_CUES)
        self.assertIn("？", labels_for(recap20, "zh")["title"])
        self.assertNotIn("?", labels_for(recap20, "zh")["title"])
        self.assertNotIn("?", labels_for(recap20, "zh_hk")["title"])

        twentyone = load_lesson(P1 / "P1-NUM-21.yaml")
        matched = [beat for beat in twentyone["beats"] if beat.get("scene") == "row_match"]
        self.assertEqual([b["part"] for b in matched], ["rows", "match", "gap", "hold", "hold", "equal"])
        self.assertEqual([b["a"] for b in matched], [8, 8, 8, 8, 8, 6])
        self.assertEqual(count_event(matched[2]), (0, 3))
        self.assertIsNone(count_event(matched[0]))
        self.assertEqual(matched[2]["s1_en"], "One. Two. Three.")
        self.assertEqual(matched[2]["s1_zh_hk"], "一。二。三。")
        self.assertEqual(labels_for(matched[3], "zh_hk")["title"], "多幾多呀？")
        recap21 = twentyone["beats"][-1]
        self.assertEqual(
            labels_for(recap21, "en")["cues"],
            [("tiles", (8, 5)), ("counters", 3), ("tiles", (3,)), ("tiles", (6, 6))],
        )
        self.assertEqual(len(labels_for(recap21, "en")["lines"]), 4)
        self.assertNotIn("sum", recap21["s3_en"].lower())
        self.assertIn("？", twentyone["title_zh"])
        self.assertNotIn("?", twentyone["title_zh_hk"])
        twentytwo = load_lesson(P1 / "P1-NUM-22.yaml")
        added = [beat for beat in twentytwo["beats"] if beat.get("scene") == "place_sum"]
        self.assertEqual([(b["a"], b["b"]) for b in added], [(23, 14), (27, 15)])
        self.assertEqual(labels_for(added[0], "en")["values"], [23, 14])
        self.assertEqual(labels_for(added[1], "zh_hk")["title"], "先個位，再十位")
        self.assertIn(
            "place_sum subtraction stays inside each column.",
            scene_problems({
                "visual": "animated", "scene": "place_sum", "op": "sub", "a": 21, "b": 15,
                "s1_en": "a", "s2_en": "b", "s3_en": "c",
                "s1_zh": "甲", "s2_zh": "乙", "s3_zh": "丙",
            }),
        )
        recap22 = twentytwo["beats"][-1]
        self.assertEqual(
            labels_for(recap22, "en")["cues"],
            [("tiles", (23, 14)), ("tens", 3, 7), ("tens", 1, 0), ("tens", 4, 2)],
        )
        self.assertNotIn("sum", " ".join(beat.get("s3_en", "") for beat in twentytwo["beats"]).lower())
        twentythree = load_lesson(P1 / "P1-NUM-23.yaml")
        trios = [beat for beat in twentythree["beats"] if beat.get("scene") == "place_sum"]
        self.assertEqual(
            [(b["a"], b["b"], b["c"]) for b in trios],
            [(12, 4, 3), (24, 6, 4), (18, 7, 5)],
        )
        self.assertEqual(labels_for(trios[2], "en")["values"], [18, 7, 5])
        self.assertEqual(labels_for(trios[0], "zh")["title"], "先个位，再十位")
        recap23 = twentythree["beats"][-1]
        self.assertEqual(
            labels_for(recap23, "en")["cues"],
            [("tiles", (12, 4, 3)), ("tens", 1, 9), ("tiles", (6, 4, 10)), ("tens", 3, 0)],
        )
        self.assertNotIn("sum", recap23["s3_en"].lower())
        twentyfour = load_lesson(P1 / "P1-NUM-24.yaml")
        taken = [beat for beat in twentyfour["beats"] if beat.get("scene") == "place_sum"]
        self.assertEqual(
            [(b["op"], b["a"], b["b"]) for b in taken],
            [("sub", 47, 23), ("sub", 58, 6), ("add", 32, 32)],
        )
        self.assertEqual(labels_for(taken[0], "zh_hk")["title"], "先個位，再十位")
        self.assertNotIn("拿走", "\n".join(b.get("s1_zh_hk", "") + b.get("s2_zh_hk", "") + b.get("s3_zh_hk", "") for b in twentyfour["beats"]))
        self.assertNotIn("剩低", twentyfour["beats"][2]["s2_zh_hk"])
        self.assertIn("攞走", twentyfour["beats"][1]["s1_zh_hk"])
        self.assertIn("剩返", twentyfour["beats"][1]["s2_zh_hk"])
        recap24 = twentyfour["beats"][-1]
        self.assertEqual(
            labels_for(recap24, "en")["lines"][1],
            "Take away six ones. Fifty-two.",
        )
        self.assertEqual(labels_for(recap24, "zh")["lines"][1], "拿走六个一。五十二。")
        self.assertEqual(labels_for(recap24, "zh_hk")["lines"][1], "攞走六個一。五十二。")
        self.assertEqual(
            labels_for(recap24, "en")["cues"],
            [("tens", 2, 4), ("tens", 5, 2), ("tiles", (32, 32)), ("tens", 6, 4)],
        )
        self.assertNotIn("sum", recap24["s3_en"].lower())
        shapes = load_lesson(P1 / "P1-SHP-01.yaml")
        lines = [beat for beat in shapes["beats"] if beat.get("scene") == "shape_line"]
        self.assertEqual([b["part"] for b in lines], ["marks", "lines", "routes"])
        self.assertEqual(count_event(lines[0]), (1, 3))
        self.assertIsNone(count_event(lines[1]))
        self.assertEqual(lines[0]["s2_en"], "One. Two. Three.")
        self.assertEqual(lines[0]["s2_zh_hk"], "一。二。三。")
        self.assertEqual(labels_for(lines[1], "zh_hk")["title"], "直嘅，定係彎嘅")
        self.assertEqual(labels_for(lines[1], "zh_hk")["curve"], "彎嘅")
        recap_s = shapes["beats"][-1]
        self.assertEqual(
            labels_for(recap_s, "en")["cues"],
            [("line", "marks", 3), ("line", "straight"), ("line", "curve"), ("line", "routes")],
        )
        self.assertNotIn("嗎", _beat_lines(shapes, "zh_hk"))
        self.assertEqual(
            takeaway_cue_picture({"kind": "flat", "items": ["pentagon", "hexagon", "circle"]}),
            ("flat", "row", ("pentagon", "hexagon", "circle")),
        )
        self.assertEqual(
            takeaway_cue_picture({"kind": "solid", "items": ["pyramid", "cone"]}),
            ("solid", "pair", ("pyramid", "cone")),
        )
        thirteen = load_lesson(P1 / "P1-NUM-13.yaml")
        blocks = [beat for beat in thirteen["beats"] if beat.get("scene") == "number_blocks"]
        self.assertEqual([b["mode"] for b in blocks], ["tens", "tens", "tens"])
        self.assertEqual([b["count"] for b in blocks], [24, 40, 100])
        self.assertEqual(count_event(blocks[0]), (0, 2))
        self.assertEqual(count_event(blocks[1]), (0, 4))
        self.assertEqual(count_event(blocks[2]), (0, 10))
        self.assertEqual(blocks[0]["s3_en"], "Two tens and four ones make twenty-four.")
        self.assertEqual(blocks[0]["s3_zh"], "两个十和四个一，是二十四。")
        self.assertEqual(blocks[1]["s3_zh_hk"], "四個十係四十。我哋可以數一數。")
        self.assertNotIn("嗎", _beat_lines(thirteen, "zh_hk"))
        self.assertNotIn("sum", " ".join(b.get("s3_en", "") for b in thirteen["beats"]).lower())
        recap13 = next(beat for beat in thirteen["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap13), 4)
        self.assertEqual(labels_for(recap13, "en")["title"], "Tens and ones")
        self.assertEqual(labels_for(recap13, "zh")["title"], "十、个和一百")
        self.assertEqual(labels_for(recap13, "zh_hk")["title"], "十、個同一百")
        self.assertEqual(
            labels_for(recap13, "en")["lines"],
            [
                "Two tens and four ones make 24.",
                "Four tens make forty.",
                "Four ones make four.",
                "Ten tens make one hundred.",
            ],
        )
        self.assertEqual(labels_for(recap13, "zh")["lines"][3], "十个十是一百。")
        self.assertEqual(labels_for(recap13, "zh_hk")["lines"][3], "十個十係一百。")
        self.assertEqual(
            labels_for(recap13, "en")["cues"],
            [("tens", 2, 4), ("tens", 4, 0), ("tens", 0, 4), ("tens", 10, 0)],
        )
        for picture in labels_for(recap13, "en")["cues"]:
            self.assertNotIn(picture, DEFAULT_TRACK_CUES)
        fourteen = load_lesson(P1 / "P1-NUM-14.yaml")
        blocks = [beat for beat in fourteen["beats"] if beat.get("scene") == "number_blocks"]
        self.assertEqual([b["mode"] for b in blocks], ["compare", "compare", "compare"])
        self.assertEqual([(b["a"], b["b"]) for b in blocks], [(24, 42), (47, 43), (100, 99)])
        self.assertIsNone(count_event(blocks[0]))
        self.assertEqual(blocks[0]["s3_en"], "Four tens is more. 42 is larger.")
        self.assertEqual(blocks[0]["s3_zh"], "四个十更多。四十二比较大。")
        self.assertEqual(blocks[2]["s3_zh_hk"], "一百比九十九大。")
        self.assertNotIn("嗎", _beat_lines(fourteen, "zh_hk"))
        self.assertNotIn("sum", " ".join(b.get("s3_en", "") for b in fourteen["beats"]).lower())
        recap = next(beat for beat in fourteen["beats"] if beat["id"] == "takeaway")
        self.assertEqual(step_count(recap), 4)
        self.assertEqual(labels_for(recap, "en")["title"], "Which is larger?")
        self.assertEqual(labels_for(recap, "zh")["title"], "哪个数比较大？")
        self.assertEqual(labels_for(recap, "zh_hk")["title"], "邊個數大啲呀？")
        self.assertEqual(
            labels_for(recap, "en")["lines"],
            [
                "42 is larger than 24.",
                "Look at the tens first.",
                "47 is larger than 43.",
                "100 is larger than 99.",
            ],
        )
        self.assertEqual(labels_for(recap, "zh")["lines"][1], "先看有几个十。")
        self.assertEqual(labels_for(recap, "zh_hk")["lines"][1], "先睇有幾個十。")
        self.assertEqual(
            labels_for(recap, "en")["cues"],
            [
                ("compare", 24, 42, 42),
                ("tens_mark", 24, 42),
                ("compare", 47, 43, 47),
                ("compare", 100, 99, 100),
            ],
        )
        for picture in labels_for(recap, "en")["cues"]:
            self.assertNotIn(picture, DEFAULT_TRACK_CUES)
        self.assertIn("？", fourteen["title_zh"])
        self.assertNotIn("?", fourteen["title_zh"])
        self.assertNotIn("?", fourteen["title_zh_hk"])
        for beat in fourteen["beats"]:
            self.assertNotIn("?", beat.get("title_zh") or "")
            self.assertNotIn("?", beat.get("title_zh_hk") or "")

    def test_part_whole_bounds(self):
        good = {
            "visual": "animated",
            "scene": "part_whole",
            "a": 3,
            "b": 4,
            "s1_en": "Mats.",
            "s2_en": "Three. Four.",
            "s3_en": "Seven.",
            "s1_zh": "圆片。",
            "s2_zh": "三，四。",
            "s3_zh": "七。",
            "s1_zh_hk": "圓片。",
            "s2_zh_hk": "三，四。",
            "s3_zh_hk": "七。",
        }
        self.assertEqual(scene_problems(good), [])
        self.assertEqual(count_event(good), (1, 2))
        self.assertEqual(labels_for(good, "zh")["whole_word"], "七")
        self.assertTrue(scene_problems(dict(good, a=0, b=0)))
        self.assertEqual(scene_problems(dict(good, a=0, b=4)), [])
        self.assertEqual(count_event(dict(good, a=0, b=4)), (1, 2))
        self.assertEqual(labels_for(dict(good, a=0, b=4), "en")["equation"], ["4", "=", "0", "+", "4"])
        self.assertEqual(labels_for(dict(good, a=0, b=4), "zh")["left"], "零")
        self.assertEqual(
            labels_for(dict(good, a=4, b=0, leave="b"), "en")["covered_equation"],
            ["4", "-", "0", "=", "4"],
        )
        self.assertEqual(
            labels_for(dict(good, a=4, b=0, leave="a"), "en")["covered_equation"],
            ["4", "-", "4", "=", "0"],
        )
        self.assertTrue(scene_problems(dict(good, b=10)))
        self.assertTrue(scene_problems(dict(good, a=9, b=9, whole=19)))
        self.assertTrue(scene_problems(dict(good, also=3)))
        self.assertTrue(scene_problems(dict(good, also=5, cover="b")))
        self.assertTrue(scene_problems(dict(good, cover="c")))
        self.assertTrue(scene_problems(dict(good, leave="c")))
        self.assertTrue(scene_problems(dict(good, leave="b", cover="b")))
        self.assertEqual(scene_problems(dict(good, a=3, b=2, leave="b")), [])
        self.assertEqual(
            labels_for(dict(good, a=3, b=2, leave="b"), "en")["covered_equation"],
            ["5", "-", "2", "=", "3"],
        )
        moved = dict(good, also=5)
        self.assertEqual(scene_problems(moved), [])
        self.assertEqual(labels_for(moved, "zh")["also_equation"], ["7", "=", "5", "+", "2"])
        covered = dict(good, a=4, b=8, cover="a")
        self.assertEqual(labels_for(covered, "en")["covered_equation"], ["12", "-", "4", "=", "8"])
        hook = {
            "visual": "animated",
            "scene": "lesson_hook",
            "motif": "parts",
            "title_en": "Make parts before adding",
            "title_zh": "先分开，再加",
            "title_zh_hk": "先分開，再加",
            "s1_en": "What parts make seven?",
            "s1_zh": "七可以分成哪两部分？",
            "s1_zh_hk": "七可以分成邊兩部分？",
        }
        self.assertEqual(scene_problems(hook), [])
        self.assertEqual(labels_for(hook, "en")["a"], 3)
        self.assertEqual(labels_for(dict(hook, a=4, b=8), "zh")["b"], 8)
        self.assertEqual(scene_problems(dict(hook, a=0, b=4)), [])
        self.assertEqual(labels_for(dict(hook, a=0, b=4), "en")["a"], 0)
        self.assertTrue(scene_problems(dict(hook, a=0, b=0)))
        recap = {
            "visual": "animated",
            "scene": "lesson_takeaway",
            "motif": "parts",
            "bonds": [[3, 4], [5, 2], [7], [4, 8]],
            "s1_en": "Three and four make seven.",
            "s2_en": "Five and two make seven too.",
            "s3_en": "Seven stays seven.",
            "s4_en": "Four and eight make twelve.",
            "s1_zh": "三和四合成七。",
            "s2_zh": "五和二也合成七。",
            "s3_zh": "七还是七。",
            "s4_zh": "四和八合成十二。",
            "s1_zh_hk": "三同四合成七。",
            "s2_zh_hk": "五同二都合成七。",
            "s3_zh_hk": "七仲係七。",
            "s4_zh_hk": "四同八合成十二。",
        }
        self.assertEqual(scene_problems(recap), [])
        self.assertEqual(step_count(recap), 4)
        self.assertTrue(scene_problems(dict(recap, bonds=[])))
        self.assertTrue(scene_problems(dict(recap, bonds=[[3, 4], [1], [2], [3], [4]])))
        self.assertEqual(scene_problems(dict(recap, bonds=[[7, 0]])), [])
        self.assertEqual(scene_problems(dict(recap, bonds=[[0, 4], [4, 0], [4], [0, -4]])), [])
        self.assertTrue(scene_problems(dict(recap, bonds=[[0, 0]])))
        self.assertEqual(scene_problems(dict(recap, bonds=[[3, -2]])), [])
        self.assertTrue(scene_problems(dict(recap, bonds=[[3, -10]])))
        self.assertTrue(scene_problems(dict(recap, bonds=[[0, -10]])))

    def test_ordinal_row_counts_a_place_or_a_total(self):
        left = {
            "visual": "animated",
            "scene": "ordinal_row",
            "mode": "ordinal",
            "direction": "left",
            "n": 6,
            "mark": 3,
            "s1_en": "Start at the left.",
            "s2_en": "First. Second. Third.",
            "s3_en": "The star is third.",
            "s1_zh": "从左边数。",
            "s2_zh": "第一，第二，第三。",
            "s3_zh": "星星是第三。",
            "s1_zh_hk": "由左邊數。",
            "s2_zh_hk": "第一，第二，第三。",
            "s3_zh_hk": "星星係第三。",
        }
        self.assertEqual(scene_problems(left), [])
        self.assertEqual(ordinal_visits(6, 3, "left", "ordinal"), [0, 1, 2])
        self.assertEqual(ordinal_visits(6, 3, "right", "ordinal"), [5, 4, 3, 2])
        self.assertEqual(ordinal_visits(6, 3, "left", "total"), [0, 1, 2, 3, 4, 5])
        self.assertEqual(count_event(left), (1, 3))
        right = dict(left, direction="right")
        self.assertEqual(count_event(right), (1, 4))
        self.assertEqual(count_event(dict(left, mode="total")), (1, 6))
        self.assertEqual(labels_for(left, "en")["ordinals"], ["1st", "2nd", "3rd"])
        self.assertEqual(labels_for(left, "zh")["ordinals"], ["第一", "第二", "第三"])
        self.assertEqual(labels_for(left, "zh")["title"], "第几个？")
        self.assertEqual(labels_for(right, "zh_hk")["ordinals"], ["第一", "第二", "第三", "第四"])
        self.assertEqual(labels_for(right, "zh_hk")["answer"], "第四")
        self.assertEqual(labels_for(right, "zh_hk")["note"], "由右邊")
        self.assertEqual(labels_for(right, "en")["answer"], "4th")
        self.assertNotEqual(labels_for(left, "zh")["title"], labels_for(left, "zh_hk")["title"])
        self.assertTrue(scene_problems(dict(left, n=0)))
        self.assertTrue(scene_problems(dict(left, mark=7)))
        self.assertTrue(scene_problems(dict(left, direction="up")))
        self.assertTrue(scene_problems(dict(left, mode="place")))
        words = [
            {"text": "Start", "start": 0.1},
            {"text": "First", "start": 1.2},
            {"text": "Second", "start": 1.8},
            {"text": "Third", "start": 2.4},
            {"text": "The", "start": 3.2},
        ]
        scheduled = schedule_marks(left, [1.0, 2.0, 1.2], words)
        self.assertEqual(len(scheduled[1]), 3)
        self.assertAlmostEqual(scheduled[1][0], 0.2, places=2)

    def test_track_stays_one_row_in_landscape_and_reads_left_to_right_in_portrait(self):
        values = list(range(21))
        self.assertEqual(track_columns(21, 1920, 1080), 21)
        land = track_slots(values, 21, left_to_right=False)
        self.assertEqual([land[n] for n in values], [(0, n) for n in values])
        cols = track_columns(21, 1080, 1920)
        self.assertEqual(cols, 6)
        rows = {}
        for n, (row, col) in track_slots(values, cols, left_to_right=True).items():
            rows.setdefault(row, []).append((col, n))
        laid = [[n for _col, n in sorted(rows[row])] for row in sorted(rows)]
        self.assertEqual(laid, [
            [0, 1, 2, 3, 4, 5],
            [6, 7, 8, 9, 10, 11],
            [12, 13, 14, 15, 16, 17],
            [18, 19, 20],
        ])

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

    def test_leaving_part_lands_on_the_spoken_numbers(self):
        words = [
            {"text": "Three", "start": 2.3},
            {"text": "Two", "start": 3.0},
            {"text": "Take", "start": 3.8},
            {"text": "two", "start": 4.2},
            {"text": "away", "start": 4.6},
            {"text": "three", "start": 5.1},
            {"text": "are", "start": 5.4},
            {"text": "left", "start": 5.7},
        ]
        beat = {
            "visual": "animated",
            "scene": "part_whole",
            "a": 3,
            "b": 2,
            "leave": "b",
            "s1_en": "Five is three and two.",
            "s2_en": "Three. Two.",
            "s3_en": "Take two away, three are left.",
            "s1_zh": "五是三加二。",
            "s2_zh": "三，二。",
            "s3_zh": "拿走两个，剩下三个。",
            "s1_zh_hk": "五係三加二。",
            "s2_zh_hk": "三，二。",
            "s3_zh_hk": "拿走兩個，剩低三個。",
        }
        durs = [2.0, 1.6, 2.4]
        scheduled = schedule_marks(beat, durs, words)
        self.assertEqual(len(scheduled[1]), 2)
        self.assertAlmostEqual(scheduled[1][1], 3.0 - 2.0, places=2)
        self.assertEqual(len(scheduled[2]), 2)
        self.assertAlmostEqual(scheduled[2][0], 4.2 - 3.6, places=2)
        self.assertAlmostEqual(scheduled[2][1], 5.1 - 3.6, places=2)
        zh = [
            {"text": "拿走", "start": 3.7},
            {"text": "两个", "start": 4.1},
            {"text": "剩下", "start": 4.6},
            {"text": "三个", "start": 5.0},
        ]
        found = removal_marks(zh, 3.6, 2.4, 2, 3)
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found[0], 0.5, places=2)
        self.assertAlmostEqual(found[1], 1.4, places=2)
        yue = [
            {"text": "拿走", "start": 3.7},
            {"text": "兩", "start": 4.05},
            {"text": "個", "start": 4.3},
            {"text": "剩", "start": 4.6},
            {"text": "低", "start": 4.8},
            {"text": "三", "start": 5.05},
            {"text": "個", "start": 5.3},
        ]
        found = removal_marks(yue, 3.6, 2.4, 2, 3)
        self.assertAlmostEqual(found[0], 0.45, places=2)
        self.assertAlmostEqual(found[1], 1.45, places=2)
        take_none = [
            {"text": "Take", "start": 3.7},
            {"text": "zero", "start": 4.15},
            {"text": "away", "start": 4.5},
            {"text": "Four", "start": 5.05},
        ]
        found = removal_marks(take_none, 3.6, 2.4, 0, 4)
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found[0], 0.55, places=2)
        self.assertAlmostEqual(found[1], 1.45, places=2)
        take_all = [
            {"text": "拿走", "start": 3.7},
            {"text": "四个", "start": 4.1},
            {"text": "剩下", "start": 4.6},
            {"text": "零个", "start": 5.05},
        ]
        found = removal_marks(take_all, 3.6, 2.4, 4, 0)
        self.assertAlmostEqual(found[0], 0.5, places=2)
        self.assertAlmostEqual(found[1], 1.45, places=2)
        none_left = [
            {"text": "Take", "start": 3.7},
            {"text": "all", "start": 3.95},
            {"text": "four", "start": 4.2},
            {"text": "away", "start": 4.5},
            {"text": "None", "start": 5.05},
            {"text": "are", "start": 5.3},
            {"text": "left", "start": 5.55},
        ]
        found = removal_marks(none_left, 3.6, 2.4, 4, 0)
        self.assertAlmostEqual(found[0], 0.6, places=2)
        self.assertAlmostEqual(found[1], 1.45, places=2)

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


class PairCountersTest(unittest.TestCase):
    def _beat(self, n: int) -> dict:
        return {
            "visual": "animated",
            "scene": "pair_counters",
            "n": n,
            "s1_en": "Count.",
            "s2_en": "One.",
            "s3_en": "Done.",
            "s1_zh": "数。",
            "s2_zh": "一。",
            "s3_zh": "好。",
            "s1_zh_hk": "數。",
            "s2_zh_hk": "一。",
            "s3_zh_hk": "好。",
        }

    def test_pair_counters_bounds_and_labels(self):
        eight = self._beat(8)
        self.assertEqual(scene_problems(eight), [])
        self.assertEqual(scene_problems(self._beat(0)), [])
        self.assertEqual(scene_problems(self._beat(20)), [])
        self.assertTrue(scene_problems(self._beat(21)))
        self.assertTrue(scene_problems(self._beat(-1)))
        self.assertTrue(scene_problems({"visual": "animated", "scene": "pair_counters"}))
        self.assertTrue(scene_problems(self._beat(1.5)))
        self.assertEqual(count_event(eight), (1, 4))
        self.assertEqual(count_event(self._beat(9)), (1, 4))
        self.assertEqual(count_event(self._beat(19)), (1, 9))
        self.assertIsNone(count_event(self._beat(0)))
        self.assertIsNone(count_event(self._beat(1)))
        self.assertEqual(labels_for(eight, "en")["pairs"], ["1", "2", "3", "4"])
        self.assertEqual(labels_for(eight, "zh")["pairs"], ["一", "二", "三", "四"])
        self.assertEqual(labels_for(eight, "zh_hk")["pairs"], ["一", "二", "三", "四"])
        self.assertEqual(labels_for(eight, "en")["answer"], "Even")
        self.assertEqual(labels_for(eight, "en")["note"], "All in pairs")
        self.assertEqual(labels_for(eight, "zh")["note"], "全部配成对")
        self.assertEqual(labels_for(eight, "zh_hk")["note"], "全部配成對")
        self.assertEqual(labels_for(self._beat(9), "en")["note"], "One left over")
        self.assertEqual(labels_for(eight, "zh")["answer"], "双数")
        self.assertEqual(labels_for(self._beat(9), "zh_hk")["answer"], "單數")
        self.assertEqual(labels_for(self._beat(9), "zh_hk")["note"], "剩低一個")
        self.assertEqual(labels_for(self._beat(9), "en")["leftover"], 1)
        self.assertEqual(labels_for(self._beat(20), "en")["pair_count"], 10)
        trad = _label_text(labels_for(self._beat(19), "zh_hk"))
        self.assertEqual(sorted({ch for ch in trad if ch in LEAK}), [])
        self.assertNotEqual(
            labels_for(eight, "zh")["title"],
            labels_for(eight, "zh_hk")["title"],
        )
        hook = {
            "visual": "animated",
            "scene": "lesson_hook",
            "motif": "pairs",
            "title_en": "Make pairs",
            "s1_en": "Can every counter find a partner?",
            "s1_zh": "每个圆片都能找到伙伴吗？",
            "s1_zh_hk": "每個圓片都搵到伙伴嗎？",
        }
        self.assertEqual(scene_problems(hook), [])
        self.assertEqual(labels_for(hook, "en")["n"], 8)
        self.assertTrue(scene_problems(dict(hook, n=21)))
        recap = {
            "visual": "animated",
            "scene": "lesson_takeaway",
            "motif": "pairs",
            "n": 8,
            "also": 19,
            "s1_en": "Eight.",
            "s2_en": "Nine.",
            "s3_en": "Two.",
            "s4_en": "Nineteen.",
            "s1_zh": "八。",
            "s2_zh": "九。",
            "s3_zh": "二。",
            "s4_zh": "十九。",
            "s1_zh_hk": "八。",
            "s2_zh_hk": "九。",
            "s3_zh_hk": "二。",
            "s4_zh_hk": "十九。",
        }
        self.assertEqual(scene_problems(recap), [])
        self.assertEqual(labels_for(recap, "zh")["also_word"], "十九")
        self.assertTrue(scene_problems(dict(recap, also=21)))
        words = [
            {"text": "Eight", "start": 0.2},
            {"text": "One", "start": 1.4},
            {"text": "Two", "start": 1.9},
            {"text": "Three", "start": 2.4},
            {"text": "Four", "start": 2.9},
            {"text": "Four", "start": 3.6},
        ]
        scheduled = schedule_marks(eight, [1.2, 2.2, 1.4], words)
        self.assertEqual(len(scheduled[1]), 4)
        self.assertAlmostEqual(scheduled[1][0], 0.2, places=2)

    def test_pair_labels_keep_a_gap(self):
        """Adjacent pair labels stay at least 12px apart, in every language and aspect."""
        import shutil
        import subprocess
        import tempfile

        from PIL import Image

        from anim import render_animated_clip

        try:
            require_manim()
        except ManimNotInstalled:
            self.skipTest("Manim is optional")
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg is optional")

        frames = ((1280, 720), (720, 1280))
        with tempfile.TemporaryDirectory(prefix="vf-pair-gap-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            subprocess.check_call(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", "4", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            for n in (8, 19):
                beat = self._beat(n)
                for lang in ("en", "zh", "zh_hk"):
                    for frame in frames:
                        dest = root / f"{n}-{lang}-{frame[0]}.mp4"
                        render_animated_clip(
                            beat, {"format": "9:16" if frame[1] > frame[0] else "16:9"},
                            label_lang_code=lang,
                            holds=[0.35, 1.5, 0.45], still_idx=[0, 1, 2],
                            pages=["a", "b", "c"],
                            audio=audio, dest=dest, cache_dir=root / "cache",
                            captions=False, progress_bar=False, frame=frame, fps=8,
                        )
                        silent = max((root / "cache" / lang).glob("*.mp4"), key=lambda p: p.stat().st_mtime)
                        shot = root / f"{n}-{lang}-{frame[0]}.png"
                        duration = float(subprocess.check_output(
                            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "csv=p=0", str(silent)],
                            text=True,
                        ))
                        last = max(0, int(duration * 8) - 1)
                        subprocess.check_call(
                            ["ffmpeg", "-y", "-i", str(silent),
                             "-vf", f"select=eq(n\\,{last})", "-frames:v", "1", str(shot)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        )
                        need = 12.0 * frame[0] / (1080.0 if frame[1] > frame[0] else 1920.0)
                        gaps = self._pair_label_gaps(shot, n // 2)
                        self.assertTrue(gaps, shot.name)
                        self.assertGreaterEqual(min(gaps), need, f"{shot.name} {gaps}")
                        if lang in {"zh", "zh_hk"}:
                            for row in _label_row_centres(shot):
                                self.assertGreaterEqual(len(row), 2, shot.name)
                                self.assertLessEqual(
                                    max(row) - min(row), 1.0,
                                    f"{shot.name} centres {row}",
                                )
                        if n == 8 and lang == "en" and frame == (1280, 720):
                            early = root / "early.png"
                            late = root / "late.png"
                            subprocess.check_call(
                                ["ffmpeg", "-y", "-i", str(silent),
                                 "-vf", "select=eq(n\\,6)", "-frames:v", "1", str(early)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            )
                            subprocess.check_call(
                                ["ffmpeg", "-y", "-i", str(silent),
                                 "-vf", "select=eq(n\\,14)", "-frames:v", "1", str(late)],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            )
                            self.assertLess(self._gold_x(early), self._gold_x(late) - 8)

    def _pair_label_gaps(self, path, pairs: int) -> list[float]:
        """Horizontal gaps between pair-count labels that share a row.

        The labels sit in the band just above each row of green counters.
        Strokes inside one glyph are merged, so the hole in a 4 is not a gap.
        """
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()

        def dark(x, y):
            r, g, b = px[x, y]
            return r < 90 and g < 110 and b < 130 and (r + g + b) < 280

        def green(x, y):
            r, g, b = px[x, y]
            return g > 120 and g > r + 40 and g > b + 20

        rows = []
        y = 0
        while y < h:
            if sum(1 for x in range(0, w, 3) if green(x, y)) < 4:
                y += 1
                continue
            y0 = y
            while y < h and sum(1 for x in range(0, w, 3) if green(x, y)) >= 3:
                y += 1
            rows.append((y0, y - 1))
            y += 1
        gaps = []
        window = max(18, int(56 * h / 720))
        for y0, _y1 in rows:
            band_top = max(0, y0 - window)
            band_bot = max(0, y0 - 2)
            if band_bot <= band_top:
                continue
            runs = []
            x = 0
            while x < w:
                if not any(dark(x, yy) for yy in range(band_top, band_bot + 1)):
                    x += 1
                    continue
                x0 = x
                while x < w and any(dark(x, yy) for yy in range(band_top, band_bot + 1)):
                    x += 1
                runs.append((x0, x - 1))
            merged = []
            for run in runs:
                if merged and run[0] - merged[-1][1] <= 10:
                    merged[-1] = (merged[-1][0], run[1])
                else:
                    merged.append(run)
            for (a0, a1), (b0, _b1) in zip(merged, merged[1:]):
                gaps.append(b0 - a1 - 1)
        self.assertGreaterEqual(len(gaps), 1, f"{path.name} rows {rows}")
        return gaps

    def _gold_x(self, path):
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        pts = []
        px = img.load()
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                r, g, b = px[x, y]
                if r > 190 and r > g + 12 and g > b + 30:
                    pts.append(x)
        self.assertGreater(len(pts), 8, path.name)
        return sum(pts) / len(pts)


class PartWholeRenderTest(unittest.TestCase):
    """Part labels stay inside the frame, clear of each other, and on one centre line."""

    def test_part_labels_align_and_stay_inside(self):
        import shutil
        import subprocess
        import tempfile

        from anim import render_animated_clip

        try:
            require_manim()
        except ManimNotInstalled:
            self.skipTest("Manim is optional")
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg is optional")

        frames = ((1280, 720), (720, 1280))
        cases = []
        for lang in ("en", "zh", "zh_hk"):
            for frame in frames:
                cases.append((1, 2, None, "", lang, frame))
        for frame in frames:
            cases.append((4, 8, None, "", "en", frame))
        cases.append((3, 4, 5, "", "en", (1280, 720)))
        cases.append((3, 4, 5, "", "en", (720, 1280)))
        cases.append((4, 8, None, "b", "zh", (1280, 720)))
        with tempfile.TemporaryDirectory(prefix="vf-part-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            subprocess.check_call(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", "4", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            for a, b, also, cover, lang, frame in cases:
                beat = self._beat(a, b, also, cover)
                dest = root / f"{a}-{b}-{also}-{cover}-{lang}-{frame[0]}.mp4"
                render_animated_clip(
                    beat, {"format": "9:16" if frame[1] > frame[0] else "16:9"},
                    label_lang_code=lang,
                    holds=[0.4, 1.6, 0.5], still_idx=[0, 1, 2],
                    pages=["a", "b", "c"],
                    audio=audio, dest=dest, cache_dir=root / "cache",
                    captions=False, progress_bar=False, frame=frame, fps=8,
                )
                silent = max((root / "cache" / lang).glob("*.mp4"), key=lambda p: p.stat().st_mtime)
                shot = root / f"{a}-{b}-{cover}-{lang}-{frame[0]}.png"
                duration = float(subprocess.check_output(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", str(silent)],
                    text=True,
                ))
                last = max(0, int(duration * 8) - 1)
                subprocess.check_call(
                    ["ffmpeg", "-y", "-i", str(silent),
                     "-vf", f"select=eq(n\\,{last})", "-frames:v", "1", str(shot)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self._assert_inside(shot)
                if not cover:
                    need = 12.0 * frame[0] / (1080.0 if frame[1] > frame[0] else 1920.0)
                    gaps = self._label_gaps(shot)
                    self.assertTrue(gaps, shot.name)
                    self.assertGreaterEqual(min(gaps), need, f"{shot.name} {gaps}")
                if lang in {"zh", "zh_hk"} and not cover:
                    centres = _label_row_centres(shot)
                    self.assertTrue(centres, shot.name)
                    for row in centres:
                        self.assertGreaterEqual(len(row), 2, shot.name)
                        self.assertLessEqual(max(row) - min(row), 1.0, f"{shot.name} centres {row}")
                if also is not None:
                    self._assert_counters_one_row(shot, greens=also, golds=a + b - also)
                if cover:
                    self._assert_minus_matches_equals(shot)
                if a == 1 and lang == "en" and frame == (1280, 720):
                    early = root / "early.png"
                    late = root / "late.png"
                    subprocess.check_call(
                        ["ffmpeg", "-y", "-i", str(silent),
                         "-vf", "select=eq(n\\,8)", "-frames:v", "1", str(early)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    subprocess.check_call(
                        ["ffmpeg", "-y", "-i", str(silent),
                         "-vf", "select=eq(n\\,14)", "-frames:v", "1", str(late)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    self.assertLess(self._highlight_x(early), self._highlight_x(late) - 8)

    def _beat(self, a, b, also, cover):
        beat = {
            "visual": "animated",
            "scene": "part_whole",
            "a": a,
            "b": b,
            "s1_en": "Two mats.",
            "s2_en": "One. Two.",
            "s3_en": "Together.",
            "s1_zh": "两个圆片。",
            "s2_zh": "一，二。",
            "s3_zh": "合在一起。",
            "s1_zh_hk": "兩個圓片。",
            "s2_zh_hk": "一，二。",
            "s3_zh_hk": "合埋一齊。",
        }
        if also is not None:
            beat["also"] = also
        if cover:
            beat["cover"] = cover
        return beat

    def _assert_inside(self, path):
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()
        inset = 2

        def cream(x, y):
            r, g, b = px[x, y]
            return abs(r - 247) < 18 and abs(g - 244) < 18 and abs(b - 238) < 18

        for x, y in (
            *[(x, y) for x in range(w) for y in range(inset)],
            *[(x, y) for x in range(w) for y in range(h - inset, h)],
            *[(x, y) for y in range(h) for x in range(inset)],
            *[(x, y) for y in range(h) for x in range(w - inset, w)],
        ):
            self.assertTrue(cream(x, y), f"{path.name} ink at {x},{y}")

    def _label_gaps(self, path):
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()

        def dark(x, y):
            r, g, b = px[x, y]
            return r < 90 and g < 110 and b < 130 and (r + g + b) < 280

        def green(x, y):
            r, g, b = px[x, y]
            return g > 120 and g > r + 40 and g > b + 20

        y = 0
        y0 = None
        while y < h:
            if sum(1 for x in range(0, w, 3) if green(x, y)) >= 4:
                y0 = y
                break
            y += 1
        self.assertIsNotNone(y0, path.name)
        window = max(24, int(46 * h / 720))
        band_bot = max(0, y0 - 6)
        band_top = max(0, y0 - window)
        runs = []
        x = 0
        while x < w:
            if not any(dark(x, yy) for yy in range(band_top, band_bot + 1)):
                x += 1
                continue
            x0 = x
            while x < w and any(dark(x, yy) for yy in range(band_top, band_bot + 1)):
                x += 1
            runs.append((x0, x - 1))
        merged = []
        for run in runs:
            if merged and run[0] - merged[-1][1] <= 16:
                merged[-1] = (merged[-1][0], run[1])
            else:
                merged.append(run)
        return [b0 - a1 - 1 for (a0, a1), (b0, _b1) in zip(merged, merged[1:])]

    def _highlight_x(self, path):
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()

        def green(x, y):
            r, g, b = px[x, y]
            return g > 120 and g > r + 40 and g > b + 20

        y = 0
        y0 = None
        while y < h:
            if sum(1 for x in range(0, w, 3) if green(x, y)) >= 4:
                y0 = y
                break
            y += 1
        window = max(24, int(46 * h / 720))
        band_bot = max(0, y0 - 6)
        band_top = max(0, y0 - window)
        pts = []
        for yy in range(band_top, band_bot + 1):
            for x in range(w):
                r, g, b = px[x, yy]
                if r > 190 and r > g + 12 and g > b + 30:
                    pts.append(x)
        self.assertGreater(len(pts), 8, path.name)
        return sum(pts) / len(pts)

    def test_leaving_counters_follow_the_words_and_leave_empty_circles(self):
        import shutil
        import subprocess
        import tempfile

        from anim import render_animated_clip

        try:
            require_manim()
        except ManimNotInstalled:
            self.skipTest("Manim is optional")
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg is optional")
        beat = self._beat(3, 2, None, "")
        beat["leave"] = "b"
        beat["s2_en"] = "Three. Two."
        beat["s3_en"] = "Take two away, three are left."
        words = [
            {"text": "Three", "start": 0.55},
            {"text": "Two", "start": 0.9},
            {"text": "Take", "start": 1.4},
            {"text": "two", "start": 1.9},
            {"text": "away", "start": 2.2},
            {"text": "three", "start": 2.7},
            {"text": "are", "start": 3.0},
            {"text": "left", "start": 3.3},
        ]
        holds = [0.4, 0.8, 2.4]
        with tempfile.TemporaryDirectory(prefix="vf-leave-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            subprocess.check_call(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", "4", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            for frame in ((1280, 720), (720, 1280)):
                dest = root / f"leave-{frame[0]}.mp4"
                render_animated_clip(
                    beat, {"format": "9:16" if frame[1] > frame[0] else "16:9"},
                    label_lang_code="en",
                    holds=holds, still_idx=[0, 1, 2], pages=["a", "b", "c"],
                    audio=audio, dest=dest, cache_dir=root / "cache",
                    captions=False, progress_bar=False, frame=frame, fps=8,
                    words=words,
                )
                silent = max((root / "cache" / "en").glob("*.mp4"), key=lambda p: p.stat().st_mtime)
                early = root / f"early-{frame[0]}.png"
                shot = root / f"leave-{frame[0]}.png"
                duration = float(subprocess.check_output(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", str(silent)],
                    text=True,
                ))
                last = max(0, int(duration * 8) - 1)
                for n, path in ((10, early), (last, shot)):
                    subprocess.check_call(
                        ["ffmpeg", "-y", "-i", str(silent),
                         "-vf", f"select=eq(n\\,{n})", "-frames:v", "1", str(path)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                self._assert_inside(early)
                self._assert_inside(shot)
                self._assert_counters_one_row(early, greens=3, golds=2)
                self._assert_counters_one_row(shot, greens=3, golds=0)
                if frame[0] > frame[1]:
                    self._assert_minus_matches_equals(shot)
                self._assert_empty_circles(shot, 2)

        recap = {
            "visual": "animated",
            "scene": "lesson_takeaway",
            "motif": "parts",
            "bonds": [[3, -2]],
            "title_en": "Five stays five?",
            "s1_en": "Five minus two is three.",
            "s2_en": "Three stay.",
            "s3_en": "Two are gone.",
            "s1_zh": "五减二是三。",
            "s2_zh": "剩下三个。",
            "s3_zh": "拿走两个。",
            "s1_zh_hk": "五減二係三。",
            "s2_zh_hk": "剩低三個。",
            "s3_zh_hk": "拿走兩個。",
        }
        with tempfile.TemporaryDirectory(prefix="vf-gone-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            subprocess.check_call(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", "2", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            for frame in ((1280, 720), (720, 1280)):
                dest = root / f"gone-{frame[0]}.mp4"
                render_animated_clip(
                    recap, {"format": "9:16" if frame[1] > frame[0] else "16:9"},
                    label_lang_code="en",
                    holds=[0.4, 0.4, 0.5], still_idx=[0, 1, 2], pages=["a", "b", "c"],
                    audio=audio, dest=dest, cache_dir=root / "cache",
                    captions=False, progress_bar=False, frame=frame, fps=8,
                )
                silent = max((root / "cache" / "en").glob("*.mp4"), key=lambda p: p.stat().st_mtime)
                shot = root / f"gone-{frame[0]}.png"
                last = max(0, int(float(subprocess.check_output(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", str(silent)],
                    text=True,
                )) * 8) - 1)
                subprocess.check_call(
                    ["ffmpeg", "-y", "-i", str(silent),
                     "-vf", f"select=eq(n\\,{last})", "-frames:v", "1", str(shot)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self._assert_inside(shot)
                self._assert_counters_one_row(shot, greens=3, golds=0)
                self._assert_empty_circles(shot, 2)

    def _assert_empty_circles(self, path, count: int):
        """Empty circles sit on the green row: a cream centre between two strokes."""
        from PIL import Image

        def green(rgb):
            r, g, b = rgb
            return g > 130 and g > r + 45 and g > b + 25

        def cream(rgb):
            r, g, b = rgb
            return abs(r - 247) < 22 and abs(g - 244) < 22 and abs(b - 238) < 22

        gblobs, w, h = self._blobs(path, green)
        self.assertEqual(len(gblobs), 3, path.name)
        diam = max(blob[3] for blob in gblobs)
        mean_y = int(sum(blob[1] for blob in gblobs) / len(gblobs))
        right = max(blob[0] + blob[2] / 2 for blob in gblobs)
        img = Image.open(path).convert("RGB")
        px = img.load()
        dark_runs = []
        x = int(right + diam * 0.25)
        limit = min(w, int(right + diam * (count + 2) * 1.8))
        while x < limit:
            if cream(px[x, mean_y]) or green(px[x, mean_y]):
                x += 1
                continue
            x0 = x
            while x < limit and not cream(px[x, mean_y]) and not green(px[x, mean_y]):
                x += 1
            if x - x0 > diam * 0.45:
                break
            dark_runs.append((x0, x - 1))
        pairs = 0
        used = set()
        for i, (a0, a1) in enumerate(dark_runs):
            if i in used:
                continue
            for j in range(i + 1, len(dark_runs)):
                b0, b1 = dark_runs[j]
                gap = b0 - a1 - 1
                if diam * 0.35 <= gap <= diam * 1.35:
                    mid = (a1 + b0) // 2
                    if cream(px[mid, mean_y]):
                        pairs += 1
                        used.add(i)
                        used.add(j)
                        break
        self.assertGreaterEqual(pairs, count, f"{path.name} strokes {dark_runs} diam {diam:.0f}")

    def test_zero_part_is_a_mat_and_taking_all_leaves_empty_circles(self):
        """Zero is an empty mat. Taking nothing leaves the four. Taking all leaves empty circles."""
        import shutil
        import subprocess
        import tempfile

        from anim import render_animated_clip

        try:
            require_manim()
        except ManimNotInstalled:
            self.skipTest("Manim is optional")
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg is optional")

        def render(beat, frame, lang, holds, words=None):
            dest = root / f"out-{frame[0]}-{lang}.mp4"
            render_animated_clip(
                beat, {"format": "9:16" if frame[1] > frame[0] else "16:9"},
                label_lang_code=lang,
                holds=holds, still_idx=list(range(len(holds))),
                pages=[str(i) for i in range(len(holds))],
                audio=audio, dest=dest, cache_dir=root / "cache",
                captions=False, progress_bar=False, frame=frame, fps=8,
                words=words,
            )
            silent = max((root / "cache" / lang).glob("*.mp4"), key=lambda p: p.stat().st_mtime)
            duration = float(subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(silent)],
                text=True,
            ))
            return silent, max(0, int(duration * 8) - 1)

        def grab(silent, n, path):
            subprocess.check_call(
                ["ffmpeg", "-y", "-i", str(silent),
                 "-vf", f"select=eq(n\\,{n})", "-frames:v", "1", str(path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

        join = self._beat(0, 4, None, "")
        join["s2_en"] = "Zero. Four."
        join["s2_zh"] = "零，四。"
        join["s2_zh_hk"] = "零，四。"
        stay = self._beat(4, 0, None, "")
        stay["leave"] = "b"
        stay["s3_en"] = "Take away zero. Four are left."
        gone = self._beat(4, 0, None, "")
        gone["leave"] = "a"
        gone["s3_en"] = "Take four away, zero are left."
        words = [
            {"text": "Four", "start": 0.55},
            {"text": "Zero", "start": 0.95},
            {"text": "Take", "start": 1.45},
            {"text": "four", "start": 1.9},
            {"text": "away", "start": 2.2},
            {"text": "zero", "start": 2.7},
            {"text": "are", "start": 3.0},
            {"text": "left", "start": 3.3},
        ]
        with tempfile.TemporaryDirectory(prefix="vf-zero-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            subprocess.check_call(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", "4", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            for frame in ((1280, 720), (720, 1280)):
                silent, last = render(join, frame, "en", [0.4, 1.2, 0.6])
                shot = root / f"join-{frame[0]}.png"
                grab(silent, last, shot)
                self._assert_inside(shot)
                self._assert_gold_row(shot, 4)
                self._assert_white_mat(shot)
            added = self._beat(4, 0, None, "")
            for frame in ((1280, 720), (720, 1280)):
                silent, last = render(added, frame, "zh", [0.4, 1.2, 0.6])
                shot = root / f"add-zh-{frame[0]}.png"
                grab(silent, last, shot)
                self._assert_inside(shot)
                self._assert_counters_one_row(shot, greens=4, golds=0)
                self._assert_white_mat(shot)
                # The empty mat's top stroke sits in the usual label band.
                centres = _label_row_centres(shot, clearance=18)
                self.assertTrue(centres, shot.name)
                for row in centres:
                    self.assertGreaterEqual(len(row), 2, shot.name)
                    self.assertLessEqual(max(row) - min(row), 1.0, f"{shot.name} centres {row}")
            for frame in ((1280, 720), (720, 1280)):
                silent, last = render(stay, frame, "en", [0.4, 0.8, 1.6])
                shot = root / f"stay-{frame[0]}.png"
                grab(silent, last, shot)
                self._assert_inside(shot)
                self._assert_counters_one_row(shot, greens=4, golds=0)
                self._assert_white_mat(shot)
                if frame[0] > frame[1]:
                    self._assert_minus_matches_equals(shot)
            for frame in ((1280, 720), (720, 1280)):
                silent, last = render(gone, frame, "en", [0.4, 0.8, 2.4], words=words)
                shot = root / f"all-{frame[0]}.png"
                grab(silent, last, shot)
                self._assert_inside(shot)
                self._assert_no_green(shot)
                self.assertGreaterEqual(self._ring_pairs(shot), 4, shot.name)

    def _assert_gold_row(self, path, count: int):
        def gold(rgb):
            r, g, b = rgb
            return r > 180 and r > g + 15 and g > 90 and b < 150

        blobs, _w, _h = self._blobs(path, gold)
        rounds = [blob for blob in blobs if blob[3] >= 8 and 0.65 <= blob[2] / max(blob[3], 1) <= 1.55]
        self.assertGreaterEqual(len(rounds), count, path.name)
        best = []
        for blob in rounds:
            # The highlight around a one-digit label is nearly square and sits
            # above the row. Counters are the largest cluster on one line.
            group = [
                other for other in rounds
                if abs(other[1] - blob[1]) <= max(8.0, blob[3] * 0.45)
            ]
            if len(group) > len(best):
                best = group
        self.assertEqual(len(best), count, path.name)
        ys = [blob[1] for blob in best]
        diam = max(blob[3] for blob in best)
        self.assertLessEqual(max(ys) - min(ys), max(6.0, diam * 0.35), path.name)

    def _assert_white_mat(self, path):
        def white(rgb):
            r, g, b = rgb
            return r > 248 and g > 248 and b > 248

        blobs, _w, _h = self._blobs(path, white)
        mats = [blob for blob in blobs if blob[2] > 16 and blob[2] > blob[3] * 1.15]
        self.assertGreaterEqual(len(mats), 1, path.name)

    def _assert_no_green(self, path):
        def green(rgb):
            r, g, b = rgb
            return g > 130 and g > r + 45 and g > b + 25

        blobs, _w, _h = self._blobs(path, green)
        self.assertEqual(blobs, [], path.name)

    def _ring_pairs(self, path) -> int:
        """How many cream-centred rings share one horizontal line."""
        from PIL import Image

        def cream(rgb):
            r, g, b = rgb
            return abs(r - 247) < 22 and abs(g - 244) < 22 and abs(b - 238) < 22

        def navy(rgb):
            r, g, b = rgb
            return r < 80 and g < 100 and b < 130 and not cream(rgb)

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()
        best = 0
        for y in range(int(h * 0.30), int(h * 0.72), 2):
            runs = []
            x = 0
            while x < w:
                if not navy(px[x, y]):
                    x += 1
                    continue
                x0 = x
                while x < w and navy(px[x, y]):
                    x += 1
                if 2 <= x - x0 <= 18:
                    runs.append((x0, x - 1))
            pairs = 0
            used = set()
            for i, (a0, a1) in enumerate(runs):
                if i in used:
                    continue
                for j in range(i + 1, min(i + 4, len(runs))):
                    b0, b1 = runs[j]
                    gap = b0 - a1 - 1
                    if 6 <= gap <= 48 and cream(px[(a1 + b0) // 2, y]):
                        pairs += 1
                        used.add(i)
                        used.add(j)
                        break
            best = max(best, pairs)
        return best

    def test_parts_hook_title_fills_the_frame(self):
        """9:16 English hook title stays at the takeaway floor, on two lines, with a full-width motif."""
        import shutil
        import subprocess
        import tempfile

        from anim import render_animated_clip

        try:
            require_manim()
        except ManimNotInstalled:
            self.skipTest("Manim is optional")
        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg is optional")
        beat = {
            "visual": "animated",
            "scene": "lesson_hook",
            "motif": "parts",
            "a": 3,
            "b": 4,
            "title_en": "Make parts before adding",
            "title_zh": "先分开，再加",
            "title_zh_hk": "先分開，再加",
            "s1_en": "What parts make seven?",
            "s1_zh": "七可以分成哪两部分？",
            "s1_zh_hk": "七可以分成邊兩部分？",
        }
        with tempfile.TemporaryDirectory(prefix="vf-hook-") as tmp:
            root = Path(tmp)
            audio = root / "silent.wav"
            subprocess.check_call(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                 "-t", "2", "-c:a", "pcm_s16le", str(audio)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            for frame in ((1280, 720), (720, 1280)):
                dest = root / f"hook-{frame[0]}.mp4"
                render_animated_clip(
                    beat, {"format": "9:16" if frame[1] > frame[0] else "16:9"},
                    label_lang_code="en",
                    holds=[1.2], still_idx=[0], pages=["a"],
                    audio=audio, dest=dest, cache_dir=root / "cache",
                    captions=False, progress_bar=False, frame=frame, fps=8,
                )
                silent = max((root / "cache" / "en").glob("*.mp4"), key=lambda p: p.stat().st_mtime)
                shot = root / f"hook-{frame[0]}.png"
                last = max(0, int(float(subprocess.check_output(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", str(silent)],
                    text=True,
                )) * 8) - 1)
                subprocess.check_call(
                    ["ffmpeg", "-y", "-i", str(silent),
                     "-vf", f"select=eq(n\\,{last})", "-frames:v", "1", str(shot)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self._assert_hook(shot, frame)

    def _blobs(self, path, pred):
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()
        seen = set()
        blobs = []
        step = 2
        for y in range(0, h, step):
            for x in range(0, w, step):
                if (x, y) in seen or not pred(px[x, y]):
                    continue
                stack = [(x, y)]
                xs, ys = [], []
                while stack:
                    cx, cy = stack.pop()
                    if cx < 0 or cy < 0 or cx >= w or cy >= h or (cx, cy) in seen:
                        continue
                    if not pred(px[cx, cy]):
                        continue
                    seen.add((cx, cy))
                    xs.append(cx)
                    ys.append(cy)
                    stack.extend(((cx + step, cy), (cx - step, cy), (cx, cy + step), (cx, cy - step)))
                if len(xs) < 18:
                    continue
                blobs.append(
                    (sum(xs) / len(xs), sum(ys) / len(ys), max(xs) - min(xs), max(ys) - min(ys))
                )
        return blobs, w, h

    def _assert_counters_one_row(self, path, greens: int, golds: int):
        def green(rgb):
            r, g, b = rgb
            return g > 130 and g > r + 45 and g > b + 25

        def gold(rgb):
            r, g, b = rgb
            return r > 180 and r > g + 15 and g > 90 and b < 150

        gblobs, _w, _h = self._blobs(path, green)
        yblobs, _w, _h = self._blobs(path, gold)
        self.assertEqual(len(gblobs), greens, f"{path.name} green {[(round(b[0]), round(b[1])) for b in gblobs]}")
        ys = [blob[1] for blob in gblobs]
        diam = max(blob[3] for blob in gblobs)
        self.assertLessEqual(max(ys) - min(ys), max(6.0, diam * 0.35), path.name)
        mean_y = sum(ys) / len(ys)
        near = [
            blob for blob in yblobs
            if abs(blob[1] - mean_y) <= max(8.0, diam * 0.45) and blob[3] >= diam * 0.55
        ]
        self.assertEqual(len(near), golds, f"{path.name} gold {[(round(b[0]), round(b[1])) for b in yblobs]}")
        if golds == 0:
            return
        gold_y = [blob[1] for blob in near]
        self.assertLessEqual(max(gold_y) - min(gold_y), max(6.0, diam * 0.35), path.name)
        self.assertLessEqual(abs(sum(gold_y) / len(gold_y) - mean_y), max(6.0, diam * 0.35), path.name)

    def _assert_minus_matches_equals(self, path):
        """The minus is a short horizontal bar as wide as each bar of '='."""
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()

        def navy(x, y):
            r, g, b = px[x, y]
            return r < 80 and g < 100 and b < 140 and (r + g + b) < 260

        seen = set()
        widths = []
        for y in range(h):
            for x in range(w):
                if (x, y) in seen or not navy(x, y):
                    continue
                stack = [(x, y)]
                xs, ys = [], []
                while stack:
                    cx, cy = stack.pop()
                    if cx < 0 or cy < 0 or cx >= w or cy >= h or (cx, cy) in seen or not navy(cx, cy):
                        continue
                    seen.add((cx, cy))
                    xs.append(cx)
                    ys.append(cy)
                    stack.extend(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)))
                bw = max(xs) - min(xs) + 1
                bh = max(ys) - min(ys) + 1
                # Operator bars only. The cover card and the bracket are much wider.
                if bh <= max(6, int(0.012 * h)) and 0.02 * w <= bw <= 0.08 * w:
                    widths.append(bw)
        self.assertGreaterEqual(len(widths), 3, f"{path.name} operator bars {widths}")
        self.assertGreaterEqual(min(widths), 0.8 * max(widths), f"{path.name} bar widths {widths}")

    def _assert_hook(self, path, frame):
        from PIL import Image

        img = Image.open(path).convert("RGB")
        w, h = img.size
        px = img.load()
        portrait = frame[1] > frame[0]
        floor = (52.0 if portrait else 44.0) * (h / (1920.0 if portrait else 1080.0))

        def text_ink(x, y):
            r, g, b = px[x, y]
            if not (r < 80 and g < 100 and b < 140 and (r + g + b) < 260):
                return False
            for dy in (-4, 0, 4):
                for dx in (-4, 0, 4):
                    xx, yy = x + dx, y + dy
                    if xx < 0 or yy < 0 or xx >= w or yy >= h:
                        continue
                    rr, gg, bb = px[xx, yy]
                    if gg > 120 and gg > rr + 40:
                        return False
                    if rr > 180 and rr > gg + 15 and bb < 150:
                        return False
            return True

        bands = []
        y = 0
        while y < int(h * 0.72):
            xs = [x for x in range(0, w, 2) if text_ink(x, y)]
            if len(xs) >= 8:
                y0 = y
                left, right = min(xs), max(xs)
                while y < int(h * 0.72):
                    xs = [x for x in range(0, w, 2) if text_ink(x, y)]
                    if len(xs) < 8:
                        break
                    left = min(left, min(xs))
                    right = max(right, max(xs))
                    y += 1
                bands.append((y0, y - 1, left, right))
            else:
                y += 1
        # Drop a hairline gap inside one glyph.
        merged = []
        for band in bands:
            if merged and band[0] - merged[-1][1] <= 3:
                prev = merged[-1]
                merged[-1] = (prev[0], band[1], min(prev[2], band[2]), max(prev[3], band[3]))
            else:
                merged.append(band)
        self.assertGreaterEqual(len(merged), 2, f"{path.name} bands {merged}")
        title_bands = sorted(merged, key=lambda band: band[3] - band[2], reverse=True)
        if portrait:
            title_bands = title_bands[:2]
            self.assertGreaterEqual(len(merged), 3, f"{path.name} expected a tag and two title lines {merged}")
        else:
            title_bands = title_bands[:1]
        for band in title_bands:
            self.assertGreaterEqual(band[1] - band[0] + 1, floor - 2, f"{path.name} title {band} floor {floor:.1f}")
        if portrait and len(title_bands) == 2:
            mid_a = (title_bands[0][2] + title_bands[0][3]) / 2
            mid_b = (title_bands[1][2] + title_bands[1][3]) / 2
            self.assertLessEqual(abs(mid_a - mid_b), 8, path.name)
            tag = min(merged, key=lambda band: band[0])
            title_h = min(band[1] - band[0] + 1 for band in title_bands)
            self.assertGreaterEqual(tag[1] - tag[0] + 1, title_h * 0.7, f"{path.name} tag {tag}")
        def coloured(x, y):
            r, g, b = px[x, y]
            green = g > 130 and g > r + 45 and g > b + 25
            gold = r > 180 and r > g + 15 and g > 90 and b < 150 and y > h * 0.2
            return green or gold
        xs = [x for y in range(0, h, 2) for x in range(0, w, 2) if coloured(x, y)]
        self.assertGreater(len(xs), 20, path.name)
        span = max(xs) - min(xs)
        self.assertGreaterEqual(span, int(w * (0.74 if portrait else 0.82)), f"{path.name} motif span {span} of {w}")


if __name__ == "__main__":
    unittest.main()
