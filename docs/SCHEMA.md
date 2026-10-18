# Lesson schema

A lesson is one YAML file under `lessons/<AREA>/`. The renderer looks up the file by id (`STAT-M01-DE` → `lessons/STAT/STAT-M01-DE.yaml`, `GAME-M03-BR` → `lessons/GAME/GAME-M03-BR.yaml`). A leftover flat `lessons/<ID>.yaml` still builds. Drafts live in `lessons/_inbox/`; retired files in `lessons/_attic/` — those two folders are skipped by the sidebar and by “build every lesson.”

## Required fields

| Field | Type | Rule |
|--------|------|------|
| `id` | string | Stable experiment/lesson ID. Must match the filename stem. See **IDs** below. |
| `title_en`, `title_zh`, `title_zh_hk` | string | YouTube title and cover title. Name the topic so it stands alone. Do not depend on the example. |
| `duration_target_s` | number | Must equal the sum of beat `seconds`. A short module is often 60–240. A standalone teaching short may run longer when the beginner explanation needs it. `validate.py` currently errors only when the absolute gap exceeds 20 seconds. |
| `beats` | list | Ordered scenes. One claim or concept per beat. |

## Required fields on each beat

| Field | Type | Rule |
|--------|------|------|
| `id` | string | Unique within the lesson. Used as the audio filename. |
| `visual` | enum | `title_card`, `definition_card`, `two_column`, `formula`, `takeaway`, `example`, `three_column`, `big_number`, `steps`, `module_open`, `module_close`, `payoff_matrix`, `table_grid`, `series`, `schematic_chart`, `dag`, `pair`, `pair_chart`, `pair_box`, `pair_slope`, `redraw`, `turns`, `shrink`, `mix`, `coin`. |
| speech | trio | **One source only.** Unstaged card: `en` / `zh` / `zh_hk`. Staged card: `s1_en` `s1_zh` `s1_zh_hk` … Do not keep both. |

Voice and captions join the stage lines in order. `validate.py` accepts either shape. Whole-card `en` on a staged beat is ignored when `s1_en` exists.

Guidance, not a build fail: around 70 English words or 140 简/繁 characters fits a 20s card. However, never compress or gut beginner explanations to hit an arbitrary word count: if an explanation needs more breathing room, expand `seconds` on that beat.

## Standalone Lesson Structure

For topic-based standalone micro-lessons:
1. **Self-Contained Hook**: Must open directly with a concrete business decision or operational question. Never use continuity phrases pointing to previous sessions (avoid "In the last sitting...", "Continuing from our last discussion...").
2. **Self-Contained Takeaway**: Must directly answer the business question raised in the hook. Never end with a cliffhanger or teaser for subsequent videos (avoid "In the next sitting we will see...", "Next unit asks..."). The final stage must leave the learner with a complete operational rule.
3. **Pacing**: Speech should provide thorough, natural spoken exposition for beginners. Keep on-slide text clean and concise, and let the voiceover do the teaching.
4. **Define before use**: Say the idea in plain language, then name it. A viewer who has not seen the other shorts in the mini-course must still follow this one. If the short uses the average, say that the average is the total divided by the number of days.
5. **No forward reference**: Do not mention a correction, a measure, or a symbol that belongs to a later short. Dividing by n−1 belongs to estimation. Range and IQR belong to their own shorts. Do not name them here.
6. **Name the symbols**: A `formula_tex` line may use Greek letters. The speech on that beat must say what each symbol is. Mu is the average. Each x is one day. n is the number of days. Sigma squared is the variance. Do not leave a symbol unexplained.
7. **Own setting**: Each short opens on its own business question and its own place. Do not require Wan Chai, Mong Kok, or the shared Monday file. A place name should work for an international student. Do not repeat the same setting across shorts just to keep a ledger.
8. **Cost before the tool**: The hook asks the business question, not the statistical one. Open on the cost of being wrong (which shop wastes, which shop runs out). The measure is the tool that answers it. Do not open on "which side is long" and only later say why anyone cares.
9. **Spoken joins**: Each card opens by picking up the last sentence of the previous card. Inside a card, each stage picks up the last idea. Do not restart. The close returns to the hook's question by name.
10. **Label the file**: A constructed example is a suppose. Do not say "last week" or "the file shows" for numbers we invented. Say suppose, then give the days.
11. **Square units**: Variance is in square units. On first use, say "cups times cups" and say why: we multiplied. "Square cups" is the name, not the first explanation. A manager cannot staff in that unit.
12. **Sign is not a count**: A sign says which side is long. Counting the days says which outcome showed up more often. Do not let the formula do the count's job. Zero on a cubed formula means the cubed distances balance. It does not prove the two sides are perfect mirrors.
13. **Beginner math**: Split a dense calculation. Square, sum, divide, and root get their own cards. A tiny example comes first: 3 × 3 = 9 is all "squared" means. Say "a number times itself" before "squared," and "what number times itself is this?" before "square root." A minus times a minus is a plus, in one sentence.
14. **Name after the number**: The main names get a large card. After the number is known, a `title_card` fills the screen with the word: Variance, then Standard deviation. The name is not only in the speech.
15. **Formula is nicknames**: A formula names steps already done, one symbol at a time. Each day is an x. The average is mu. How far is x minus mu. Sigma means add. n is how many days. Do not drop five symbols on a card the viewer has not walked.
16. **Same average, different plan**: When the short is about spread, say the different plan out loud, on its own card, before the arithmetic.
17. **Cover order**: Mixed covers follow the slide. The speech language (first part of the slide key) is on top. The second language sits below. `en+zh` and `zh+en` do not both paint English first.
13. **Quiz transfer**: Q1 may check the short's own file. Q2 should use a new small file. The three languages must ask the same question and offer the same four options. Series number cells are plain `c11`–`c26`.

