# Lesson schema

A lesson is one YAML file under `lessons/<AREA>/`. The renderer looks up the file by id (`GAME-GI-01` → `lessons/GAME/GAME-GI-01.yaml`). A leftover flat `lessons/<ID>.yaml` still builds. Drafts live in `lessons/_inbox/`; retired files in `lessons/_attic/` — those two folders are skipped by the sidebar and by “build every lesson.”

## Required fields

| Field | Type | Rule |
|--------|------|------|
| `id` | string | Stable experiment ID. Must match the filename stem. See **IDs** below. |
| `title_en`, `title_zh` | string | Short titles. Locked glossary terms must appear exactly. |
| `duration_target_s` | number | 60–180. Authoring target, not a render guarantee. |
| `beats` | list | Ordered scenes. One claim per beat. |

## Required fields on each beat

| Field | Type | Rule |
|--------|------|------|
| `id` | string | Unique within the lesson. Used as the audio filename. |
| `visual` | enum | `title_card`, `definition_card`, `two_column`, `formula`, `takeaway`, `example`, `three_column`, `big_number`, `steps`, `module_open`, `module_close`. |
| `en` | string | Spoken English. At most 70 words. |
| `zh` or `zh_cn` | string | Spoken 简体. At most 140 characters. |
| `zh_hk` | string | Spoken 繁體 / Cantonese script. Required on current lessons. |

## Optional fields

Lesson: `course`, `audience`, `objective_en`, `objective_zh`, `glossary`, `quiz`.

Beat: `kicker` (or `kicker_en` / `kicker_zh` / `kicker_zh_hk`), `title_en`, `title_zh`, `title_zh_hk`, `formula`, `gloss_*`, `left_*`, `right_*`, `setup_*`, `result_*`, `q1_*`, `q2_*`, `col1_*`, `col2_*`, `col3_*`, `step1_*`, `step2_*`, `step3_*`, `number`, `unit_*`, `caption_*`, `seconds`. Common English kickers (Concept, Definition, Example, Takeaway, …) are translated when labels are Chinese.

On-slide fields by visual:

| visual | On-screen fields |
|--------|------------------|
| `title_card` | Centered title and kicker |
| `definition_card` | `formula` or `formula_tex`, optional `gloss_*` |
| `two_column` | `left_*`, `right_*` |
| `formula` | `formula` or `formula_tex`, optional `gloss_*` |

`formula_tex` is matplotlib mathtext (LaTeX math subset), e.g. `"A = L + E"` or `"\\frac{Q_d}{P}"`. Optional `formula_tex_zh` / `formula_tex_zh_hk`. Keep a plain `formula` line as fallback.
| `example` | `setup_*` and `result_*` (falls back to `left_*` / `right_*`) |
| `takeaway` | `q1_*` and `q2_*` **required** in EN / 简 / 繁. Check and `validate.py` fail if either is missing. There is no default incentive pair. |
| `module_open` | Unit title plus `item1_*` … `item4_*` agenda. Used on `{MODULE}-IN` hook. |
| `module_close` | Claim panel plus `next_*`. Used on `{MODULE}-OUT`. |
| `three_column` | `col1_*`, `col2_*`, `col3_*` |
| `big_number` | `number` (or `formula`), `unit_*`, `caption_*` |
| `steps` | `step1_*`, `step2_*`, `step3_*` |
| `payoff_matrix` | `row_player_*`, `col_player_*`, `row1_*` `row2_*`, `col1_*` `col2_*`, `c11` `c12` `c21` `c22`, optional `note_*`, `highlight: c12` |

`validate.py` fails the section when the required stems above are empty. All 51 current lessons pass that table.

Glossary item: `en`, `zh`, `lock` (boolean). If `lock: true`, neither the bot nor an RA may paraphrase that pair.

## Visual contract

The picture is language-neutral in structure. `--labels en` or `--labels zh` only swaps titles and column labels. Do not put full spoken sentences on the slide. Do not add a new visual type without changing `factory/slides.py` and this document in the same commit.

## IDs

Teaching shorts use `AREA-TOPIC-NN`:

| Piece | What it is | Example |
|-------|------------|---------|
| `AREA` | Course | `ECON` `ACC` `AUD` `GBA` `GAME` |
| `TOPIC` | Two-letter topic | `OC` opportunity cost, `DC` debits |
| `NN` | **Variant slot**, not “first slide” or “first beat” | `01` |

`01` means “first cut of this topic.” A retake, a longer arm, or a different experiment treatment is `02`, `03`, … The factory does not require `01`; it only requires that `id` equals the filename and never collides.

Current tree only ships `01` because each topic has one script. Do not rename those files just to drop the suffix — `out/ECON-OC-01/` and every module list would go stale.

Module files are `AREA-M##` (`ECON-M01`). Bookend shorts are `{MODULE}-IN` and `{MODULE}-OUT` (`ACC-M01-IN`). Those ids have no variant slot.

Beat `id` is a different namespace: `hook`, `define`, `takeaway` inside one lesson. It is the audio filename, not part of `ECON-OC-01`.

## File naming

```
lessons/<AREA>/<ID>.yaml
modules/<AREA-M##>.yaml
out/<ID>/slides/<lang or zh+en>/<nn>_<beat_id>[_sN].png
out/<ID>/preview/<lang>/…
out/<ID>/audio/{en,zh_cn,zh_hk}/<beat_id>.mp3
out/<ID>/cells/<ID>_{en,zhcn,zhhk,<mix>}.mp4
```

Matched cells: `en`, `zhcn`, `zhhk` (voice = captions = that language). Mix name is `voice-caption-slide` with short tokens `en` / `zh` / `hk`, e.g. `en-en-zh` = English speech and captions, bilingual slides. Voice and captions stay the same language.

Faculty do not start from `briefs/`. Use the console Check tab and `docs/SOP-faculty.html`. Course zips: `out/_packs/CUHK-VF-{ECON,ACC,GBA}.zip`.
