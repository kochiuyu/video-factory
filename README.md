# Video factory

Short educational videos from a text lesson file — no video editor required.

## What you get

Finished **slide-film** explainers: still slides that advance with a spoken lecture and burned-in captions. One lesson can ship in several languages (English, Mainland Chinese / Putonghua, Hong Kong Chinese / Cantonese). The picture stays the same; only the voice, captions, and (optionally) on-slide labels change.

The reference course in this repo is **Practical Business Statistics**, module 1 — fifteen standalone shorts on center, spread, shape, and association (`lessons/STAT/STAT-M01-T01` … `T15`). See [docs/M01_BEGINNER_REVIEW.md](docs/M01_BEGINNER_REVIEW.md) for the latest beginner-teaching conventions.

This repository is what you hand to collaborators. Give them the repo and the docs below — not a chat transcript.

## What you write

You author **one YAML file per short**. That file is the whole lesson:

- the spoken script in each language
- which on-screen visual to paint (table, number line, bars, formula, …)
- titles, labels, and a short quiz

You do **not** scrub a timeline, place clips, or record in a video suite. If a claim is not in the YAML, it will not appear in the video.

Example path: `lessons/STAT/STAT-M01-T02-MEAN.yaml`.

## What the factory does

When you build a lesson, the tools under `factory/` run a fixed pipeline:

1. **Paint slides** — render PNG stills from the YAML visual fields
2. **Synthesize speech** — text-to-speech for each language (or reuse MP3s you supply)
3. **Align timing** — pad the shorter languages so every language shares one clock per section
4. **Burn captions and mux** — combine slides + audio into language **cells** (finished MP4s, one primary language each; bilingual slide variants such as English voice with Chinese labels are optional)

A browser console (`python factory/app.py` → `http://127.0.0.1:8765`) can preview slides and kick off the same builds.

**Glossary (first use):** A **beat** is one scene/card in the YAML. **Staged speech** means the narration is split to match progressive reveals on that card (`s1`, `s2`, `s3`). A **cell** is one finished language cut of the short.

## Quick start

First run on a blank machine: follow [docs/SETUP.md](docs/SETUP.md) (venv, fonts, diagnose, console). Windows FFmpeg notes: [docs/WINDOWS.md](docs/WINDOWS.md).

```bash
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python factory/diagnose.py
python factory/app.py
```

Browser console: `http://127.0.0.1:8765`. Leave the terminal open while the console runs.

On another machine, point fonts at local Noto files if needed:

```bash
export VF_FONT_LATIN=/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf
export VF_FONT_LATIN_BOLD=/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf
export VF_FONT_CJK=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
export VF_FONT_CJK_BOLD=/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc
```

## Repo layout

| Path | Role |
|------|------|
| `factory/` | Pipeline code: build, validate, console, slides, speech, mux |
| `lessons/<AREA>/` | Lesson YAML by subject area (`STAT`, `ECON`, `LAE`, …). Drafts: `lessons/_inbox/`; retired: `lessons/_attic/` |
| `docs/` | Schema, authoring/revise prompts, QA, setup, SOP |
| `minicourses/` | Lists of shorts in a module (e.g. `STAT-M01.yaml`); collections are **not** joined into one video |
| `themes/` | Slide color palettes |
| `fonts/` | Bundled Latin + CJK fonts |
| `out/` | Fallback build output when Downloads cannot be used. The default root is `<Downloads>/video-factory-out` |

The renderer also accepts a leftover flat `lessons/<ID>.yaml`.

Build products go to `<Downloads>/video-factory-out` (`%USERPROFILE%\Downloads\video-factory-out` on Windows, `~/Downloads/video-factory-out` on macOS and Linux). Lesson YAML stays in the repo, so a Dropbox checkout does not sync the PNGs, audio, and MP4s. Set `VF_OUT` or pass `--out` only to override that folder. A machine that already has `VF_OUT` set keeps that path. If Downloads cannot be used, output falls back to `<repo>/out`. See [docs/SETUP.md](docs/SETUP.md).

## Validate and build

Check the **saved** YAML before you treat a lesson as done:

```bash
python factory/validate.py lessons/STAT/STAT-M01-T02-MEAN.yaml
```

Prints `OK <id> N beats` or `INVALID` with errors. Usage: `validate.py LESSON.yaml`.

Build one lesson (paint → speech → align → cells):

```bash
python factory/build.py lessons/STAT/STAT-M01-T02-MEAN.yaml --cells en,zh,hk --match-titles
```

Useful flags (see `python factory/build.py -h`):

| Flag | Meaning |
|------|---------|
| `--cells en,zh,hk` | Which language cuts to produce. Also accepts bilingual slide cells such as `en+zh`, `zh+en` |
| `--match-titles` | Paint slide titles in that cell's language (EN / 简体 / 繁體) |
| `--slides-only` | PNG stills only — no speech or mux |
| `--caption-preview` | Stills + caption bars; no speech or mux |
| `--force-tts` | Regenerate all beat audio |
| `--no-tts` | Require existing MP3s on the usual paths |
| `--all` | Every YAML under `lessons/` with the same flags |
| `--theme <name>` | Palette from `themes/<name>.yaml` |
| `--out <dir>` | Lesson output root. Wins over `$VF_OUT`. Unset, the default is `<Downloads>/video-factory-out` |

