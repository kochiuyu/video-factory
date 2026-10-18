# M01 beginner accessibility & exposition review

**Date:** 2026-10-19 (Asia/Hong_Kong)  
**Scope:** `lessons/STAT/STAT-M01-T01` … `T15` on Chiuyu-X1 Dropbox tree  
**Method:** Read REVISE_PROMPT + SCHEMA visual contract; full YAML skim (hooks, bridges, quizzes, divisors, place names, definitions); cross-check docs coverage vs factory visuals.

## Executive summary

The revise pass left M01 in good shape for beginners: idea-before-name, Shop A/B/C, `/n` for descriptive variance/covariance, speech-matched staged visuals, and concrete limit language on most shorts. **One blocker remains:** T14 still opens as a handoff from the covariance short (breaks standalone). **Several quizzes still use joke / absurdist wrong answers** (notably T04, T05, T07, parts of T01/T14). Docs already describe most new visuals; gaps are mainly **quiz-distractor rules**, **`/n` in AUTHORING**, **QA standalone/teaser checks**, and a **stale rent ledger** (9,400 / 18,600) that disagrees with T13–T14.

**Applied in this pass (safe):** T14 standalone speech rewrite; T14 Cantonese typos (`罐款`/`畎`/`嗐`); T07 quiz “middle 50%” → “about the middle half” to match speech. Docs updated (see end). Larger quiz / pacing rewrites listed as proposals.

---

## Top beginner-risk findings (module-wide)

1. **T14 is not standalone (blocker).** Hook: “Covariance told us…”. Data: “same five shops as the covariance short.” A viewer who only opens T14 cannot follow the rule in REVISE/AUTHORING. *(Fixed in this pass.)*
2. **Joke / absurdist quiz distractors remain** in T04 Q2, T05 Q2, T07 Q2, T01 Q1 C/D, and several T14 options (e.g. “regulators fine…”, “auditors prohibit…”, “automatically doubles revenue”). These train recognition of nonsense, not common misconceptions.
3. **Long academic quiz stems** (often 110–150 Latin chars on the correct option) hard for shaky-English beginners (T01, T13, T15 especially).
4. **T08 / T11 / T12 are very long** (910 / 884 / 804 s). Pedagogy is careful, but cognitive load is high for one sitting; consider a “fast path” or split later.
5. **T04 grouped `freq_bars` keeps a zero-height “Over 150” bar** (`counts=2;3;0`). Accurate but can look like a glitch to beginners.
6. **Cross-short number reuse without restating** is mostly OK after T14 fix, but T15 still casually recalls cov 176,000 / r≈+1.00 — fine for a recap, worth one on-screen reminder (already partly present).
7. **Docs AUTHORING shared ledger rents (9,400 / 18,600)** disagree with the live T13–T14 file (10k–19k, cov 176,000, r≈+1.00) — authors can re-introduce stale association numbers.
8. **T12 still says “older books call it peakedness”** (corrective). Safe, but a shorter “not peakedness — heavy tails” line is clearer for beginners.

---

## Per-lesson severity

| Lesson | Sev | Notes |
|--------|-----|-------|
| T01 Intro | improve | Solid four-dial frame. Quiz Q1 options C/D weak/absurd; option A jargon-heavy. |
| T02 Mean | ok | Balance_line + equal-share clear. |
| T03 Median | ok | Rank_line walk complete; bridges are pedagogical Qs, not “Next we”. |
| T04 Mode | improve | Zero bar on grouped chart; Q2 C/D joke distractors; answer title very compressed. |
| T05 Range | improve | Monday/Tuesday suppose OK. Q2 C/D absurd. |
| T06 Percentile | ok | Nearest-rank + “about” wording good. |
| T07 IQR | improve | Speech correctly softens “middle half”; quiz still said “middle 50%” *(aligned this pass)*. Q2 B/C/D still jokes. |
| T08 Var/SD | ok–improve | Best beginner-math model; `/n` consistent. Length 910 s is the main risk. |
| T09 CV | ok | ratio_bars + $40 unit example clear. |
| T10 Outlier | ok | Fences + “flag then check” correct. |
| T11 Skew | ok–improve | Cubes worked on screen. Length 884 s. |
| T12 Kurt | ok–improve | standardize + tails framing good; peakedness aside OK. Length 804 s. |
| T13 Cov | ok | `/n` → 176,000; causation caution present. Some long options. |
| T14 Corr | blocker→fixed | Handoff speech *(fixed)*; CJK typos *(fixed)*; residual joke distractors (propose). |
| T15 Recap | ok | Dashboard + `/n` reminder. Quiz already realistic; stems long. |

---

## Line-level / concrete issues

### Blocker (was)
- **T14 `hook.en` / `zh` / `zh_hk`:** “Covariance told us…” — handoff.  
- **T14 `data.s1_*`:** “same five shops as the covariance short” / “沿用协方差那一课”.