## Stage speech

These visuals paint progressive stills. Write one spoken chunk per still:

| visual | stages | Speech keys |
|--------|--------|-------------|
| `definition_card`, `formula` | 2 | `s1_*`, `s2_*` |
| `two_column`, `example`, `takeaway`, `three_column`, `steps` | 3 | `s1_*` … `s3_*` |
| `payoff_matrix` | up to 5 | `s1_*` … `s5_*` |
| `series` | 3, or cols+2 with `reveal: cells` | `s1_*` … `s3_*`. Fields: `row1`/`row2`, `col1`–`col6`, `c11`–`c26`, optional `footer`. Two rows across up to six days. Default: stage 2 fills row 1, stage 3 fills row 2 and the footer. `reveal: cells` fills row 1 one cell at a time during the first speech chunk, so a spoken count is on the card while it is named. |
| `table_grid`, `schematic_chart`, `dag`, `pair`, `pair_chart`, `pair_box`, `pair_slope`, `redraw`, `turns`, `shrink`, `mix`, `coin` | 3 | `s1_*` … `s3_*` |
| `title_card`, `big_number`, `module_open`, `module_close` | 1 | `en` / `zh` / `zh_hk` only |

`s1` is on screen with `_s1.png`, `s2` with `_s2.png`, and so on. Do not put factory talk in the speech (“watch the gold bar”, “this card”, “in the left box”).

## Optional fields

Lesson: `course`, `course_en`, `course_zh`, `course_zh_hk`, `audience`, `audience_en`, `audience_zh`, `audience_zh_hk`, `objective_en`, `objective_zh`, `objective_zh_hk`, `glossary`, `quiz`.

Beat: `kicker` (or `kicker_en` / `kicker_zh` / `kicker_zh_hk`), `title_en`, `title_zh`, `title_zh_hk`, `formula`, `gloss_*`, `left_*`, `right_*`, `setup_*`, `result_*`, `q1_*`, `q2_*`, `col1_*`, `col2_*`, `col3_*`, `step1_*`, `step2_*`, `step3_*`, `s1_*` … `s5_*`, `number`, `unit_*`, `caption_*`, `seconds`. Common English kickers (Concept, Definition, Example, Takeaway, …) are translated when labels are Chinese.

On-slide fields by visual:

| visual | On-screen fields |
|--------|------------------|
| `title_card` | Centered title and kicker |
| `definition_card` | `formula` or `formula_tex`, optional `gloss_*` |
| `two_column` | `left_*`, `right_*` |
| `formula` | `formula` or `formula_tex`, optional `gloss_*` |

`formula_tex` is matplotlib mathtext (LaTeX math subset), e.g. `"A = L + E"` or `"\\frac{Q_d}{P}"`. Optional `formula_tex_zh` / `formula_tex_zh_hk`. Only `formula_tex*` is sent to the math renderer. A plain `formula` / `formula_en` / `formula_zh` line is always painted as text. Do not put a spoken sentence in `formula_tex`. An underscore in `S_i` inside `formula_en` is ordinary text, not LaTeX.
| `example` | `setup_*` and `result_*` (falls back to `left_*` / `right_*`) |
| `takeaway` | `q1_*` and `q2_*` **required** in EN / 简 / 繁. Check and `validate.py` fail if either is missing. There is no default incentive pair. |
| `module_open` | Unit title plus `item1_*` … `item4_*` agenda. Used on `{MODULE}-IN` hook. A beat `kicker_*` replaces the default OPEN stamp. |
| `module_close` | Claim panel plus `next_*`. Used on `{MODULE}-OUT`. A beat `kicker_*` replaces CLOSE. `next_label_*` replaces the NEXT stamp when the line is a rule, not a handoff. |
| `three_column` | `col1_*`, `col2_*`, `col3_*` |
| `big_number` | `number` (or `formula`), `unit_*`, `caption_*` |
| `steps` | `step1_*` … `step3_*` stay three columns. `step4_*` and `step5_*` switch the card to a numbered stack. Optional `ex1_*` … `ex5_*` is the coffee example under that step. |
| `payoff_matrix` | `row_player_*`, `col_player_*`, `row1_*` `row2_*`, `col1_*` `col2_*`, `c11` `c12` `c21` `c22`, optional `note_*`, `highlight: c12` |
| `table_grid` | `rows` 2–4, `cols` 2 or 3, `row1_*`…, `col1_*`…, `c11`…. Optional `footer_*` and `stamp_*` (a gold line under the grid, used for “50 against 20. Extra 30.”). `highlight: c12` or `row1` / `col2` / `all`. A moving reading uses `highlight_s1`… and `caption_s1_*`. Cell format is `c21_fmt: blank` or `fmts: c21=blank, c13=mark`. `blank` is a missing cell, `mark` is a gold outline, `quiet` is a muted value. Optional `reveal: cols`. A six-cell grid reserves a caption band; do not put the caption inside a cell. |
| `schematic_chart` | `chart:` `histogram` `scatter` `boxplot` `two_line` `residual` `guesses`. Scatter reads `points`, optional `flag`, `bins`, `fit: "9400,310; 18600,390"`, `curve`, `kink`. A band reads `band` (or `band_lo` / `band_hi`) and optional `wide`. A guesses strip reads `guesses`, `mark`, optional `claim`, and optional `line`. Dots at or past the line turn gold. `two_line` reads `event_*` and optional `dash_*` (the missing path, “if the rent had stayed”). Axes are `x_*` / `y_*`. |
| `pair` | Two small tables. `left_*` and `right_*` are the titles. Left cells are `lrow1_*`, `lcol1_*`, `lc11`…; right cells are `rrow1_*`, `rcol1_*`, `rc11`…. Up to 3 rows and 2 columns each. Optional `footer_*`, `highlight: left` or `lc21` or `right`. Cell format uses the same `fmts` as a table: `lc31=blank, rc31=blank, lc11=quiet`. Stages: left table, right table, mark. |
| `pair_chart` | Two schematic histograms. `left_*` and `right_*` are the titles. `left_bars` and `right_bars` are comma-separated heights from 0 to 1. Optional `left_note_*`, `right_note_*`, `footer_*`. Stages: left, right, notes. |
| `pair_box` | Two boxplots on one shared scale. `left_*` and `right_*` are the names. Each side reads `left_lo`, `left_q1`, `left_med`, `left_q3`, `left_hi`, `left_flag` (and the `right_` twins). Ticks are `tick_lo`, `tick_mid`, `tick_hi`. A value at or above `flag_from` sits above the axis break. Shop names sit under the boxes. The footer is its own band. |
| `pair_slope` | Two Mondays, two clouds, two lines. `left_*` and `right_*` are the panel titles. `left_points` and `right_points` are `x,y; x,y`. `left_fit` and `right_fit` are the two green lines. Optional `footer_*`. Stages: left Monday, right Monday, the tilt. |
| `redraw` | Two handfuls. `left_*` and `right_*` are the titles. Chips are `l1_*`…`l3_*` and `r1_*`…`r3_*`. The second right chip turns gold on the last still, the row put back. |
| `turns` | A row of days. `days: Mon;Tue;Wed` (or `days_en` / `days_zh` / `days_zh_hk`). `hold` is the grey day, 1-based. Optional `footer_*`. Stages: the row, the held day, the note. |
| `shrink` | A copied step pulled toward zero. `full` and `pulled` are the bar lengths. Optional `unit_*` (“Step, not cups”). Optional `footer_*`. Stages: the copy, the pull, the note. |
| `mix` | One gap, two unnamed parts. `gap_*` is the bar label (`420 − 310`). `left_*` and `right_*` are the two blank parts. Do not name the shares. Optional `footer_*`. Stages: the gap, the split, the note. |
| `coin` | Two faces. `left_*` is the chosen face, `right_*` is the drawn face. Optional `footer_*`. Stages: chosen, drawn, the note. |
| `dag` | Nodes `n1_id` + `n1_*` … `n5_*` (or `nodes`). Edges `e1: X->T` … or `edges:` list. `highlight: X->Y`. Optional `role_*`. Stages: nodes, edges, highlight+role. |

