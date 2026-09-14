#!/usr/bin/env python3
"""One-page faculty SOP and a zip per pilot course."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from catalog import MODULES, iter_lesson_paths

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "lessons"
OUT = ROOT / "out"
DOCS = ROOT / "docs"

COURSES = {
    "ECON": {
        "id": "ECON",
        "title_en": "Principles of Economics",
        "title_zh": "经济学原理",
        "title_zh_hk": "經濟學原理",
        "dept": "Economics",
        "prefixes": ("ECON-",),
    },
    "ACC": {
        "id": "ACC",
        "title_en": "Introductory Accounting and Auditing",
        "title_zh": "会计与审计入门",
        "title_zh_hk": "會計與審計入門",
        "dept": "Accounting",
        "prefixes": ("ACC-", "AUD-"),
    },
    "GBA": {
        "id": "GBA",
        "title_en": "Greater Bay Area",
        "title_zh": "粤港澳大湾区",
        "title_zh_hk": "粵港澳大灣區",
        "dept": "GBA / area studies",
        "prefixes": ("GBA-",),
    },
}


def course_of(lesson_id: str) -> str | None:
    lid = (lesson_id or "").upper()
    for cid, spec in COURSES.items():
        if any(lid.startswith(p) for p in spec["prefixes"]):
            return cid
    return None


def course_members(course_id: str) -> dict:
    spec = COURSES[course_id]
    lessons = sorted(
        p.stem
        for p in iter_lesson_paths()
        if any(p.stem.upper().startswith(pref) for pref in spec["prefixes"])
    )
    modules = sorted(
        p.stem
        for p in MODULES.glob("*.yaml")
        if any(p.stem.upper().startswith(pref) for pref in spec["prefixes"])
    )
    return {"lessons": lessons, "modules": modules, **spec}


def sop_html(course_id: str | None = None) -> str:
    spec = COURSES.get(course_id or "", {})
    heading = spec.get("title_en") or "AI bilingual teaching videos"
    zh = spec.get("title_zh") or "双语教学短片"
    members = course_members(course_id) if course_id in COURSES else {"modules": [], "lessons": []}
    mod_line = ", ".join(members["modules"]) or "ACC-M01 / ECON-M01 / GBA-M01"
    les_n = len(members["lessons"]) or "—"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SOP — {heading}</title>
<style>
  @page {{ size: A4; margin: 14mm; }}
  body {{ margin:0; font: 12.5px/1.35 "Segoe UI", "Noto Sans CJK SC", sans-serif; color:#1b2430; }}
  main {{ max-width: 780px; margin: 0 auto; padding: 16px 20px 24px; }}
  h1 {{ font-size: 20px; margin: 0 0 2px; color:#0b1f3a; }}
  .zh {{ color:#5c6672; margin: 0 0 8px; }}
  .banner {{ background:#0b1f3a; color:#f4efe6; padding:8px 10px; border-radius:8px; font-size:12px; }}
  h2 {{ font-size: 13px; letter-spacing:.04em; text-transform:uppercase; color:#8a7340; margin:14px 0 6px; }}
  ol.steps {{ margin:0; padding-left:18px; }}
  ol.steps li {{ margin: 0 0 5px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  th, td {{ border:1px solid #d7d0c4; padding:5px 7px; text-align:left; vertical-align:top; }}
  th {{ background:#f4efe6; color:#0b1f3a; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px 16px; }}
  .note {{ font-size:11.5px; color:#5c6672; }}
  .box {{ border:1px solid #d7d0c4; border-radius:8px; padding:8px 10px; }}
  @media print {{ .banner {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
</style>
</head>
<body>
<main>
  <h1>Faculty SOP — one page</h1>
  <p class="zh">{zh} · CUHK bilingual video factory · {heading}</p>
  <p class="banner">This pack is ready for a pilot course. You do not need ffmpeg, Python, or the factory console to teach with it.</p>

  <h2>What you received</h2>
  <div class="grid">
    <div class="box">Modules (5–10 min units): <strong>{mod_line}</strong></div>
    <div class="box">Short lessons in this zip: <strong>{les_n}</strong></div>
    <div class="box">Each unit has EN / 简 / 繁 speech, optional bilingual slides, optional no-caption twin, speeds 1× 1.25× 1.5× 2×.</div>
    <div class="box">Quiz: 100-point student sheet + answer key + CSV. Do not put the key on the LMS.</div>
  </div>

  <h2>Six steps</h2>
  <ol class="steps">
    <li><strong>Pick one module</strong> for the week, not every short. Students watch the module; shorts are backup.</li>
    <li><strong>Assign one treatment</strong> from <em>treatments.csv</em>. File names look like <code>ECON-M01__en__cap-burn__1p00x.mp4</code> — lesson, speech, captions on/off, speed. Do not rename.</li>
    <li><strong>Upload the MP4</strong> to Blackboard / Moodle / KEEP. Attach the matching <code>.srt</code> if the player can turn captions on. Soft captions = Year 2 / SEN option.</li>
    <li><strong>Release the student quiz HTML or CSV</strong> after the video. Mark with the key. Scores are out of 100.</li>
    <li><strong>Do not mix speeds in one cell.</strong> A student in the 1.5× arm only sees the 1p50x file. Log the <code>cell_id</code> from the CSV next to the student id.</li>
    <li><strong>If a file is missing</strong>, send the operator the module id. Faculty do not rebuild videos. Operators use the console: select the module → tick languages → Build. Experiment pack is optional.</li>
  </ol>

  <h2>Recommended first assignment</h2>
  <table>
    <tr><th>Arm</th><th>File to post</th><th>Why</th></tr>
    <tr><td>A · matched EN</td><td><code>…__en__cap-burn__1p00x.mp4</code></td><td>Baseline, English-medium section</td></tr>
    <tr><td>B · matched 简</td><td><code>…__zhcn__cap-burn__1p00x.mp4</code></td><td>Putonghua section</td></tr>
    <tr><td>C · matched 繁</td><td><code>…__zhhk__cap-burn__1p00x.mp4</code></td><td>Cantonese section</td></tr>
    <tr><td>D · mix slides</td><td><code>…__en-en-zh__cap-burn__1p00x.mp4</code></td><td>EN speech, bilingual slides</td></tr>
    <tr><td>E · speed</td><td>same cell at <code>1p50x</code> or <code>2p00x</code></td><td>Grant playback-speed arm; fall back to 1.25× if 2× is too fast</td></tr>
    <tr><td>F · no caption</td><td><code>…__cap-off__1p00x.mp4</code></td><td>Year-2 subtitle-off / accessibility contrast</td></tr>
  </table>

  <h2>Do / do not</h2>
  <div class="grid">
    <div class="box"><strong>Do</strong> keep burned-in and soft SRT together. Do print this page. Do record completion and quiz score.</div>
    <div class="box"><strong>Do not</strong> re-export from PowerPoint. Do not hand students the answer key. Do not edit YAML unless you are the drafter.</div>
  </div>
  <p class="note">Ethics: informed consent and anonymised scores. Operator docs: SETUP.md, SCHEMA.md. This page is the only sheet faculty need in class.</p>
</main>
</body>
</html>
"""