For a three-language lesson, default cells are `en`, `zh`, and `hk`. Files land under `out/<ID>/cells/`.

Day-to-day operator steps: [docs/SOP.md](docs/SOP.md). Faculty one-pager: [docs/SOP-faculty.html](docs/SOP-faculty.html).

## Doc map — when to use which

| Doc | Use it when |
|------|-------------|
| [docs/SCHEMA.md](docs/SCHEMA.md) | Field reference, stage counts, **visual index**, bilingual budgets, IDs |
| [docs/AUTHORING_PROMPT.md](docs/AUTHORING_PROMPT.md) | Drafting a **new** lesson (paste as standing instructions) |
| [docs/REVISE_PROMPT.md](docs/REVISE_PROMPT.md) | Rewriting an **existing** YAML — especially elevating 简 / 繁 and matching speech to visuals |
| [docs/QA_CHECKLIST.md](docs/QA_CHECKLIST.md) | Delivery gate after authoring or revision |
| [docs/AUTHORING_PROMPT_LAE.md](docs/AUTHORING_PROMPT_LAE.md) | Parallel track: Low-Altitude Economy (`LAE`) on the same factory contract |
| [docs/M01_BEGINNER_REVIEW.md](docs/M01_BEGINNER_REVIEW.md) | What the M01 beginner pass fixed; conventions below |
| [docs/SETUP.md](docs/SETUP.md) | Install and first console run |
| [docs/THEMES.md](docs/THEMES.md) | Slide palettes |
| [docs/WINDOWS.md](docs/WINDOWS.md) | Windows FFmpeg repair only |

`docs/INSTALL.md` and `docs/BRIEF.template.md` are pointers only — do not keep a second copy of setup steps.

**Visual catalogue:** do not duplicate SCHEMA here. Open [docs/SCHEMA.md](docs/SCHEMA.md) → **Stage speech** (fields and reveal order) and **Visual contract → Visual index** (when to use `rank_line`, `freq_bars`, `dev_bars`, `ratio_bars`, `quad_scatter`, …).

## Beginner conventions (current)

Keep these in every new or revised short (full detail in SCHEMA / AUTHORING / REVISE / QA):

1. **Standalone** — Open on a business cost; close by answering that question. No "last short…" handoff and no "next we will…" teaser.
2. **Staged speech** — Progressive cards use `s1_*` / `s2_*` / `s3_*` only (not a whole-card `en` on the same beat). Narration follows what appears on screen.
3. **Work numbers on screen** — Do not speak a finished result unless a card already showed the arithmetic or footer.
4. **Realistic quiz distractors** — Wrong answers are beginner mistakes (wrong formula, wrong interpretation, causation myth), not jokes or bans. Prefer shorter correct options when you can; keep the answer letter unless asked to change it.
5. **M01 descriptive divisor** — Variance / covariance and related descriptive formulas divide by **n** (`/n`), not `n-1` (estimation is another short).
6. **Neutral shops** — Shop A / B / C and days. No Mong Kok, Wan Chai, Airport, or other real place names; Chinese cards keep A店 (not 甲店).
7. **Uncluttered bilingual** — Stay inside SCHEMA on-screen budgets; put equation walks on `steps` with `layout: rows`; one idea per card when the picture would clutter.
8. **Define before name** — Plain idea, then the term. Name every symbol in speech on the formula beat.

Speech standards in-repo: **T02-MEAN** for teaching voice; **T08-VARSTD** for beginner math.

## Revise workflow (one short at a time)

How M01 was revised (VF-Revise style):

1. Edit **one** lesson YAML.
2. `python factory/validate.py lessons/.../<ID>.yaml`
3. **Stop for OK** before the next short (and before any video build).
4. After OK to build: `python factory/build.py ... --cells ... --match-titles`, then **stop for OK** again before the next build or commit.

Do not invent topics, story numbers, or new quiz answers. If a suppose file must be added so a card can teach, flag it and wait.

## Design that must stay fixed

1. Schema first — if it is not in the YAML, it is not in the video.
2. One clock per section — pad audio to `max(English, 简, 繁)` per section, then join clips.
3. Speech synthesis lives inside `build.py` (Edge neural voices by default); `--no-tts` accepts vendor MP3s on the same paths.
4. Template / renderer changes are code reviews, not chat improvisation.

## YouTube paste file

A build writes one text file beside each requested cell MP4: `out/lessons/<ID>/cells/<ID>_<cell>.youtube.txt`. Line 1 is the short lesson title plus a language tag (`(English)`, `(普通话)`, `(粵語)`, or a speech/slides tag on a mixed cell). The optional `youtube:` descriptions follow. Each description must be strictly less than 2500 characters. ASCII `<` and `>` in the title or description are written as fullwidth `＜` and `＞`, because YouTube Studio rejects the ASCII brackets. Nothing is uploaded. See `docs/SCHEMA.md`.

## Out of scope

Avatar lip-sync, generative B-roll that differs by language, and live lecture capture. Those are a different factory.