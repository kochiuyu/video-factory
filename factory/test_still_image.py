"""Opt-in still_image cards. Existing visuals stay on their own layout."""

from hashlib import sha256
import copy
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from mux import caption_safe_top
from slides import (
    CONTENT_BOTTOM,
    H,
    LAYOUT_VERSION,
    STAGEABLE,
    W,
    _contain_size,
    render_beat,
    resolve_still_image,
    stage_count,
)
from theme import load_theme
from validate import load_lesson, validate


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "factory" / "fixtures" / "still_image.yaml"
IMAGE = ROOT / "factory" / "fixtures" / "still_image.png"
MEAN = ROOT / "lessons" / "STAT" / "STAT-M01-T02-MEAN.yaml"
# Byte identity of the production Mean lesson on main 55af61b, LF form.
MEAN_SHA256 = "55e7d014230d1687de559f34b60707f1aee16a44757758ec103b32b45abad121"
RED = (220, 30, 40)
BLUE = (30, 90, 200)
GREEN = (0, 170, 70)


def _lesson(beats, **extra):
    lesson = {
        "id": "STILL-IMAGE-FIXTURE",
        "title_en": "The last tray of egg tarts",
        "title_zh": "最后一盘蛋挞",
        "title_zh_hk": "最後一盤蛋撻",
        "duration_target_s": sum(beat["seconds"] for beat in beats),
        "beats": beats,
    }
    lesson.update(extra)
    return lesson


def _beat(**extra):
    beat = {
        "id": "tray",
        "visual": "still_image",
        "seconds": 12,
        "kicker_en": "ACC-01",
        "title_en": "The last tray of egg tarts",
        "title_zh": "最后一盘蛋挞",
        "title_zh_hk": "最後一盤蛋撻",
        "image": "still_image.png",
        "en": "The last tray is still on the counter.",
        "zh": "最后一盘还在柜上。",
        "zh_hk": "最後一盤仲喺櫃上。",
    }
    beat.update(extra)
    return beat


def _ready(lesson=None):
    lesson = load_lesson(FIXTURE) if lesson is None else lesson
    lesson["_yaml"] = str(FIXTURE)
    return lesson


def _paint(lesson, lang="en", focus=False, second=None):
    holder = copy.deepcopy(lesson)
    holder["_yaml"] = str(holder.get("_yaml") or FIXTURE)
    if focus:
        holder["slide_style"] = "focus"
    beat = holder["beats"][0]
    return render_beat(
        beat, holder, 1, len(holder["beats"]), lang, load_theme("cuhk-navy"), second_lang=second,
    )


def _bbox(image, predicate):
    px = image.load()
    left, top, right, bottom = image.width, image.height, -1, -1
    for y in range(image.height):
        for x in range(image.width):
            if predicate(px[x, y]):
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right < 0:
        return None
    return left, top, right, bottom


def _solid(path: Path, size, color, lower=None):
    image = Image.new("RGB", size, color)
    if lower is not None:
        half = size[1] // 2
        band = Image.new("RGB", (size[0], size[1] - half), lower)
        image.paste(band, (0, half))
    image.save(path)