`validate.py` fails the section when the required stems above are empty.

Glossary item: `en`, `zh`, `zh_hk` (optional), `lock` (boolean). If `lock: true`, neither the bot nor an RA may paraphrase that pair.

## Quiz schema

Quizzes support both open comprehension/transfer items and multiple-choice questions.

### Multiple choice format (Preferred for interactive shorts)

```yaml
quiz:
- id: Q1
  type: multiple_choice
  question_en: Question stem in English
  question_zh: 简体中文题干
  question_zh_hk: 繁體中文題幹
  options_en:
  - "A: First option"
  - "B: Second option"
  - "C: Third option"
  - "D: Fourth option"
  options_zh:
  - "A: 第一选项"
  - "B: 第二选项"
  - "C: 第三选项"
  - "D: 第四选项"
  options_zh_hk:
  - "A: 第一選項"
  - "B: 第二選項"
  - "C: 第三選項"
  - "D: 第四選項"
  answer: B
  explanation_en: Pedagogical rationale for correct answer.
  explanation_zh: 简明解析。
  explanation_zh_hk: 簡明解析。

## Normative validation contract
The structural rules in this section are mandatory. Examples elsewhere in this document are illustrative and do not override them.

### Validation profile
Before delivery, validate all of the following:

1. The YAML parses successfully as exactly one document.
2. `id` exactly matches the exported filename stem.
3. `course`, module, and lesson numbering are consistent with the requested lesson.
4. `duration_target_s` is between 60 and 240 and exactly equals the sum of all beat `seconds`.
5. Beat IDs are unique within the lesson.
6. Every `visual` is included in the visual enum in this schema.
7. Every beat contains the required on-screen fields for its visual.
8. Every unstaged beat contains exactly one complete speech trio: `en`, `zh`, and `zh_hk`.
9. Every staged beat contains the exact required stage count, with English, Simplified Chinese, and Hong Kong Traditional Chinese present at every stage.
10. A staged beat must not also contain whole-beat `en`, `zh`, or `zh_hk` speech.
11. Every `takeaway` contains `q1_en`, `q1_zh`, `q1_zh_hk`, `q2_en`, `q2_zh`, and `q2_zh_hk`.
12. Every multiple-choice question contains exactly four options in each language, a valid answer key, and an explanation in each language.
13. Locked glossary strings are unchanged.
14. The exported file contains no citation markers, Markdown fences, commentary, obsolete IDs, or invalid YAML escapes.
15. Re-open and parse the saved export. Validation of only an in-memory draft is insufficient.

### Machine-readable stage profile

```yaml
validation_profile:
  id_matches_filename: true
  duration_equals_beat_sum: true
  takeaway_questions:
    - q1_en
    - q1_zh
    - q1_zh_hk
    - q2_en
    - q2_zh
    - q2_zh_hk
  staged_speech:
    definition_card: 2
    formula: 2
    two_column: 3
    example: 3
    takeaway: 3
    three_column: 3
    steps: 3
    table_grid: 3
    schematic_chart: 3
    dag: 3
    pair: 3
    pair_chart: 3
    pair_box: 3
    pair_slope: 3
    redraw: 3
    turns: 3
    shrink: 3
    mix: 3
    coin: 3
  unstaged_visuals:
    - title_card
    - big_number
    - module_open
    - module_close
