# Lesson YAML QA checklist

Use this checklist after authoring or revising a lesson and before delivery. Validation must be performed on the saved export, not only on an in-memory draft.

## 1. Source and scope
- [ ] Identify whether the task is new authoring or revision.
- [ ] Confirm the requested course, module, lesson number, and topic.
- [ ] Identify the source course plan and any existing YAML.
- [ ] Separate supplied facts from teaching assumptions.
- [ ] Identify any conflicts among the user request, course plan, prompt files, and schema.
- [ ] Apply precedence: explicit user instruction, applicable authoring/revision guidance, then SCHEMA for structural requirements.

## 2. File identity
- [ ] Export as UTF-8 YAML.
- [ ] Filename is exactly `<id>.yaml`.
- [ ] `id` matches the filename stem character for character.
- [ ] `course` matches the requested module.
- [ ] Topic numbering and mnemonic suffix are consistent.
- [ ] No obsolete ID, course code, or previous-topic reference remains.

## 3. YAML syntax
- [ ] Parse as exactly one YAML document.
- [ ] Indentation and list nesting are valid.
- [ ] Scalar types are correct.
- [ ] No Markdown fences or commentary exist inside the YAML.
- [ ] No citation markers exist inside the YAML.
- [ ] No invalid escapes such as `\>`, `\<`, or `\=` occur.
- [ ] Comparison operators in ordinary text are unescaped.
- [ ] `formula_tex` contains only renderer-compatible math, not lecture prose.
- [ ] Saved file reopens and parses successfully.

## 4. Lesson-level completeness
- [ ] Required lesson fields are present.
- [ ] Titles and objective are synchronized across English, 简体, and 繁體.
- [ ] `title_*` is the short cover title only. It does not already contain `(English)`, `(普通话)`, `(粵語)`, or a speech/slides tag.
- [ ] If `youtube:` is present, it has only `description_en`, `description_zh`, and `description_zh_hk`. Each description is strictly less than 2500 characters. It was not copied from `objective_*`.
- [ ] A mono YouTube title (base title plus the language tag) is within 100 characters. A mixed-cell title over 100 is a warning to shorten before upload, not a reason to invent a second title field.
- [ ] `duration_target_s` equals the sum of beat `seconds`. A short module is often 60–240. A standalone teaching short may run longer when the beginner explanation is split.
- [ ] Glossary items contain required language fields.
- [ ] Every `lock: true` glossary string is preserved exactly.

## 5. Beat structure
- [ ] Beat IDs are unique.
- [ ] Every visual is listed in SCHEMA.
- [ ] Every visual has all required on-screen fields.
- [ ] Each beat advances one primary claim or concept.
- [ ] On-screen text is concise; spoken explanation remains in speech fields.

### Unstaged beats
For `title_card`, `big_number`, `module_open`, and `module_close`:
- [ ] Exactly one `en`, `zh`, and `zh_hk` speech trio is present.
- [ ] No staged speech keys are present.

### Staged beats
- [ ] `definition_card` and `formula` have exactly 2 stages.
- [ ] `two_column`, `example`, `takeaway`, `three_column`, and 3-step `steps` have exactly 3 stages.
- [ ] A `steps` stack with `step4_*` / `step5_*` has exactly one speech stage per row (`s1`…`s4` / `s1`…`s5`). `validate.py` fails a mismatch.
- [ ] `table_grid`, `series`, `rank_line`, `freq_bars`, `balance_line`, `box_line`, `dev_bars`, `ratio_bars`, `quad_scatter`, `schematic_chart`, `dag`, `pair`, `pair_chart`, `pair_box`, `pair_slope`, `redraw`, `turns`, `shrink`, `mix`, and `coin` have exactly 3 stages. Optional `mode: ruler` + `r` for the −1…+1 scale (clouds then pin).
- [ ] `payoff_matrix` has no more than 5 stages and matches its intended reveal sequence.
- [ ] Every stage contains English, 简体, and 繁體.
- [ ] No whole-beat `en`, `zh`, or `zh_hk` duplicates staged speech.
- [ ] Stage narration forms one continuous spoken argument.

