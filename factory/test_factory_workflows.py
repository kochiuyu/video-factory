"""Exercise the quiz round trip and render a fixture without a TTS service."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import app
import build
from build_report import BuildReport
import catalog
import ff
import langs
import quiz
import xlsx_lesson
import yaml
from validate import load_lesson


ROOT = Path(__file__).resolve().parents[1]
MEAN = ROOT / "lessons" / "STAT" / "STAT-M01-T02-MEAN.yaml"


class QuizRoundTrip(unittest.TestCase):
    def test_author_excel_and_export_preserve_stat_multiple_choice(self):
        original = load_lesson(MEAN)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lesson = root / MEAN.name
            shutil.copyfile(MEAN, lesson)
            with patch.object(app, "resolve_yaml", return_value=lesson), patch.dict(os.environ, {"VF_OUT": tmp}):
                inspected = app.lesson_inspect(lesson.name)
                self.assertEqual(inspected["quiz"][0]["prompt"]["en"], original["quiz"][0]["question_en"])
                rows = [{k: row[k] for k in ("id", "prompt", "answer")} for row in inspected["quiz"]]
                result = app.save_light_edits(lesson.name, {
                    "title": {"en": "Arithmetic mean"},
                    "quiz": rows,
                })
                self.assertTrue(result["valid"], result)
            edited = load_lesson(lesson)
            self.assertEqual(edited["title_en"], "Arithmetic mean")
            self.assertEqual(edited["quiz"], original["quiz"])
            book = xlsx_lesson.export_lesson(edited, root / "quiz.xlsx")
            result = xlsx_lesson.import_workbook(lesson, book, app._dump_yaml)
            self.assertTrue(result["ok"], result)
            self.assertEqual(load_lesson(lesson)["quiz"], original["quiz"])

            workbook = xlsx_lesson.load_workbook(book)
            for col in range(3, 9):
                workbook["Quiz"].cell(2, col).value = None
            workbook.save(book)
            workbook.close()
            self.assertTrue(xlsx_lesson.import_workbook(lesson, book, app._dump_yaml)["ok"])
            self.assertEqual(load_lesson(lesson)["quiz"], original["quiz"])

            _, student, key = quiz.export_lesson_quiz(original, root / "export")
            question = original["quiz"][0]
            sheet = student.read_text(encoding="utf-8")
            self.assertIn(question["question_en"], sheet)
            self.assertIn(question["options_en"][0], sheet)
            self.assertNotIn(question["explanation_en"], sheet)
            self.assertIn(question["explanation_en"], key.read_text(encoding="utf-8"))

    def test_author_edits_multiple_choice_and_refuses_incomplete_choices(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / MEAN.name
            shutil.copyfile(MEAN, source)
            with patch.object(app, "resolve_yaml", return_value=source), patch.dict(os.environ, {"VF_OUT": tmp}):
                inspected = app.lesson_inspect(source.name)
                q = inspected["quiz"][0]
                q["correct"] = "B"
                q["options"]["en"][1] = "B: Revised choice."
                q["explanation"]["en"] = "A revised explanation."
                result = app.save_light_edits(source.name, {"quiz": [q]})
                self.assertTrue(result["ok"], result)
                saved = load_lesson(source)["quiz"][0]
                self.assertEqual(saved["answer"], "B")
                self.assertEqual(saved["options_en"][1], "B: Revised choice.")
                self.assertEqual(saved["explanation_en"], "A revised explanation.")
                before = source.read_bytes()
                q["options"]["zh"] = ["One choice"]
                result = app.save_light_edits(source.name, {"quiz": [q]})
                self.assertFalse(result["ok"])
                self.assertEqual(before, source.read_bytes())

    def test_rename_preserves_unexposed_fields(self):
        original = load_lesson(MEAN)["quiz"][0]
        rows = [{"id": "Q-new", "original_id": original["id"], "prompt_en": "Revised question"}]
        edited, = quiz.merge_quiz_rows([original], rows)
        self.assertEqual(edited, {**original, "id": "Q-new", "question_en": "Revised question"})


class BuildResults(unittest.TestCase):
    def test_report_preserves_completed_cut_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            first = root / "verified.mp4"
            first.touch()
            report = BuildReport(root, "video", {})

            def fail_after_first(_source, *, report):
                report.cuts({"en": ("en", "en", "en"), "zh": ("zh", "zh", "zh")})
                report.video("en", first, 42.0, reused=True)
                raise ValueError("Putonghua render interrupted")

            with self.assertRaisesRegex(ValueError, "interrupted"):
                report.run(MEAN, fail_after_first)
            path = report.write([MEAN.name])
            data = json.loads(path.read_text(encoding="utf-8"))
            item, = data["items"]
            self.assertEqual(item["cuts"]["en"]["status"], "reused")
            self.assertEqual(item["cuts"]["zh"]["status"], "failed")
            self.assertEqual(len(item["source_sha256"]), 64)
            _, summary = app.read_build_report(path.relative_to(root).as_posix(), root)
            self.assertEqual((summary["verified"], summary["failed"]), (1, 1))

    def test_batch_continues_after_invalid_lesson(self):
        paths = [Path("bad.yaml"), Path("good.yaml")]
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(catalog, "iter_lesson_paths", return_value=paths),
            patch.object(build, "build", side_effect=[ValueError("Invalid lesson"), []]) as render,
            patch.object(sys, "argv", ["build.py", "--out", tmp, "--all", "--slides-only"]),
            redirect_stdout(StringIO()) as log,
        ):
            with self.assertRaises(SystemExit):
                build.main()
            self.assertEqual([call.args[0] for call in render.call_args_list], paths)
            self.assertIn("FAILED bad.yaml", log.getvalue())

    def test_console_uses_verified_outputs_and_reads_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            relative = Path("lessons") / MEAN.stem / "cells" / "existing.mp4"
            stale = root / relative
            stale.parent.mkdir(parents=True)
            stale.touch()
            proc = MagicMock()
            proc.returncode = 0
            with (
                patch.dict(os.environ, {"VF_OUT": tmp}),
                patch.object(app, "resolve_yaml", return_value=MEAN),
                patch.object(app, "_job", dict(app._job)),
                patch.object(app.subprocess, "Popen", return_value=proc) as popen,
            ):
                proc.stdout = ["output root: \u7e41\n"]
                app.run_build(MEAN.name, False, "en")
                self.assertEqual(app._job["status"], "error")
                self.assertEqual(app._job["cells"], [])
                self.assertEqual(popen.call_args.kwargs["encoding"], "utf-8")
                proc.stdout = ["build-video: " + json.dumps(relative.as_posix()) + "\n"]
                app.run_build(MEAN.name, False, "en")
                self.assertEqual(app._job["status"], "ok")
                self.assertEqual(app._job["cells"], [f"/media/{relative.as_posix()}"])

    def test_legacy_putonghua_alias_and_unavailable_voice(self):
        lesson = {"beats": [{"s1_en": "One", "s1_zh": "\u4e00"}]}
        self.assertEqual(langs.selected_cells(lesson, ["zh"]), {"zh": ("zh", "zh", "zh")})
        with self.assertRaisesRegex(ValueError, "requires a narration track"):
            langs.selected_cells(lesson, ["hk"])

    def test_local_tracks_share_one_clock_across_separate_renders(self):
        lesson = {
            "id": "STAT-M01-T01-SMOKE",
            "title_en": "Example",
            "title_zh": "\u793a\u4f8b",
            "title_zh_hk": "\u793a\u4f8b",
            "beats": [{
                "id": "opening", "visual": "title_card",
                "title_en": "Example", "title_zh": "\u793a\u4f8b", "title_zh_hk": "\u793a\u4f8b",
                "en": "An example.", "zh": "\u4e00\u4e2a\u793a\u4f8b\u3002",
                "zh_hk": "\u4e00\u500b\u4f8b\u5b50\u3002", "seconds": 2,
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / f"{lesson['id']}.yaml"
            source.write_text(yaml.safe_dump(lesson, allow_unicode=True), encoding="utf-8")
            output = root / "render"
            cmd = [sys.executable, str(ROOT / "factory" / "build.py"), str(source),
                   "--out", str(output), "--no-tts", "--match-titles", "--no-progress-bar"]
            env = {**os.environ, "PYTHONUTF8": "1", "VF_PAD_CAP": "", "VF_CLIP_JOBS": "1",
                   "VF_BEAT_FADE": "0"}

            def render(cells, *extra):
                return subprocess.run(
                    cmd + ["--cells", cells, *extra], env=env, capture_output=True,
                    encoding="utf-8", timeout=120,
                )

            legacy = output / "ACC-M01" / "cells" / "ACC-M01_en.mp4"
            legacy.parent.mkdir(parents=True)
            legacy.touch()
            missing = render("en", "--preflight")
            self.assertFalse((output / "lessons").exists())
            report_lines = [line for line in missing.stdout.splitlines() if line.startswith("build-report: ")]
            report_path = output / json.loads(report_lines[0].removeprefix("build-report: "))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["mode"], "preflight")
            self.assertEqual(report["items"][0]["cuts"]["en"]["status"], "failed")
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("en/opening.mp3", missing.stdout)
            self.assertNotIn("build-video:", missing.stdout)
            self.assertTrue(legacy.is_file())

            for lang, length in (("en", 0.8), ("zh_cn", 1.5), ("zh_hk", 1.1)):
                mp3 = output / "lessons" / lesson["id"] / "audio" / lang / "opening.mp3"
                mp3.parent.mkdir(parents=True)
                ff.check_call(["-y", "-f", "lavfi", "-i",
                               f"sine=frequency=440:duration={length}", "-c:a", "libmp3lame", str(mp3)])
            ready = render("zh", "--preflight")
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            self.assertFalse((output / "lessons" / lesson["id"] / "cells").exists())
            for requested in ("en", "en,zh,hk"):
                proc = render(requested)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                outputs = [output / json.loads(line.removeprefix("build-video: "))
                           for line in proc.stdout.splitlines() if line.startswith("build-video: ")]
                self.assertEqual(len(outputs), len(requested.split(",")))
                line, = (line for line in proc.stdout.splitlines() if line.startswith("build-report: "))
                path = output / json.loads(line.removeprefix("build-report: "))
                report = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(report["status"], "complete")
                self.assertEqual(set(report["items"][0]["cuts"]), set(requested.split(",")))
                for path in outputs:
                    self.assertAlmostEqual(ff.probe_duration(path), 1.5, delta=0.15)
