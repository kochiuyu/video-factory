#!/usr/bin/env python3
"""Make series_links.json (prev / next / playlist URLs) from upload results.

Input TSV: a header row, first column ``topic`` (T01) or ``id``/``lesson_id``
(full lesson id), then one column per cell (zh, hk+en, zh+en, en+zh ...)
holding the YouTube video id. Empty cells are skipped.

    python series_links.py results.tsv --module STAT-M03 \
        --lessons-dir ../lessons/STAT --playlist zh=PL... --playlist hk+en=PL... \
        -o ../lessons/STAT/series_links.json

The output is merged into an existing file (other modules are kept).
build.py and validate.py read ``series_links.json`` from the lesson folder,
or the path in ``VF_SERIES_LINKS``.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def video_url(video_id: str) -> str:
    return f"https://youtu.be/{video_id}"


def playlist_url(playlist_id: str) -> str:
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def _resolve(key: str, module: str, lesson_ids: list[str]) -> str:
    key = key.strip()
    if re.match(r"^T\d+$", key):
        prefix = f"{module}-T{int(key[1:]):02d}"
        for lid in lesson_ids:
            if lid == prefix or lid.startswith(prefix + "-"):
                return lid
        return prefix
    return key


def build_links(tsv: Path, module: str, lesson_ids: list[str], playlists: dict[str, str]) -> dict:
    with open(tsv, encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh, delimiter="\t"))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    order = [_resolve(r[0], module, lesson_ids) for r in body]
    entry: dict = {"total": len(lesson_ids) or len(order), "order": sorted(set(order) | set(lesson_ids))}
    for col, cell in enumerate(header[1:], start=1):
        cell = cell.strip()
        urls = {}
        for lid, row in zip(order, body):
            vid = row[col].strip() if col < len(row) else ""
            if vid:
                urls[lid] = video_url(vid)
        entry[cell] = {"urls": urls}
        if playlists.get(cell):
            entry[cell]["playlist_url"] = playlist_url(playlists[cell])
    return {module: entry}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tsv", type=Path)
    ap.add_argument("--module", required=True, help="e.g. STAT-M03")
    ap.add_argument("--lessons-dir", type=Path, help="folder with <module>-Txx-*.yaml (sets ids and total)")
    ap.add_argument("--playlist", action="append", default=[], help="cell=PLAYLIST_ID")
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    lesson_ids = []
    if args.lessons_dir:
        lesson_ids = sorted(p.stem for p in args.lessons_dir.glob(f"{args.module}-T*.yaml"))
    playlists = dict(item.split("=", 1) for item in args.playlist)
    data = json.loads(args.out.read_text(encoding="utf-8")) if args.out.is_file() else {}
    data.update(build_links(args.tsv, args.module, lesson_ids, playlists))
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