## 6. Standalone lesson test
- [ ] Hook opens with a concrete decision, operational problem, or puzzling question.
- [ ] Hook card title names the topic: "What is the median?", "What is the mode?", "What is skewness?".
- [ ] Hook speech still opens on the cost of being wrong, then names the word at the end of the hook.
- [ ] Same average does not mean the same plan, when the short is about spread: the different plan is said out loud before the arithmetic.
- [ ] Hook does not refer to previous lessons.
- [ ] Hook does not hand off from another short ("last time", "covariance told us", "as in the mean short"). Restate any reused file in one sentence.
- [ ] Shops are generic (Shop A, Shop B, Shop C). No Mong Kok, Wan Chai, Airport, or any real place or branch name. No switch to 甲店 on the Chinese line.
- [ ] Each card opens from the last sentence of the previous card.
- [ ] A dense calculation is split. Square, sum, divide, and root are not packed on one card.
- [ ] A tiny example comes before a symbol: 3 × 3 = 9 before “squared”; “what number times itself” before “square root.”
- [ ] The main names appear as large words on a card after the number is known, not only in the speech.
- [ ] A formula is nicknames for steps already done. No symbol arrives before the number it names.
- [ ] Median walks an odd line and an even line. Mode walks a winner, a tie, and no mode, then a grouped band.
- [ ] Why the other numbers fail is said before the count, when the short is about labels.
- [ ] Drawbacks are named, then the next tool: no mode leads to the modal class.
- [ ] Variance is said as cups times cups on first use.
- [ ] Speech matches the visual. A series that names each day uses `reveal: cells`. A walk of distances from the mean uses `dev_bars` (dots → signed bars → far bars); squares use `dev_bars` `power: 2` (products row → squares → sum; no empty band below the mean line). A short spoken arithmetic list uses `steps`. A median walk uses `rank_line` (written → ordered → middle); a range walk uses `rank_line` with `mark: ends` + `span: ends` (written → ordered → ends + bracket). A mode/frequency walk uses `freq_bars` (labels → bars+counts → tallest/none + footer). A mean balance walk uses `balance_line` (values → mean fulcrum → left=right pulls + footer). An IQR walk finds Q1 and Q3 on `rank_line`, then uses `box_line` (values → Q1 and Q3 → box + whiskers + span). A CV walk uses `ratio_bars` (raw SDs → own average → shares).
- [ ] `freq_bars` has `counts`, matching labels (`labels`/`labels_*` or `l1_*`…`l6_*`), a valid `mark`, and speech only in `s1_*`/`s2_*`/`s3_*` (no whole-card `en` on that beat).
- [ ] `rank_line` has 3–6 values and speech only in `s1_*`/`s2_*`/`s3_*`. Any `labels` match the value count and stay chip-short; `mark`, `span` and `break` name places inside the line; `span_*` is a math line that prints once; the s3 speech reads the gold chips and the bracket in the order they appear.
- [ ] `balance_line` has 3–6 numeric `values`, a `mean`, optional labels/`left_*`/`right_*`/`footer_*`, and speech only in `s1_*`/`s2_*`/`s3_*`.
- [ ] `box_line` has 3–8 numeric `values`; Q1 and Q3 (nearest rank, or given `q1`/`q3`) match the speech; `span_*` is a math line that prints once; `break: last` only for one far value above Q3; speech only in `s1_*`/`s2_*`/`s3_*` (values → Q1 and Q3 → box + span). The speech says "about the middle half" and names the place rule. With `fences`: the fence numbers (Q1 − 1.5 × IQR, Q3 + 1.5 × IQR) match the speech, the speech follows box → fences → flagged value, and it says a flag means check, not delete.
- [ ] `dev_bars` has 3–6 numeric `values` and a `mean`; the bar numbers it computes (`−65`, `4,225`) match the speech; `power` is 1–4; `values_b` (if any) has as many values and a `name_a_*`/`name_b_*` legend; the footer sum matches the bars; speech only in `s1_*`/`s2_*`/`s3_*` (power 1: dots → signed bars → far bars; power 2: products row → squares → sum). The variance divides by n in a descriptive short. With `standardize: true` the bar numbers are powered distances ÷ σ to that power (kurtosis: `6.25`, `2.56`, `0.81`) and the footer averages them; a kurtosis short says raw (Normal = 3) or excess (raw − 3) and frames it as heavy tails, not peakedness.
- [ ] `ratio_bars` has 2–4 `means` above zero and as many `sds` (same unit, each at most its mean); the computed CV percents match the speech; the footer does not name the CV before the name card does; speech only in `s1_*`/`s2_*`/`s3_*` (raw SDs → own average → shares).
- [ ] No equation wraps mid-line on any card in any of the 7 cells. A `steps` trio of equations uses `layout: rows`. Spot-check bilingual cells after layout changes.
- [ ] In bilingual cells, digits and letters inside a Chinese line sit on the Chinese baseline at the Chinese height (no floating or oversized `390` / `24`). An equation with a unit word (`350 杯`) matches the pure-math line above it.
- [ ] Main-term name cards use unstaged `title_card` with `en`/`zh`/`zh_hk` only.
- [ ] The close answers the hook's question by name.
- [ ] The number is not an order. The close still looks at the rest of the file.
- [ ] Final stage directly resolves the hook.
- [ ] Final stage includes the key numerical result when applicable.
- [ ] Final stage states the governing assumption or limitation.
- [ ] Final stage gives a usable decision rule.
- [ ] Ending does not preview another lesson or introduce a new topic.
- [ ] Ending does not tease the next short ("Next we…", "in the next video"). Bridge questions inside the short are fine; module teasers are not.

