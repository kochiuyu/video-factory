#!/usr/bin/env python3
"""Export a 100-point quiz from lesson.quiz and takeaway q1/q2 fields."""

from __future__ import annotations

import csv
import html
from pathlib import Path

from catalog import lesson_path
from validate import load_lesson

ROOT = Path(__file__).resolve().parents[1]


def _pick(obj: dict, stem: str, lang: str) -> str:
    if lang == "zh":
        keys = (f"{stem}_zh", f"{stem}_zh_cn", stem)
    elif lang == "zh_hk":
        keys = (f"{stem}_zh_hk", f"{stem}_zh", stem)
    else:
        keys = (f"{stem}_en", stem)
    for key in keys:
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def collect_items(lesson: dict, source_id: str | None = None) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    src = source_id or lesson.get("id") or ""
    for raw in lesson.get("quiz") or []:
        if not isinstance(raw, dict):
            continue
        qid = str(raw.get("id") or f"Q{len(items)+1}")
        row = {
            "id": qid,
            "source": src,
            "type": raw.get("type") or "comprehension",
            "prompt_en": (raw.get("en") or raw.get("prompt_en") or "").strip(),
            "prompt_zh": (raw.get("zh") or raw.get("prompt_zh") or "").strip(),
            "prompt_zh_hk": (raw.get("zh_hk") or raw.get("prompt_zh_hk") or "").strip(),
            "answer_en": (raw.get("answer_en") or "").strip(),
            "answer_zh": (raw.get("answer_zh") or "").strip(),
            "answer_zh_hk": (raw.get("answer_zh_hk") or "").strip(),
        }
        key = _norm(row["prompt_en"] or row["prompt_zh"])
        if key and key not in seen:
            seen.add(key)
            items.append(row)
    for beat in lesson.get("beats") or []:
        if not (beat.get("q1_en") or beat.get("q1_zh") or beat.get("q2_en")):
            continue
        for stem, kind in (("q1", "check"), ("q2", "transfer")):
            prompt_en = _pick(beat, stem, "en")
            if not prompt_en and not _pick(beat, stem, "zh"):
                continue
            key = _norm(prompt_en or _pick(beat, stem, "zh"))
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "id": f"{beat.get('id') or 'takeaway'}-{stem}",
                    "source": src,
                    "type": kind,
                    "prompt_en": prompt_en,
                    "prompt_zh": _pick(beat, stem, "zh"),
                    "prompt_zh_hk": _pick(beat, stem, "zh_hk"),
                    "answer_en": "",
                    "answer_zh": "",
                    "answer_zh_hk": "",
                }
            )
    return items


def assign_points(items: list[dict], total: int = 100) -> list[dict]:
    n = max(1, len(items))
    base, rem = divmod(total, n)
    out = []
    for i, item in enumerate(items):
        row = dict(item)
        row["points"] = base + (1 if i >= n - rem else 0)
        out.append(row)
    return out


def collect_module(member_ids: list[str]) -> list[dict]:
    items: list[dict] = []
    for lid in member_ids:
        path = lesson_path(lid)
        if path is None:
            continue
        lesson = load_lesson(path)
        items.extend(collect_items(lesson, lid))
    return items


