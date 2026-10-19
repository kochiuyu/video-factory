#!/usr/bin/env python3
"""Output root: default repo out/, VF_OUT, and --out."""

from __future__ import annotations

import html
import http.client
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cache import write_mark
from catalog import OUT, ROOT, media_href, migrate_out_layout, out_dir, out_root
from mathtex import cache_dir
from youtube import write_youtube_sidecars


def _without_vf_out():
    return patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "VF_OUT"}, clear=True)


class OutRoot(unittest.TestCase):
    def test_default_is_repo_out(self) -> None:
        with _without_vf_out():
            self.assertEqual(out_root(), OUT)
            self.assertEqual(out_root(), ROOT / "out")
            self.assertEqual(out_dir("ZZ-NOT-A-MODULE"), OUT / "lessons" / "ZZ-NOT-A-MODULE")
            self.assertEqual(out_dir("ACC-M01"), OUT / "modules" / "ACC-M01")

    def test_blank_vf_out_is_default(self) -> None:
        with patch.dict(os.environ, {"VF_OUT": "   "}):
            self.assertEqual(out_root(), OUT)

    def test_vf_out_and_cli_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_root = Path(tmp) / "env"
            cli_root = Path(tmp) / "cli"
            with patch.dict(os.environ, {"VF_OUT": str(env_root)}):
                self.assertEqual(out_root(), env_root.resolve())
                self.assertEqual(out_dir("ZZ-NOT-A-MODULE"), env_root.resolve() / "lessons" / "ZZ-NOT-A-MODULE")
                self.assertEqual(out_root(cli_root), cli_root.resolve())
                self.assertEqual(cache_dir(), env_root.resolve() / "_mathtex")

    def test_relative_override_is_repo_relative(self) -> None:
        with _without_vf_out():
            self.assertEqual(out_root("out"), OUT.resolve())
            self.assertEqual(out_root(Path("out")), OUT.resolve())

    def test_explicit_relative_root_argument_is_unchanged(self) -> None:
        rel = Path("out")
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"VF_OUT": tmp}):
                self.assertEqual(out_dir("ZZ-REL", root=rel), rel / "lessons" / "ZZ-REL")
                self.assertEqual(
                    media_href("ZZ-REL", "cells", "a.mp4", root=rel),
                    "/media/lessons/ZZ-REL/cells/a.mp4",
                )

    def test_refuses_repo_and_other_in_repo_dirs(self) -> None:
        with _without_vf_out():
            for bad in (ROOT, ROOT / "lessons", Path("lessons"), Path(".")):
                with self.assertRaises(SystemExit):
                    out_root(bad)

    def test_migrate_stays_inside_vf_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            legacy = base / "ZZ-MOVE"
            legacy.mkdir()
            (legacy / "note.txt").write_text("hi", encoding="utf-8")
            with patch.dict(os.environ, {"VF_OUT": tmp}):
                rows = migrate_out_layout()
            self.assertTrue((base / "lessons" / "ZZ-MOVE" / "note.txt").is_file())
            self.assertFalse(legacy.exists())
            self.assertFalse((ROOT / "out" / "lessons" / "ZZ-MOVE").exists())
            self.assertTrue(any("ZZ-MOVE" in row for row in rows))

    def test_sidecars_and_stamps_follow_the_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"VF_OUT": tmp}):
                folder = out_dir("ZZ-SIDE")
                paths = write_youtube_sidecars(
                    {"id": "ZZ-SIDE", "title_en": "Side"},
                    {"en": ("en", "en", "en")},
                    folder,
                )
                self.assertTrue(str(paths[0]).startswith(str(Path(tmp).resolve())))
                self.assertTrue(paths[0].is_file())
                dest = folder / "cells" / "ZZ-SIDE_en.mp4"
                dest.write_bytes(b"not-a-video")
                write_mark(dest, "abc")
                self.assertEqual((dest.parent / "ZZ-SIDE_en.mp4.stamp").read_text(encoding="utf-8").strip(), "abc")

    def test_attach_log_uses_the_build_root(self) -> None:
        import build

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lesson = root / "lessons" / "ZZ-LOG"
            before = (OUT / "last_build.log").read_bytes() if (OUT / "last_build.log").is_file() else None
            old_out, old_err = sys.stdout, sys.stderr
            try:
                build._attach_log(lesson, "ZZ-LOG", root)
                for stream in (sys.stdout, sys.stderr):
                    for handle in getattr(stream, "streams", [])[1:]:
                        handle.close()
            finally:
                sys.stdout, sys.stderr = old_out, old_err
            self.assertTrue((root / "last_build.log").is_file())
            self.assertTrue((lesson / "build.log").is_file())
            after = (OUT / "last_build.log").read_bytes() if (OUT / "last_build.log").is_file() else None
            self.assertEqual(before, after)

    def test_build_cli_prints_vf_out_and_skips_repo_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "factory" / "build.py"), str(ROOT / "missing.yaml"), "--slides-only"],
                cwd=str(ROOT),
                env={**os.environ, "VF_OUT": tmp, "PYTHONUTF8": "1"},
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn(f"output root: {Path(tmp).resolve()}", proc.stdout)
            self.assertFalse((OUT / "lessons" / "missing").exists())

    def test_help_mentions_vf_out(self) -> None:
        for script in ("build.py", "app.py"):
            proc = subprocess.run(
                [sys.executable, str(ROOT / "factory" / script), "-h"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("VF_OUT", proc.stdout)

    def test_console_build_forwards_out_root(self) -> None:
        import app

        with tempfile.TemporaryDirectory() as tmp:
            before = (OUT / "last_build.log").read_bytes() if (OUT / "last_build.log").is_file() else None
            with patch.dict(os.environ, {"VF_OUT": tmp}):
                proc = MagicMock()
                proc.stdout = []
                proc.returncode = 0
                with patch.object(app.subprocess, "Popen", return_value=proc) as popen:
                    app.run_build("", False, "en", all_lessons=True)
            cmd = popen.call_args.args[0]
            self.assertIn("--out", cmd)
            self.assertIn(str(Path(tmp).resolve()), cmd)
            self.assertTrue((Path(tmp).resolve() / "last_build.log").is_file())
            after = (OUT / "last_build.log").read_bytes() if (OUT / "last_build.log").is_file() else None
            self.assertEqual(before, after)

    def test_console_serves_the_override_root(self) -> None:
        import app

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "last_build.log").write_text("hello-log\n", encoding="utf-8")
            with patch.dict(os.environ, {"VF_OUT": tmp}):
                server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    host, port = server.server_address
                    with urlopen(f"http://{host}:{port}/") as resp:
                        body = resp.read().decode("utf-8")
                    self.assertIn(html.escape(str(root)) + "/last_build.log", body)
                    self.assertNotIn("__OUT_ROOT__", body)
                    with urlopen(f"http://{host}:{port}/media/last_build.log") as resp:
                        self.assertEqual(resp.read(), b"hello-log\n")
                    conn = http.client.HTTPConnection(host, port, timeout=5)
                    conn.request("GET", "/media/../catalog.py")
                    denied = conn.getresponse()
                    denied.read()
                    self.assertEqual(denied.status, 403)
                    conn.close()
                finally:
                    server.shutdown()
                    server.server_close()


if __name__ == "__main__":
    unittest.main()
