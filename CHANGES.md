# Changes

## 2026-11-04 — YouTube series numbering

- `youtube.py`: series header carries the module title after the module code (`Series: STAT M03 · Distributions for a coffee chain · … · Lesson 05/15`), from `minicourses/<COURSE>-M<mm>.yaml` `title_en` / `title_zh` / `title_zh_hk` by speech voice (`zh_hk` falls back to `title_zh`). Lookup: `VF_MINICOURSES`, then `minicourses/` in any parent of the lesson file, then the repo root beside `factory/`. Missing file or title -> omitted. `load_series_links` carries it as `module_title`.
- `youtube.py`: title prefix follows the speech language via `COURSE_WORDS` (STAT: `STAT` / `统计` / `統計`); unknown course -> the course code. Cover chip stays numeric `1.09 · LESSON-ID`. `VF_LEGACY_YT_SERIES=1` still turns all of it off.

- `youtube.py`: title prefix `STAT 1.09 · ` from the lesson id (`series_prefix`), `Series:` / `系列：` first description line in the speech language, optional previous / next / playlist lines (same mix, known URLs only), `youtube.series` lesson block, `series_links.json` loader, 2300-character built-description warning. A prefix-only overrun of 100 is a warning.
- `series_links.py` (new): builds `series_links.json` from an upload results TSV.
- `build.py`, `validate.py`: pass the links file to sidecars and warnings.
- `cover.py`: top-right id shows `1.09 · STAT-M01-T09-CV`.
- `VF_LEGACY_YT_SERIES=1` restores the previous titles, descriptions and cover.
- Tests: 10 new in `test_youtube.py` (64 total).