class StillImageValidation(unittest.TestCase):
    def test_fixture_validates_and_mean_yaml_stays_byte_identical(self):
        self.assertEqual(validate(load_lesson(FIXTURE), glyphs=False, source=FIXTURE), [])
        text = MEAN.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(sha256(text).hexdigest(), MEAN_SHA256)
        self.assertEqual(LAYOUT_VERSION, "2026-11-04-reveal-steps-type-v1")
        self.assertNotIn("still_image", STAGEABLE)
        self.assertEqual(stage_count(_beat()), 1)
        self.assertEqual(stage_count({"visual": "still_image", "s1_en": "A.", "s2_en": "B."}), 1)
        self.assertEqual(stage_count({"visual": "definition_card"}), 2)
        self.assertEqual(stage_count({"visual": "coin"}), 3)

    def test_title_image_and_staged_speech_are_required_rules(self):
        missing_title = _lesson([_beat(title_en="", title_zh="", title_zh_hk="", title=None)])
        # Drop the title keys so the stem is actually empty.
        for key in ("title_en", "title_zh", "title_zh_hk", "title"):
            missing_title["beats"][0].pop(key, None)
        errors = validate(missing_title, glyphs=False, source=FIXTURE)
        self.assertTrue(any("missing title" in err for err in errors), errors)

        missing_image = _lesson([_beat()])
        missing_image["beats"][0].pop("image")
        errors = validate(missing_image, glyphs=False, source=FIXTURE)
        self.assertTrue(any("missing image" in err for err in errors), errors)

        staged = _lesson([_beat(s1_en="One.", s1_zh="一。", s1_zh_hk="一。")])
        errors = validate(staged, glyphs=False, source=FIXTURE)
        self.assertTrue(any("unstaged" in err for err in errors), errors)

    def test_image_path_stays_inside_the_repo(self):
        outside = Path(tempfile.gettempdir()) / "vf-still-outside.png"
        _solid(outside, (8, 8), RED)
        cases = {
            "https://kochiuyu.github.io/micro-cases/tarts.jpg": "URL",
            "art/../../outside.png": "stay inside",
            "factory/fixtures/../fixtures/still_image.png": "stay inside",
            "notes.gif": ".jpg",
            str(outside): "stay inside",
            "factory/fixtures/no-such-still.png": "not found",
        }
        for image, needle in cases.items():
            errors = validate(_lesson([_beat(image=image)]), glyphs=False, source=FIXTURE)
            self.assertTrue(any(needle in err for err in errors), (image, errors))

        found, err = resolve_still_image(str(IMAGE.resolve()), FIXTURE)
        self.assertEqual(err, "")
        self.assertEqual(found, IMAGE.resolve())

    def test_yaml_directory_wins_and_repo_root_is_the_fallback(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "factory" / "fixtures") as tmp:
            folder = Path(tmp)
            local = folder / "pic.png"
            _solid(local, (12, 12), GREEN)
            yaml_path = folder / "draft.yaml"
            yaml_path.write_text("id: DRAFT\n", encoding="utf-8")
            found, err = resolve_still_image("pic.png", yaml_path)
            self.assertEqual(err, "")
            self.assertEqual(found, local.resolve())

            found, err = resolve_still_image("factory/fixtures/still_image.png", yaml_path)
            self.assertEqual(err, "")
            self.assertEqual(found, IMAGE.resolve())

            upper = folder / "shot.PNG"
            _solid(upper, (8, 8), RED)
            jpeg = folder / "shot.jpeg"
            Image.new("RGB", (6, 6), BLUE).save(jpeg, "JPEG")
            for name in ("shot.PNG", "shot.jpeg"):
                found, err = resolve_still_image(name, yaml_path)
                self.assertEqual(err, "", name)
                self.assertEqual(found, (folder / name).resolve())

            lesson = _lesson([_beat(image="pic.png")], _yaml=str(yaml_path), id="STILL-DRAFT-NOT-A-LESSON")
            errors = validate(lesson, glyphs=False, source=yaml_path)
            self.assertEqual(errors, [])
            image = render_beat(lesson["beats"][0], lesson, 1, 1, "en", load_theme("cuhk-navy"))
            self.assertIsNotNone(_bbox(image, lambda px: px == GREEN))
            self.assertIsNone(_bbox(image, lambda px: px == RED))