### Improve — quizzes (propose rewrite; keep answer letters)
| ID | Problem | Suggested direction |
|----|---------|---------------------|
| T01 Q1 C/D | Absurd | Misconceptions: “Summaries always hide the busy shop”; “You only need the biggest row” |
| T04 Q2 C/D | Jokes | “Median of Small/Medium/Large is the middle label”; “Average lid size is a factory SKU” |
| T05 Q2 C/D | Absurd | “Range uses every shop equally”; “Range equals the average” |
| T07 Q2 B/C/D | Jokes | “IQR ignores the middle shops”; “IQR always equals the range”; “IQR replaces the need for Q1/Q3 labels” |
| T14 Q1 B/C/D, Q2 B/D | Mixed / jokes | Keep causation myths; replace regulator/sample-size jokes with “r near 1 means perfect staffing formula”, “units still sit inside r” |

### Improve — exposition (propose)
- **T04 grouped:** drop the zero bar or tag it “none in band” in footer/speech.  
- **T08/T11/T12 length:** optional “core path” beats vs appendix, or accept long build.  
- **T01/T13/T15 quiz English:** shorten correct options to ≤ ~90 chars.  
- **T12 name/defn:** lead with “heavy tails,” mention peakedness only as a one-line myth.

### OK patterns to keep
- Hook titles name the topic; speech opens on cost.  
- Bridge questions at beat ends (“Where does it end?”) — seamless pedagogy, not module teasers.  
- `/n` in T08/T13/T14/T15.  
- IQR “about the middle half” + nearest-rank place rule.  
- Kurtosis = tails; outlier = flag then check; correlation ≠ causation.

---

## Docs coverage audit (before this pass)

| Guidance | REVISE | AUTHORING | SCHEMA | QA | LAE |
|----------|--------|-----------|--------|----|-----|
| New visuals + fields/stages | strong | strong | strong | strong | partial |
| Shop A/B/C, no districts | yes | yes | yes | yes | missing |
| No handoff / standalone | yes | yes | weak | partial | missing |
| No next-short teaser | yes | yes | — | ending check | — |
| Speech follows reveal | yes | yes | — | yes | — |
| M01 `/n` descriptive | yes | **missing** | weak | yes | — |
| Quiz distractor quality | **missing** | **missing** | — | **missing** | — |
| Equation one-line / layout rows | yes | weak | yes | partial | — |
| One-short-at-a-time revise workflow | **missing** (agent) | — | — | — | — |
| Live association ledger (10k–19k) | — | **stale 9.4k/18.6k** | — | — | — |

---

## Prioritized “improve exposition” list

1. **Batch-rewrite joke quiz distractors** (T01/T04/T05/T07/T14) — high beginner value, low story risk.  
2. **Shorten long correct options** in T01/T13/T15.  
3. **T04 zero bar** visual/footer decision.  
4. **Optional pacing plan** for T08/T11/T12 — **applied** (YAML comment headers + this REVIEW; beats kept).  
5. **T12 peakedness** one-line myth only.  
6. After builds resume: bilingual spot-check of T08 squares, T10 fences, T14 ruler (equations unbreakable; CJK digits).

---

## Visual usage map (current M01)

| Visual | Count | Used in |
|--------|------:|---------|
| two_column | 35 | most |
| title_card | 33 | hooks + name cards |
| steps | 22 | formulas / arithmetic |
| rank_line | 16 | T01,T03,T05–T07 |
| takeaway | 15 | all closes |
| definition_card | 15 | most |
| dev_bars | 11 | T08,T11,T12 |
| series | 10 | data beats |
| box_line | 5 | T07,T10 |
| freq_bars | 4 | T04 |
| table_grid | 3 | T01,T04,T15 |
| balance_line | 3 | T02,T08,T11 |
| quad_scatter | 3 | T13,T14 |
| dag | 2 | T14,T15 |
| ratio_bars | 1 | T09 |

Durations (target = sum seconds): T01 524 … T08 910, T11 884, T12 804 … T15 500. Module spoken total ≈ **9,056 s (~2.5 h)**.

---

## Changes made in this review pass

### YAML (Dropbox, backed up under `%TEMP%`)
- **T14:** standalone hook + data speech (EN/简/繁); data kicker/title no longer imply “same as last short”; objective_* no longer say “covariance short”; Cantonese typo fixes in quiz/explanation (`罐款`→`罰款`, `畎`→`付`, `嗐`→`嗰`).  
- **T07:** quiz/explanation “middle 50%” → “about the middle half” / 大约中间一半 (answer letters unchanged).

### Docs
Also copied to Dropbox as `docs/M01_BEGINNER_REVIEW.md`. Files updated: SCHEMA, AUTHORING_PROMPT, REVISE_PROMPT, QA_CHECKLIST, AUTHORING_PROMPT_LAE.

### Not changed (need user OK)
- (none for M01 beginner-risk list — pacing notes applied without cutting beats.)
(Joke distractor + long-correct shortening batch: **applied** — see section below.)
(T04 zero bar + T12 peakedness: **applied** — see section below.)

---

## Quiz batch applied (2026-10-19 Asia/Hong_Kong)