def write_quiz_files(
    out_dir: Path,
    lesson_id: str,
    title: dict,
    items: list[dict],
) -> list[Path]:
    items = assign_points(items)
    quiz_dir = out_dir / "quiz"
    quiz_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    csv_path = quiz_dir / f"{lesson_id}_quiz.csv"
    fields = [
        "item",
        "source",
        "type",
        "points",
        "prompt_en",
        "prompt_zh",
        "prompt_zh_hk",
        "answer_en",
        "answer_zh",
        "answer_zh_hk",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for i, item in enumerate(items, start=1):
            writer.writerow(
                {
                    "item": i,
                    "source": item.get("source") or lesson_id,
                    "type": item.get("type") or "",
                    "points": item.get("points") or 0,
                    "prompt_en": item.get("prompt_en") or "",
                    "prompt_zh": item.get("prompt_zh") or "",
                    "prompt_zh_hk": item.get("prompt_zh_hk") or "",
                    "answer_en": item.get("answer_en") or "",
                    "answer_zh": item.get("answer_zh") or "",
                    "answer_zh_hk": item.get("answer_zh_hk") or "",
                }
            )
    written.append(csv_path)
    student = quiz_dir / f"{lesson_id}_quiz.html"
    key = quiz_dir / f"{lesson_id}_quiz_key.html"
    student.write_text(_html_page(lesson_id, title, items, answers=False), encoding="utf-8")
    key.write_text(_html_page(lesson_id, title, items, answers=True), encoding="utf-8")
    written.extend([student, key])
    print(f"quiz: {len(items)} items, {sum(i.get('points') or 0 for i in items)} points -> {quiz_dir}")
    return written


def export_lesson_quiz(lesson: dict, out_dir: Path) -> list[Path]:
    title = {
        "en": lesson.get("title_en") or lesson.get("id") or "",
        "zh": lesson.get("title_zh") or "",
        "zh_hk": lesson.get("title_zh_hk") or "",
    }
    return write_quiz_files(out_dir, lesson.get("id") or "lesson", title, collect_items(lesson))


def export_module_quiz(mod: dict, out_dir: Path) -> list[Path]:
    title = {
        "en": mod.get("title_en") or mod.get("id") or "",
        "zh": mod.get("title_zh") or "",
        "zh_hk": mod.get("title_zh_hk") or "",
    }
    items = collect_module(list(mod.get("lessons") or []))
    return write_quiz_files(out_dir, mod.get("id") or "module", title, items)


def _html_page(lesson_id: str, title: dict, items: list[dict], answers: bool) -> str:
    heading = html.escape(title.get("en") or lesson_id)
    sub = " · ".join(html.escape(t) for t in (title.get("zh"), title.get("zh_hk")) if t)
    total = sum(int(i.get("points") or 0) for i in items)
    kind = "Answer key" if answers else "Student sheet"
    blocks = []
    for i, item in enumerate(items, start=1):
        pts = int(item.get("points") or 0)
        prompts = []
        for lang, label in (("en", "EN"), ("zh", "简"), ("zh_hk", "繁")):
            text = item.get(f"prompt_{lang}") or ""
            if text:
                prompts.append(f'<p class="q"><span class="lang">{label}</span> {html.escape(text)}</p>')
        ans = ""
        if answers:
            lines = []
            for lang, label in (("en", "EN"), ("zh", "简"), ("zh_hk", "繁")):
                text = item.get(f"answer_{lang}") or ""
                if text:
                    lines.append(f'<p class="a"><span class="lang">{label}</span> {html.escape(text)}</p>')
            if not lines:
                lines.append('<p class="a muted">No keyed answer — mark from the spoken takeaway.</p>')
            ans = '<div class="key">' + "".join(lines) + "</div>"
        else:
            ans = '<div class="lines"><i></i><i></i><i></i></div>'
        blocks.append(
            f'<article class="item"><header><strong>{i}.</strong> '
            f'<span class="type">{html.escape(str(item.get("type") or ""))}</span> '
            f'<span class="pts">{pts} / {total}</span></header>'
            + "".join(prompts)
            + ans
            + "</article>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{heading} — {kind}</title>
<style>
  body {{ margin:0; font:16px/1.45 "Segoe UI", "Noto Sans", sans-serif; color:#1b2430; background:#f4efe6; }}
  main {{ max-width:820px; margin:24px auto 48px; background:#fff; padding:28px 32px; border-radius:14px; box-shadow:0 8px 24px rgba(12,28,48,.08); }}
  h1 {{ margin:0 0 4px; font-size:22px; color:#0b1f3a; }}
  .sub {{ color:#5c6672; margin:0 0 8px; }}
  .meta {{ font-size:13px; color:#7a8492; margin:0 0 20px; }}
  .item {{ border-top:1px solid #e6e0d4; padding:16px 0; }}
  .item header {{ display:flex; gap:10px; align-items:baseline; margin-bottom:8px; }}
  .type {{ font-size:11px; letter-spacing:.04em; text-transform:uppercase; color:#8a7340; }}
  .pts {{ margin-left:auto; font-size:13px; color:#0b1f3a; font-weight:650; }}
  .q {{ margin:4px 0; }}
  .a {{ margin:4px 0; color:#1d4a32; }}
  .lang {{ display:inline-block; min-width:2em; font-size:11px; color:#7a8492; font-weight:650; }}
  .lines i {{ display:block; height:28px; border-bottom:1px solid #d7d0c4; margin:6px 0 0; }}
  .muted {{ color:#7a8492; }}
  @media print {{ body {{ background:#fff; }} main {{ box-shadow:none; margin:0; padding:0; }} }}
</style>
</head>
<body>
<main>
  <h1>{heading}</h1>
  <p class="sub">{sub}</p>
  <p class="meta">{html.escape(lesson_id)} · {kind} · {len(items)} items · {total} points</p>
  {"".join(blocks)}
</main>
</body>
</html>
"""