```

The profile documents validation expectations. It is not part of an individual lesson YAML unless an implementation explicitly requires it.

## Lesson-type profiles
A lesson does not need a fixed number of beats or a fixed duration, provided it stays within the supported duration range and its timing metadata is consistent.

### Topic lesson
A topic lesson normally contains:
1. a self-contained hook;
2. a definition or concept beat;
3. an explanation or comparison beat;
4. one worked example;
5. a takeaway that resolves the hook.

This five-beat pattern is guidance, not a schema requirement.

### Recap lesson
A recap lesson may contain four or more beats and may use `module_open`. It must still end with a `takeaway` that provides a complete decision rule. Its `duration_target_s` is the sum of its actual beats; it does not inherit a fixed duration from topic lessons.

## YAML scalar and escaping policy
Use one consistent scalar policy:

- Use plain scalars only for simple identifiers, booleans, enums, and numbers.
- Prefer single-quoted strings for ordinary text containing colons, comparison operators, brackets, backslashes, or Markdown-sensitive punctuation.
- Escape an apostrophe inside a single-quoted scalar by doubling it.
- Use `>-` for long spoken paragraphs when that improves readability.
- Use double quotes only when YAML escape processing is intentionally required.
- Never write invalid YAML escapes such as `\>`, `\<`, or `\=`.
- In ordinary text, write `>`, `<`, `>=`, and `<=` without a backslash.
- Reserve LaTeX-style backslashes for `formula_tex` fields.

## Numerical language contract
- Use `=` for exact identities under the stated model.
- Use `≈` or the word “approximately” for rounded results.
- Use “model probability” when parameters are supplied as assumptions.
- Use “estimated probability” only when parameters are estimated from data.
- Use “coverage” for probabilities of the form `P(X <= threshold)`.
- Use “guarantee” only for a genuine deterministic guarantee.
- Do not describe a mean as an exact expected observation, a percentile as a contractual promise, an approximation as exact, or a probability threshold as a complete operating policy.


## Visual contract

The picture is language-neutral in structure. `--labels en` or `--labels zh` only swaps titles and column labels. Do not put full spoken sentences on the slide. Do not add a new visual type without changing `factory/slides.py` and this document in the same commit.

## IDs

Teaching shorts use `MODULE-TOPIC`:

| Piece | What it is | Example |
|-------|------------|---------|
| `MODULE` | The module id, which already starts with the course | `STAT-M01`, `ECON-CH`, `GAME-M03` |
| `TOPIC` | **2–4 letters**, unique inside that module | `DE` data is not evidence, `SET` dataset, `OC` opportunity cost |

A short is `STAT-M01-DE`. Bookends stay `STAT-M01-IN` and `STAT-M01-OUT`. The old `01` variant slot is not used. A later retake of the same short can add `-02`, but the tree does not ship one. The factory only requires that `id` equals the filename and never collides.

Two topic codes were lengthened so they would not collide with a bookend: auditor independence is `AUD-M01-IND`, the innovation cluster is `GBA-M02-INN`.

Faculty edit sheet: Author tab, Download Excel. Yellow cells are the speech and labels. Import Excel merges them back into the YAML, keeps a `.bak`, and refuses the write if `validate.py` fails. CLI: `python3 factory/xlsx_lesson.py export lessons/STAT/STAT-M01-DE.yaml`. The RA review zip includes one workbook per short under `xlsx/`. Needs `openpyxl` (`requirements.txt`).

Module files are `AREA-M##` (`ECON-M01`). Bookend shorts are `{MODULE}-IN` and `{MODULE}-OUT` (`ACC-M01-IN`). Those ids have no variant slot.