## 7. Evidence discipline
For each substantive business statement, mark it internally as:
- [ ] supplied fact;
- [ ] teaching assumption; or
- [ ] decision implication.

Then confirm:
- [ ] Teaching assumptions are signalled with “assume”, “suppose”, or equivalent language.
- [ ] No teaching assumption is presented as an audit, ledger, contract, SLA, verified record, measured rate, penalty, policy, or observed customer reaction.
- [ ] No invented citation, number, organizational policy, or historical record appears.
- [ ] Recommendations name any additional operational inputs they require.

## 8. Mathematical and model review
- [ ] M01 descriptive variance / SD / covariance / correlation inputs use ÷ n, not n−1.
- [ ] Every finished number the speech uses already appeared on a card (worked arithmetic or footer).
- [ ] Bernoulli defines the binary outcomes and what `X=1` means.
- [ ] Binomial states fixed `n`, binary outcomes, independence, and constant `p`.
- [ ] Poisson specifies the interval, stable rate, and independent-event assumption.
- [ ] Exponential states nonnegative waiting time and constant hazard.
- [ ] Uniform states bounded support and constant density.
- [ ] Normal use is supported rather than assumed from aggregation alone.
- [ ] Poisson approximation states `lambda=np` and distinguishes approximate from exact results.
- [ ] Empirical Rule values are labelled approximate.
- [ ] Expected value is not described as a guaranteed observation.
- [ ] Point probability and rounded measurement are distinguished for continuous variables.
- [ ] Percentiles are not described as contractual guarantees.
- [ ] Queueing, inventory, acceptance, or maintenance conclusions are not inferred from one probability alone.

## 9. Numerical language
- [ ] `=` is used only for exact identities under the model.
- [ ] `≈` or “approximately” is used for rounded values.
- [ ] “Model probability” is used for supplied parameters.
- [ ] “Estimated probability” is used only for estimated parameters.
- [ ] “Coverage” is used consistently for threshold probabilities.
- [ ] “Guarantee” is used only for deterministic guarantees.
- [ ] Units are explicit and consistent, including squared units for variance.

## 10. Workplace boundary
- [ ] No identifiable employee is ranked, scored, or evaluated.
- [ ] Statistical extremeness is not interpreted as individual contribution or causation.
- [ ] Compensation or promotion decisions are not inferred from model output.
- [ ] Employee-focused examples are reframed as process or demand measurements.

## 11. Multilingual quality
- [ ] English sounds like a spoken university lecture.
- [ ] 简体 is natural spoken Putonghua and avoids Cantonese particles.
- [ ] 繁體 is natural Hong Kong lecture Cantonese, not mechanical conversion.
- [ ] On-screen labels are short in all languages and inside the SCHEMA bilingual budgets (no `WARN` lines from `validate.py`, or each one checked on a zh+en / hk+en render).
- [ ] Math lines differ across languages only by a unit word, so the bilingual card prints the equation once.
- [ ] Meaning, numbers, assumptions, and qualifications are synchronized across languages.
- [ ] No language field is missing or accidentally joined to another line.
- [ ] Chinese punctuation is used on Chinese lines.

## 12. Quiz validation
- [ ] Distractors are realistic misconceptions, not jokes, bans, fines, or magic. Correct options stay readable for beginners when possible.
For each multiple-choice question:
- [ ] `type: multiple_choice` is present.
- [ ] Question stem exists in all three languages.
- [ ] Exactly four distinct options, A through D, exist in all three languages.
- [ ] Answer is one of A, B, C, or D.
- [ ] Correct answer is mathematically and conceptually valid.
- [ ] Explanation exists in all three languages.
- [ ] Q1 tests comprehension.
- [ ] Q2 tests application or transfer.
- [ ] Quiz wording does not claim approximation as certainty or guarantee.

## 13. Takeaway validation
- [ ] `q1_en`, `q1_zh`, `q1_zh_hk` are present.
- [ ] `q2_en`, `q2_zh`, `q2_zh_hk` are present.
- [ ] Takeaway speech contains the visual's required number of stages.
- [ ] Questions and spoken answers align.

## 14. Final export review
- [ ] Reopen the saved file.
- [ ] Parse it again.
- [ ] Confirm filename and `id` again.
- [ ] Recalculate beat-duration total.
- [ ] Search for obsolete IDs and course names.
- [ ] Search for “next lesson”, “next chapter”, or equivalent teasers.
- [ ] Search for unsupported words such as “audit”, “ledger”, “contract”, “guarantee”, and “must”, then verify each occurrence.
- [ ] Confirm the requested deliverables are present and nothing extra is embedded in the YAML.