**User OK:** rewrite joke distractors (T01/T04/T05/T07/T14) + shorten long correct options (T01/T13/T15).  
**Backup:** `%TEMP%\m01-quiz-batch-bak-20261019-002945`  
**Validate:** all seven YAMLs `OK` via `factory/validate.py` (validate-only; no video build).

| File | Items | What changed | Answer letters |
|------|-------|--------------|----------------|
| T01-INTRO | Q1 | Shortened correct A; replaced absurd C/D with busy-shop / biggest-row misconceptions; explanations updated | A unchanged |
| T04-MODE | Q2 | Replaced ban/competition jokes C/D with median-of-labels / average-SKU misconceptions; explanations updated | A unchanged |
| T05-RANGE | Q2 | Replaced text-only / always-zero jokes C/D with “uses every shop equally” / “equals the average”; explanations updated | A unchanged |
| T07-IQR | Q2 | Replaced zero/auditor/revenue jokes B/C/D with middle-ignore / equals-range / no-need-Q1Q3 misconceptions; explanations updated | A unchanged |
| T13-COV | Q1 A, Q2 A | Shortened long academic correct options (EN/简/繁); distractors untouched | A unchanged |
| T14-CORR | Q1 C/D, Q2 B/D | Replaced same-variable/invalid-averages and sample-size/regulator jokes with staffing-formula / equal-averages / units-in-r / shop-causes-shop misconceptions; kept causation myth B (Q1) and C (Q2); explanations updated | A unchanged |
| T15-RECAP | Q1 A, Q2 A | Shortened long academic correct options (EN/简/繁); distractors untouched | A unchanged |

**Still out of scope (need later OK):** T08/T11/T12 pacing/length.

---

## T04 zero-bar + T12 peakedness batch (2026-10-19 Asia/Hong_Kong)

**User OK:** fix T04 empty Over-150 bar; soften T12 peakedness to one-line myth.  
**Backup:** `%TEMP%\m01-t04-t12-bak-20261019-003257`  
**Validate:** T04 OK (13 beats), T12 OK (15 beats). No video build.

### T04 — chose **drop** empty bar (not label-only)
`freq_bars` still draws a 4px stub + `0` for a zero count, which reads like a glitch. Schema allows 2–6 bars. Dropped the empty third category; kept the lesson fact in speech.

- `labels_*`: `Under 100;100 to 150` (removed Over 150 / 150以上)
- `counts`: `2;3` (was `2;3;0`); sales days 52, 64, 100, 136, 148 unchanged
- `s2_*`: now says no day sold over 150, so the empty band stays off the chart (EN/简/繁)

### T12 — one-line myth in `name_kurt`
- EN before: `Older books call it peakedness, but the peak is not what drives it: B's whole number comes from its two far days.`
- EN after: `Myth: peakedness. The weight is in the tails: B's whole number comes from its two far days.`
- ZH: `旧的书说…峰有多尖…` → `别说成尖峰——看尾部：B店整个数都来自那两天远的日子。`
- ZH_HK: `舊啲嘅書…峰有幾尖…` → `唔好話成尖峰——睇尾部：B店成個數都嚟自嗰兩個遠日子。`
Numbers 2.5 / 1.3 and heavy-tails teaching kept.

**Still out of scope:** T08/T11/T12 pacing/length.

---

## T08 / T11 / T12 pacing batch (2026-10-19 Asia/Hong_Kong)

**User OK:** optional core-path guidance only — no cuts, no new shorts, no video builds.  
**Approach:** SCHEMA has no `pacing` / `author_notes` / optional-beat field. Used **YAML comment headers** (author/teacher only; not spoken) on each lesson + this REVIEW section. Beats, quiz answers, and numbers untouched.  
**Backup:** `%TEMP%\m01-pacing-bak-20261019-003547`  
**Validate:** T08 OK (17), T11 OK (18), T12 OK (15).

### Core path vs optional deep-dive

| Lesson | Full | Core (first sitting) | Optional deep-dive |
|--------|-----:|----------------------|--------------------|
| **T08** Var/SD | ~910 s | `hook`, `data`, `plans`, `distance`, `cancel`, `square`, `squares`, `share`, `name_var`, `formula`, `name_sd`, `compare`, `read`, `limit`, `answer` | `average` (mean refresh if T02 fresh); `variance` (symbol nickname walk — denser companion to `formula`) |
| **T11** Skew | ~884 s | `hook`, `data`, `plans`, `distance`, `shape`, `clue`, `name_right`, `name_left`, `why_cube`, `cubes_a`, `cubes_b`, `formula`, `name_skew`, `answer` | `average`; `squares` (skip if T08 just watched); `defn`; `limit` (add on full watch) |
| **T12** Kurt | ~804 s | `hook`, `data`, `plans`, `distance`, `why_fourth`, `compare`, `fourths`, `name_kurt`, `defn`, `benchmark`, `limit`, `answer` | `average`; `squares` (if T08 fresh); `cubes` (if T11 fresh) |

**How to use:** Play the full short when time allows. For one sitting under cognitive load, prioritize the CORE beat ids above, then return for OPTIONAL cards. Do not delete beats from the YAML.