Beat `id` is a different namespace: `hook`, `define`, `takeaway` inside one lesson. It is the audio filename, not part of the lesson id.

## File naming

```
lessons/<AREA>/<ID>.yaml
modules/<AREA-M##>.yaml
out/<ID>/slides/<lang or zh+en>/<nn>_<beat_id>[_sN].png
out/<ID>/preview/<lang>/…
out/<ID>/audio/{en,zh_cn,zh_hk}/<beat_id>.mp3
out/<ID>/cells/<ID>_{en,zh,hk,en+zh,…}.mp4
```

Primary language sets voice, captions, and primary slide labels: `en`, `zh` (Putonghua / 简), `hk` (Cantonese / 繁). A name with `+second` adds that language on the slides, for example `en+zh` is English speech and captions with bilingual English + 简 slides. Voice and captions stay the same language.

Faculty do not start from `briefs/`. Use the console Check tab and `docs/SOP-faculty.html`. Course zips: `out/_packs/CUHK-VF-{ECON,ACC,GBA}.zip`.

Draft a new short with `docs/AUTHORING_PROMPT.md`. Revise an existing YAML with `docs/REVISE_PROMPT.md`. Before delivery, run `docs/QA_CHECKLIST.md`.

## Mini-courses

A mini-course is a collection of standalone shorts on one larger topic. It is not a module. Building the index file paints each short and does not concatenate them. It is not bound by the six-lesson or 5–10 minute module cap.

Index files live in `minicourses/<id>.yaml` with `kind: minicourse` and a `lessons:` list. The live collections are `STAT-M01` (syllabus `docs/courses/STAT-M01.md`), `STAT-M02` (syllabus `docs/courses/STAT-M02.md`), `STAT-M03` (syllabus `docs/courses/STAT-M03.md`: fifteen distribution shorts, `STAT-M03-T01-INTRO` through `STAT-M03-T15-RECAP`), `STAT-M05` (syllabus `docs/courses/STAT-M05.md`: fifteen hypothesis-testing shorts, `STAT-M05-T01-FRAME` through `STAT-M05-T15-RECAP`), and `STAT-M06` (syllabus `docs/courses/STAT-M06.md`: fifteen simple-regression shorts, `STAT-M06-T01-SCATT` through `STAT-M06-T15-RECAP`), and `STAT-M07` (syllabus `docs/courses/STAT-M07.md`: fifteen multiple-regression and store-experiment shorts, `STAT-M07-T01-TWOVR` through `STAT-M07-T15-RECAP`). `STAT-M08` (syllabus `docs/courses/STAT-M08.md`: fifteen logistic-regression and customer-choice shorts, `STAT-M08-T01-BINRY` through `STAT-M08-T15-RECAP`). `STAT-M09` (syllabus `docs/courses/STAT-M09.md`: fifteen time-series and demand-forecasting shorts, `STAT-M09-T01-TIMED` through `STAT-M09-T15-RECAP`). `STAT-M10` (syllabus `docs/courses/STAT-M10.md`: fifteen applied A/B-testing shorts, `STAT-M10-T01-COUNT` through `STAT-M10-T15-RECAP`). `STAT-M04` (syllabus `docs/courses/STAT-M04.md`: fifteen sampling and interval shorts, `STAT-M04-T01-INTRO` through `STAT-M04-T15-RECAP`) An earlier hybrid draft is archived at `lessons/_attic/STAT-M04-hybrid/`. Build each short on its own. The factory does not concatenate a mini-course. The earlier chapter modules `STAT-M01` through `STAT-M40` are archived under `modules/_attic/chapter-series/`; their shorts are under `lessons/_attic/STAT-chapter/`. Do not restore those module files while the mini-courses use the same ids.
