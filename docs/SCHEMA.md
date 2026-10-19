# Lesson schema

A lesson is one YAML file under `lessons/<AREA>/`. The renderer looks up the file by id (`STAT-M01-DE` → `lessons/STAT/STAT-M01-DE.yaml`, `GAME-M03-BR` → `lessons/GAME/GAME-M03-BR.yaml`). A leftover flat `lessons/<ID>.yaml` still builds. Drafts live in `lessons/_inbox/`; retired files in `lessons/_attic/` — those two folders are skipped by the sidebar and by “build every lesson.”

## Required fields

| Field | Type | Rule |
|--------|------|------|
| `id` | string | Stable experiment/lesson ID. Must match the filename stem. See **IDs** below. |
| `title_en`, `title_zh`, `title_zh_hk` | string | Short base title. Used on the cover and as the start of the YouTube title. Name the topic so it stands alone. Do not depend on the example. Do not append `(English)`, `(普通话)`, or `(粵語)` here. |
| `duration_target_s` | number | Must equal the sum of beat `seconds`. A short module is often 60–240. A standalone teaching short may run longer when the beginner explanation needs it. `validate.py` currently errors only when the absolute gap exceeds 20 seconds. |
| `beats` | list | Ordered scenes. One claim or concept per beat. |

## Required fields on each beat

| Field | Type | Rule |
|--------|------|------|
| `id` | string | Unique within the lesson. Used as the audio filename. |
| `visual` | enum | `title_card`, `definition_card`, `two_column`, `formula`, `takeaway`, `example`, `three_column`, `big_number`, `steps`, `module_open`, `module_close`, `payoff_matrix`, `table_grid`, `series`, `rank_line`, `freq_bars`, `balance_line`, `box_line`, `dev_bars`, `ratio_bars`, `quad_scatter`, `schematic_chart`, `dag`, `pair`, `pair_chart`, `pair_box`, `pair_slope`, `redraw`, `turns`, `shrink`, `mix`, `coin`. |
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
7. **Own setting, neutral names**: Each short opens on its own business question. Never use Mong Kok, Wan Chai, Airport, or any other real place or branch name: use Shop A, Shop B, Shop C and days (A店 on a Chinese card, never 甲店). Do not require the shared Monday file. Do not repeat the same setting across shorts just to keep a ledger.
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
18. **Quiz transfer**: Q1 may check the short's own file. Q2 should use a new small file. The three languages must ask the same question and offer the same four options. Series number cells are plain `c11`–`c26`.

## Stage speech

These visuals paint progressive stills. Write one spoken chunk per still:

| visual | stages | Speech keys |
|--------|--------|-------------|
| `definition_card`, `formula` | 2 | `s1_*`, `s2_*` |
| `two_column`, `example`, `takeaway`, `three_column`, `steps` | 3 | `s1_*` … `s3_*` (a `steps` stack with `step4_*`/`step5_*` takes `s1_*` … `s4_*`/`s5_*`, one per row; `layout: rows` draws 1–3 steps as full-width rows, centred, the current row gold, instead of three columns — use it when the steps are equations) |
| `payoff_matrix` | up to 5 | `s1_*` … `s5_*` |
| `series` | 3 | `s1_*` … `s3_*`. Fields: `row1`/`row2`, `col1`–`col6`, `c11`–`c26`, optional `footer`, optional `tag_*` (the small gold label in the panel; no tag when unset, the kicker already names the card). Up to two rows across up to six days; when `row2` and every `c2*` are empty (or `rows: 1`), only one row is drawn. Bilingual column headers stack the second language under the first. Default: stage 2 fills row 1, stage 3 fills row 2 and the footer. With `reveal: cells`, row-1 cells still paint one at a time during **s1** only — the stage count stays 3 (not cols+2). Use that when speech names each day while its cell appears. |
| `rank_line` | 3 | `s1_*` … `s3_*`. Stage 1 shows the values as written. Stage 2 draws the ordered line and numbers the positions. Stage 3 turns the marked chips gold (the middle by default; the two ends with `mark: ends`), draws the `span` bracket and its text, and shows the footer. An odd count marks one middle cell. An even count marks the two middle cells. The bracket, labels and break are reserved from stage 1, so nothing jumps. |
| `freq_bars` | 3 | `s1_*` … `s3_*`. Stage 1 shows the category labels on the axis. Stage 2 grows the bars and writes the counts. Stage 3 golds the tallest bar(s) (or none) and shows the footer. |
| `balance_line` | 3 | `s1_*` … `s3_*`. Stage 1 places the values on a number line. Stage 2 marks the mean as the fulcrum. Stage 3 shows signed distances, the left vs right pull totals that balance, and the footer. |
| `box_line` | 3 | `s1_*` … `s3_*`. Stage 1 places the values as dots on a cup scale (numbers under them). Stage 2 golds Q1 and Q3 and labels them (`Q1 = 310`). Stage 3 draws the box from Q1 to Q3, the whiskers out to the lowest and highest value, the bracket with `span_*` under the box, and the footer. The scale, break and bands are pinned from stage 1, so nothing jumps. With `fences` the plan is an outlier screen: stage 1 the values, the box and whiskers (whiskers stop at the last value inside the fences) with `Q1 = …` / `Q3 = …`; stage 2 dashed fences with their numbers on top and a bracket from Q3 out to the upper fence carrying `span_*` (default `1.5 × IQR = …`); stage 3 the values outside a fence turn gold with a ring, plus the footer. |
| `dev_bars` | 3 | `s1_*` … `s3_*`. With `power: 1` (default), stage 1 places each value as a dot above or below the mean line (the raw value under its label), stage 2 grows signed bars from the line and writes each distance (`−65` … `+65`), and stage 3 golds the far bars (`mark`) and shows the footer. With `power: 2` (or 3, 4), stage 1 writes the products row (`−65 × −65`) under each label with the powered bars drawn muted and unlabelled, stage 2 draws the bars in full with each value (squares all point up; cubes keep the sign), and stage 3 golds the far bars and shows the footer. Even powers reserve no room below the mean line, so the squares fill the card. `signed_first: true` restores the older plan (stage 1 = the signed distance bars), which keeps a band below the line for them. The mean line, scale and bands are pinned from stage 1, so nothing jumps. With `values_b`, each bar number sits in its own half of the day slot and is painted after every bar, so the twin bar never covers it. |
| `ratio_bars` | 3 | `s1_*` … `s3_*`. Stage 1 draws each standard deviation as a bar on one shared scale (30 vs 150 cups: the big shop looks jumpier). Stage 2 turns every bar into that shop's own average at full height, with the standard deviation as the white slice on top and a bracket note (`30 cups`); `average 300` sits above the bar. Stage 3 writes the share large in each bar (`10%`, `5%`), adds the `30 / 300` note, golds the `mark` bar(s) and shows the footer. Slots, baseline and full height are pinned from stage 1. |
| `quad_scatter` | 3 | `s1_*` … `s3_*`. Stage 1 places the points on the axes. Stage 2 draws the mean cross-hairs and the + / − quadrant signs. Stage 3 golds the `mark` points, writes each paired product, and shows the footer. The plot box is pinned from stage 1. (`mode: ruler`: ruler → clouds → pin at `r`). |
| `table_grid`, `schematic_chart`, `dag`, `pair`, `pair_chart`, `pair_box`, `pair_slope`, `redraw`, `turns`, `shrink`, `mix`, `coin` | 3 | `s1_*` … `s3_*` |
| `title_card`, `big_number`, `module_open`, `module_close` | 1 | `en` / `zh` / `zh_hk` only |

`s1` is on screen with `_s1.png`, `s2` with `_s2.png`, and so on. Do not put factory talk in the speech (“watch the gold bar”, “this card”, “in the left box”).

## Optional fields