def write_sop(dest: Path, course_id: str | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(sop_html(course_id), encoding="utf-8")
    return dest


def _add_tree(zf: zipfile.ZipFile, src: Path, arc: str) -> int:
    if not src.exists():
        return 0
    n = 0
    if src.is_file():
        if src.suffix in {".tmp", ".txt"} and src.name.endswith(".concat.txt"):
            return 0
        zf.write(src, arc)
        return 1
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in {".tmp"} or path.name.endswith(".concat.txt") or path.name == ".stamp":
            continue
        zf.write(path, f"{arc}/{path.relative_to(src).as_posix()}")
        n += 1
    return n


def write_course_zip(course_id: str, out_root: Path | None = None) -> Path:
    if course_id not in COURSES:
        raise ValueError(f"Unknown course {course_id}")
    out_root = out_root or OUT
    spec = course_members(course_id)
    pack_dir = out_root / "_packs"
    pack_dir.mkdir(parents=True, exist_ok=True)
    zip_path = pack_dir / f"CUHK-VF-{course_id}.zip"
    manifest_rows: list[dict] = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        sop_bytes = sop_html(course_id).encode("utf-8")
        zf.writestr("SOP.html", sop_bytes)
        readme = (
            f"{spec['title_en']}\n{spec['title_zh']}\n\n"
            "Open SOP.html first.\n"
            "Videos: modules/*/cells and pack.\n"
            "Quizzes: */quiz (student HTML + key + CSV).\n"
            "Do not upload *_quiz_key.html to the LMS.\n"
        )
        zf.writestr("README.txt", readme)
        for mid in spec["modules"]:
            root = out_root / mid
            for folder, label in (("cells", "video"), ("pack", "treatment"), ("quiz", "quiz"), ("srt", "subtitle")):
                n = _add_tree(zf, root / folder, f"modules/{mid}/{folder}")
                if n:
                    manifest_rows.append({"path": f"modules/{mid}/{folder}/", "kind": label, "id": mid, "files": n})
        for lid in spec["lessons"]:
            root = out_root / lid
            for folder, label in (("cells", "video"), ("pack", "treatment"), ("quiz", "quiz"), ("srt", "subtitle")):
                n = _add_tree(zf, root / folder, f"lessons/{lid}/{folder}")
                if n:
                    manifest_rows.append({"path": f"lessons/{lid}/{folder}/", "kind": label, "id": lid, "files": n})
        man = io.StringIO()
        writer = csv.DictWriter(man, fieldnames=["path", "kind", "id", "files"])
        writer.writeheader()
        writer.writerows(manifest_rows)
        zf.writestr("MANIFEST.csv", man.getvalue())
    zip_path.write_bytes(buf.getvalue())
    print(f"bundle: {zip_path} ({zip_path.stat().st_size} bytes, {len(manifest_rows)} folders)")
    return zip_path
