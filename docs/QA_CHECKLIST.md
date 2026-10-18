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
- [ ] `table_grid`, `rank_line`, `schematic_chart`, `dag`, `pair`, `pair_chart`, `pair_box`, `pair_slope`, `redraw`, `turns`, `shrink`, `mix`, and `coin` have exactly 3 stages.
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
- [ ] Shops are generic (Shop A, Shop B) unless a place name is required. No switch to 甲店 on the Chinese line.
- [ ] Each card opens from the last sentence of the previous card.
- [ ] A dense calculation is split. Square, sum, divide, and root are not packed on one card.
- [ ] A tiny example comes before a symbol: 3 × 3 = 9 before “squared”; “what number times itself” before “square root.”
- [ ] The main names appear as large words on a card after the number is known, not only in the speech.
- [ ] A formula is nicknames for steps already done. No symbol arrives before the number it names.
- [ ] Median walks an odd line and an even line. Mode walks a winner, a tie, and no mode, then a grouped band.
- [ ] Why the other numbers fail is said before the count, when the short is about labels.
- [ ] Drawbacks are named, then the next tool: no mode leads to the modal class.
- [ ] Variance is said as cups times cups on first use.
- [ ] Speech matches the visual. A series that names each day uses `reveal: cells`. A spoken list of gaps uses `steps`.
- [ ] The close answers the hook's question by name.
- [ ] The number is not an order. The close still looks at the rest of the file.
- [ ] Final stage directly resolves the hook.
- [ ] Final stage includes the key numerical result when applicable.
- [ ] Final stage states the governing assumption or limitation.
- [ ] Final stage gives a usable decision rule.
- [ ] Ending does not preview another lesson or introduce a new topic.

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
- [ ] On-screen labels are short in all languages.
- [ ] Meaning, numbers, assumptions, and qualifications are synchronized across languages.
- [ ] No language field is missing or accidentally joined to another line.
- [ ] Chinese punctuation is used on Chinese lines.

## 12. Quiz validation
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