Lesson: `course`, `course_en`, `course_zh`, `course_zh_hk`, `audience`, `audience_en`, `audience_zh`, `audience_zh_hk`, `objective_en`, `objective_zh`, `objective_zh_hk`, `youtube`, `glossary`, `quiz`.

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
| `steps` | `step1_*` … `step3_*` stay three columns. `step4_*` and `step5_*` switch the card to a numbered stack with one still per row, so a 4-row stack needs `s1`…`s4` and a 5-row stack `s1`…`s5` (`validate.py` fails a mismatch; a 3-column card takes at most `s1`…`s3`). Stack text scales to the row height. Optional `ex1_*` … `ex5_*` is the coffee example under that step. |
| `rank_line` | Three to six values on one line. `values: 80;200;120` (or `values_en` / `values_zh` / `values_zh_hk` when the chips are words). A YAML list is also read. `v1_*` … `v6_*` is the other shape, one chip per stem; `values` wins when both are set. `order: sorted` (default) rearranges numbers from low to high on stage 2. `order: as_given` keeps the written order, for a line that is already ranked. `mark: middle` (default) golds the middle; `mark: none` leaves the chips plain. `mark: ends` golds the first and last chips (range); `mark: 2;4` golds 1-based places. Optional chip labels via `labels: Shop A;Shop B` (or `labels_en` / `labels_zh` / `labels_zh_hk`, or `l1_*` … `l6_*`) sit small above each value and travel with it when sorted; keep them chip-short (A店 / Shop A). Optional `span: ends` (or `all`, or a 1-based range such as `2-4`) draws a bracket under the ordered line on stage 3, with `span_*` as its gold text (write it as a math line, `420 − 310 = 110 cups` / `420 − 310 = 110 杯`, so it prints once). Optional `break: last` (or a place such as `5`) puts an axis break (`//` and a gap) before that place on the ordered line, for one far value. Optional `footer_*` is the gold line on stage 3. Commas stay inside a value (`1,200;80;40`), so do not comma-separate the list. Use for median, an ordered Likert line, or range (ends + span). Speech only in `s1_*`/`s2_*`/`s3_*` (written → ordered → middle, or ends + span). |
| `freq_bars` | Two to six category bars. `counts: 40;280;100` (semicolon or YAML list). Labels are `labels: Small;Medium;Large` (or `labels_en` / `labels_zh` / `labels_zh_hk`) or `l1_*` … `l6_*`. `mark: tallest` (default) golds every bar tied for the maximum count; `mark: none` leaves them plain; `mark: all` golds every bar; `mark: 2;3` picks 1-based indices. Optional `footer_*` is the gold line on stage 3. Use for mode, frequency, or categorical counts when the lesson is which category wins by count — not for a Monday cell sheet (`table_grid`) or a spoken arithmetic list (`steps`). Speech only in `s1_*`/`s2_*`/`s3_*`. |
| `balance_line` | Three to six numeric values on a seesaw line. `values: 250;300;350;500` (semicolon or YAML list; `values_en` / `values_zh` / `values_zh_hk` also work). `v1_*` … `v6_*` is the other shape; `values` wins when both are set. `mean: 350` (aliases `center`, `fulcrum`) is the fulcrum. Optional shop labels via `labels` / `labels_*` or `l1_*` … `l6_*`. Optional `left_*` / `right_*` override the stage-3 pull captions (default: “N below” / “N above”, auto-computed from the signed distances). Optional `footer_*` is the gold line on stage 3. Use for the mean as a balance point — not for a median order (`rank_line`) or a spoken deviation list (`steps`). Speech only in `s1_*`/`s2_*`/`s3_*` (values → mean fulcrum → left=right pulls + footer). |
| `box_line` | One horizontal box on a number line. `values: 360;420;280;390;310` (3–8 numbers, semicolon or YAML list; commas stay inside a value, `4,200`). The line sorts them. Q1 and Q3 default to the nearest-rank method (place = 0.25 × n and 0.75 × n, rounded up); `q1:` / `q3:` override them. Optional `span_*` is the gold text under the box bracket (default `Q3 − Q1 = …`; write it as a math line, `390 − 310 = 80 cups` / `390 − 310 = 80 杯`, so it prints once). Optional `break: last` puts an axis break before one far value above Q3 (`4,200`). Optional `median:` draws a line inside the box. Optional `fences: on` adds the 1.5 × IQR fences (Q1 − 1.5 × IQR and Q3 + 1.5 × IQR), or `fences: 190;510` gives them directly; the scale widens to show both fences, crowded numbers drop onto two staggered rows, and the tag reads FENCES / 围栏 / 圍欄 (`tag_*` overrides any box_line tag). Use it for an outlier screen; with `break: last` the far value must sit above the upper fence. Optional `footer_*` is the gold line on stage 3. The box carries no chip labels; Q labels are language-neutral, so bilingual cells only stack the span and footer. Use for the IQR, a box-plot picture, or showing that one far value stretches the whiskers but barely moves the box — not for a median walk (`rank_line`). Speech only in `s1_*`/`s2_*`/`s3_*` (values → Q1 and Q3 → box + span + footer). |
| `dev_bars` | Signed deviation bars around a mean line. `values: 300;330;365;400;430` (3–6 numbers, semicolon or YAML list), `mean: 365` (required), optional bar labels via `labels` / `labels_*` or `l1_*`…`l6_*` (`Day 1`), optional `power: 1|2|3|4` (default 1), optional `mark: far` (default, the largest distance(s)) / `none` / `all` / 1-based places such as `1;5`, optional `values_b` (a second shop drawn beside each bar on the same scale, with `name_a_*` / `name_b_*` for the legend; `mark` lights the first shop only), optional `signed_first: true` (power 2–4: stage 1 shows the signed bars first), optional `standardize: true` (power 2–4: each powered distance is divided by σ to the same power, σ from that shop's own days with divide by n, so the bars read as small plain numbers such as `6.25`; their average is the kurtosis at power 4), optional `tag_*` (default from the power: DISTANCE FROM THE MEAN / TIMES ITSELF / CUBED / FOURTH POWER), optional `footer_*`. The bar numbers are computed and language-neutral (U+2212 minus), so a bilingual cell only stacks the bar labels, the legend and the footer. Use it for deviations (power 1), squares before the variance (power 2), Shop A beside Shop B, and cubes or fourth powers (skewness, kurtosis). Not for the mean seesaw (`balance_line`). Speech only in `s1_*`/`s2_*`/`s3_*`. |
| `ratio_bars` | Coefficient of variation as a slice of each shop's own average. `means: 300;3000` and `sds: 30;150` (2–4 shops, numbers, every mean above zero, each sd at most its mean), optional bar labels via `labels` / `labels_*` or `l1_*`…`l4_*` (`Shop A`), optional `unit_*` (`cups` / `杯`, written after the sd numbers), optional `mark: highest` (default, the largest CV) / `lowest` / `none` / `all` / 1-based places, optional `tag_*` or per-stage `tag1_*`…`tag3_*` (defaults SWING IN CUPS / AGAINST ITS OWN AVERAGE / SWING AS A SHARE), optional `footer_*`. The CV percents (`10%`, `5%`) and the `30 / 300` notes are computed; do not type them. Use it when a bigger standard deviation belongs to a bigger shop (CV), or to compare swings across product lines. Not for a single shop (`dev_bars`). Speech only in `s1_*`/`s2_*`/`s3_*`. |
| `quad_scatter` | Scatter with mean cross-hairs and quadrant signs. `xs: 10000;12000;13000;16000;19000` and `ys: 300;330;360;400;460` (3–8 points). Optional `mean_x` / `mean_y` (default: averages of `xs` / `ys`). Optional labels via `labels` / `labels_*` or `l1_*`…. Optional `x_axis_*` / `y_axis_*`. Optional `mark: same` (default) / `opposite` / `none` / `all` / places. Optional `tag_*` / `footer_*`. Mode is `scatter`. Products use U+2212.  Set `mode: ruler` for a −1…+1 scale: no `xs`/`ys`; required `r` (e.g. `0.996`); optional `left_*`/`mid_*`/`right_*` cloud captions; `s1` ruler → `s2` three mini clouds → `s3` gold pin at `r` + footer. Speech only in `s1_*`/`s2_*`/`s3_*`. |
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

`validate.py` fails the section when the required stems above are empty. It also fails a `steps` beat whose speech stages do not match its rows (4–5 rows need one stage per row; 3 columns take at most 3). A `rank_line` with fewer than 3 or more than 6 values fails, as does a `mark`, `span` or `break` outside the line, or chip labels whose count differs from the values. Value lists that differ in length across languages fail. A `freq_bars` with fewer than 2 or more than 6 bars, or without `counts`, fails. A `balance_line` with fewer than 3 or more than 6 values, non-numeric values, or without `mean`, fails. A `box_line` with fewer than 3 or more than 8 values, non-numeric values, a non-numeric `q1`/`q3`/`median`, Q1 above Q3, quartiles outside the values, or a `break` that is not `last` (with the far value above Q3), fails, as do `fences` that are not `on` or two numbers, fences inside the box, or `fences` with `break: last` whose far value is not above the upper fence. A `dev_bars` with fewer than 3 or more than 6 values, non-numeric values, no `mean`, a `values_b` of a different length, a `power` outside 1–4, a `mark` outside the bars, or labels whose count differs from the values, fails. A `ratio_bars` with fewer than 2 or more than 4 means, non-numeric means or sds, a mean at or below zero, an sd above its mean, a `mark` outside the bars, or labels whose count differs from the means, fails. A `quad_scatter` with fewer than 3 or more than 8 points, non-numeric `xs`/`ys`, mismatched lengths, a bad `mark`, or labels whose count differs from the points, fails.

Shape only, not a lesson. Odd count, one middle. Even count, the two middles:

```yaml
# rank_line shape. Do not paste this in as a short.
visual: rank_line
values: 80;200;120
order: sorted
mark: middle
footer_en: Middle = 120
footer_zh: 中间 = 120
footer_zh_hk: 中間 = 120
# even: values 200;300;100;400, footer Share 200 and 300
# words already in order: order as_given, and v1_en … v3_en instead of values
```

Range shape: gold ends, labelled chips, a bracket, and an axis break for one far value.

```yaml
# rank_line range shape. Do not paste this in as a short.
visual: rank_line
values: 380;310;420;370;4,200
labels_en: Shop A;Shop B;Shop C;Shop D;Shop E
labels_zh: A店;B店;C店;D店;E店
labels_zh_hk: A店;B店;C店;D店;E店
order: sorted
mark: ends
span: ends
break: last
span_en: 4,200 − 310 = 3,890 cups
span_zh: 4,200 − 310 = 3,890 杯
span_zh_hk: 4,200 − 310 = 3,890 杯
```


```yaml
# freq_bars shape. Do not paste this in as a short.
visual: freq_bars
labels: Small;Medium;Large
counts: 40;280;100
mark: tallest
footer_en: Mode = Medium
footer_zh: 众数 = 中杯
footer_zh_hk: 眾數 = 中杯
# tie: counts 40;150;150, footer Medium and Large
# none: counts 1;1;1, mark none
```

```yaml
# balance_line shape. Do not paste this in as a short.
visual: balance_line
values: 250;300;350;500
mean: 350
labels: A;B;C;D
left_en: 150 cups below
right_en: 150 cups above
footer_en: "−100 − 50 + 0 + 150 = 0"
footer_zh: "−100 − 50 + 0 + 150 = 0"
footer_zh_hk: "−100 − 50 + 0 + 150 = 0"
# mean aliases: center, fulcrum
```

```yaml
# box_line shape. Do not paste this in as a short.
visual: box_line
values: 280;310;360;390;420;4,200
break: last
span_en: 420 − 310 = 110 cups
span_zh: 420 − 310 = 110 杯
span_zh_hk: 420 − 310 = 110 杯
footer_en: 'End to end: 140 → 3,920 cups'
# Q1/Q3 default to nearest rank (0.25 × 6 = 1.5 → place 2; 0.75 × 6 = 4.5 → place 5)
# optional: q1: 310, q3: 420, median: 375
# outlier screen: fences: on   (or fences: 190;510); span_* then sits on the Q3 → upper-fence bracket, e.g. 1.5 × 80 = 120 cups
```

```yaml
# dev_bars shape. Do not paste this in as a short.
visual: dev_bars
values: 300;330;365;400;430
mean: 365
power: 2            # 1 = signed distances (default); 2 = times itself; 3, 4 for skew / kurtosis
labels_en: Day 1;Day 2;Day 3;Day 4;Day 5
labels_zh: 第1天;第2天;第3天;第4天;第5天
mark: far           # far (default) | none | all | 1;5
footer_en: Sum of squares = 10,900
footer_zh: 平方之和 = 10,900
# optional second shop on the same scale:
# values_b: 350;360;365;370;380
# name_a_en: Shop A / name_b_en: Shop B
```

```yaml
# ratio_bars shape. Do not paste this in as a short.
visual: ratio_bars
means: 300;3000     # each shop's average
sds: 30;150         # each shop's standard deviation, same unit
unit_en: cups
unit_zh: 杯
labels_en: Shop A;Shop B
labels_zh: A店;B店
mark: highest       # highest (default) | lowest | none | all | 1;2
footer_en: 'A: 10% of its day. B: 5%.'
footer_zh: A店：一天的10%；B店：5%
# quad_scatter shape. Do not paste this in as a short.
visual: quad_scatter
xs: 10000;12000;13000;16000;19000
ys: 300;330;360;400;460
mean_x: 14000
mean_y: 370
labels_en: Shop A;Shop B;Shop C;Shop D;Shop E
x_axis_en: Rent ($)
y_axis_en: Cups
mark: same
footer_en: "Products 880,000 / 5 = 176,000"

# quad_scatter ruler (correlation scale). Do not paste this in as a short.
visual: quad_scatter
mode: ruler
r: 0.996
left_en: Near −1
mid_en: Near 0
right_en: Near +1
footer_en: "Five shops: r ≈ +1.00"

```

Glossary item: `en`, `zh`, `zh_hk` (optional), `lock` (boolean). If `lock: true`, neither the bot nor an RA may paraphrase that pair.

## YouTube upload text

Optional. v1 writes a paste file only. There is no YouTube API upload, no JSON sidecar, and no copy from `objective_*`.

```yaml
youtube:
  description_en: |
    ...
  description_zh: |
    ...
  description_zh_hk: |
    ...
```

Each requested cell gets one file beside its MP4:

```
out/lessons/<ID>/cells/<ID>_<cell>.youtube.txt
```

Line 1 is the YouTube title. A blank line follows. The description body is the rest. A missing description still writes the file: the title, a blank line, and an empty body.

The factory builds the title from the short base title plus a language tag. The description follows the **speech** language, so `en+zh` uses `description_en`.

| Cell | Title |
|------|--------|
| `en` | `title_en` + ` (English)` |
| `zh` | `title_zh` + ` (普通话)` |
| `hk` | `title_zh_hk` + ` (粵語)` |
| `en+zh` | `title_en` + ` (Speech: English · Slides: 简体)` |
| `en+hk` | `title_en` + ` (Speech: English · Slides: 繁體)` |
| `zh+en` | `title_zh` + `（旁白：普通话 · 画面：English）` |
| `zh+hk` | `title_zh` + `（旁白：普通话 · 画面：繁體）` |
| `hk+en` | `title_zh_hk` + `（旁白：粵語 · 畫面：English）` |
| `hk+zh` | `title_zh_hk` + `（旁白：粵語 · 畫面：简体）` |

English tags use a leading space and halfwidth parentheses. Chinese tags sit against the title and use fullwidth parentheses. Putonghua tags stay in 简体 (`画面`). Cantonese tags stay in 繁體 (`畫面`). The dot is `·`.

Limits, counted after trimming the description and on the full YouTube title including the tag:

- A description must be strictly less than 2500 characters. 2500 or more is an error.
- A mono YouTube title over 100 characters is an error when the base title itself is still within 100.
- A mono title over 100 is only a warning when the base title is already over 100, so an existing long cover title does not fail the lesson.
- A mixed-cell title over 100 is a warning. The speech/slides tag is longer, and some existing English titles plus that tag already pass 100. The sidecar is still written. Shorten the base title before upload.

`validate.py` prints title warnings and still exits 0. A description error exits 1.

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
4. `duration_target_s` equals the sum of all beat `seconds`. A short module is often 60–240. A standalone teaching short may run longer when the beginner explanation needs it. `validate.py` currently errors only when the absolute gap exceeds 20 seconds.
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
    steps: 3   # 4 or 5 for a numbered stack: one stage per row
    rank_line: 3
    freq_bars: 3
    balance_line: 3
    box_line: 3
    dev_bars: 3
    ratio_bars: 3
    quad_scatter: 3
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

- In M01 descriptive lessons, variance / SD / covariance that describe the file divide by **n**. Do not document n−1 as the default inside these shorts.
- Each topic short stands alone: the hook must not depend on “last short” or “the covariance short.” Restate the file and any reused total in one sentence.
- Use `=` for exact identities under the stated model.
- Use `≈` or the word “approximately” for rounded results.
- Use “model probability” when parameters are supplied as assumptions.
- Use “estimated probability” only when parameters are estimated from data.
- Use “coverage” for probabilities of the form `P(X <= threshold)`.
- Use “guarantee” only for a genuine deterministic guarantee.
- Do not describe a mean as an exact expected observation, a percentile as a contractual promise, an approximation as exact, or a probability threshold as a complete operating policy.


## Visual contract

### Visual index (when to use)

| Visual | Use when | Stages (typical) |
|---|---|---|
| `rank_line` | Ordered chips: median, percentile place, range ends, quartile marks | written → ordered → mark/span/footer |
| `freq_bars` | Category counts / mode / modal class | labels → bars+counts → tallest/none |
| `balance_line` | Mean as seesaw (left pull = right pull) | values → fulcrum → pulls + footer |
| `box_line` | IQR box; add `fences` for outlier screen | values → Q1/Q3 → box[/fences] |
| `dev_bars` | Deviations, squares, cubes, fourth powers (`power`, optional `standardize`, `values_b`) | dots or products → bars → far + footer |
| `ratio_bars` | CV: SD vs own mean | raw SDs → own average → CV shares |
| `quad_scatter` | Covariance cloud; `mode: ruler` + `r` for correlation scale | points → means → products / pin |
| `steps` + `layout: rows` | Equation stack that must stay one line each | one speech stage per row |
| `series` / `table_grid` / `two_column` / `definition_card` / `title_card` / `takeaway` / `dag` | Data sheet, dials, compare, define, name, close, confounder | per SCHEMA stage table |

Prefer the dedicated visual over packing the same idea into `two_column` prose. Keep bilingual fields inside the budgets below.


The picture is language-neutral in structure. `--labels en` or `--labels zh` only swaps titles and column labels. Do not put full spoken sentences on the slide. Do not add a new visual type without changing `factory/slides.py` and this document in the same commit.

Digits and operators stay ASCII in every language (no full-width １２３ in Chinese lines). A combining mark (x̄, X̄) is painted with its base letter.

Mixed Chinese + digit lines match the Chinese. In any line with CJK, Latin letters and digits sit on the CJK baseline (they no longer float up). Inside a Chinese phrase (`六家里有四家不高于 390`, `A店`, a title with `24`), digits and letters are drawn in the CJK face itself when it has them (YaHei on Windows, Noto CJK on the box), so their height and weight match the characters; when the CJK face lacks them, the Latin face is scaled to the CJK digit height. An equation with a unit word (`1,400 / 4 = 350 杯`) keeps the Latin face, so it matches the pure-math line above it. The English half of a one-line pair (`比较哪些店  The Group`) keeps its own face. Rewording Chinese titles to avoid digits is no longer needed.

Short equations stay on one line. A line (or one language of a pair) with exactly one `=` or `≈`, at most 40 characters and 6 CJK characters, and a number on the right (`10,900 / 5 = 2,180`, `平方之和 = 10,900`, `第 4 位 = 390 杯`) is one unbreakable unit: the card shrinks it by up to 30% before it may wrap. Longer lines or two equations in one step (`48 × 48 = 2,304. 36 × 36 = 1,296.`) wrap as before, so give each equation its own step.

### Bilingual on-screen budgets

A bilingual cell (`en+zh`, `en+hk`, `zh+en`, `hk+en`) stacks both languages on one card. Keep each on-screen field within these limits (Latin characters for `_en`, CJK characters for `_zh` / `_zh_hk`). `validate.py` prints `WARN` lines past them; it does not fail the lesson.

| field | Latin | CJK |
|---|---:|---:|
| `title_*` | 32 | 14 |
| `left_*` / `right_*` | 28 | 12 |
| `step*_*` in a 4–5 row stack | 30 | 14 |
| `step*_*` in 3 columns, `col1_*`…`col3_*` | 40 | 18 |
| chips and bar labels (`values`, `labels`, `v*`, `l*`, `days`; `dev_bars` and `ratio_bars` bar labels; `quad_scatter` point labels) | 10 | 4 |
| `footer_*`, `rank_line` / `box_line` `span_*` | 36 | 16 |
| `formula_*` (per line), `gloss_*`, `setup_*`, `result_*` | 40 | 18 |
| `q1_*` / `q2_*`, `claim_*`, `next_*` | 45 | 20 |
| `module_open` `item*_*` | 30 | 14 |

Math lines print once: when the two languages of a field differ only by a unit word (at most 8 letters or CJK characters, same digits and operators, an `=` present), the bilingual card shows the primary line only. Write "1,400 / 4 = 350 cups" / "1,400 / 4 = 350 杯", not two different sentences. A multi-line field (a `definition_card` formula) prints once when every line is identical or the same equation up to a unit word (`CV = σ / μ × 100%` + `A: 30 / 300 × 100% = 10%` / `A店：…`).

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
out/lessons/<ID>/slides/<lang or zh+en>/<nn>_<beat_id>[_sN].png
out/lessons/<ID>/preview/<lang>/…
out/lessons/<ID>/audio/{en,zh_cn,zh_hk}/<beat_id>.mp3
out/lessons/<ID>/cells/<ID>_{en,zh,hk,en+zh,…}.mp4
out/lessons/<ID>/cells/<ID>_{en,zh,hk,en+zh,…}.youtube.txt
```

The `.youtube.txt` file is the paste title and description for that cell. See **YouTube upload text**.

`out/` in these paths is the lesson output root. The default is `<Downloads>/video-factory-out`. Set `VF_OUT` or pass `--out` only to override it. If Downloads cannot be used, the root falls back to `<repo>/out`. Lesson YAML stays in `lessons/`. See `docs/SETUP.md`.

Primary language sets voice, captions, and primary slide labels: `en`, `zh` (Putonghua / 简), `hk` (Cantonese / 繁). A name with `+second` adds that language on the slides, for example `en+zh` is English speech and captions with bilingual English + 简 slides. Voice and captions stay the same language.

Faculty do not start from `briefs/`. Use the console Check tab and `docs/SOP-faculty.html`. Course zips: `out/_packs/CUHK-VF-{ECON,ACC,GBA}.zip`.

Draft a new short with `docs/AUTHORING_PROMPT.md`. Revise an existing YAML with `docs/REVISE_PROMPT.md`. Before delivery, run `docs/QA_CHECKLIST.md`.

## Mini-courses

A mini-course is a collection of standalone shorts on one larger topic. It is not a module. Building the index file paints each short and does not concatenate them. It is not bound by the six-lesson or 5–10 minute module cap.

Index files live in `minicourses/<id>.yaml` with `kind: minicourse` and a `lessons:` list. The live collections are `STAT-M01` (syllabus `docs/courses/STAT-M01.md`), `STAT-M02` (syllabus `docs/courses/STAT-M02.md`), `STAT-M03` (syllabus `docs/courses/STAT-M03.md`: fifteen distribution shorts, `STAT-M03-T01-INTRO` through `STAT-M03-T15-RECAP`), `STAT-M05` (syllabus `docs/courses/STAT-M05.md`: fifteen hypothesis-testing shorts, `STAT-M05-T01-FRAME` through `STAT-M05-T15-RECAP`), and `STAT-M06` (syllabus `docs/courses/STAT-M06.md`: fifteen simple-regression shorts, `STAT-M06-T01-SCATT` through `STAT-M06-T15-RECAP`), and `STAT-M07` (syllabus `docs/courses/STAT-M07.md`: fifteen multiple-regression and store-experiment shorts, `STAT-M07-T01-TWOVR` through `STAT-M07-T15-RECAP`). `STAT-M08` (syllabus `docs/courses/STAT-M08.md`: fifteen logistic-regression and customer-choice shorts, `STAT-M08-T01-BINRY` through `STAT-M08-T15-RECAP`). `STAT-M09` (syllabus `docs/courses/STAT-M09.md`: fifteen time-series and demand-forecasting shorts, `STAT-M09-T01-TIMED` through `STAT-M09-T15-RECAP`). `STAT-M10` (syllabus `docs/courses/STAT-M10.md`: fifteen applied A/B-testing shorts, `STAT-M10-T01-COUNT` through `STAT-M10-T15-RECAP`). `STAT-M04` (syllabus `docs/courses/STAT-M04.md`: fifteen sampling and interval shorts, `STAT-M04-T01-INTRO` through `STAT-M04-T15-RECAP`) An earlier hybrid draft is archived at `lessons/_attic/STAT-M04-hybrid/`. Build each short on its own. The factory does not concatenate a mini-course. The earlier chapter modules `STAT-M01` through `STAT-M40` are archived under `modules/_attic/chapter-series/`; their shorts are under `lessons/_attic/STAT-chapter/`. Do not restore those module files while the mini-courses use the same ids.