class StillImageRender(unittest.TestCase):
    def test_contain_keeps_aspect_and_centers_without_a_navy_band(self):
        theme = load_theme("cuhk-navy")
        wide, tall = _contain_size(20, 40, 1792, 700)
        self.assertLessEqual(wide, 1792)
        self.assertLessEqual(tall, 700)
        self.assertAlmostEqual(wide / tall, 0.5, delta=0.02)
        self.assertEqual(_contain_size(80, 20, 1792, 700)[0], 1792)

        image = _paint(_ready())
        px = image.load()
        self.assertEqual(image.size, (W, H))
        self.assertEqual(px[8, 400], theme["navy"])
        self.assertEqual(px[W - 40, 40], theme["gold"])
        for y in range(48, 360):
            self.assertNotEqual(px[1400, y], theme["navy"], y)
            self.assertNotEqual(px[1700, y], theme["navy"], y)

        art = _bbox(image, lambda pixel: pixel in {RED, BLUE})
        self.assertIsNotNone(art)
        left, top, right, bottom = art
        self.assertLessEqual(bottom, CONTENT_BOTTOM)
        self.assertAlmostEqual((right - left) / (bottom - top), 0.5, delta=0.04)
        self.assertAlmostEqual((left + right) / 2, W / 2, delta=8)
        self.assertLess(right - left, W * 0.6)
        mid_y = (top + bottom) // 2
        self.assertNotIn(px[80, mid_y], {RED, BLUE})
        self.assertNotIn(px[W - 80, mid_y], {RED, BLUE})
        self.assertTrue(any(px[x, mid_y] == theme["navy"] for x in range(left, left - 8, -1)))
        self.assertGreater(sum(1 for y in range(40, 96) for x in range(64, 200) if px[x, y] == theme["navy"]), 400)
        self.assertTrue(any(
            px[x, y] == theme["gold"]
            for y in range(H - 140, H - 90)
            for x in range(W - 220, W - 30)
        ))
        run = _gold_run(image, theme["gold"])
        self.assertIsNotNone(run)
        length, start, y = run
        self.assertGreaterEqual(length, 150)
        self.assertLessEqual(length, 190)
        self.assertLess(start, 80)
        self.assertNotEqual(px[600, y], theme["gold"])
        self.assertEqual(px[960, 180], theme["bg"])

        plain = {
            "id": "OLD-LAYOUT",
            "title_en": "Definition",
            "title_zh": "定义",
            "title_zh_hk": "定義",
            "beats": [{
                "id": "define",
                "visual": "definition_card",
                "title_en": "Definition",
                "formula_en": "A = B",
                "en": "A line.",
                "zh": "一行。",
                "zh_hk": "一行。",
            }],
        }
        band = render_beat(plain["beats"][0], plain, 1, 1, "en", theme)
        self.assertEqual(band.getpixel((1400, 180)), theme["navy"])

    def test_caption_sits_under_the_image_and_focus_keeps_its_chrome(self):
        theme = load_theme("cuhk-navy")
        plain = _paint(_ready())
        noted = _ready()
        noted["beats"][0]["caption_en"] = "One tray left"
        noted["beats"][0]["footer_en"] = "Footer should not replace the caption"
        caption = _paint(noted)
        art = _bbox(caption, lambda pixel: pixel in {RED, BLUE})
        self.assertIsNotNone(art)
        muted_plain = _count_between(plain, theme["muted"], 360, CONTENT_BOTTOM)
        muted_caption = _count_between(caption, theme["muted"], art[3] + 2, CONTENT_BOTTOM)
        self.assertEqual(muted_plain, 0)
        self.assertGreater(muted_caption, 20)
        self.assertLessEqual(art[3], CONTENT_BOTTOM)

        focus = _paint(_ready(), focus=True)
        fx = focus.load()
        self.assertEqual(fx[W - 40, 40], theme["bg"])
        self.assertEqual(fx[8, 400], theme["navy"])
        self.assertFalse(any(
            fx[x, y] == theme["gold"]
            for y in range(H - 140, H - 90)
            for x in range(W - 220, W - 30)
        ))
        safe = caption_safe_top(H) - 16
        framed = _bbox(focus, lambda pixel: pixel in {RED, BLUE})
        self.assertIsNotNone(framed)
        self.assertLessEqual(framed[3], safe)
        self.assertNotEqual(list(plain.getdata()), list(focus.getdata()))

    def test_chinese_title_is_painted_and_a_wide_picture_is_not_stretched(self):
        theme = load_theme("cuhk-navy")
        english = _paint(_ready(), "en")
        chinese = _paint(_ready(), "zh")
        self.assertNotEqual(list(english.crop((60, 90, 900, 280)).getdata()), list(chinese.crop((60, 90, 900, 280)).getdata()))
        bilingual = _paint(_ready(), "en", second="zh")
        self.assertNotEqual(
            list(english.crop((60, 100, 1100, 320)).getdata()),
            list(bilingual.crop((60, 100, 1100, 320)).getdata()),
        )

        with tempfile.TemporaryDirectory(dir=ROOT / "factory" / "fixtures") as tmp:
            wide_path = Path(tmp) / "wide.png"
            _solid(wide_path, (80, 20), GREEN)
            lesson = _ready()
            lesson["beats"][0]["image"] = str(wide_path.resolve())
            image = _paint(lesson)
            art = _bbox(image, lambda pixel: pixel == GREEN)
            self.assertIsNotNone(art)
            left, top, right, bottom = art
            self.assertGreater(right - left, 1400)
            self.assertLess(bottom - top, 600)
            self.assertAlmostEqual((right - left) / (bottom - top), 4.0, delta=0.08)
            self.assertNotEqual(image.getpixel((960, top - 12)), GREEN)
            self.assertLessEqual(bottom, CONTENT_BOTTOM)


def _gold_run(image, gold):
    px = image.load()
    best = None
    for y in range(90, 320):
        xs = [x for x in range(40, 420) if px[x, y] == gold]
        if len(xs) < 40:
            continue
        run = 1
        for left, right in zip(xs, xs[1:]):
            if right == left + 1:
                run += 1
            else:
                break
        if best is None or run > best[0]:
            best = (run, xs[0], y)
    return best


def _count_between(image, color, top, bottom):
    px = image.load()
    found = 0
    for y in range(max(0, top), min(image.height, bottom)):
        for x in range(40, image.width - 40):
            if px[x, y] == color:
                found += 1
    return found


if __name__ == "__main__":
    unittest.main()
